import unittest
from datetime import datetime

import numpy as np

from tests import support

support.load_plugins()
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.plugins import window  # noqa: E402
from pixelpane.testing import FakeCtx, render  # noqa: E402

NOON = datetime(2026, 7, 10, 13, 0)


def wx(condition="sunny", temp=70, wind=5):
    return {"weather": {"condition": condition, "temp": temp, "wind": wind, "unit": "F"}}


def mean(frames, rows=slice(0, 20)):
    return np.asarray(frames[len(frames) // 2][0])[rows].astype(float).mean(axis=(0, 1))


class WindowTest(unittest.TestCase):
    def test_skips_without_weather(self):
        self.assertEqual(render("window", 1, now=NOON), [])
        self.assertEqual(SCENES["window"].empty_text, "NO WEATHER YET")

    def test_renders_and_moves(self):
        out = render("window", 2, now=NOON, data=wx("partlycloudy"))
        self.assertEqual(len(out), 30)
        self.assertGreater(len({img.tobytes() for img, _ in out}), 1)

    def test_night_is_dark_and_dusk_is_warm(self):
        day = mean(render("window", 1, now=NOON, data=wx()))
        night = mean(render("window", 1, now=NOON.replace(hour=23), data=wx("clear-night")))
        dusk = mean(render("window", 1, now=NOON.replace(hour=19, minute=30), data=wx()), slice(15, 21))
        self.assertLess(night.sum(), day.sum() / 3)
        self.assertGreater(dusk[0], dusk[2])   # the horizon glows orange

    def test_the_sun_and_moon_cross_the_sky(self):
        ctx = FakeCtx("window", now=NOON)
        self.assertIsNone(window.sun_place(ctx, NOON.replace(hour=23))[0])
        p, elev = window.sun_place(ctx, NOON.replace(hour=13, minute=15))   # halfway from 7:00 to 19:30
        self.assertAlmostEqual(p, 0.5, places=2)
        self.assertAlmostEqual(elev, 1.0, places=2)
        self.assertAlmostEqual(window.moon_place(ctx, NOON.replace(hour=13, minute=15), 0.0), 0.5, places=2)  # new: with the sun
        self.assertIsNone(window.moon_place(ctx, NOON.replace(hour=13, minute=15), 0.5))   # full: down by day
        self.assertIsNotNone(window.moon_place(ctx, NOON.replace(hour=23), 0.5))           # and up at night

    def test_rain_snow_and_the_season(self):
        def busy(frames):   # pixels that change from one frame to the next
            a, b = (np.asarray(frames[k][0]).astype(int) for k in (10, 11))
            return int((abs(a - b).sum(axis=2) > 30).sum())
        dry = busy(render("window", 1, now=NOON, data=wx("cloudy")))
        rain = busy(render("window", 1, now=NOON, data=wx("pouring", wind=20)))
        self.assertGreater(rain, dry + 30)   # it's coming down
        snow = render("window", 1, now=datetime(2026, 12, 20, 11), data=wx("snowy", 20))
        ground = np.asarray(snow[5][0])[28, 12]
        self.assertTrue(all(ground > 150), ground)   # snow on the ground
        self.assertEqual(window.season(datetime(2026, 10, 26)), "autumn")
        self.assertEqual(window.season(datetime(2026, 1, 5)), "winter")
        self.assertEqual(window.season(datetime(2026, 5, 1)), "spring")

    def test_bad_air_hazes_the_horizon(self):
        clear = mean(render("window", 1, now=NOON, data=wx()), slice(14, 21))
        data = dict(wx(), tiles={"items": [{"kind": "aqi", "value": 200}]})
        hazy = mean(render("window", 1, now=NOON, data=data), slice(14, 21))
        self.assertGreater(hazy[0] - hazy[2], clear[0] - clear[2] + 20)   # yellower, less blue

    def test_the_temperature_can_be_hidden(self):
        on = render("window", 0.2, now=NOON, data=wx(temp=84))[0][0]
        off = render("window", 0.2, now=NOON, data=wx(temp=84), settings={"show_temp": False})[0][0]
        self.assertNotEqual(on.crop((0, 25, 14, 32)).tobytes(), off.crop((0, 25, 14, 32)).tobytes())


if __name__ == "__main__":
    unittest.main()
