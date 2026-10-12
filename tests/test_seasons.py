import unittest
from datetime import date

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


if __name__ == "__main__":
    unittest.main()
