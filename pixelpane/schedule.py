"""Schedules: quiet hours, dimming and time-of-day playlists.

config["schedule"] is a list of rules, each
    {"label": "Night", "days": [0, 1, 2, 3, 4, 5, 6], "from": "23:00", "to": "07:00",
     "action": "off" | "dim" | "playlist", "brightness": 20, "rotation": [...], "enabled": true}
days are Monday=0 ... Sunday=6 and name the day a window starts on, so a 23:00-07:00
rule on Friday runs into Saturday morning. from == to means a whole day.

At any moment the board is off if any "off" rule is on, dimmed to the lowest
"dim" rule that is on, and plays the first "playlist" rule's rotation.
"""
from __future__ import annotations

from datetime import datetime, timedelta

ACTIONS = ("off", "dim", "playlist")
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def parse_hhmm(s: str) -> int:
    """'07:30' -> minutes after midnight; raises ValueError."""
    if not isinstance(s, str) or len(s) != 5 or s[2] != ":":
        raise ValueError("time must be HH:MM")
    h, m = int(s[:2]), int(s[3:])
    if not (0 <= h < 24 and 0 <= m < 60):
        raise ValueError("time must be HH:MM")
    return h * 60 + m


def window(rule: dict, dt: datetime) -> datetime | None:
    """When rule's window that covers dt ends, or None if dt is outside it."""
    if not rule.get("enabled", True):
        return None
    start, end = parse_hhmm(rule["from"]), parse_hhmm(rule["to"])
    length = (end - start) % (24 * 60) or 24 * 60
    days = set(rule.get("days") or range(7))
    minute = dt.hour * 60 + dt.minute
    midnight = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    # the window could have started today or (if it runs past midnight) yesterday
    for back in (0, 1):
        began = midnight - timedelta(days=back) + timedelta(minutes=start)
        if (began.weekday() in days and began <= dt
                and (minute + back * 24 * 60 - start) < length):
            return began + timedelta(minutes=length)
    return None


def active(rules: list, dt: datetime) -> dict:
    """What the schedule says right now:
    {"off": bool, "until": datetime | None, "brightness": int | None,
     "rotation": list | None, "rules": [labels of rules that are on]}"""
    out = {"off": False, "until": None, "brightness": None, "rotation": None, "rules": []}
    for i, rule in enumerate(rules or []):
        try:
            ends = window(rule, dt)
        except (KeyError, ValueError, TypeError):
            continue   # validated on the way in; never let a bad rule stop the board
        if not ends:
            continue
        out["rules"].append(rule.get("label") or f"rule {i + 1}")
        action = rule.get("action")
        if action == "off":
            out["off"] = True
            out["until"] = max(out["until"], ends) if out["until"] else ends
        elif action == "dim":
            level = int(rule.get("brightness") or 1)
            out["brightness"] = level if out["brightness"] is None else min(out["brightness"], level)
        elif action == "playlist" and out["rotation"] is None and rule.get("rotation"):
            out["rotation"] = list(rule["rotation"])
    return out
