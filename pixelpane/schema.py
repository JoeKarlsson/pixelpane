"""Validation for config changes coming in through PUT /api/config.

Everything the page or Home Assistant sends is checked here before it is saved,
so a typo becomes a clear 400 instead of a scene that breaks later.
"""
from __future__ import annotations

from typing import Any

from . import plugin, seasons
from .plugin import SCENES

DISPLAYS = {"auto", "hzeller", "piomatter", "fake"}
MASK = "••••••••"  # what secrets look like on the way out; sending it back keeps the old value
PANEL_SIZES = {16, 32, 64, 128}


class ConfigError(ValueError):
    pass


def _num(v: Any, what: str, lo: float | None = None, hi: float | None = None, integer: bool = False,
         nullable: bool = False) -> Any:
    if v is None and nullable:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{what} must be a number")
    if integer and int(v) != v:
        raise ConfigError(f"{what} must be a whole number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise ConfigError(f"{what} must be between {lo} and {hi}")
    return int(v) if integer else v


def _str_list(v: Any, what: str) -> list[str]:
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise ConfigError(f"{what} must be a list of strings")
    return v


def valid_scene(name: Any) -> bool:
    base, _, arg = str(name).partition(":")
    if base == "gif" and arg:
        return arg.replace("_", "").isalnum()
    return base in SCENES or base in ("seasonal", "generative")


def category_name(v: Any, what: str = "category") -> str:
    """A GIF category: what follows "gif:" in the playlist, so letters, digits and _ only."""
    if not isinstance(v, str):
        raise ConfigError(f"{what} must be text")
    name = "_".join(v.strip().lower().replace("-", " ").split())
    if not name or len(name) > 24 or not name.replace("_", "").isalnum() or not name.isascii():
        raise ConfigError(f"{what} must be 1 to 24 letters, digits or _")
    return name


def theme_name(v: Any, what: str = "theme") -> str:
    if v != "all" and v not in seasons.THEMES:
        raise ConfigError(f"{what} must be all or one of {sorted(seasons.THEMES)}")
    return v


def _gif_meta(v: Any) -> dict:
    if not isinstance(v, dict):
        raise ConfigError("gif_meta must be an object")
    out = {}
    for gid, m in v.items():
        if not isinstance(m, dict) or set(m) - {"category", "theme"}:
            raise ConfigError(f"gif_meta[{gid!r}] must be {{category, theme}}")
        out[gid] = {**({"category": category_name(m["category"])} if "category" in m else {}),
                    **({"theme": theme_name(m["theme"])} if "theme" in m else {})}
    return out


def _field(f: dict, v: Any, what: str) -> Any:
    t = f.get("type")
    if t in ("number",):
        return _num(v, what, f.get("min"), f.get("max"), nullable=True)
    if t == "range":
        return _num(v, what, f.get("min", 0), f.get("max", 1))
    if t == "secret":
        if v is None or v == "":
            return None
        if not isinstance(v, str):
            raise ConfigError(f"{what} must be text")
        return v
    if t == "list":
        return _str_list(v, what)
    if t == "choices":
        v = _str_list(v, what)
        bad = [x for x in v if x not in f.get("options", [])]
        if bad:
            raise ConfigError(f"{what}: unknown choice {bad}")
        return v
    if t == "monthday":
        if v is None:
            return None
        if not isinstance(v, dict):
            raise ConfigError(f"{what} must be {{month, day, name}} or null")
        name = v.get("name", "")
        if not isinstance(name, str) or len(name) > 24:
            raise ConfigError(f"{what}.name must be text up to 24 characters")
        return {"month": _num(v.get("month"), f"{what}.month", 1, 12, integer=True),
                "day": _num(v.get("day"), f"{what}.day", 1, 31, integer=True), "name": name}
    if not isinstance(v, str):
        raise ConfigError(f"{what} must be text")
    return v


def _plugins(v: Any) -> dict:
    if not isinstance(v, dict):
        raise ConfigError("plugins must be an object")
    out = {}
    for name, settings in v.items():
        p = plugin.PLUGINS.get(name)
        if not p:
            raise ConfigError(f"unknown plugin {name!r}")
        if not isinstance(settings, dict):
            raise ConfigError(f"plugins.{name} must be an object")
        fields = {f["key"]: f for f in p.fields}
        clean = {}
        for key, value in settings.items():
            what = f"plugins.{name}.{key}"
            if key == "enabled":
                if not isinstance(value, bool):
                    raise ConfigError(f"{what} must be true or false")
                clean[key] = value
            elif key in fields:
                if fields[key].get("type") == "secret" and value == MASK:
                    continue  # unchanged secret coming back from the page
                clean[key] = _field(fields[key], value, what)
            elif key in p.defaults:
                clean[key] = value  # a setting without a form field: stored as given
            else:
                raise ConfigError(f"{what} is not a setting of {name}")
        out[name] = clean
    return out


def masked(config: dict) -> dict:
    """A copy of config safe to send out: the API token and secret plugin fields hidden."""
    out = dict(config)
    if out.get("api_token"):
        out["api_token"] = MASK
    plugins = {}
    for name, settings in (config.get("plugins") or {}).items():
        p = plugin.PLUGINS.get(name)
        secrets = {f["key"] for f in (p.fields if p else []) if f.get("type") == "secret"}
        plugins[name] = {k: (MASK if k in secrets and v else v) for k, v in settings.items()}
    out["plugins"] = plugins
    return out


def validate(changes: Any) -> dict:
    """Check a partial config; returns the cleaned dict or raises ConfigError."""
    if not isinstance(changes, dict):
        raise ConfigError("config must be an object")
    out: dict[str, Any] = {}
    for key, v in changes.items():
        if key == "brightness":
            out[key] = _num(v, key, 1, 100, integer=True)
        elif key == "rotation":
            v = _str_list(v, key)
            bad = [s for s in v if not valid_scene(s)]
            if bad:
                raise ConfigError(f"unknown scenes: {bad}")
            out[key] = v
        elif key in ("dwell", "data_ttl_minutes"):
            if not isinstance(v, dict):
                raise ConfigError(f"{key} must be an object")
            out[key] = {k: _num(x, f"{key}.{k}", 1, 24 * 60 * 60) for k, x in v.items()}
        elif key == "plugins":
            out[key] = _plugins(v)
        elif key == "hidden_gifs":
            out[key] = _str_list(v, key)
        elif key == "gif_meta":
            out[key] = _gif_meta(v)
        elif key == "gpio_slowdown":
            out[key] = _num(v, key, 0, 5, integer=True, nullable=True)
        elif key == "refresh_hz":
            out[key] = _num(v, key, 30, 2000, integer=True, nullable=True)
        elif key == "display":
            if v not in DISPLAYS:
                raise ConfigError(f"display must be one of {sorted(DISPLAYS)}")
            out[key] = v
        elif key == "adafruit_board":
            if v not in ("hat", "bonnet"):
                raise ConfigError("adafruit_board must be hat or bonnet")
            out[key] = v
        elif key == "hardware_mapping":
            if not isinstance(v, str) or not v:
                raise ConfigError("hardware_mapping must be text")
            out[key] = v
        elif key == "panel_bgr":
            if not isinstance(v, bool):
                raise ConfigError("panel_bgr must be true or false")
            out[key] = v
        elif key == "panel":
            if not isinstance(v, dict) or set(v) - {"cols", "rows"}:
                raise ConfigError("panel must be {cols, rows}")
            for k in ("cols", "rows"):
                if k in v and v[k] not in PANEL_SIZES:
                    raise ConfigError(f"panel.{k} must be one of {sorted(PANEL_SIZES)}")
            out[key] = v
        elif key == "api_token":
            if v == MASK:
                continue
            if v is not None and (not isinstance(v, str) or len(v) < 8):
                raise ConfigError("api_token must be at least 8 characters, or null to turn it off")
            out[key] = v
        else:
            raise ConfigError(f"unknown setting {key!r}")
    return out
