"""Render scenes without a panel, for checking them by eye.

    python -m pixelpane.preview sheet out.png [scene ...]   # 4 frames per scene, one row each
    python -m pixelpane.preview gif out.gif scene [seconds]  # animated, 8x scale
"""
import random
import sys
from datetime import datetime, timedelta

from PIL import Image

from . import plugin
from .app import Ctx
from .plugin import SCENES
from .state import GifLibrary, State

SAMPLE = {
    "weather": {"temp": 52, "condition": "rainy", "high": 61, "low": 44, "precip": 40, "unit": "F"},
    "now_playing": {"title": "Midnight City", "artist": "M83", "player": "Office", "state": "playing"},
    "next_event": {"title": "Team standup", "start": (datetime.now() + timedelta(minutes=25)).isoformat()},
    "homelab": {"alerts": 2, "names": ["Plex", "NAS"]},
    "tiles": {"items": [{"icon": "thermometer", "text": "71F office", "color": "#ffaa44"}]},
}


def frames_of(name, secs, params=None):
    state = State()
    for k, v in SAMPLE.items():
        state.put_data(k, v)
    rng = random.Random(7)
    ctx = Ctx(state, GifLibrary(state, rng), rng)
    out, t = [], 0.0
    for img, hold in SCENES[name](ctx, secs, **(params or {})):
        out.append((t, img.copy(), hold))
        t += hold
    return out


def sheet(path, names, secs=12, cols=4, scale=6):
    rows = []
    for name in names:
        fr = frames_of(name, secs)
        if not fr:
            continue
        picks = [fr[min(len(fr) - 1, int(len(fr) * k / cols))] for k in range(1, cols + 1)]
        rows.append([img for _, img, _ in picks])
    out = Image.new("RGB", (cols * 34 * scale, len(rows) * 34 * scale), (40, 40, 48))
    for r, row in enumerate(rows):
        for c, img in enumerate(row):
            out.paste(img.resize((32 * scale, 32 * scale), Image.NEAREST), (c * 34 * scale, r * 34 * scale))
    out.save(path)
    print(path, len(rows), "scenes")


def gif(path, name, secs=8, scale=8):
    fr = frames_of(name, secs)
    imgs = [img.resize((32 * scale, 32 * scale), Image.NEAREST) for _, img, _ in fr]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], loop=0,
                 duration=[int(h * 1000) for _, _, h in fr])
    print(path, len(imgs), "frames")


if __name__ == "__main__":
    plugin.load()
    mode, path, *rest = sys.argv[1:]
    if mode == "sheet":
        sheet(path, rest or [n for n in SCENES if n not in ("gif",)])
    else:
        gif(path, rest[0], float(rest[1]) if len(rest) > 1 else 8)
