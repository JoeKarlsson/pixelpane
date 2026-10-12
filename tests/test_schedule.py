import random
import unittest
from datetime import datetime
from unittest import mock

from tests import support

support.load_plugins()
from pixelpane import schedule, schema  # noqa: E402
from pixelpane.app import Player, health  # noqa: E402
from pixelpane.display import FakeDisplay  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402

NIGHT = {"label": "Night", "days": [4], "from": "23:00", "to": "07:00", "action": "off"}   # Friday night
FRI = datetime(2026, 10, 16)   # a Friday


def at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return FRI.replace(day=FRI.day + day, hour=h, minute=m)


class WindowTest(unittest.TestCase):
    def test_overnight_window_belongs_to_the_day_it_starts(self):
        self.assertIsNone(schedule.window(NIGHT, at(0, "22:59")))
        self.assertEqual(schedule.window(NIGHT, at(0, "23:00")), at(1, "07:00"))
        self.assertEqual(schedule.window(NIGHT, at(1, "06:59")), at(1, "07:00"))   # Saturday morning
        self.assertIsNone(schedule.window(NIGHT, at(1, "07:00")))
        self.assertIsNone(schedule.window(NIGHT, at(1, "23:30")))                   # Saturday isn't ticked
        self.assertIsNone(schedule.window(NIGHT, at(-1, "06:00")))                  # nor was Thursday

    def test_same_day_window_and_whole_day(self):
        day = {"from": "09:00", "to": "17:00", "action": "dim", "brightness": 20}
        self.assertTrue(schedule.window(day, at(0, "12:00")))
        self.assertIsNone(schedule.window(day, at(0, "17:00")))
        whole = {"days": [5], "from": "00:00", "to": "00:00", "action": "off"}
        self.assertEqual(schedule.window(whole, at(1, "15:00")), at(2, "00:00"))
        self.assertIsNone(schedule.window(dict(whole, enabled=False), at(1, "15:00")))

    def test_combining_rules(self):
        rules = [NIGHT, {"from": "20:00", "to": "23:30", "action": "dim", "brightness": 30},
                 {"from": "21:00", "to": "22:00", "action": "dim", "brightness": 10},
                 {"from": "18:00", "to": "22:00", "action": "playlist", "rotation": ["clock", "moon"]}]
        a = schedule.active(rules, at(0, "21:30"))
        self.assertEqual((a["off"], a["brightness"], a["rotation"]), (False, 10, ["clock", "moon"]))
        a = schedule.active(rules, at(0, "23:15"))
        self.assertEqual((a["off"], a["until"], a["brightness"]), (True, at(1, "07:00"), 30))


class ValidationTest(unittest.TestCase):
    def test_rules_are_checked(self):
        ok = schema.validate({"schedule": [NIGHT, {"from": "18:00", "to": "22:00", "action": "playlist",
                                                   "rotation": ["clock", "gif:retro"]}]})
        self.assertEqual(ok["schedule"][1]["days"], list(range(7)))
        for bad in ([{"from": "25:00", "to": "07:00", "action": "off"}],
                    [{"from": "23:00", "to": "07:00", "action": "nap"}],
                    [{"from": "23:00", "to": "07:00", "action": "dim"}],
                    [{"from": "23:00", "to": "07:00", "action": "playlist", "rotation": ["nope"]}],
                    [dict(NIGHT, days=[7])], [dict(NIGHT, extra=1)], {"not": "a list"}):
            with self.assertRaises(schema.ConfigError, msg=bad):
                schema.validate({"schedule": bad})


class PlayerScheduleTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.state.update_config({"schedule": [
            {"from": "00:00", "to": "00:00", "action": "off", "days": [4]},   # all Friday
            {"from": "00:00", "to": "00:00", "action": "dim", "brightness": 15, "days": [5]},
            {"from": "00:00", "to": "00:00", "action": "playlist", "rotation": ["moon"], "days": [5]}]})

    def test_scheduled_off_and_override(self):
        with mock.patch("pixelpane.state.now", return_value=at(0, "12:00")):
            self.assertTrue(self.state.power)
            self.assertFalse(self.state.effective_power())
            h = health(self.state)
            self.assertEqual((h["on"], h["schedule"]["off"]), (False, True))
            # pressing Power on during quiet hours wins until they end
            self.state.set(power=False)
            self.state.set(power=True)
            self.assertTrue(self.state.effective_power())
            self.assertTrue(self.state.schedule_status()["overridden"])

    def test_dim_and_scheduled_playlist(self):
        with mock.patch("pixelpane.state.now", return_value=at(1, "12:00")):
            self.state.set(brightness=80)
            self.assertEqual(self.state.effective_brightness(), 15)
            player = Player(self.state, FakeDisplay(), GifLibrary(self.state, random.Random(1)), random.Random(1))
            self.assertEqual(player.next_item(), "moon")
        with mock.patch("pixelpane.state.now", return_value=at(2, "12:00")):
            self.assertEqual(self.state.effective_brightness(), 80)
            self.assertNotEqual(self.state.rotation(), ["moon"])

    def test_settings_page_and_api(self):
        client = create_app(self.state, GifLibrary(self.state, random.Random(1)), health).test_client()
        r = client.get("/settings")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"Schedule", r.data)
        r = client.put("/api/config", json={"schedule": [NIGHT]})
        self.assertEqual(r.get_json()["schedule"][0]["label"], "Night")


if __name__ == "__main__":
    unittest.main()
