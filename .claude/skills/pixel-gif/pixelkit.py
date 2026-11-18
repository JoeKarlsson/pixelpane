"""Helpers for the pixel-gif skill: save a board GIF, a frame sheet to check by eye,
how much each frame changes, and showing frames on the real board."""
import base64
import json
import os
import urllib.request

from PIL import Image, ImageDraw

BOARD = os.environ.get("PIXELPANE_URL", "http://192.168.30.47")
TOKEN = os.environ.get("PIXELPANE_TOKEN")   # the board's Settings > Access token; writes need it


def save_gif(frames, path, ms=100, scale=1):
    """Frames (RGB PIL images) as a looping GIF, optionally zoomed `scale` times with hard pixels."""
    out = [f.convert("RGB").resize((f.width * scale, f.height * scale), Image.NEAREST) for f in frames]
    out[0].save(path, save_all=True, append_images=out[1:], duration=ms, loop=0, disposal=1)
    return path


def frame_sheet(frames, path, zoom=6, cols=8):
    """Every frame zoomed and numbered, then a row with the last frame beside the first (the loop seam)."""
    w, h = frames[0].width * zoom, frames[0].height * zoom
    pad, label = 4, 10
    rows = -(-len(frames) // cols) + 1
    sheet = Image.new("RGB", (cols * (w + pad), rows * (h + pad + label)), (40, 40, 48))
    d = ImageDraw.Draw(sheet)
    cells = [(str(i), f) for i, f in enumerate(frames)]
    seam = [(f"last {len(frames) - 1}", frames[-1]), ("first 0", frames[0])]
    for k, (name, f) in enumerate(cells):
        x, y = (k % cols) * (w + pad), (k // cols) * (h + pad + label)
        d.text((x, y), name, fill=(200, 200, 210))
        sheet.paste(f.convert("RGB").resize((w, h), Image.NEAREST), (x, y + label))
    y = (rows - 1) * (h + pad + label)
    for k, (name, f) in enumerate(seam):
        d.text((k * (w + pad), y), name, fill=(255, 200, 120))
        sheet.paste(f.convert("RGB").resize((w, h), Image.NEAREST), (k * (w + pad), y + label))
    sheet.save(path)
    return path


def frame_change(frames, box=None):
    """Share of pixels (0..1) that change between each frame and the next, wrapping round the loop.
    `box` (x0, y0, x1, y1) limits it to one area, such as the sky or the water."""
    out = []
    for a, b in zip(frames, frames[1:] + frames[:1]):
        a, b = (f.convert("RGB").crop(box) if box else f.convert("RGB") for f in (a, b))
        pa, pb = a.getdata(), b.getdata()
        out.append(sum(p != q for p, q in zip(pa, pb)) / len(pa))
    return out


def show_on_board(frames, ms=100):
    """Hold the board on these frames (the Draw page's sketch). Refuses when the board is
    pinned to something else, such as ON AIR."""
    with urllib.request.urlopen(f"{BOARD}/api/health", timeout=5) as r:
        pinned = json.load(r).get("pinned")
    if pinned and pinned.get("scene") != "sketch":
        raise RuntimeError(f"board is pinned to {pinned.get('scene')!r}; not taking it over")
    w, h = frames[0].size
    body = {"width": w, "height": h, "ms": ms,
            "frames": [base64.b64encode(f.convert("RGB").tobytes()).decode() for f in frames]}
    if not TOKEN:
        raise RuntimeError("set PIXELPANE_TOKEN to the board's API token (Settings, Access)")
    req = urllib.request.Request(f"{BOARD}/api/sketch", data=json.dumps(body).encode(), method="PUT",
                                 headers={"Content-Type": "application/json", "X-PixelPane-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)
