"""Config, runtime state, pushed data and the GIF library."""
import json
import os
import threading
import time
from collections import OrderedDict, deque
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageSequence

from . import plugin, seasons
from .gfx import H, W

HOME = Path(os.environ.get("PIXELPANE_HOME", "/opt/pixelpane"))
VAR = Path(os.environ.get("PIXELPANE_STATE", "/var/lib/pixelpane"))
DEFAULTS = json.loads(Path(__file__).with_name("default_config.json").read_text())


def _atomic_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=2))
    os.replace(tmp, path)


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


# Settings that moved into plugin sections (2026-10-12); old saved configs are moved over.
MOVED = {"weather_fallback": ("weather", None), "birthday": ("seasonal", "birthday"),
         "holiday_share": ("seasonal", "holiday_share"), "generative": ("generative", "scenes"),
         "theme_gif_share": ("gifs", "theme_share"), "art_hosts": ("now_playing", "art_hosts")}


def migrate(saved):
    """Move pre-plugin keys into config["plugins"]; returns (config, changed)."""
    changed = False
    for old, (name, key) in MOVED.items():
        if old in saved:
            value = saved.pop(old)
            section = saved.setdefault("plugins", {}).setdefault(name, {})
            if key is None and isinstance(value, dict):
                section.update(value)
            else:
                section[key] = value
            changed = True
    return saved, changed


def merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


class State:
    """Everything the player, the web API and Home Assistant share."""

    def __init__(self):
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.config_path = VAR / "config.json"
        self.state_path = VAR / "state.json"
        self.data_path = VAR / "data.json"
        saved, moved = migrate(_read(self.config_path))
        if moved:
            _atomic_write(self.config_path, saved)
        self.config = merge(DEFAULTS, saved)
        saved = _read(self.state_path)
        self.power = saved.get("power", True)
        self.brightness = saved.get("brightness", self.config["brightness"])
        self.pinned = saved.get("pinned")
        # Pushed data survives restarts; a deploy must not blank the widgets.
        self.data = {k: tuple(v) for k, v in _read(self.data_path).items()}
        self.notifications = deque(maxlen=20)
        self.play_next = None
        self.skip = False
        self.label = "starting"
        self.now = {"source": "starting"}  # what the player is on and why (see Player.mark)
        self.last_frame = Image.new("RGB", (W, H))
        self.started = time.time()

    # -- persistence --
    def save_state(self):
        with self.lock:
            _atomic_write(self.state_path, {"power": self.power, "brightness": self.brightness,
                                            "pinned": self.pinned})

    def update_config(self, changes):
        with self.lock:
            saved = merge(_read(self.config_path), changes)
            _atomic_write(self.config_path, saved)
            self.config = merge(DEFAULTS, saved)

    # -- controls (each wakes the player) --
    def set(self, power=None, brightness=None):
        with self.lock:
            if power is not None:
                self.power = bool(power)
            if brightness is not None:
                self.brightness = max(1, min(100, int(brightness)))
        self.save_state()
        self.wake.set()

    def pin(self, scene, params=None, minutes=None):
        with self.lock:
            self.pinned = None if not scene else {
                "scene": scene, "params": params or {},
                "until": time.time() + minutes * 60 if minutes else None}
        self.save_state()
        self.wake.set()

    def notify(self, item):
        self.notifications.append(item)
        self.wake.set()

    def skip_scene(self):
        """End the current scene (not a notification) and move on."""
        self.skip = True
        self.wake.set()

    def request(self, scene, params=None):
        self.play_next = {"scene": scene, "params": params or {}}
        self.wake.set()

    def put_data(self, key, payload):
        with self.lock:
            self.data[key] = (time.time(), payload)
            _atomic_write(self.data_path, self.data)

    def get_data(self, key):
        with self.lock:
            item = self.data.get(key)
        if not item:
            return None
        ttl = plugin.data_ttl(self.config, key)
        if ttl is None:  # no enabled plugin takes this key
            return None
        return item[1] if time.time() - item[0] < ttl * 60 else None

    def active_pin(self):
        with self.lock:
            p = self.pinned
            if p and p.get("until") and time.time() > p["until"]:
                self.pinned = p = None
                self.save_state()
            return p

    def themes(self, today=None):
        b = plugin.settings(self.config, "seasonal").get("birthday") or {}
        birthday = (b["month"], b["day"]) if b.get("month") and b.get("day") else None
        return seasons.active_themes(today or date.today(), birthday)


class GifLibrary:
    """Repo GIFs (gifs/, gifs/themes/<t>/) plus web uploads (uploads/all|<t>/)."""

    ROOTS = {"repo": HOME / "gifs", "upload": VAR / "uploads"}

    def __init__(self, state, rng):
        self.state, self.rng = state, rng
        self.bags = {}
        self.cache = OrderedDict()

    def _files(self, root, sub):
        d = root / sub if sub else root
        if not d.is_dir():
            return []
        return sorted(p for p in d.iterdir() if p.suffix.lower() == ".gif" and p.is_file())

    def gif_id(self, path):
        for name, root in self.ROOTS.items():
            try:
                return f"{name}/{path.relative_to(root)}"
            except ValueError:
                continue
        return str(path)

    def resolve(self, gif_id):
        name, _, rel = gif_id.partition("/")
        root = self.ROOTS.get(name)
        if not root or ".." in Path(rel).parts:
            return None
        p = root / rel
        return p if p.is_file() else None

    def pool(self, theme=None):
        if theme:
            files = self._files(self.ROOTS["repo"], f"themes/{theme}") + self._files(self.ROOTS["upload"], theme)
        else:
            files = self._files(self.ROOTS["repo"], None) + self._files(self.ROOTS["upload"], "all")
        hidden = set(self.state.config.get("hidden_gifs", []))
        return [p for p in files if self.gif_id(p) not in hidden]

    def listing(self):
        out = []
        for theme in [None] + list(seasons.THEMES):
            for p in (self._files(self.ROOTS["repo"], f"themes/{theme}" if theme else None)
                      + self._files(self.ROOTS["upload"], theme or "all")):
                gid = self.gif_id(p)
                out.append({"id": gid, "name": p.name, "theme": theme or "all",
                            "category": self.category(p) if not theme else theme,
                            "upload": gid.startswith("upload/"),
                            "hidden": gid in self.state.config.get("hidden_gifs", [])})
        return out

    def _draw(self, key, files):
        bag = self.bags.get(key)
        if not bag:
            bag = list(files)
            self.rng.shuffle(bag)
            self.bags[key] = bag
        while bag:
            p = bag.pop()
            if p in files:
                return p
        return None

    @staticmethod
    def category(path):
        """All-year GIFs are named <category>-<what-it-shows>.gif."""
        return path.stem.split("-", 1)[0].lower() if "-" in path.stem else "other"

    def categories(self):
        return sorted({self.category(p) for p in self.pool()})

    def next(self, category=None):
        cfg = self.state.config
        if category:
            files = [p for p in self.pool() if self.category(p) == category]
            return self._draw(f"cat:{category}", files) if files else None
        themed = [(t, self.pool(t)) for t in self.state.themes()]
        themed = [(t, f) for t, f in themed if f]
        if themed and self.rng.random() < plugin.settings(cfg, "gifs")["theme_share"]:
            t, files = self.rng.choice(themed)
            return self._draw(t, files)
        files = self.pool()
        return self._draw("all", files) if files else None

    def frames(self, path):
        key = str(path)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        try:
            frames = decode_gif(path)
        except (OSError, ValueError):
            frames = []
        self.cache[key] = frames
        if len(self.cache) > 16:
            self.cache.popitem(last=False)
        return frames


def fit(img, smooth=False):
    """Center-crop to square and scale to the panel."""
    w, h = img.size
    if (w, h) == (W, H):
        return img
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return img.resize((W, H), Image.LANCZOS if smooth else Image.NEAREST)


def decode_gif(path, smooth=False, limit=400):
    out = []
    with Image.open(path) as im:
        for i, frame in enumerate(ImageSequence.Iterator(im)):
            if i >= limit:
                break
            rgba = frame.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
            img = fit(Image.alpha_composite(bg, rgba).convert("RGB"), smooth)
            ms = frame.info.get("duration") or 100
            out.append((img, max(20, ms) / 1000))
    return out


def convert_upload(src, dest, smooth=False):
    """Save any image or animation as a 32x32 looping GIF."""
    frames = decode_gif(src, smooth)
    if not frames:
        raise ValueError("no frames")
    dest.parent.mkdir(parents=True, exist_ok=True)
    imgs = [f for f, _ in frames]
    imgs[0].save(dest, save_all=True, append_images=imgs[1:], loop=0,
                 duration=[int(d * 1000) for _, d in frames], disposal=1)
    return len(imgs)


def now():
    return datetime.now()
