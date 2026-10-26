import unittest
from datetime import date
from unittest import mock

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


class CountdownTest(unittest.TestCase):
    """In a holiday's last days it takes over the seasonal slot, gets extra turns and the GIFs."""

    def setUp(self):
        seasons.configure(None)
        self.addCleanup(seasons.configure, None)

    def test_days_until_the_big_day(self):
        d = seasons.days_until
        self.assertEqual(d("halloween", date(2026, 10, 26)), 5)
        self.assertEqual(d("halloween", date(2026, 10, 31)), 0)
        self.assertEqual(d("christmas", date(2026, 12, 26)), -1)
        self.assertEqual(d("new_year", date(2026, 12, 31)), 1)
        self.assertEqual(d("thanksgiving", date(2026, 11, 24)), 2)
        self.assertIsNone(d("autumn", date(2026, 10, 26)))          # seasons have no big day
        self.assertIsNone(d("christmas", date(2026, 10, 26)))       # not on yet
        seasons.configure({"custom": [{"key": "diwali", "name": "Diwali", "dates": [["10-28", "11-01"]]},
                                      {"key": "hogmanay", "name": "Hogmanay", "dates": [["12-30", "01-02"]]}]})
        self.assertEqual(d("diwali", date(2026, 10, 29)), 3)
        self.assertEqual(d("hogmanay", date(2026, 12, 30)), 3)     # the range wraps the new year

    def test_the_run_up_takes_over(self):
        from tests import support
        support.load_plugins()
        from pixelpane import plugin
        from pixelpane.plugins import seasonal
        support.reset()
        ctx = support.ctx_with()
        ctx.state.update_config({"plugins": {"seasonal": {"holiday_share": 0.0, "countdown_days": 7}}})
        early, late = date(2026, 10, 5), date(2026, 10, 26)
        with mock.patch("pixelpane.state.date") as fake:
            fake.today.return_value = early
            self.assertEqual(ctx.state.close_holidays(), [])
            self.assertEqual({seasonal.pick(ctx) for _ in range(20)}, {"autumn"})   # share 0: the season
            self.assertIsNone(seasonal.holiday_soon(ctx))
            fake.today.return_value = late
            self.assertEqual(ctx.state.close_holidays(), ["halloween"])
            self.assertEqual({seasonal.pick(ctx) for _ in range(20)}, {"halloween"})
            self.assertEqual(seasonal.holiday_soon(ctx), ("halloween", 10))
            self.assertEqual(plugin.boosted(ctx.config, ctx, {}, 2e9), "halloween")
            ctx.state.update_config({"plugins": {"seasonal": {"countdown_days": 0}}})
            self.assertEqual(ctx.state.close_holidays(), [])                       # 0 turns it off

    def test_close_holiday_gets_the_themed_gifs(self):
        from tests import support
        support.load_plugins()
        support.reset()
        support.make_gif(support.HOME / "gifs/themes/halloween/pumpkin-two.gif")
        support.make_gif(support.HOME / "gifs/themes/autumn/leaf.gif")
        ctx = support.ctx_with()
        ctx.state.update_config({"plugins": {"gifs": {"theme_share": 1.0}, "seasonal": {"countdown_days": 7}}})
        with mock.patch("pixelpane.state.date") as fake:
            fake.today.return_value = date(2026, 10, 26)
            picks = {ctx.gifs.next().parent.name for _ in range(30)}
        self.assertEqual(picks, {"halloween"})   # not autumn, in Halloween's last week
