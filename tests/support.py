"""Test fixtures: a throwaway GIF library and state dir, set up before pixelpane is imported.

pixelpane.state reads PIXELPANE_HOME / PIXELPANE_STATE at import time, so every
test module imports this first.
"""
import os
import random
import shutil
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(tempfile.mkdtemp(prefix="pixelpane-test-"))
HOME, VAR = ROOT / "home", ROOT / "var"
os.environ["PIXELPANE_HOME"] = str(HOME)
os.environ["PIXELPANE_STATE"] = str(VAR)
os.environ["PIXELPANE_CACHE"] = str(ROOT / "cache")
os.environ["PIXELPANE_PLUGINS"] = str(ROOT / "user-plugins")


def load_plugins():
    from pixelpane import plugin
    plugin.load(user_dir=None)


def make_gif(path, size=(32, 32), frames=3, colors=((255, 0, 0), (0, 255, 0), (0, 0, 255))):
    path.parent.mkdir(parents=True, exist_ok=True)
    imgs = [Image.new("RGB", size, colors[i % len(colors)]) for i in range(frames)]
    imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=80, loop=0)
    return path


LIBRARY = {
    "gifs/retro-mario-run.gif": (32, 32),
    "gifs/retro-sonic-dash.gif": (32, 32),
    "gifs/space-earth-spin.gif": (64, 48),   # not square: must be cropped and scaled
    "gifs/abstract-plasma.gif": (16, 16),    # small: must be scaled up
    "gifs/themes/halloween/pumpkin-glow.gif": (32, 32),
    "gifs/themes/winter/snowman-wave.gif": (32, 32),
}


def reset():
    """Fresh library and empty state dir for each test."""
    shutil.rmtree(HOME, ignore_errors=True)
    shutil.rmtree(VAR, ignore_errors=True)
    for rel, size in LIBRARY.items():
        make_gif(HOME / rel, size)
    (HOME / "gifs" / "README.md").write_text("not a gif")
    VAR.mkdir(parents=True)


SAMPLE_DATA = {
    "weather": {"temp": 52, "condition": "rainy", "high": 61, "low": 44, "precip": 40, "unit": "F"},
    "now_playing": {"title": "Midnight City", "artist": "M83", "player": "Office", "state": "playing"},
    "homelab": {"alerts": 2, "names": ["plex", "nas"], "warnings": 0},
    "tiles": {"items": [{"icon": "thermometer", "text": "71F office", "color": "#ffaa44"}]},
}


def ctx_with(data=None, seed=1):
    """A scene context backed by a real State (and its data store) and GifLibrary."""
    load_plugins()
    from pixelpane.app import Ctx
    from pixelpane.state import GifLibrary, State
    state = State()
    for k, v in (data or {}).items():
        state.put_data(k, v)
    rng = random.Random(seed)
    return Ctx(state, GifLibrary(state, rng), rng)
