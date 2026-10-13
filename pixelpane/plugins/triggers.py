"""Triggers: notifications the board raises by itself, on a timetable or when data changes."""
import json
import logging
import time
from datetime import datetime, timedelta

from .. import gfx
from ..plugin import Plugin
from ..state import VAR, _atomic_write

log = logging.getLogger("pixelpane.triggers")

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
STYLE_OPTIONS = [{"label": "Like the others", "value": "default"}, {"label": "Classic", "value": "classic"},
                 {"label": "Banner", "value": "banner"}, {"label": "Burst", "value": "burst"},
                 {"label": "Ticker", "value": "ticker"}]
READINGS = ["temp", "aqi", "humidity", "co2", "battery"]
# what a watch can look at: value -> label
SIGNALS = {
    "weather.temp": "Outside temperature", "weather.condition": "Weather condition",
    "weather.wind": "Wind (mph)", "weather.precip": "Chance of rain (%)",
    **{f"tile.{k}": f"Reading: {n}" for k, n in (("temp", "temperature"), ("aqi", "air quality"),
                                                   ("humidity", "humidity"), ("co2", "CO2"), ("battery", "battery"))},
    "homelab.alerts": "Homelab alerts", "homelab.warnings": "Homelab warnings",
    "now_playing.title": "Song playing", "calendar.minutes": "Minutes to the next event",
    "status.dots": "Status dots on",
}
OPS = [{"label": "goes above", "value": "above"}, {"label": "goes below", "value": "below"},
       {"label": "becomes", "value": "is"}, {"label": "stops being", "value": "is_not"},
       {"label": "changes", "value": "changes"}]
ICON_OPTIONS = [{"label": i, "value": i} for i in gfx.ICONS]
TILE_SIGNALS = [k for k in SIGNALS if k.startswith("tile.")]
STATE_FILE = VAR / "triggers.json"   # which reminders already went off today

plugin = Plugin(
    "triggers", "Reminders and watches: notifications the board raises itself",
    defaults={"reminders": [], "watches": []},
    about="Reminders go off at a time on the days you pick (take the bins out, stand up, "
          "water the plants). Watches keep an eye on the data the board already gets and "
          "raise a notification when something becomes true: the air quality goes above "
          "150, it starts to snow, a homelab alert fires, the next meeting is 5 minutes "
          "away. A watch goes off when its condition starts being true, not again until it "
          "has stopped and started again, and at most once per cooldown. In the text, "
          "{value} is the current value and {label} the reading's label.",
    fields=[
        {"key": "reminders", "label": "Reminders", "type": "items", "max": 12, "add_label": "Add a reminder",
         "item_label": "reminder", "fields": [
             {"key": "text", "label": "Text", "type": "text", "default": "", "maxlength": 80,
              "placeholder": "Take the bins out"},
             {"key": "time", "label": "Time", "type": "text", "default": "09:00", "placeholder": "HH:MM",
              "pattern": r"([01]\d|2[0-3]):[0-5]\d"},
             {"key": "days", "label": "Days", "type": "choices", "options": DAYS, "default": list(DAYS)},
             {"key": "icon", "label": "Icon", "type": "select", "options": ICON_OPTIONS, "default": "bell"},
             {"key": "color", "label": "Color", "type": "color", "default": "#fbbf24"},
             {"key": "style", "label": "Style", "type": "select", "options": STYLE_OPTIONS, "default": "default"}]},
        {"key": "watches", "label": "Watches", "type": "items", "max": 12, "add_label": "Add a watch",
         "item_label": "watch", "fields": [
             {"key": "when", "label": "When", "type": "select", "default": "tile.aqi",
              "options": [{"label": v, "value": k} for k, v in SIGNALS.items()]},
             {"key": "label", "label": "Reading label", "type": "text", "default": "", "maxlength": 24,
              "placeholder": "any", "help": "Only readings with this label (office...). Empty: any.",
              "show_when": {"when": TILE_SIGNALS}},
             {"key": "op", "label": "Condition", "type": "select", "options": OPS, "default": "above"},
             {"key": "value", "label": "Value", "type": "text", "default": "150", "maxlength": 40,
              "show_when": {"op": ["above", "below", "is", "is_not"]}},
             {"key": "text", "label": "Text", "type": "text", "default": "", "maxlength": 80,
              "placeholder": "Air quality {value}"},
             {"key": "icon", "label": "Icon", "type": "select", "options": ICON_OPTIONS, "default": "alert"},
             {"key": "color", "label": "Color", "type": "color", "default": "#f87171"},
             {"key": "cooldown", "label": "Quiet for (minutes)", "type": "number", "min": 0, "max": 1440,
              "default": 60, "help": "After going off, wait at least this long before going off again."},
             {"key": "style", "label": "Style", "type": "select", "options": STYLE_OPTIONS, "default": "default"}]},
    ])


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def signal(ctx, when, label=""):
    """The current value of a signal and the label to show with it: (value, label), or (None, "")."""
    src, _, field = str(when).partition(".")
    if src == "tile":
        for item in (ctx.data("tiles") or {}).get("items") or []:
            lab = str(item.get("label") or "")
            if item.get("kind") == field and (not label or lab.lower() == label.lower()):
                return item.get("value"), lab
        return None, ""
    if src == "calendar":
        ev = ctx.data("next_event") or {}
        try:
            start = datetime.fromisoformat(str(ev.get("start")))
        except ValueError:
            return None, ""
        if start.tzinfo:
            start = start.astimezone().replace(tzinfo=None)
        mins = (start - ctx.now()).total_seconds() / 60
        return (round(mins) if mins >= 0 else None), str(ev.get("title") or "")
    if src == "status":
        return len((ctx.data("status") or {}).get("dots") or []), ""
    data = ctx.data(src) or {}
    return data.get(field), ""


def holds(op, value, target):
    """Is the watch's condition true right now? (changes is handled by the caller.)"""
    if value is None:
        return False
    a, b = _num(value), _num(target)
    if op in ("above", "below"):
        return a is not None and b is not None and (a > b if op == "above" else a < b)
    same = a == b if a is not None and b is not None else str(value).strip().lower() == str(target).strip().lower()
    return same if op == "is" else not same


def fill(text, value, label, fallback):
    out = (text or fallback).replace("{value}", "" if value is None else
                                     (f"{value:g}" if isinstance(value, float) else str(value)))
    return out.replace("{label}", label or "")


def note(item, text):
    n = {"text": text, "icon": item.get("icon") or "bell", "color": item.get("color") or "#ffffff"}
    if item.get("style") not in (None, "", "default"):
        n["style"] = item["style"]
    return n


def _key(item, *fields):
    return json.dumps([item.get(f) for f in fields])


def due_reminders(reminders, now, fired):
    """Reminders whose time came in the last 10 minutes on one of their days and that
    haven't gone off today. Marks them in fired ({key: "YYYY-MM-DD"})."""
    today = now.strftime("%Y-%m-%d")
    out = []
    for r in reminders:
        if not r.get("text") or DAYS[now.weekday()] not in (r.get("days") or DAYS):
            continue
        try:
            hh, mm = (int(x) for x in str(r.get("time")).split(":"))
        except ValueError:
            continue
        at = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        key = _key(r, "text", "time")
        if at <= now < at + timedelta(minutes=10) and fired.get(key) != today:
            fired[key] = today
            out.append(r)
    return out


class Watcher:
    """Edge detection and cooldowns for the watches."""

    def __init__(self):
        self.was, self.last, self.fired = {}, {}, {}

    def check(self, ctx, watches, now=None):
        now = time.time() if now is None else now
        out = []
        for w in watches:
            key = _key(w, "when", "label", "op", "value")
            value, label = signal(ctx, w.get("when"), w.get("label") or "")
            op = w.get("op") or "above"
            if op == "changes":
                prev, self.last[key] = self.last.get(key), value
                hit = key in self.was and value is not None and prev is not None and value != prev
                self.was[key] = True
                edge = hit
            else:
                now_true = holds(op, value, w.get("value"))
                # the first look only learns the state: a watch fires when something becomes true
                edge = key in self.was and now_true and not self.was[key]
                self.was[key] = now_true
            cool = float(w.get("cooldown") or 0) * 60
            if edge and now - self.fired.get(key, -1e12) >= cool:
                self.fired[key] = now
                fallback = f"{SIGNALS.get(w.get('when'), w.get('when'))} {{value}}"
                out.append(note(w, fill(w.get("text"), value, label, fallback)))
        return out


def _load_fired():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


@plugin.task
def run(ctx, stop):
    fired, watcher = _load_fired(), Watcher()
    while True:
        cfg = ctx.settings("triggers")
        due = due_reminders(cfg.get("reminders") or [], ctx.now(), fired)
        for r in due:
            ctx.state.notify(note(r, r["text"]))
        if due:
            try:
                today = ctx.now().strftime("%Y-%m-%d")
                _atomic_write(STATE_FILE, {k: v for k, v in fired.items() if v == today})
            except OSError as e:
                log.warning("couldn't save reminders: %s", e)
        for n in watcher.check(ctx, cfg.get("watches") or []):
            ctx.state.notify(n)
        if stop.wait(15):
            return
