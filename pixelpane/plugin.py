"""Plugins: every scene comes from one, and each can be switched on or off.

A plugin is a Python module that creates a Plugin and registers scenes on it:

    from pixelpane.kit import ticks, scroll_text
    from pixelpane.plugin import Plugin

    plugin = Plugin("hello", "Says hello", data={"greeting": 60}, defaults={"color": "#ff5fa2"})

    @plugin.scene("hello")
    def hello(ctx, secs):
        text = (ctx.data("greeting") or {}).get("text", "HELLO")
        color = ctx.settings("hello")["color"]
        for i, t in ticks(secs, 10):
            img = gfx.blank()
            scroll_text(img, 12, text, gfx.hex_color(color), "5x7", t)
            yield img, 0.1

Built-in plugins live in pixelpane/plugins/. Your own go in the plugins folder
(PIXELPANE_PLUGINS, default /etc/pixelpane/plugins), one .py file each, or in a
Python package that declares a "pixelpane.plugins" entry point.
Settings come from config["plugins"][name], merged over the plugin's defaults;
"enabled": false turns a plugin off. See docs/PLUGINS.md.
"""
import importlib
import importlib.metadata
import importlib.util
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger("pixelpane.plugin")

# The plugin API this PixelPane speaks. A plugin that needs a newer one is refused
# with a clear error instead of failing in odd ways later.
API_VERSION = 1

SCENES = {}    # scene name -> generator function (with .kind, .plugin, .pinnable, .params, .empty_text)
PICKERS = {}   # playlist entry -> fn(ctx) returning the scene to play (seasonal, generative)
WRAPPERS = []  # fn(ctx, frames, info) that rework every scene's frames (overlays, transitions)
PLUGINS = {}   # plugin name -> Plugin
ERRORS = []    # plugins that failed to load: [{"source", "error"}], shown on the page

BUILTIN = ["alerts", "clock", "weather", "now_playing", "calendar", "homelab", "tiles",
           "gifs", "seasonal", "generative", "sky", "generator", "effects", "triggers"]
# Root-owned on the Pi, so the service (which can write /var/lib/pixelpane) can't
# plant code that it would then load.
USER_DIR = Path(os.environ.get("PIXELPANE_PLUGINS", "/etc/pixelpane/plugins"))
ENTRY_POINTS = "pixelpane.plugins"

# Kinds that make sense to hold on screen with POST /api/pin
PINNABLE_KINDS = {"widget", "generative", "seasonal", "mode"}
PARAM_TYPES = {"text": str, "color": str, "number": (int, float), "bool": bool}


class PluginError(Exception):
    pass


class Plugin:
    def __init__(self, name, description="", data=None, defaults=None, about="", fields=None,
                 version="", api=1):
        """data: keys Home Assistant (or anything) may POST to /api/data/<key>, with
        how many minutes each stays fresh. defaults: this plugin's settings.
        about: a paragraph for the control page. fields: how to edit the settings
        there, a list of {key, label, type, help, ...} where type is number, range,
        text, list (one item per line), choices (checkboxes from options),
        monthday, select, toggle, color (#rrggbb) or secret; key may be dotted
        ("birthday.month").
        version: your plugin's own version, shown on the page. api: the plugin API
        version it was written for (pixelpane.plugin.API_VERSION)."""
        if api > API_VERSION:
            raise PluginError(f"plugin {name!r} needs plugin API {api}; this PixelPane has {API_VERSION}")
        if name in PLUGINS:
            raise PluginError(f"a plugin named {name!r} already exists ({PLUGINS[name].source})")
        self.name, self.description, self.about = name, description, about
        self.version, self.api = str(version), api
        self.fields = list(fields or [])
        self.data = dict(data or {})
        self.defaults = dict(defaults or {})
        self.scenes = []
        self.tasks = []
        self.source = "built-in"
        PLUGINS[name] = self

    def scene(self, name, kind="widget", pinnable=None, params=None, empty_text=None):
        """Register a scene. kind: widget, gif, generative, seasonal, interrupt or mode.

        pinnable: may POST /api/pin hold it on screen (default: yes for widget,
        generative, seasonal and mode scenes). params: what /api/play and /api/pin may
        pass it, {name: "text" | "color" | "number" | "bool"}; anything else is refused.
        empty_text: shown when someone asks for the scene and it has nothing to show
        (a setup problem worth seeing); without it the scene just skips."""
        if name in SCENES or name in PICKERS:
            raise PluginError(f"scene {name!r} already exists (from plugin {_owner(name)!r})")

        def deco(fn):
            fn.kind, fn.plugin = kind, self.name
            fn.pinnable = kind in PINNABLE_KINDS if pinnable is None else pinnable
            fn.params = dict(params or {})
            fn.empty_text = empty_text
            SCENES[name] = fn
            self.scenes.append(name)
            return fn
        return deco

    def picker(self, name):
        """Register a playlist entry that picks one of this plugin's scenes each time it
        comes up: fn(ctx) returns a scene name, or None to skip."""
        if name in SCENES or name in PICKERS:
            raise PluginError(f"scene {name!r} already exists (from plugin {_owner(name)!r})")

        def deco(fn):
            fn.plugin = self.name
            PICKERS[name] = fn
            return fn
        return deco

    def frames(self, fn):
        """Register a frame wrapper, fn(ctx, frames, info), run around every scene while
        the plugin is on. frames yields the scene's (image, seconds) pairs; the wrapper
        yields its own. info is {"scene", "kind", "prev"}: prev is the last frame of the
        scene before, or None. Images may be cached (GIF frames): copy before drawing."""
        fn.plugin = self.name
        WRAPPERS.append(fn)
        return fn

    def task(self, fn):
        """Register a background task, run as fn(ctx, stop_event) in its own thread while
        the plugin is on. stop_event is set when the plugin is turned off or the board
        stops. If it raises, it is logged and started again after a pause."""
        self.tasks.append(fn)
        return fn


def _owner(scene):
    fn = SCENES.get(scene) or PICKERS.get(scene)
    return getattr(fn, "plugin", "?")


def _forget(before):
    """Undo what a plugin that failed half-way registered."""
    for name in set(PLUGINS) - before["plugins"]:
        PLUGINS.pop(name)
    for name in set(SCENES) - before["scenes"]:
        SCENES.pop(name)
    for name in set(PICKERS) - before["pickers"]:
        PICKERS.pop(name)
    del WRAPPERS[before["wrappers"]:]


def _guarded(source, load_one):
    """Run one plugin load; a broken plugin is logged and recorded, never fatal."""
    before = {"plugins": set(PLUGINS), "scenes": set(SCENES), "pickers": set(PICKERS),
              "wrappers": len(WRAPPERS)}
    try:
        load_one()
    except Exception as e:  # one broken plugin must not stop the board
        _forget(before)
        ERRORS.append({"source": source, "error": f"{type(e).__name__}: {e}"})
        log.exception("plugin %s failed to load", source)
        return
    for name in set(PLUGINS) - before["plugins"]:
        PLUGINS[name].source = source
    log.info("loaded plugin %s", source)


def load(user_dir=USER_DIR, entry_points=True):
    """Import the built-in plugins, then installed packages that declare a
    "pixelpane.plugins" entry point, then any .py files in the user plugin folder."""
    for name in BUILTIN:
        importlib.import_module(f"pixelpane.plugins.{name}")
    if entry_points:
        for ep in importlib.metadata.entry_points(group=ENTRY_POINTS):
            dist = getattr(ep, "dist", None)
            label = f"package {dist.name} {dist.version}" if dist else f"package {ep.value}"
            _guarded(label, ep.load)
    if user_dir and Path(user_dir).is_dir():
        for path in sorted(Path(user_dir).glob("*.py")):
            def one(path=path):
                spec = importlib.util.spec_from_file_location(f"pixelpane_user_{path.stem}", path)
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
            _guarded(f"file {path.name}", one)
    return PLUGINS


def settings(config, name):
    """A plugin's settings: its defaults with config["plugins"][name] on top."""
    p = PLUGINS.get(name)
    out = dict(p.defaults) if p else {}
    out.update((config.get("plugins") or {}).get(name) or {})
    out.setdefault("enabled", True)
    return out


def enabled(config, name):
    return bool(settings(config, name).get("enabled", True))


def scene_enabled(config, scene):
    fn = SCENES.get(scene) or PICKERS.get(scene)
    return bool(fn) and enabled(config, fn.plugin)


def wrap(config, ctx, frames, info):
    """frames run through the frame wrappers of every enabled plugin."""
    for fn in WRAPPERS:
        if enabled(config, fn.plugin):
            frames = fn(ctx, frames, info)
    return frames


def pinnable(scene):
    if scene in PICKERS:
        return True
    fn = SCENES.get(scene)
    return bool(fn) and fn.pinnable


def check_params(scene, params):
    """Params from the API for a scene, checked against what it declared; raises ValueError."""
    if params is None:
        return {}
    if not isinstance(params, dict):
        raise ValueError("params must be an object")
    fn = SCENES.get(str(scene).partition(":")[0])
    allowed = fn.params if fn else {}
    out = {}
    for k, v in params.items():
        kind = allowed.get(k)
        if not kind:
            raise ValueError(f"scene {scene} takes no param {k!r}")
        if not isinstance(v, PARAM_TYPES[kind]) or (kind == "number" and isinstance(v, bool)):
            raise ValueError(f"param {k} must be {kind}")
        if isinstance(v, str) and len(v) > 200:
            raise ValueError(f"param {k} is too long")
        out[k] = v
    return out


def data_ttl(config, key):
    """Minutes a pushed data key stays fresh, or None if no enabled plugin takes it."""
    for p in PLUGINS.values():
        if key in p.data and enabled(config, p.name):
            return (config.get("data_ttl_minutes") or {}).get(key, p.data[key])
    return None


def describe(config):
    out = []
    for p in PLUGINS.values():
        secrets = {f["key"] for f in p.fields if f.get("type") == "secret"}
        s = {k: ("••••••••" if k in secrets and v else v) for k, v in settings(config, p.name).items()}
        out.append({"name": p.name, "description": p.description, "about": p.about, "fields": p.fields,
                    "enabled": enabled(config, p.name), "scenes": p.scenes, "data": p.data, "settings": s,
                    "version": p.version, "source": p.source,
                    "tasks": [TASKS[id(fn)].status() for fn in p.tasks if id(fn) in TASKS]})
    return out


# --- background tasks ----------------------------------------------------------

TASKS = {}   # id(fn) -> Supervisor


class Supervisor:
    """Runs one plugin task while its plugin is on: stops it when the plugin is turned
    off, starts it again when it comes back, and restarts it (after a growing pause)
    if it crashes."""

    def __init__(self, plugin, fn, ctx, stop):
        self.plugin, self.fn, self.ctx, self.stop = plugin, fn, ctx, stop
        self.thread, self.halt = None, None
        self.crashes, self.last_error, self.restart_at = 0, None, 0.0
        TASKS[id(fn)] = self

    def status(self):
        return {"name": self.fn.__name__, "running": bool(self.thread and self.thread.is_alive()),
                "crashes": self.crashes, "last_error": self.last_error}

    def _run(self, halt):
        try:
            self.fn(self.ctx, halt)
        except Exception as e:
            self.crashes += 1
            self.last_error = f"{type(e).__name__}: {e}"
            self.restart_at = time.monotonic() + min(300, 5 * 2 ** min(self.crashes, 6))
            log.exception("task %s.%s crashed", self.plugin.name, self.fn.__name__)

    def check(self):
        """One supervision step (called every few seconds)."""
        on = not self.stop.is_set() and enabled(self.ctx.config, self.plugin.name)
        alive = bool(self.thread and self.thread.is_alive())
        if alive and not on:
            self.halt.set()
        elif not alive and on and time.monotonic() >= self.restart_at:
            self.halt = threading.Event()
            self.thread = threading.Thread(target=self._run, args=(self.halt,), daemon=True,
                                           name=f"{self.plugin.name}-{self.fn.__name__}")
            self.thread.start()


def run_tasks(ctx, stop, every=3.0):
    """Start every plugin task under a supervisor; returns the supervisor thread."""
    sups = [Supervisor(p, fn, ctx, stop) for p in PLUGINS.values() for fn in p.tasks]

    def loop():
        while True:
            for s in sups:
                s.check()
            if stop.wait(every):
                for s in sups:
                    s.check()   # sets every task's halt event
                return
    t = threading.Thread(target=loop, daemon=True, name="plugin-tasks")
    t.start()
    return t
