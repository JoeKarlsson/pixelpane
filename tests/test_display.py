import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np
from PIL import Image

from tests import support

from pixelpane import display  # noqa: E402


class FakePio:
    """Just enough of adafruit_blinka_raspberry_pi5_piomatter to check the wiring."""

    def __init__(self):
        self.shown = []
        fake = self

        class Matrix:
            def __init__(self, colorspace, pinout, framebuffer, geometry):
                self.fb, self.pinout, self.geometry = framebuffer, pinout, geometry

            def show(self):
                fake.shown.append(self.fb.copy())
        self.PioMatter = Matrix
        self.Geometry = lambda **kw: SimpleNamespace(**kw)
        self.Orientation = SimpleNamespace(Normal="normal")
        self.Colorspace = SimpleNamespace(RGB888Packed="rgb888p")
        self.Pinout = SimpleNamespace(AdafruitMatrixHat="hat", AdafruitMatrixHatBGR="hat-bgr",
                                      AdafruitMatrixBonnet="bonnet", AdafruitMatrixBonnetBGR="bonnet-bgr")


class DisplayTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def test_piomatter_frames_and_brightness(self):
        pio = FakePio()
        d = display.PioMatterDisplay(brightness=50, piomatter=pio, np=np)
        self.assertEqual((d.matrix.pinout, d.matrix.geometry.width, d.matrix.geometry.n_addr_lines), ("hat", 32, 4))
        d.show(Image.new("RGB", (32, 32), (200, 100, 10)))
        self.assertEqual(tuple(pio.shown[-1][5, 5]), (100, 50, 5))
        d.brightness = 100
        d.show(Image.new("RGB", (32, 32), (200, 100, 10)))
        self.assertEqual(tuple(pio.shown[-1][0, 0]), (200, 100, 10))
        d.clear()
        self.assertFalse(pio.shown[-1].any())
        self.assertEqual(display.PioMatterDisplay(piomatter=pio, np=np, bgr=True).matrix.pinout, "hat-bgr")
        self.assertEqual(display.PioMatterDisplay(piomatter=pio, np=np, board="bonnet").matrix.pinout, "bonnet")

    def test_auto_picks_backend_by_pi_model(self):
        with mock.patch.object(display, "pi_model", return_value="Raspberry Pi 5 Model B Rev 1.0"), \
                mock.patch.object(display, "PioMatterDisplay") as pio, mock.patch.object(display, "MatrixDisplay") as hz:
            display.open_display({"display": "auto"}, 60)
            pio.assert_called_once()
            hz.assert_not_called()
        with mock.patch.object(display, "pi_model", return_value="Raspberry Pi 3 Model B Rev 1.2"), \
                mock.patch.object(display, "PioMatterDisplay") as pio, mock.patch.object(display, "MatrixDisplay") as hz:
            display.open_display({"display": "auto", "gpio_slowdown": 2}, 60)
            hz.assert_called_once_with(60, 2, None, "adafruit-hat", cols=32, rows=32)
            pio.assert_not_called()
        self.assertIsInstance(display.open_display({"display": "fake"}, 60), display.FakeDisplay)


class PanelTest(unittest.TestCase):
    def setUp(self):
        support.reset()

    def frame(self):
        img = Image.new("RGB", (32, 32), (10, 20, 30))
        img.putpixel((0, 0), (255, 0, 0))
        return img

    def test_compose_scales_and_centers(self):
        same = display.compose(self.frame(), 32, 32)
        self.assertEqual(same.size, (32, 32))
        big = display.compose(self.frame(), 64, 64)                   # 2x, crisp
        self.assertEqual(big.size, (64, 64))
        self.assertEqual([big.getpixel(p) for p in ((0, 0), (1, 1), (2, 2))], [(255, 0, 0), (255, 0, 0), (10, 20, 30)])
        wide = display.compose(self.frame(), 64, 32)                  # 1x, centered
        self.assertEqual((wide.getpixel((0, 0)), wide.getpixel((16, 0))), ((0, 0, 0), (255, 0, 0)))
        huge = display.compose(self.frame(), 128, 64)                 # 2x, centered
        self.assertEqual((huge.getpixel((31, 0)), huge.getpixel((32, 0))), ((0, 0, 0), (255, 0, 0)))
        native = Image.new("RGB", (64, 64))
        self.assertIs(display.compose(native, 64, 64), native)        # already panel-sized

    def test_backends_get_the_geometry(self):
        pio = FakePio()
        d = display.PioMatterDisplay(piomatter=pio, np=np, cols=64, rows=64)
        self.assertEqual((d.matrix.geometry.width, d.matrix.geometry.height, d.matrix.geometry.n_addr_lines), (64, 64, 5))
        d.show(self.frame())
        self.assertEqual(pio.shown[-1].shape, (64, 64, 3))
        fake = display.open_display({"display": "fake", "panel": {"cols": 64, "rows": 32}}, 60)
        fake.show(self.frame())
        self.assertEqual(fake.frame.size, (64, 32))

    def test_big_square_panels_get_full_resolution_gifs(self):
        import random
        from pixelpane.state import GifLibrary, State
        state = State()
        lib = GifLibrary(state, random.Random(1))
        path = support.HOME / "gifs" / "space-earth-spin.gif"              # 64x48 source
        self.assertEqual(lib.frames(path)[0][0].size, (32, 32))
        state.update_config({"panel": {"cols": 64, "rows": 64}})
        self.assertEqual(lib.frames(path)[0][0].size, (64, 64))
        state.update_config({"panel": {"cols": 64, "rows": 32}})          # not square: 32x32, centered later
        self.assertEqual(lib.frames(path)[0][0].size, (32, 32))


if __name__ == "__main__":
    unittest.main()
