"""The LED panel, or a stand-in that only keeps the last frame (testing).

Two real backends:
- MatrixDisplay: hzeller/rpi-rgb-led-matrix, for Pi 2, 3, 4 and Zero 2 W.
- PioMatterDisplay: Adafruit PioMatter, for the Pi 5 (its GPIO moved to the RP1
  chip, which the hzeller library does not drive). Not yet tested on hardware.
"""
from pathlib import Path


def pi_model():
    try:
        return Path("/proc/device-tree/model").read_text(errors="ignore").strip("\x00 \n")
    except OSError:
        return ""


def open_display(config, brightness):
    """Pick the backend: config["display"] = auto | hzeller | piomatter | fake."""
    kind = config.get("display") or "auto"
    if kind == "auto":
        kind = "piomatter" if "Raspberry Pi 5" in pi_model() else "hzeller"
    if kind == "fake":
        return FakeDisplay()
    if kind == "piomatter":
        return PioMatterDisplay(brightness, config.get("panel_bgr", False), config.get("adafruit_board", "hat"))
    return MatrixDisplay(brightness, config.get("gpio_slowdown"), config.get("refresh_hz"),
                         config.get("hardware_mapping") or "adafruit-hat")


class FakeDisplay:
    def __init__(self, **_):
        self.brightness = 100
        self.frame = None

    def show(self, img):
        self.frame = img

    def clear(self):
        self.frame = None


class MatrixDisplay:
    def __init__(self, brightness=60, gpio_slowdown=None, refresh_hz=None, mapping="adafruit-hat"):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        o = RGBMatrixOptions()
        o.rows = o.cols = 32
        o.chain_length = 1
        o.hardware_mapping = mapping  # "adafruit-hat-pwm" after the HAT's GPIO4-GPIO18 solder mod
        o.brightness = brightness
        o.drop_privileges = False  # app.py drops to the pixelpane user itself
        if gpio_slowdown is not None:
            o.gpio_slowdown = gpio_slowdown
        if refresh_hz:
            # Caps refresh only; it does not lower CPU (the timing loop spins either way).
            o.limit_refresh_rate_hz = int(refresh_hz)
        self.matrix = RGBMatrix(options=o)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.brightness = brightness

    def show(self, img):
        if self.matrix.brightness != self.brightness:
            self.matrix.brightness = self.brightness
        self.canvas.brightness = self.brightness
        self.canvas.SetImage(img.convert("RGB"))
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self):
        self.canvas.Clear()
        self.canvas = self.matrix.SwapOnVSync(self.canvas)


class PioMatterDisplay:
    def __init__(self, brightness=60, bgr=False, board="hat", piomatter=None, np=None):
        if piomatter is None:
            import adafruit_blinka_raspberry_pi5_piomatter as piomatter
        if np is None:
            import numpy as np
        self.np = np
        geometry = piomatter.Geometry(width=32, height=32, n_addr_lines=4,
                                      rotation=piomatter.Orientation.Normal)
        self.framebuffer = np.zeros((32, 32, 3), dtype=np.uint8)
        name = ("AdafruitMatrixBonnet" if board == "bonnet" else "AdafruitMatrixHat") + ("BGR" if bgr else "")
        pinout = getattr(piomatter.Pinout, name)
        self.matrix = piomatter.PioMatter(colorspace=piomatter.Colorspace.RGB888Packed, pinout=pinout,
                                          framebuffer=self.framebuffer, geometry=geometry)
        self.brightness = brightness

    def show(self, img):
        frame = self.np.asarray(img.convert("RGB"), dtype=self.np.uint16)
        # PioMatter has no brightness control, so scale the pixels (1-100 like the other backend)
        self.framebuffer[:] = (frame * max(1, min(100, self.brightness)) // 100).astype(self.np.uint8)
        self.matrix.show()

    def clear(self):
        self.framebuffer[:] = 0
        self.matrix.show()
