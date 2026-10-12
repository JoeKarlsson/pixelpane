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

    def test_token_and_masking(self):
        self.bad({"api_token": "short"}, "8 characters")
        self.assertEqual(self.ok({"api_token": schema.MASK}), {})          # unchanged on the way back
        self.assertEqual(self.ok({"api_token": None}), {"api_token": None})
        out = schema.masked({"api_token": "s3cret-token", "plugins": {}})
        self.assertEqual(out["api_token"], schema.MASK)


if __name__ == "__main__":
    unittest.main()
