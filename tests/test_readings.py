"""Tile readings (temp, aqi, humidity, co2, battery) and the weather show how they feel."""
import threading
import time
import unittest

import numpy as np

from tests import support

support.load_plugins()
from pixelpane import kit  # noqa: E402
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.plugins import tiles  # noqa: E402
from pixelpane.plugins.weather import WEATHER_ICON  # noqa: E402
from pixelpane.testing import render  # noqa: E402

DEFAULTS = {"temp_unit": "F", "humidity_low": 30, "humidity_high": 60, "co2_high": 1200}


def feel(kind, value, **extra):
    return tiles.read(dict(kind=kind, value=value, **extra), DEFAULTS)


def avg_color(img):
    return tuple(np.asarray(img).reshape(-1, 3).mean(axis=0))


class ReadTest(unittest.TestCase):
    def test_temperature_bands(self):
        self.assertEqual([feel("temp", v)["word"] for v in (50, 64, 72, 80, 95)],
                         ["COLD", "COOL", "COMFY", "WARM", "HOT"])
        self.assertEqual(feel("temp", 95)["mood"], "heat")
        self.assertEqual(feel("temp", 50)["mood"], "frost")

    def test_celsius_and_custom_comfort(self):
        self.assertEqual(feel("temp", 22, unit="C")["word"], "COMFY")
        self.assertEqual(feel("temp", 35, unit="C")["word"], "HOT")
        self.assertEqual(tiles.read({"kind": "temp", "value": 22}, dict(DEFAULTS, temp_unit="C"))["word"], "COMFY")
        warm_house = dict(DEFAULTS, comfy_low=74, comfy_high=80)
        self.assertEqual(tiles.read({"kind": "temp", "value": 72}, warm_house)["word"], "COOL")

    def test_air_quality_follows_epa_bands(self):
        self.assertEqual([feel("aqi", v)["severity"] for v in (20, 80, 120, 170, 250, 400)], [0, 1, 2, 3, 4, 5])
        self.assertLess(feel("aqi", 20)["amount"], feel("aqi", 250)["amount"])

    def test_other_kinds(self):
        self.assertEqual(feel("humidity", 20)["word"], "DRY")
        self.assertEqual(feel("humidity", 80)["mood"], "droplets")
        self.assertEqual(feel("co2", 600)["severity"], 0)
        self.assertEqual(feel("co2", 1500)["severity"], 3)
        self.assertEqual(feel("battery", 10)["word"], "LOW")

    def test_not_a_reading(self):
        self.assertIsNone(feel("temp", "warm"))
        self.assertIsNone(feel("pressure", 1013))
        self.assertIsNone(tiles.read({"icon": "bell", "text": "HI"}, DEFAULTS))


class ReadingSceneTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def frames(self, *items, secs=3):
        return render("tiles", secs, data={"tiles": {"items": list(items)}})

    def test_every_kind_animates(self):
        for kind, value in (("temp", 40), ("temp", 72), ("temp", 95), ("aqi", 20), ("aqi", 180),
                            ("humidity", 85), ("humidity", 15), ("co2", 1500), ("battery", 12)):
            frames = self.frames({"kind": kind, "value": value})
            self.assertGreater(len({img.tobytes() for img, _ in frames[10:]}), 5, (kind, value))

    def test_hot_looks_warm_and_cold_looks_cold(self):
        hot = avg_color(self.frames({"kind": "temp", "value": 98})[-1][0])
        cold = avg_color(self.frames({"kind": "temp", "value": 30})[-1][0])
        self.assertGreater(hot[0], hot[2])
        self.assertGreater(cold[2], cold[0])

    def test_bad_air_is_murkier_than_good_air(self):
        good = avg_color(self.frames({"kind": "aqi", "value": 15})[-1][0])
        bad = avg_color(self.frames({"kind": "aqi", "value": 250})[-1][0])
        self.assertGreater(sum(bad), sum(good))
        self.assertGreater(bad[0], good[0])

    def test_plain_cards_still_work_beside_readings(self):
        frames = self.frames({"icon": "washer", "text": "DONE"}, {"kind": "aqi", "value": 40}, secs=8)
        self.assertEqual(frames[0][0].size, (32, 32))
        self.assertGreater(len(frames), 70)

    def test_focus_shows_only_that_tile(self):
        items = [{"kind": "aqi", "value": 40}, {"kind": "temp", "value": 99, "label": "attic"}]
        both = render("tiles", 8, data={"tiles": {"items": items}})
        one = render("tiles", 8, data={"tiles": {"items": items}}, params={"focus": "temp:ATTIC"})
        self.assertLess(avg_color(one[5][0])[2], avg_color(both[5][0])[2] + 1)   # starts on the hot attic
        self.assertIn("focus", SCENES["tiles"].params)

    def test_sent_history_draws_a_sparkline_and_trend(self):
        flat = self.frames({"kind": "temp", "value": 72})[-1][0]
        rising = self.frames({"kind": "temp", "value": 72, "history": [66, 67, 68, 69, 70, 71]})[-1][0]
        bottom = lambda img: sum(sum(img.getpixel((x, 30))) for x in range(32))  # noqa: E731
        self.assertGreater(bottom(rising), bottom(flat))


class WatchTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def run_watch(self, ctx, seconds=0.3):
        stop = threading.Event()
        orig = stop.wait
        stop.wait = lambda t=None: orig(0.01)   # don't wait 30 s between rounds
        th = threading.Thread(target=tiles.watch, args=(ctx, stop))
        th.start()
        time.sleep(seconds)
        stop.set()
        th.join(2)

    def test_a_reading_that_turns_bad_jumps_the_queue_once(self):
        ctx = support.ctx_with({"tiles": {"items": [{"kind": "aqi", "value": 180}]}})
        self.run_watch(ctx)
        self.assertEqual(ctx.state.play_next, {"scene": "tiles", "params": {"focus": "aqi:"}})
        ctx.state.play_next = None
        self.run_watch(ctx)
        self.assertIsNone(ctx.state.play_next)   # not again within the hour
        self.assertEqual(list(ctx.store("tiles")["history"]["aqi:"])[-1], 180.0)

    def test_alerts_can_be_turned_off(self):
        ctx = support.ctx_with({"tiles": {"items": [{"kind": "co2", "value": 2000, "alert": False},
                                                    {"kind": "temp", "value": 72}]}})
        self.run_watch(ctx)
        self.assertIsNone(ctx.state.play_next)
        ctx = support.ctx_with({"tiles": {"items": [{"kind": "co2", "value": 2000}]}})
        ctx.state.update_config({"plugins": {"tiles": {"alert": False}}})
        self.run_watch(ctx)
        self.assertIsNone(ctx.state.play_next)


class WeatherMoodTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_every_condition_fills_the_panel(self):
        for cond in WEATHER_ICON:
            frames = render("weather", 3, data={"weather": {"temp": 50, "condition": cond, "wind": 20}})
            lit = {(x, y) for img, _ in frames for x in range(32) for y in range(14, 24) if sum(img.getpixel((x, y))) > 30}
            self.assertGreater(len(lit), 40, cond)

    def test_temperature_colors_the_digits(self):
        self.assertGreater(kit.temp_color(95)[0], kit.temp_color(95)[2])
        self.assertGreater(kit.temp_color(30)[2], kit.temp_color(30)[0])
        self.assertEqual(kit.temp_color(72), (60, 220, 170))

    def test_moods_animate(self):
        import random
        for name in ("calm", "glow", "frost", "heat", "haze", "bubbles", "droplets", "rain", "snow", "stars", "wind", "fog"):
            m = kit.Mood(random.Random(1), name, 0.7)
            self.assertGreater(len({m.frame(k / 10).tobytes() for k in range(20)}), 3, name)


if __name__ == "__main__":
    unittest.main()
