"""The LED panel, or a stand-in that only keeps the last frame (testing).

Two real backends:
- MatrixDisplay: hzeller/rpi-rgb-led-matrix, for Pi 2, 3, 4 and Zero 2 W.
- PioMatterDisplay: Adafruit PioMatter, for the Pi 5 (its GPIO moved to the RP1
  chip, which the hzeller library does not drive). Not yet tested on hardware.
"""
from pathlib import Path

from PIL import Image


def panel_size(config):
    """(cols, rows) of the physical panel; scenes draw at 32x32 and are fitted to it."""
    p = config.get("panel") or {}
    return int(p.get("cols", 32)), int(p.get("rows", 32))


def compose(img, cols, rows):
    """Fit a frame to the panel: whole-number pixel scaling, centered, black around it."""
    if img.size == (cols, rows):
        return img
    w, h = img.size
    scale = max(1, min(cols // w, rows // h))
    if scale > 1:
        img = img.resize((w * scale, h * scale), Image.NEAREST)
    canvas = Image.new("RGB", (cols, rows))
    canvas.paste(img, ((cols - img.width) // 2, (rows - img.height) // 2))
    return canvas


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
    cols, rows = panel_size(config)
    if kind == "fake":
        return FakeDisplay(cols=cols, rows=rows)
    if kind == "piomatter":
        return PioMatterDisplay(brightness, config.get("panel_bgr", False), config.get("adafruit_board", "hat"),
                                cols=cols, rows=rows)
    return MatrixDisplay(brightness, config.get("gpio_slowdown"), config.get("refresh_hz"),
                         config.get("hardware_mapping") or "adafruit-hat", cols=cols, rows=rows)


class FakeDisplay:
    def __init__(self, cols=32, rows=32, **_):
        self.brightness = 100
        self.frame = None
        self.cols, self.rows = cols, rows

    def show(self, img):
        self.frame = compose(img, self.cols, self.rows)

    def clear(self):
        self.frame = None


class MatrixDisplay:
    def __init__(self, brightness=60, gpio_slowdown=None, refresh_hz=None, mapping="adafruit-hat", cols=32, rows=32):
        from rgbmatrix import RGBMatrix, RGBMatrixOptions

        o = RGBMatrixOptions()
        # one panel up to 64 wide; 128-wide setups are two 64-wide panels chained
        o.rows, o.cols = rows, min(cols, 64)
        o.chain_length = max(1, cols // 64) if cols > 64 else 1
        self.cols, self.rows = cols, rows
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
        self.canvas.SetImage(compose(img.convert("RGB"), self.cols, self.rows))
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self):
        self.canvas.Clear()
        self.canvas = self.matrix.SwapOnVSync(self.canvas)


class PioMatterDisplay:
    def __init__(self, brightness=60, bgr=False, board="hat", piomatter=None, np=None, cols=32, rows=32):
        if piomatter is None:
            import adafruit_blinka_raspberry_pi5_piomatter as piomatter
        if np is None:
            import numpy as np
        self.np = np
        self.cols, self.rows = cols, rows
        addr = 5 if rows >= 64 else 4 if rows >= 32 else 3   # 64-row panels use the E line
        geometry = piomatter.Geometry(width=cols, height=rows, n_addr_lines=addr,
                                      rotation=piomatter.Orientation.Normal)
        self.framebuffer = np.zeros((rows, cols, 3), dtype=np.uint8)
        name = ("AdafruitMatrixBonnet" if board == "bonnet" else "AdafruitMatrixHat") + ("BGR" if bgr else "")
        pinout = getattr(piomatter.Pinout, name)
        self.matrix = piomatter.PioMatter(colorspace=piomatter.Colorspace.RGB888Packed, pinout=pinout,
                                          framebuffer=self.framebuffer, geometry=geometry)
        self.brightness = brightness

    def show(self, img):
        frame = self.np.asarray(compose(img.convert("RGB"), self.cols, self.rows), dtype=self.np.uint16)
        # PioMatter has no brightness control, so scale the pixels (1-100 like the other backend)
        self.framebuffer[:] = (frame * max(1, min(100, self.brightness)) // 100).astype(self.np.uint8)
        self.matrix.show()

    def clear(self):
        self.framebuffer[:] = 0
        self.matrix.show()
