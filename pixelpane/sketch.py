"""What you draw on the Draw and Animate pages: one or more frames the "sketch" scene
plays. The pages send the whole drawing many times a second while you draw, so it
lives in memory and is written to disk only once the drawing stops changing."""
import base64
import threading
from pathlib import Path

from PIL import Image, PngImagePlugin

MAX_FRAMES = 64
MIN_MS, MAX_MS = 20, 5000


class SketchError(ValueError):
    pass


def parse(b, size):
    """Frames from an API body: {"width", "height", "ms", "frames": [base64 RGB bytes]}.
    The drawing must be the board's drawing size (it changes only with the panel)."""
    if not isinstance(b, dict):
        raise SketchError("expected an object")
    w, h = size
    if (b.get("width"), b.get("height")) != (w, h):
        raise SketchError(f"drawings on this board are {w}x{h}; reload the page")
    frames = b.get("frames")
    if not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES:
        raise SketchError(f"frames must be a list of 1 to {MAX_FRAMES}")
    ms = b.get("ms", 150)
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not MIN_MS <= ms <= MAX_MS:
        raise SketchError(f"ms must be a number from {MIN_MS} to {MAX_MS}")
    out = []
    for f in frames:
        try:
            raw = base64.b64decode(f, validate=True) if isinstance(f, str) else b""
        except ValueError:
            raw = b""
        if len(raw) != w * h * 3:
            raise SketchError(f"each frame must be {w}x{h} RGB, base64")
        out.append(Image.frombytes("RGB", (w, h), raw))
    return out, int(ms)


def encode(frames, ms):
    """The API form of frames (what parse reads)."""
    w, h = frames[0].size if frames else (0, 0)
    return {"width": w, "height": h, "ms": ms,
            "frames": [base64.b64encode(f.tobytes()).decode() for f in frames]}


def save_gif(frames, ms, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(dest, save_all=True, append_images=frames[1:], loop=0, duration=ms, disposal=1)


class Sketch:
    """The current drawing, kept on disk as a PNG strip (frames stacked top to bottom),
    so it is still there after a restart."""

    def __init__(self, path: Path, save_after=2.0):
        self.path, self.save_after = path, save_after
        self.lock = threading.Lock()
        self.frames, self.ms = [], 150
        self.version = 0   # bumped on every change
        self._timer = None
        try:
            with Image.open(path) as im:
                strip, n = im.convert("RGB"), int(im.info.get("frames", 1))
                self.ms = int(im.info.get("ms", 150))
            w, h = strip.width, strip.height // n
            self.frames = [strip.crop((0, i * h, w, (i + 1) * h)) for i in range(n)]
        except (OSError, ValueError, ZeroDivisionError):
            pass

    def get(self):
        with self.lock:
            return list(self.frames), self.ms, self.version

    def set(self, frames, ms):
        with self.lock:
            self.frames, self.ms = list(frames), ms
            self.version += 1
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(self.save_after, self.save)
            self._timer.daemon = True
            self._timer.start()

    def save(self):
        frames, ms, _ = self.get()
        if not frames:
            return
        w, h = frames[0].size
        strip = Image.new("RGB", (w, h * len(frames)))
        for i, f in enumerate(frames):
            strip.paste(f, (0, i * h))
        info = PngImagePlugin.PngInfo()
        info.add_text("frames", str(len(frames)))
        info.add_text("ms", str(ms))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        strip.save(tmp, "PNG", pnginfo=info)
        tmp.replace(self.path)
