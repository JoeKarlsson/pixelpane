"""The web pages' one color, taken from what the board shows."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image  # noqa: E402

from pixelpane import app  # noqa: E402


class LiveColorTest(unittest.TestCase):
    def test_takes_the_vivid_color_on_screen(self):
        frame = Image.new("RGB", (32, 32))
        frame.paste((0, 200, 60), (4, 4, 28, 28))
        r, g, b = bytes.fromhex(app.live_color(frame)[1:])
        self.assertGreater(g, r)
        self.assertGreater(g, b)

    def test_black_text_on_it_is_always_readable(self):
        frame = Image.new("RGB", (32, 32), (0, 0, 255))   # pure blue: black on it is about 2.4:1
        rgb = bytes.fromhex(app.live_color(frame)[1:])
        self.assertGreaterEqual((app._luminance(rgb) + 0.05) / 0.05, 4.5)
        self.assertGreater(rgb[2], rgb[0])   # still reads as blue

    def test_falls_back_when_dark_grey_or_off(self):
        self.assertEqual(app.live_color(Image.new("RGB", (32, 32))), app.LIVE_DEFAULT)
        self.assertEqual(app.live_color(Image.new("RGB", (32, 32), (128, 128, 128))), app.LIVE_DEFAULT)
        self.assertEqual(app.live_color(Image.new("RGB", (32, 32), (255, 0, 0)), on=False), app.LIVE_DEFAULT)

    def test_health_carries_it(self):
        from tests import support
        ctx = support.ctx_with()
        self.assertRegex(app.health(ctx.state)["live_color"], r"^#[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()
