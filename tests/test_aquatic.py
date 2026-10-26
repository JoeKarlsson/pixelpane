import unittest
from datetime import datetime, timedelta
from unittest import mock

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
        pale = aquatic.Swimmer(tank["fish"][0], tank["now"], 7, 1.0, ctx.rng)
        self.assertGreater(min(pale.body), 180)   # washed out toward white
        self.assertLess(pale.speed, aquatic.SPEED[pale.stage] * 0.4)

    def test_no_readings_means_fine(self):
        self.assertEqual(aquatic.air_stress(support.ctx_with()), 0.0)

    def test_feeding_perks_fish_up(self):
        ctx = support.ctx_with()
        with self.at(ctx, START):
            aquatic.advance(ctx)
            for f in self.tank(ctx)["fish"]:
                f["health"] = 0.5
            list(SCENES["aquatic"](ctx, 10, feed=True))
        self.assertTrue(any(f["health"] > 0.5 for f in self.tank(ctx)["fish"]))

    def test_saved_state_names_are_checked(self):
        ctx = support.ctx_with()
        with self.assertRaises(ValueError):
            ctx.saved("../config")


if __name__ == "__main__":
    unittest.main()
