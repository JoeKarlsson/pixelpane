import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from tests import support

support.load_plugins()
from pixelpane import astro  # noqa: E402
from pixelpane.plugin import SCENES  # noqa: E402
from pixelpane.plugins import sky  # noqa: E402

CHICAGO = ZoneInfo("America/Chicago")


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


class AstroTest(unittest.TestCase):
    def near(self, got, want, minutes=10):
        self.assertLess(abs(got - want), timedelta(minutes=minutes), (got, want))

    def test_sunrise_and_sunset(self):
        def local(*a):   # sun_times answers in the machine's local time
            return utc(*a).astimezone().replace(tzinfo=None)
        rise, sets = astro.sun_times(date(2026, 3, 20), 51.48, 0.0)            # Greenwich, equinox
        self.near(rise, local(2026, 3, 20, 6, 3), 3)
        self.near(sets, local(2026, 3, 20, 18, 12), 3)
        rise, sets = astro.sun_times(date(2026, 6, 21), 44.95, -93.09)         # St Paul, solstice
        self.near(rise, local(2026, 6, 21, 10, 26), 3)                          # 5:26 CDT
        self.near(sets, local(2026, 6, 22, 2, 3), 3)                            # 21:03 CDT
        self.assertIsNone(astro.sun_times(date(2026, 12, 21), 78.2, 15.6))    # polar night

    def test_phase_times_match_published_ones(self):
        self.near(astro.next_phase(utc(2024, 4, 7), False), utc(2024, 4, 8, 18, 21))   # eclipse new moon
        self.near(astro.next_phase(utc(2024, 9, 17), True), utc(2024, 9, 18, 2, 34))
        self.near(astro.next_phase(utc(2023, 8, 30), True), utc(2023, 8, 31, 1, 35))
        self.near(astro.last_new_moon(utc(2026, 10, 12)), utc(2026, 10, 10, 15, 50), 30)

    def test_full_moon_names(self):
        def name(*when):
            return astro.full_moon_name(astro.next_phase(utc(*when), True), CHICAGO)
        self.assertEqual(name(2024, 9, 17), {"name": "harvest", "blue": False, "super": True})
        self.assertEqual(name(2024, 10, 16), {"name": "hunter's", "blue": False, "super": True})
        self.assertEqual(name(2023, 8, 30), {"name": "sturgeon", "blue": True, "super": True})
        self.assertEqual(name(2023, 8, 1)["blue"], False)
        self.assertEqual(name(2025, 9, 6)["name"], "corn")      # Harvest fell in October that year
        self.assertEqual(name(2025, 10, 6)["name"], "harvest")
        self.assertEqual(name(2026, 1, 1), {"name": "wolf", "blue": False, "super": True})
        self.assertEqual(name(2026, 10, 25)["name"], "hunter's")
        self.assertEqual(name(2026, 6, 28)["super"], False)

    def test_moon_phase(self):
        info = astro.moon_phase(datetime(2026, 10, 12, 21, tzinfo=CHICAGO))
        self.assertEqual(info["phase"], "waxing crescent")
        self.assertLess(info["illumination"], 0.15)
        full = astro.moon_phase(datetime(2024, 10, 17, 6, tzinfo=CHICAGO))
        self.assertEqual(full["phase"], "full moon")
        self.assertEqual(full["full"]["name"], "hunter's")
        self.assertGreater(full["illumination"], 0.98)

    def test_sun_signs(self):
        for d, sign in [((4, 13), "aries"), ((1, 5), "capricorn"), ((12, 25), "capricorn"),
                        ((1, 20), "aquarius"), ((3, 20), "pisces"), ((3, 21), "aries"),
                        ((7, 23), "leo"), ((10, 22), "libra"), ((10, 23), "scorpio")]:
            self.assertEqual(astro.sun_sign(date(2026, *d)), sign, d)
        self.assertEqual(sky.sign_dates("libra"), ("SEP 23", "OCT 22"))
        self.assertEqual(sky.sign_dates("capricorn"), ("DEC 22", "JAN 19"))
        self.assertEqual(set(sky.GLYPHS), set(astro.SIGNS))


class SkySceneTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.ctx = support.ctx_with()

    def frames(self, scene, when):
        with mock.patch.object(self.ctx, "now", return_value=when):
            return [img for img, _ in SCENES[scene](self.ctx, 4)]

    def test_moon_and_zodiac_animate(self):
        for scene in ("moon", "zodiac"):
            frames = self.frames(scene, datetime(2026, 10, 19, 21))
            self.assertGreaterEqual(len(frames), 30)
            self.assertNotEqual(frames[0].tobytes(), frames[10].tobytes(), scene)
            self.assertEqual(frames[0].size, (32, 32))

    def test_waxing_moon_is_lit_on_the_right_in_the_north(self):
        self.assertEqual(sky.phase_shade(0.25, 0.5, 0), 1.0)
        self.assertEqual(sky.phase_shade(0.25, -0.5, 0), 0.0)
        self.assertEqual(sky.phase_shade(0.25, 0.5, 0, southern=True), 0.0)
        self.assertEqual(sky.phase_shade(0.75, -0.5, 0), 1.0)      # last quarter: left side
        self.assertEqual(sky.phase_shade(0.5, -0.9, 0.1), 1.0)     # full
        self.assertEqual(sky.phase_shade(0.0, 0.9, 0.1), 0.0)      # new

    def test_full_moon_is_tinted(self):
        hunters = self.frames("moon", datetime(2024, 10, 17, 6))[20]
        r, g, b = hunters.getpixel((15, 8))
        self.assertGreater(r, b + 40)


if __name__ == "__main__":
    unittest.main()
