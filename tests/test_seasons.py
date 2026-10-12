import unittest
from datetime import date

from pixelpane import seasons
from pixelpane.seasons import active_themes, thanksgiving


class SeasonsTest(unittest.TestCase):
    def test_thanksgiving_is_fourth_thursday(self):
        self.assertEqual(thanksgiving(2026), date(2026, 11, 26))
        self.assertEqual(thanksgiving(2027), date(2027, 11, 25))

    def test_themes(self):
        cases = {
            date(2026, 10, 12): ["autumn", "halloween"],
            date(2026, 11, 23): ["autumn", "thanksgiving"],
            date(2026, 11, 22): ["autumn"],
            date(2026, 12, 31): ["winter", "new_year"],
            date(2027, 1, 1): ["winter", "new_year"],
            date(2026, 12, 25): ["winter", "christmas"],
            date(2027, 2, 14): ["winter", "valentines"],
            date(2027, 3, 17): ["spring", "st_patricks"],
            date(2027, 4, 13): ["spring"],
            date(2027, 4, 14): ["spring"],
            date(2027, 7, 4): ["summer", "july4"],
            date(2027, 8, 31): ["summer"],
        }
        for d, want in cases.items():
            self.assertEqual(active_themes(d), want, d)
        self.assertEqual(active_themes(date(2027, 4, 13), (4, 13)), ["spring", "birthday"])

    def test_birthday_is_configurable(self):
        self.assertIn("birthday", active_themes(date(2027, 6, 1), (6, 1)))


class CustomThemesTest(unittest.TestCase):
    def tearDown(self):
        seasons.configure(None)

    def test_custom_holidays_and_switching_built_ins_off(self):
        seasons.configure({"off": ["july4"], "custom": [
            {"key": "diwali", "name": "Diwali", "dates": [["2026-11-08", "2026-11-12"]]},
            {"key": "winter_break", "name": "Winter break", "dates": [["12-30", "01-02"]]}]})
        self.assertEqual(seasons.THEMES["diwali"], "Diwali")
        self.assertEqual(active_themes(date(2026, 11, 10)), ["autumn", "diwali"])
        self.assertEqual(active_themes(date(2027, 11, 10)), ["autumn"])          # 2026 only
        self.assertEqual(active_themes(date(2027, 1, 2)), ["winter", "winter_break"])  # wraps the year
        self.assertEqual(active_themes(date(2027, 7, 4)), ["summer"])            # switched off

    def test_southern_hemisphere_flips_seasons(self):
        seasons.configure({"hemisphere": "south"})
        self.assertEqual(active_themes(date(2027, 7, 15)), ["winter"])
        self.assertEqual(active_themes(date(2026, 12, 25)), ["summer", "christmas"])
        self.assertIn("Jun to Aug", seasons.THEMES["winter"])


if __name__ == "__main__":
    unittest.main()
