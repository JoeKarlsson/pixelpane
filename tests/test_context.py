"""Scenes that react to what's happening: boosts, album colors, the window's visitors,
and brightness that follows the room."""
import random
import threading
import time
import unittest
from datetime import datetime, timedelta
from unittest import mock

import numpy as np
from PIL import Image

from tests import support

support.load_plugins()
from pixelpane import plugin  # noqa: E402
from pixelpane.app import Player  # noqa: E402
from pixelpane.display import FakeDisplay  # noqa: E402
from pixelpane.plugins import now_playing, room_light, window  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.testing import render  # noqa: E402

PLAYING = {"title": "Midnight City", "artist": "M83", "state": "playing"}


class BoostTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_music_and_meetings_ask_for_a_turn(self):
        ctx = support.ctx_with()
        self.assertIsNone(plugin.boosted(ctx.config, ctx, {}, time.time()))
        ctx.state.put_data("now_playing", PLAYING)
        self.assertEqual(plugin.boosted(ctx.config, ctx, {}, time.time()), "now_playing")
        self.assertIsNone(plugin.boosted(ctx.config, ctx, {"now_playing": time.time() - 60}, time.time()))
        ctx.state.update_config({"plugins": {"now_playing": {"boost": False}}})
        self.assertIsNone(plugin.boosted(ctx.config, ctx, {}, time.time()))
        soon = (datetime.now() + timedelta(minutes=10)).isoformat()
        ctx.state.put_data("next_event", {"title": "Standup", "start": soon})
        self.assertEqual(plugin.boosted(ctx.config, ctx, {}, time.time()), "calendar")
        later = (datetime.now() + timedelta(hours=2)).isoformat()
        ctx.state.put_data("next_event", {"title": "Standup", "start": later})
        self.assertIsNone(plugin.boosted(ctx.config, ctx, {}, time.time()))

    def test_the_window_comes_round_when_the_weather_turns(self):
        ctx = support.ctx_with({"weather": {"condition": "cloudy", "temp": 50}})
        self.assertIsNone(window.weather_turned(ctx))           # first look: nothing has turned
        ctx.state.put_data("weather", {"condition": "partlycloudy", "temp": 50})
        self.assertIsNone(window.weather_turned(ctx))           # clouds coming and going don't count
        ctx.state.put_data("weather", {"condition": "rainy", "temp": 50})
        self.assertEqual(window.weather_turned(ctx), ("window", 10))
        with mock.patch("time.time", return_value=time.time() + 1801):
            self.assertIsNone(window.weather_turned(ctx))       # half an hour later it's old news

    def test_a_broken_boost_is_skipped(self):
        ctx = support.ctx_with()

        def broken(ctx):
            raise RuntimeError("boom")
        broken.plugin = "clock"
        with mock.patch.object(plugin, "BOOSTS", [broken] + plugin.BOOSTS), \
                self.assertLogs("pixelpane.plugin", "ERROR"):
            self.assertIsNone(plugin.boosted(ctx.config, ctx, {}, time.time()))


class BoostLoopTest(unittest.TestCase):
    def test_a_boost_slots_in_between_playlist_entries(self):
        support.reset()
        state = State()
        state.update_config({"rotation": ["clock"], "dwell": {"clock": 1, "now_playing": 1}})
        state.put_data("now_playing", {"title": "Hi", "state": "playing"})
        state.update_config({"plugins": {"now_playing": {"art_seconds": 0}}})
        player = Player(state, FakeDisplay(), GifLibrary(state, random.Random(1)), random.Random(1))
        stop = threading.Event()
        sources = []
        thread = threading.Thread(target=player.run, args=(stop,), daemon=True)
        thread.start()
        end = time.time() + 12
        boost = ("boosted", "now_playing")
        while time.time() < end and not (boost in sources and sources[-1] != boost):
            src = (state.now.get("source"), state.now.get("entry"))
            if src[0] and (not sources or sources[-1] != src):
                sources.append(src)
            time.sleep(0.02)
        stop.set()
        state.wake.set()
        thread.join(timeout=5)
        self.assertIn(("boosted", "now_playing"), sources)
        k = sources.index(("boosted", "now_playing"))
        self.assertEqual(sources[k + 1][0], "playlist")   # never two boosts in a row


class NowPlayingTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_album_colors(self):
        art = Image.new("RGB", (32, 32), (200, 30, 40))
        art.paste((20, 60, 200), (0, 16, 32, 32))
        colors = now_playing.art_palette(art)
        self.assertEqual(len(colors), 2)
        self.assertTrue(any(c[0] > c[2] for c in colors) and any(c[2] > c[0] for c in colors))
        self.assertIsNone(now_playing.art_palette(Image.new("RGB", (32, 32), (128, 128, 128))))

    def test_paused_shows_dimmed_for_a_while_then_skips(self):
        ctx = support.ctx_with({"now_playing": PLAYING})
        playing = list(plugin.SCENES["now_playing"](ctx, 1))
        ctx.state.put_data("now_playing", dict(PLAYING, state="paused"))
        paused = list(plugin.SCENES["now_playing"](ctx, 1))
        self.assertTrue(paused)
        bright = np.asarray(playing[-1][0]).sum()
        dim = np.asarray(paused[-1][0]).sum()
        self.assertLess(dim, bright)
        with mock.patch("time.time", return_value=time.time() + now_playing.PAUSED_FOR + 1):
            self.assertEqual(list(plugin.SCENES["now_playing"](ctx, 1)), [])


class VisitorsTest(unittest.TestCase):
    def test_who_comes_when(self):
        v = window.visitors
        self.assertIn("birds", v(datetime(2026, 6, 10, 7), 0.2, 0.05, False, 62, False))
        self.assertNotIn("birds", v(datetime(2026, 6, 10, 7), 0.2, 0.05, True, 62, False))   # not in the rain
        self.assertIn("fireflies", v(datetime(2026, 7, 10, 22), -0.8, None, False, 72, False))
        self.assertNotIn("fireflies", v(datetime(2026, 7, 10, 22), -0.8, None, False, 50, False))
        self.assertTrue({"bats", "pumpkin"} <= v(datetime(2026, 10, 30, 19), -0.3, None, False, 45, False))
        self.assertIn("lights", v(datetime(2026, 12, 20, 21), -1, None, False, 20, True))
        self.assertIn("snowman", v(datetime(2027, 1, 10, 12), 0.5, 0.4, False, 25, True))
        self.assertIn("fireworks", v(datetime(2026, 7, 4, 22), -1, None, False, 75, False))
        self.assertEqual(v(datetime(2026, 8, 12, 13), 1, 0.5, False, 80, False), set())

    def test_visitors_can_be_turned_off_and_rain_builds_on_the_horizon(self):
        now = datetime(2026, 7, 4, 22, 30)
        wx = {"weather": {"condition": "clear-night", "temp": 75, "wind": 3, "unit": "F"}}
        on = render("window", 2, now=now, data=wx)
        off = render("window", 2, now=now, data=wx, settings={"visitors": False})
        self.assertNotEqual(on[-1][0].tobytes(), off[-1][0].tobytes())   # fireworks
        noon = datetime(2026, 8, 12, 13)
        dry = render("window", 0.2, now=noon, data={"weather": {"condition": "sunny", "temp": 80, "precip": 0}})
        wet = render("window", 0.2, now=noon, data={"weather": {"condition": "sunny", "temp": 80, "precip": 90}})
        self.assertLess(sum(wet[0][0].getpixel((1, 2))), sum(dry[0][0].getpixel((1, 2))))   # dark in the west


class RoomLightTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_the_curve(self):
        t = room_light.target
        self.assertEqual(t(0, 3, 300, 0.25), 0.25)
        self.assertEqual(t(300, 3, 300, 0.25), 1.0)
        self.assertAlmostEqual(t(30, 3, 300, 0.25), 0.625)   # halfway on a log scale

    def test_it_eases_down_in_a_dark_room_and_leaves_it_alone_without_a_reading(self):
        ctx = support.ctx_with()
        self.assertEqual(plugin.level(ctx.config, ctx, 80), 80)
        ctx.state.put_data("room_light", {"lux": 0})
        first = plugin.level(ctx.config, ctx, 80)
        self.assertEqual(first, 20)   # starts at the target, no fade from nothing
        ctx.state.put_data("room_light", {"lux": 1000})
        steps = [plugin.level(ctx.config, ctx, 80) for _ in range(300)]
        self.assertLess(steps[0], 25)              # it eases up
        self.assertEqual(steps[-1], 80)            # and gets there
        self.assertEqual(steps, sorted(steps))


if __name__ == "__main__":
    unittest.main()
