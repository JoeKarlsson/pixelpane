"""The web pages' one color, taken from what the board shows."""
import unittest

from PIL import Image

from tests import support  # noqa: F401  (sets up a scratch board before pixelpane loads)

from pixelpane import app, livecolor  # noqa: E402


class LiveColorTest(unittest.TestCase):
    def test_takes_the_vivid_color_on_screen(self):
        frame = Image.new("RGB", (32, 32))
        frame.paste((0, 200, 60), (4, 4, 28, 28))
        r, g, b = bytes.fromhex(livecolor.live_color(frame)[1:])
        self.assertGreater(g, r)
        self.assertGreater(g, b)

    def test_black_text_on_it_is_always_readable(self):
        frame = Image.new("RGB", (32, 32), (0, 0, 255))   # pure blue: black on it is about 2.4:1
        rgb = bytes.fromhex(livecolor.live_color(frame)[1:])
        self.assertGreaterEqual((livecolor._luminance(rgb) + 0.05) / 0.05, 4.5)
        self.assertGreater(rgb[2], rgb[0])   # still reads as blue

    def test_falls_back_when_dark_grey_or_off(self):
        self.assertEqual(livecolor.live_color(Image.new("RGB", (32, 32))), livecolor.LIVE_DEFAULT)
        self.assertEqual(livecolor.live_color(Image.new("RGB", (32, 32), (128, 128, 128))), livecolor.LIVE_DEFAULT)
        self.assertEqual(livecolor.live_color(Image.new("RGB", (32, 32), (255, 0, 0)), on=False), livecolor.LIVE_DEFAULT)
        self.assertEqual(livecolor.live_color(Image.new("RGB", (32, 32)), default="#123456"), "#123456")   # the Appearance setting

    def test_health_carries_it(self):
        ctx = support.ctx_with()
        self.assertRegex(app.health(ctx.state)["live_color"], r"^#[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()
