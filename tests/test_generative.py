import random
import unittest
from datetime import datetime, timedelta
from unittest import mock

from tests import support

support.load_plugins()
from pixelpane.app import Player  # noqa: E402
from pixelpane.display import FakeDisplay  # noqa: E402
from pixelpane.plugin import PICKERS, PLUGINS, SCENES  # noqa: E402
from pixelpane.plugins import generative  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402

NEW = ["lava", "smog", "ripples", "reaction", "sand", "aurora", "fireflies", "aquarium", "snake", "hourglass"]


def frames(name, ctx, secs=3):
    return list(SCENES[name](ctx, secs))


class GenerativeScenesTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_new_scenes_render_and_move(self):
        ctx = support.ctx_with()
        for name in NEW:
            with self.subTest(scene=name):
                self.assertEqual(SCENES[name].kind, "generative")
                self.assertIn(name, PLUGINS["generative"].fields[0]["options"])
                out = frames(name, ctx, secs=3)
                self.assertAlmostEqual(sum(h for _, h in out), 3, delta=0.3)
                self.assertGreater(len({img.tobytes() for img, _ in out}), 1, f"{name} is still")

    def test_default_scenes_are_all_options(self):
        opts = PLUGINS["generative"].fields[0]["options"]
        self.assertTrue(set(PLUGINS["generative"].defaults["scenes"]) <= set(opts))

    def test_snake_finds_the_food(self):
        from collections import deque
        body = deque([(5, 5), (4, 5), (3, 5)])
        self.assertEqual(generative._snake_step(body, (9, 5), 16), (6, 5))
        boxed = deque([(0, 0), (1, 0), (1, 1), (0, 1), (0, 2)])   # cornered by its own body
        self.assertIsNone(generative._snake_step(boxed, (9, 9), 16))
        blocked = deque([(0, 0), (1, 0), (2, 0)])
        self.assertEqual(generative._snake_step(blocked, None, 16), (0, 1))   # no food: just survive

    def test_hourglass_counts_down_to_the_next_event(self):
        now = datetime(2026, 10, 12, 9, 0)
        ctx = support.ctx_with({"next_event": {"title": "Standup", "start": (now + timedelta(minutes=30)).isoformat()}})
        with mock.patch.object(ctx, "now", return_value=now):
            self.assertAlmostEqual(generative._minutes_to_event(ctx), 30, delta=0.1)
            img, _ = frames("hourglass", ctx, secs=0.2)[0]
        self.assertTrue(any(img.getpixel((x, y)) != (0, 0, 0) for x in range(32) for y in range(26, 32)))  # "30M"


class AmbientTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def pick(self, data, scenes=None):
        support.reset()   # config and data persist on disk between States
        state = State()
        for k, v in data.items():
            state.put_data(k, v)
        if scenes:
            state.update_config({"plugins": {"generative": {"scenes": scenes}}})
        player = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1))
        return player.resolve("ambient")[0]

    def test_ambient_is_a_playlist_entry(self):
        self.assertIn("ambient", PICKERS)

    def test_follows_the_weather(self):
        self.assertEqual(self.pick({"weather": {"temp": 50, "condition": "rainy"}}), "ripples")
        self.assertEqual(self.pick({"weather": {"temp": 95, "condition": "sunny"}}), "fire")
        self.assertEqual(self.pick({"weather": {"temp": 35, "condition": "clear-night"}}, ["aurora", "fire"]), "aurora")
        self.assertEqual(self.pick({"weather": {"temp": 70, "condition": "clear-night"}}), "fireflies")
        self.assertEqual(self.pick({"weather": {"temp": 31, "condition": "sunny", "unit": "C"}}), "fire")  # 88F

    def test_bad_air_shows_smog(self):
        tiles = {"items": [{"kind": "temp", "value": 70}, {"kind": "aqi", "value": 180}]}
        self.assertEqual(self.pick({"tiles": tiles, "weather": {"temp": 50, "condition": "rainy"}}), "smog")
        self.assertNotEqual(self.pick({"tiles": {"items": [{"kind": "aqi", "value": 40}]}}), "smog")

    def test_keeps_to_ticked_scenes(self):
        self.assertEqual(self.pick({"weather": {"temp": 50, "condition": "rainy"}}, ["plasma"]), "plasma")
        self.assertEqual(self.pick({}, ["life"]), "life")   # no weather: any ticked scene


if __name__ == "__main__":
    unittest.main()
