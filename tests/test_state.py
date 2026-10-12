import json
import unittest
from datetime import date
from unittest import mock

from tests import support

support.load_plugins()
from pixelpane import state as st  # noqa: E402  (support sets the env first)


class StateTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_defaults_and_partial_config_update(self):
        s = st.State()
        self.assertEqual(s.config["dwell"]["gif"], st.DEFAULTS["dwell"]["gif"])
        s.update_config({"dwell": {"clock": 5}})
        self.assertEqual(s.config["dwell"]["clock"], 5)
        self.assertEqual(s.config["dwell"]["weather"], st.DEFAULTS["dwell"]["weather"])  # merged, not replaced
        saved = json.loads((support.VAR / "config.json").read_text())
        self.assertEqual(saved, {"dwell": {"clock": 5}})  # only overrides are stored
        self.assertEqual(st.State().config["dwell"]["clock"], 5)

    def test_power_and_brightness_persist_and_clamp(self):
        s = st.State()
        s.set(power=False, brightness=500)
        self.assertEqual((s.power, s.brightness), (False, 100))
        s.set(brightness=-3)
        self.assertEqual(s.brightness, 1)
        self.assertTrue(s.wake.is_set())
        again = st.State()
        self.assertEqual((again.power, again.brightness), (False, 1))

    def test_pin_expires(self):
        s = st.State()
        with mock.patch("pixelpane.state.time.time", return_value=1000.0):
            s.pin("on_air", minutes=1)
        with mock.patch("pixelpane.state.time.time", return_value=1030.0):
            self.assertEqual(s.active_pin()["scene"], "on_air")
        with mock.patch("pixelpane.state.time.time", return_value=1061.0):
            self.assertIsNone(s.active_pin())
        self.assertIsNone(st.State().pinned)  # expiry is saved

    def test_pin_without_minutes_stays(self):
        s = st.State()
        s.pin("message", {"text": "hi"})
        self.assertEqual(st.State().active_pin()["params"], {"text": "hi"})
        s.pin(None)
        self.assertIsNone(st.State().active_pin())

    def test_pushed_data_survives_restart_and_expires(self):
        s = st.State()
        with mock.patch("pixelpane.state.time.time", return_value=10_000.0):
            s.put_data("weather", {"temp": 50})
        restarted = st.State()
        ttl = st.plugin.data_ttl(restarted.config, "weather") * 60
        with mock.patch("pixelpane.state.time.time", return_value=10_000.0 + ttl - 1):
            self.assertEqual(restarted.get_data("weather"), {"temp": 50})
        with mock.patch("pixelpane.state.time.time", return_value=10_000.0 + ttl + 1):
            self.assertIsNone(restarted.get_data("weather"))
        self.assertIsNone(restarted.get_data("tiles"))

    def test_themes_use_configured_birthday(self):
        s = st.State()
        self.assertNotIn("birthday", s.themes(date(2027, 4, 13)))  # no birthday by default
        s.update_config({"plugins": {"seasonal": {"birthday": {"month": 6, "day": 1}}}})
        self.assertNotIn("birthday", s.themes(date(2027, 4, 13)))
        self.assertIn("birthday", s.themes(date(2027, 6, 1)))

    def test_old_config_keys_move_into_plugin_sections(self):
        (support.VAR / "config.json").write_text(json.dumps({
            "weather_fallback": {"latitude": 51.5, "longitude": -0.1},
            "birthday": {"month": 4, "day": 13, "name": "Joe"},
            "generative": ["fire"], "theme_gif_share": 0.5, "art_hosts": ["http://ha:8123/"],
            "rotation": ["clock"]}))
        s = st.State()
        p = s.config["plugins"]
        self.assertEqual(p["weather"], {"latitude": 51.5, "longitude": -0.1})
        self.assertEqual(p["seasonal"]["birthday"]["name"], "Joe")
        self.assertEqual((p["generative"]["scenes"], p["gifs"]["theme_share"]), (["fire"], 0.5))
        self.assertEqual(p["now_playing"]["art_hosts"], ["http://ha:8123/"])
        self.assertEqual(s.config["rotation"], ["clock"])
        saved = json.loads((support.VAR / "config.json").read_text())
        self.assertNotIn("birthday", saved)  # rewritten once
        self.assertIn("birthday", s.themes(date(2027, 4, 13)))

    def test_corrupt_files_fall_back_to_defaults(self):
        (support.VAR / "config.json").write_text("{not json")
        (support.VAR / "data.json").write_text("[]oops")
        s = st.State()
        self.assertEqual(s.config["rotation"], st.DEFAULTS["rotation"])
        self.assertEqual(s.data, {})


if __name__ == "__main__":
    unittest.main()
