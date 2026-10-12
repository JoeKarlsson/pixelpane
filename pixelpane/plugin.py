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
(PIXELPANE_PLUGINS, default /var/lib/pixelpane/plugins), one .py file each.
Settings come from config["plugins"][name], merged over the plugin's defaults;
"enabled": false turns a plugin off. See docs/PLUGINS.md.
"""
import importlib
import importlib.util
import logging
import os
from pathlib import Path

log = logging.getLogger("pixelpane.plugin")

SCENES = {}    # scene name -> generator function (with .kind and .plugin)
PLUGINS = {}   # plugin name -> Plugin

BUILTIN = ["alerts", "clock", "weather", "now_playing", "calendar", "homelab", "tiles",
           "gifs", "seasonal", "generative", "sky", "generator"]
USER_DIR = Path(os.environ.get("PIXELPANE_PLUGINS", "/var/lib/pixelpane/plugins"))


class Plugin:
    def __init__(self, name, description="", data=None, defaults=None, about="", fields=None):
        """data: keys Home Assistant (or anything) may POST to /api/data/<key>, with
        how many minutes each stays fresh. defaults: this plugin's settings.
        about: a paragraph for the control page. fields: how to edit the settings
        there, a list of {key, label, type, help, ...} where type is number, range,
        text, list (one item per line), choices (checkboxes from options) or
        monthday; key may be dotted ("birthday.month") for nested settings."""
        self.name, self.description, self.about = name, description, about
        self.fields = list(fields or [])
        self.data = dict(data or {})
        self.defaults = dict(defaults or {})
        self.scenes = []
        self.tasks = []
        PLUGINS[name] = self

    def scene(self, name, kind="widget"):
        """Register a scene. kind: widget, gif, generative, seasonal, interrupt or mode."""
        def deco(fn):
            fn.kind, fn.plugin = kind, self.name
            SCENES[name] = fn
            self.scenes.append(name)
            return fn
        return deco

    def task(self, fn):
        """Register a background task, run as fn(ctx, stop_event) in its own thread."""
        self.tasks.append(fn)
        return fn


def load(user_dir=USER_DIR):
    """Import the built-in plugins, then any .py files in the user plugin folder."""
    for name in BUILTIN:
        importlib.import_module(f"pixelpane.plugins.{name}")
    if user_dir and Path(user_dir).is_dir():
        for path in sorted(Path(user_dir).glob("*.py")):
            try:
                spec = importlib.util.spec_from_file_location(f"pixelpane_user_{path.stem}", path)
                spec.loader.exec_module(importlib.util.module_from_spec(spec))
                log.info("loaded plugin file %s", path.name)
            except Exception:  # one broken plugin must not stop the board
                log.exception("plugin file %s failed to load", path.name)
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
    fn = SCENES.get(scene)
    return bool(fn) and enabled(config, fn.plugin)


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
                    "enabled": enabled(config, p.name), "scenes": p.scenes, "data": p.data, "settings": s})
    return out
