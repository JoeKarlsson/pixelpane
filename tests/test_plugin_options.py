"""Each plugin's own settings change what it draws, and the defaults draw what it did before."""
import unittest
from datetime import datetime, timedelta

import numpy as np

from tests import support

support.load_plugins()
from pixelpane.plugins.homelab import lab_pages  # noqa: E402
from pixelpane.testing import render  # noqa: E402

AFTERNOON = datetime(2026, 10, 13, 15, 5, 7)


def arr(img):
    return np.asarray(img).astype(int)


def rows_changed(a, b):
    return {int(y) for y in np.nonzero(np.abs(arr(a) - arr(b)).sum(axis=2))[0]}


class ClockOptionsTest(unittest.TestCase):
    def frames(self, **settings):
        return render("clock", 1, settings=settings, now=AFTERNOON, params={"face": "classic"})

    def test_24_hour_and_leading_zero(self):
        twelve = self.frames()[0][0].tobytes()
        self.assertNotEqual(self.frames(hours="24")[0][0].tobytes(), twelve)
        self.assertNotEqual(self.frames(leading_zero=True)[0][0].tobytes(), twelve)

    def test_steady_colon(self):
        f = self.frames()                      # 4 fps: frame 2 is half a second in, colon off
        self.assertTrue(rows_changed(f[0][0], f[2][0]) - {31})
        f = self.frames(blink=False)           # only the seconds bar moves
        self.assertEqual(rows_changed(f[0][0], f[2][0]) - {31}, set())

    def test_date_and_temperature_lines(self):
        data = {"weather": {"temp": 50}}
        full = render("clock", 1, data=data, now=AFTERNOON, params={"face": "classic"})[0][0]
        bare = render("clock", 1, data=data, now=AFTERNOON, params={"face": "classic"},
                      settings={"show_date": False, "show_temp": False})[0][0]
        self.assertGreater(arr(full)[14:30].sum(), 0)
        self.assertEqual(arr(bare)[14:30].sum(), 0)


class CalendarOptionsTest(unittest.TestCase):
    def event(self, minutes):
        return {"next_event": {"title": "Standup", "start": (datetime.now() + timedelta(minutes=minutes)).isoformat()}}

    def test_look_ahead(self):
        self.assertTrue(render("calendar", 1, data=self.event(5 * 60)))
        self.assertFalse(render("calendar", 1, data=self.event(5 * 60), settings={"lookahead_hours": 4}))

    def test_bell_window_and_title_color(self):
        base = render("calendar", 1, data=self.event(20))[0][0]
        bell = render("calendar", 1, data=self.event(20), settings={"bell_minutes": 30})[0][0]
        self.assertTrue(rows_changed(base, bell) & set(range(0, 10)))      # bell icon, red countdown
        later = render("calendar", 1, data=self.event(20))[8][0]   # the long title has scrolled in
        pink = render("calendar", 1, data=self.event(20), settings={"title_color": "#ff00ff"})[8][0]
        self.assertTrue(rows_changed(later, pink) & set(range(18, 25)))


class NowPlayingOptionsTest(unittest.TestCase):
    DATA = {"now_playing": {"title": "Hi", "artist": "Yo", "state": "playing", "player": "Office"}}

    def test_equalizer_room_and_colors(self):
        base = render("now_playing", 1, data=self.DATA)
        quiet = render("now_playing", 1, data=self.DATA, settings={"equalizer": False, "show_room": False})
        self.assertGreater(arr(base[5][0])[0:9, 12:32].sum(), 0)
        self.assertEqual(arr(quiet[5][0])[0:9, 12:32].sum(), 0)
        self.assertEqual(arr(quiet[5][0])[27:].sum(), 0)
        red = render("now_playing", 1, data=self.DATA, settings={"title_color": "#ff0000"})[5][0]
        self.assertGreater(arr(red)[12:19, :, 0].sum(), arr(red)[12:19, :, 2].sum())


class WeatherOptionsTest(unittest.TestCase):
    DATA = {"weather": {"temp": 95, "condition": "rainy", "high": 99, "low": 80, "precip": 60}}

    def brightness(self, **settings):
        frames = render("weather", 2, data=self.DATA, settings=settings)
        return sum(arr(img)[13:18].sum() for img, _ in frames)   # rows with only background

    def test_background_strength(self):
        full, subtle, off = self.brightness(), self.brightness(mood="subtle"), self.brightness(mood="off")
        self.assertGreater(full, subtle)
        self.assertGreater(subtle, off)
        self.assertEqual(off, 0)

    def test_lines_and_white_digits(self):
        img = render("weather", 1, data=self.DATA, settings={"mood": "off", "show_high_low": False,
                                                             "show_line": False, "temp_colors": False})[0][0]
        self.assertEqual(arr(img)[16:].sum(), 0)
        digits = arr(img)[2:12, 16:]
        self.assertEqual(digits.max(axis=(0, 1)).tolist(), [255, 255, 255])


class TilesOptionsTest(unittest.TestCase):
    ITEM = {"kind": "temp", "value": 95, "history": [80, 84, 88, 90, 93]}

    def frames(self, **settings):
        return render("tiles", 2, data={"tiles": {"items": [self.ITEM]}}, settings=settings)

    def test_plain_tile_is_still(self):
        f = self.frames(moods="off", count_up=False, trend=False, sparkline=False)
        self.assertEqual(len({img.tobytes() for img, _ in f}), 1)
        self.assertEqual(arr(f[0][0])[26:].sum(), 0)

    def test_sparkline_and_subtle(self):
        self.assertGreater(arr(self.frames(moods="off")[-1][0])[26:].sum(), 0)
        full = sum(arr(img).sum() for img, _ in self.frames())
        subtle = sum(arr(img).sum() for img, _ in self.frames(moods="subtle"))
        self.assertLess(subtle, full)


class HomelabOptionsTest(unittest.TestCase):
    LAB = {"alerts": 0, "hosts": [{"name": "P1", "cpu": 82}], "nas": {"used_pct": 50}}

    def test_pages(self):
        self.assertEqual([p.__name__ for p in lab_pages(self.LAB, ["nas"])], ["_lab_status", "_lab_nas"])
        self.assertEqual(len(lab_pages(self.LAB)), 3)

    def test_cpu_thresholds(self):
        def bar(**settings):
            frames = render("homelab", 8, data={"homelab": self.LAB}, settings=dict(settings, pages=["hosts"]))
            return frames[-1][0].getpixel((12, 9))   # inside P1's CPU bar, late on its page
        self.assertEqual(bar(), (255, 180, 40))                        # amber at 82% by default
        self.assertEqual(bar(cpu_warn=90, cpu_crit=95), (60, 220, 90))  # green when 90 is the line


class SpeedAndStarsTest(unittest.TestCase):
    def test_generative_speed_keeps_the_length(self):
        for speed in ("slow", "normal", "fast"):
            frames = render("plasma", 4, settings={"speed": speed})
            self.assertAlmostEqual(sum(h for _, h in frames), 4, delta=0.2)
        slow, fast = (len(render("plasma", 4, settings={"speed": s})) for s in ("slow", "fast"))
        self.assertLess(slow, fast)

    def test_star_density(self):
        def lit(stars):
            img = render("moon", 0.1, settings={"stars": stars})[0][0]
            return int((arr(img)[:17].sum(axis=2) > 30).sum())   # stars, plus the moon itself
        self.assertLess(lit("none"), lit("lots"))


if __name__ == "__main__":
    unittest.main()
