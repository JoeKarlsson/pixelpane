import unittest

from tests import support

support.load_plugins()
from pixelpane import schema  # noqa: E402


class SchemaTest(unittest.TestCase):
    def ok(self, changes):
        return schema.validate(changes)

    def bad(self, changes, words):
        with self.assertRaises(schema.ConfigError) as e:
            schema.validate(changes)
        self.assertIn(words, str(e.exception))

    def test_top_level(self):
        self.assertEqual(self.ok({"brightness": 40, "rotation": ["clock", "gif:retro", "seasonal"]}),
                         {"brightness": 40, "rotation": ["clock", "gif:retro", "seasonal"]})
        self.bad({"brightness": "lots"}, "number")
        self.bad({"brightness": 500}, "between")
        self.bad({"rotation": ["clock", "nope"]}, "unknown scenes")
        self.bad({"dwell": {"clock": 0}}, "between")
        self.bad({"display": "crt"}, "display")
        self.bad({"panel": {"cols": 33}}, "panel.cols")
        self.bad({"wat": 1}, "unknown setting")
        self.bad([], "object")

    def test_plugin_fields(self):
        c = self.ok({"plugins": {"generative": {"scenes": ["fire"], "enabled": False},
                                 "seasonal": {"birthday": {"month": 4, "day": 13, "name": "Ada"}, "holiday_share": 0.5},
                                 "weather": {"latitude": None}}})
        self.assertEqual(c["plugins"]["seasonal"]["birthday"], {"month": 4, "day": 13, "name": "Ada"})
        self.bad({"plugins": {"generative": {"scenes": ["lava"]}}}, "unknown choice")
        self.bad({"plugins": {"seasonal": {"birthday": {"month": 13, "day": 1}}}}, "month")
        self.bad({"plugins": {"seasonal": {"holiday_share": 2}}}, "between")
        self.bad({"plugins": {"gifs": {"enabled": "yes"}}}, "true or false")
        self.bad({"plugins": {"gifs": {"color": "red"}}}, "not a setting")
        self.bad({"plugins": {"nope": {}}}, "unknown plugin")

    def test_themes(self):
        c = self.ok({"themes": {"hemisphere": "south", "off": ["july4"],
                                "custom": [{"name": "Lunar New Year", "dates": [["2027-02-06", "2027-02-10"]]}]}})
        self.assertEqual(c["themes"]["custom"][0]["key"], "lunar_new_year")
        self.bad({"themes": {"hemisphere": "east"}}, "north or south")
        self.bad({"themes": {"off": ["winter"]}}, "not built-in holidays")
        self.bad({"themes": {"custom": [{"key": "halloween", "dates": [["10-01", "10-31"]]}]}}, "taken")
        self.bad({"themes": {"custom": [{"key": "x", "dates": [["02-30", "03-01"]]}]}}, "not a real date")
        self.bad({"themes": {"custom": [{"key": "x", "dates": [["2027-02-10", "2027-02-06"]]}]}}, "in order")
        self.bad({"themes": {"custom": [{"key": "x", "dates": []}]}}, "ranges")

    def test_color_field(self):
        f = {"key": "color", "type": "color"}
        self.assertEqual(schema._field(f, "#FF5FA2", "color"), "#ff5fa2")
        for v in ("red", "#fff", "ff5fa2", None):
            with self.assertRaises(schema.ConfigError):
                schema._field(f, v, "color")

    def test_token_and_masking(self):
        self.bad({"api_token": "short"}, "8 characters")
        self.assertEqual(self.ok({"api_token": schema.MASK}), {})          # unchanged on the way back
        self.assertEqual(self.ok({"api_token": None}), {"api_token": None})
        out = schema.masked({"api_token": "s3cret-token", "plugins": {}})
        self.assertEqual(out["api_token"], schema.MASK)


if __name__ == "__main__":
    unittest.main()
