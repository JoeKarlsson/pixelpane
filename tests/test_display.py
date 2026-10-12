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
            hz.assert_called_once_with(60, 2, None, "adafruit-hat")
            pio.assert_not_called()
        self.assertIsInstance(display.open_display({"display": "fake"}, 60), display.FakeDisplay)


if __name__ == "__main__":
    unittest.main()
