"""Validation for config changes coming in through PUT /api/config.

Everything the page or Home Assistant sends is checked here before it is saved,
so a typo becomes a clear 400 instead of a scene that breaks later.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from . import plugin, schedule, seasons
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
    return not arg and (base in SCENES or base in plugin.PICKERS)


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
    if t == "color":
        if not isinstance(v, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ConfigError(f"{what} must be a color like #ff5fa2")
        return v.lower()
    if t == "select":
        allowed = [o["value"] for o in f.get("options", [])]
        if v not in allowed:
            raise ConfigError(f"{what} must be one of {allowed}")
        return v
    if t == "toggle":
        if not isinstance(v, bool):
            raise ConfigError(f"{what} must be true or false")
        return v
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


def _like_default(default: Any, v: Any, what: str) -> Any:
    """A setting without a form field: it must at least be the same kind of value as
    its default (a default of None accepts anything JSON)."""
    if default is None or v is None:
        return v
    kinds = [(bool, "true or false"), ((int, float), "a number"), (str, "text"), (list, "a list"),
             (dict, "an object")]
    for kind, word in kinds:
        if isinstance(default, kind) and not (kind != bool and isinstance(default, bool)):
            if not isinstance(v, kind) or (kind != bool and isinstance(v, bool)):
                raise ConfigError(f"{what} must be {word}")
            return v
    return v


def reset_secrets(changes: dict, config: dict) -> dict:
    """A secret field with "reset_on": [keys] is cleared when one of those keys changes
    and no new secret comes with it. Otherwise anyone who can change the generator's
    server URL could have the board send its saved API key to a server of theirs."""
    for name, clean in (changes.get("plugins") or {}).items():
        p = plugin.PLUGINS.get(name)
        current = plugin.settings(config, name)
        for f in p.fields if p else []:
            if f.get("type") != "secret" or f["key"] in clean:
                continue
            if any(k in clean and clean[k] != current.get(k) for k in f.get("reset_on", ())):
                clean[f["key"]] = None
    return changes


DAY = re.compile(r"(\d{4}-)?\d{2}-\d{2}")


def _day(v: Any, what: str) -> str:
    """"MM-DD" (every year) or "YYYY-MM-DD" (that year only)."""
    if not isinstance(v, str) or not DAY.fullmatch(v):
        raise ConfigError(f"{what} must be a date like 11-08 or 2027-02-06")
    try:
        date.fromisoformat(v if len(v) == 10 else f"2024-{v}")   # 2024 has a Feb 29
    except ValueError:
        raise ConfigError(f"{what}: {v} is not a real date") from None
    return v


def _themes(v: Any) -> dict:
    if not isinstance(v, dict) or set(v) - {"hemisphere", "off", "custom"}:
        raise ConfigError("themes must be {hemisphere, off, custom}")
    out = {}
    if "hemisphere" in v:
        if v["hemisphere"] not in ("north", "south"):
            raise ConfigError("themes.hemisphere must be north or south")
        out["hemisphere"] = v["hemisphere"]
    if "off" in v:
        off = _str_list(v["off"], "themes.off")
        bad = [x for x in off if x not in seasons.HOLIDAYS]
        if bad:
            raise ConfigError(f"themes.off: {bad} are not built-in holidays ({', '.join(seasons.HOLIDAYS)})")
        out["off"] = off
    if "custom" in v:
        if not isinstance(v["custom"], list) or len(v["custom"]) > 50:
            raise ConfigError("themes.custom must be a list of up to 50 holidays")
        out["custom"], keys = [], set()
        for i, c in enumerate(v["custom"]):
            what = f"themes.custom[{i}]"
            if not isinstance(c, dict) or set(c) - {"key", "name", "dates"}:
                raise ConfigError(f"{what} must be {{key, name, dates}}")
            key = category_name(c.get("key") or c.get("name"), f"{what}.key")
            if key in seasons.BUILTIN or key == "all" or key in keys:
                raise ConfigError(f"{what}.key {key!r} is taken")
            keys.add(key)
            name = c.get("name") or key
            if not isinstance(name, str) or len(name) > 40:
                raise ConfigError(f"{what}.name must be text up to 40 characters")
            dates = c.get("dates")
            if not isinstance(dates, list) or not dates or len(dates) > 50:
                raise ConfigError(f"{what}.dates must be a list of [from, to] ranges")
            clean = []
            for j, r in enumerate(dates):
                if not isinstance(r, list) or len(r) != 2:
                    raise ConfigError(f"{what}.dates[{j}] must be [from, to]")
                a, b = (_day(x, f"{what}.dates[{j}]") for x in r)
                if len(a) != len(b) or (len(a) == 10 and b < a):
                    raise ConfigError(f"{what}.dates[{j}]: use two yearly dates or two full dates, in order")
                clean.append([a, b])
            out["custom"].append({"key": key, "name": name, "dates": clean})
    return out


def _hosts(v: Any) -> list[str]:
    v = _str_list(v, "allowed_hosts")
    out = []
    for h in v:
        h = h.strip().lower().rstrip(".")
        if not h or len(h) > 253 or not all(c.isalnum() or c in "-." for c in h):
            raise ConfigError(f"allowed_hosts: {h!r} is not a host name")
        out.append(h)
    return out


def _schedule(v: Any) -> list[dict]:
    if not isinstance(v, list) or len(v) > 30:
        raise ConfigError("schedule must be a list of up to 30 rules")
    out = []
    for i, r in enumerate(v):
        what = f"schedule[{i}]"
        if not isinstance(r, dict):
            raise ConfigError(f"{what} must be an object")
        extra = set(r) - {"label", "days", "from", "to", "action", "brightness", "rotation", "enabled"}
        if extra:
            raise ConfigError(f"{what}: unknown keys {sorted(extra)}")
        rule = {"label": r.get("label") or "", "enabled": r.get("enabled", True)}
        if not isinstance(rule["label"], str) or len(rule["label"]) > 40:
            raise ConfigError(f"{what}.label must be text up to 40 characters")
        if not isinstance(rule["enabled"], bool):
            raise ConfigError(f"{what}.enabled must be true or false")
        days = r.get("days", list(range(7)))
        if (not isinstance(days, list) or not days
                or not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in days)):
            raise ConfigError(f"{what}.days must be a list of 0 (Monday) to 6 (Sunday)")
        rule["days"] = sorted(set(days))
        for k in ("from", "to"):
            try:
                schedule.parse_hhmm(r.get(k))
            except ValueError:
                raise ConfigError(f"{what}.{k} must be a time like 07:30") from None
            rule[k] = r[k]
        rule["action"] = r.get("action")
        if rule["action"] not in schedule.ACTIONS:
            raise ConfigError(f"{what}.action must be one of {list(schedule.ACTIONS)}")
        if rule["action"] == "dim":
            rule["brightness"] = _num(r.get("brightness"), f"{what}.brightness", 1, 100, integer=True)
        if rule["action"] == "playlist":
            rot = _str_list(r.get("rotation"), f"{what}.rotation")
            bad = [x for x in rot if not valid_scene(x)]
            if not rot or bad:
                raise ConfigError(f"{what}.rotation: needs scenes; unknown {bad}" if bad else
                                  f"{what}.rotation needs at least one scene")
            rule["rotation"] = rot
        out.append(rule)
    return out


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
                clean[key] = _like_default(p.defaults[key], value, what)  # no form field
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
        elif key == "schedule":
            out[key] = _schedule(v)
        elif key == "ui":
            if not isinstance(v, dict) or set(v) - {"theme", "accent"}:
                raise ConfigError("ui must be {theme, accent}")
            if "theme" in v and v["theme"] not in ("dark", "light", "auto"):
                raise ConfigError("ui.theme must be dark, light or auto")
            out[key] = {**({"theme": v["theme"]} if "theme" in v else {}),
                        **({"accent": _field({"type": "color"}, v["accent"], "ui.accent")} if "accent" in v else {})}
        elif key == "themes":
            out[key] = _themes(v)
        elif key == "allowed_hosts":
            out[key] = _hosts(v)
        elif key == "api_token":
            if v == MASK:
                continue
            if v is not None and (not isinstance(v, str) or len(v) < 8):
                raise ConfigError("api_token must be at least 8 characters, or null to turn it off")
            out[key] = v
        else:
            raise ConfigError(f"unknown setting {key!r}")
    return out
