import unittest
from datetime import datetime, timedelta
from unittest import mock

import numpy as np

from tests import support

support.load_plugins()
from pixelpane.plugin import PLUGINS, SCENES  # noqa: E402
from pixelpane.plugins import aquatic  # noqa: E402
from pixelpane.testing import render  # noqa: E402

START = datetime(2026, 10, 1, 9, 0)


class AquaticTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def at(self, ctx, when):
        return mock.patch.object(ctx, "now", return_value=when)

    def tank(self, ctx):
        return ctx.saved("aquatic")

    def test_renders_and_moves(self):
        out = render("aquatic", 3, now=START)
        self.assertAlmostEqual(sum(h for _, h in out), 3, delta=0.3)
        self.assertGreater(len({img.tobytes() for img, _ in out}), 1)
        self.assertEqual(SCENES["aquatic"].kind, "generative")
        self.assertIn("aquatic", PLUGINS)

    def test_a_new_tank_has_fish_of_every_age_and_eggs(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            tank = aquatic.advance(ctx)
        stages = {aquatic.stage(f, tank["now"], 7) for f in tank["fish"]}
        self.assertEqual(stages, {"fry", "juvenile", "adult"})
        self.assertEqual(len(tank["eggs"]), 2)

    def test_eggs_hatch_and_adults_lay_but_the_tank_never_overfills(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            aquatic.advance(ctx)
        with self.at(ctx, START + timedelta(days=1)):
            tank = aquatic.advance(ctx)
        self.assertGreaterEqual(len(tank["fish"]), 5)   # both eggs hatched
        for day in range(2, 30):
            with self.at(ctx, START + timedelta(days=day)):
                tank = aquatic.advance(ctx)
            self.assertLessEqual(len(tank["fish"]) + len(tank["eggs"]), 8)
            self.assertTrue(tank["fish"] or tank["eggs"])   # it never empties for good
        self.assertNotIn(1, [f["id"] for f in tank["fish"]])   # the first fish died of old age

    def test_the_tank_survives_a_restart(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            ids = [f["id"] for f in aquatic.advance(ctx)["fish"]]
        again = support.ctx_with()   # a fresh State reads it back from disk
        with self.at(again, START + timedelta(minutes=5)):
            self.assertEqual([f["id"] for f in aquatic.advance(again)["fish"]], ids)

    def test_stale_air_makes_fish_pale_and_stops_eggs(self):
        ctx = support.ctx_with({"tiles": {"items": [{"kind": "co2", "value": 2000}]}})
        self.assertEqual(aquatic.air_stress(ctx), 1.0)
        with self.at(ctx, START):
            aquatic.advance(ctx)
        eggs = len(self.tank(ctx)["eggs"])
        with self.at(ctx, START + timedelta(hours=6)):
            tank = aquatic.advance(ctx)
        self.assertTrue(all(f["health"] < 0.1 for f in tank["fish"]))
        self.assertLessEqual(len(tank["eggs"]), eggs)
        pale = aquatic.Swimmer(tank["fish"][0], tank, ctx.rng)
        self.assertGreater(min(pale.body), 180)   # washed out toward white
        self.assertLess(pale.speed, aquatic.SPEED[pale.stage] * 0.4)

    def test_no_readings_means_fine(self):
        self.assertEqual(aquatic.air_stress(support.ctx_with()), 0.0)

    def test_it_feeds_itself_once_per_feeding_time(self):
        ctx = support.ctx_with()
        ctx.state.update_config({"plugins": {"aquatic": {"feed_times": ["08:00", "18:00"]}}})
        with self.at(ctx, START.replace(hour=7)):
            self.assertFalse(aquatic.feeding_due(ctx))       # nothing due yet today
        with self.at(ctx, START.replace(hour=8, minute=30)):
            self.assertTrue(aquatic.feeding_due(ctx))
            self.assertFalse(aquatic.feeding_due(ctx))       # once
        with self.at(ctx, START.replace(hour=18, minute=5)):
            self.assertTrue(aquatic.feeding_due(ctx))

    def test_rare_looks_appear_and_run_in_the_family(self):
        import random
        tank = {"fish": [], "eggs": [], "unlocked": [], "next_id": 1}
        aquatic._new_tank(tank)
        rng, events = random.Random(3), []
        for _ in range(400):
            aquatic._hatch(tank, rng, {"hue": 0.1, "trait": None, "gen": 2}, 0, events)
        rare = [f for f in tank["fish"] if f["trait"]]
        self.assertTrue(5 < len(rare) < 40, len(rare))       # about 4 in 100
        self.assertEqual(tank["stats"]["rare"], len(events))
        kids = []
        for _ in range(200):
            aquatic._hatch(tank, rng, {"hue": 0.1, "trait": "gold", "gen": 3}, 0, kids)
        golds = sum(f["trait"] == "gold" for f in tank["fish"][-200:])
        self.assertTrue(80 < golds < 130, golds)             # half take after the parent
        self.assertEqual(tank["stats"]["gen"], 3)

    def test_the_tank_earns_decorations_and_says_so(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            aquatic.advance(ctx)
        self.tank(ctx)["stats"]["gen"] = 3
        with self.at(ctx, START + timedelta(minutes=10)):
            self.assertIn("castle", aquatic.advance(ctx)["unlocked"])
        self.assertIn("CASTLE", ctx.state.notifications[-1]["text"])
        # a week of good air (one life cycle) brings the snail
        with self.at(ctx, START + timedelta(days=7, hours=1)):
            self.assertIn("snail", aquatic.advance(ctx)["unlocked"])

    def test_a_long_catch_up_doesnt_announce_old_news(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            aquatic.advance(ctx)
        aquatic._announce(ctx, [(START.timestamp(), "unlock", "castle")], (START + timedelta(days=3)).timestamp())
        self.assertEqual(len(ctx.state.notifications), 0)
        ctx.state.update_config({"plugins": {"aquatic": {"alerts": False}}})
        aquatic._announce(ctx, [(START.timestamp(), "rare", "gold")], START.timestamp())
        self.assertEqual(len(ctx.state.notifications), 0)

    def test_day_and_night(self):
        ctx = support.ctx_with()
        self.assertEqual(aquatic.daylight(ctx, START.replace(hour=12)), 1.0)   # 7:00-19:30 without a location
        self.assertEqual(aquatic.daylight(ctx, START.replace(hour=23)), 0.0)
        self.assertAlmostEqual(aquatic.daylight(ctx, START.replace(hour=7)), 0.5)
        ctx.state.update_config({"plugins": {"weather": {"latitude": 44.95, "longitude": -93.09}}})
        self.assertEqual(aquatic.daylight(ctx, START.replace(hour=6, minute=30)), 0.0)   # before an October sunrise
        night = render("aquatic", 1, now=START.replace(hour=2))[0][0]
        day = render("aquatic", 1, now=START.replace(hour=12))[0][0]
        self.assertLess(np.asarray(night).sum(), np.asarray(day).sum())

    def test_greet_brings_them_to_the_glass_and_tap_scatters_them(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            tank = aquatic.advance(ctx)
        fish = [aquatic.Swimmer(f, tank, ctx.rng) for f in tank["fish"]]
        for k, f in enumerate(fish):
            f.goal = (3 + k * 7, 10)
        for i in range(120):
            for f in fish:
                f.move(i / 15, ctx.rng, [])
        self.assertTrue(all(f.front for f in fish))
        out = list(SCENES["aquatic"](ctx, 2, tap=True))
        self.assertEqual(len(out), 30)
        self.assertEqual(SCENES["aquatic"].params, {"feed": "bool", "greet": "bool", "tap": "bool"})

    def test_aquarium_shows_the_living_tank(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            list(SCENES["aquarium"](ctx, 1))
        self.assertIn("last", self.tank(ctx))   # it advanced the real tank
        support.reset()   # a board that never had a tank
        fresh = support.ctx_with()
        fresh.state.update_config({"plugins": {"aquatic": {"enabled": False}}})
        with self.at(fresh, START):
            self.assertEqual(len(list(SCENES["aquarium"](fresh, 1))), 15)
        self.assertEqual(fresh.saved("aquatic"), {})   # visitors only: the tank is left alone

    def test_saved_state_names_are_checked(self):
        ctx = support.ctx_with()
        with self.assertRaises(ValueError):
            ctx.saved("../config")


if __name__ == "__main__":
    unittest.main()
