"""Tiles: info cards. Readings (temperature, air quality, humidity, CO2, battery) get a
full-panel mood that shows how they feel; anything else gets an animated icon and gauge."""
import time
from collections import deque

from .. import gfx
from ..gfx import W
from ..kit import (SEVERITY, Mood, animated_icon, arrow, gauge, outlined_center, outlined_text,
                   scroll_seconds, scroll_text, sparkline, temp_color, ticks)
from ..plugin import Plugin

plugin = Plugin(
    "tiles", "Info cards: readings that look how they feel",
    data={"tiles": 240},
    defaults={"temp_unit": "F", "comfy_low": None, "comfy_high": None, "humidity_low": 30,
              "humidity_high": 60, "co2_high": 1200, "alert": True,
              "cold_color": "#5aa0ff", "comfy_color": "#3cdcaa", "hot_color": "#ff3c28"},
    about="Cards pushed from anywhere. Send a reading as {kind, value, label} and the whole "
          "panel shows how it feels: frost creeping in when it's cold, heat shimmer when it's "
          "hot, clear sparkling air or thick smog for air quality, condensation when it's humid, "
          "murky bubbles when CO2 is high. Kinds: temp, aqi, humidity, co2, battery. The number "
          "counts up, an arrow shows the trend and a sparkline the last few hours. Anything else "
          "is {icon, text, color, level}: an animated icon, text and a gauge. "
          "POST /api/data/tiles with {items: [...]}.",
    fields=[{"key": "temp_unit", "label": "Temperature unit", "type": "select",
             "options": [{"value": "F", "label": "Fahrenheit"}, {"value": "C", "label": "Celsius"}],
             "help": "What temp readings are in, unless a tile says its own unit."},
            {"key": "comfy_low", "label": "Comfortable from", "type": "number", "step": 1,
             "help": "Below this a temp tile turns cool, then cold. Empty: 68F / 20C."},
            {"key": "comfy_high", "label": "Comfortable up to", "type": "number", "step": 1,
             "help": "Above this it turns warm, then hot. Empty: 76F / 24C."},
            {"key": "humidity_low", "label": "Humidity: dry below (%)", "type": "number", "min": 0, "max": 100},
            {"key": "humidity_high", "label": "Humidity: humid above (%)", "type": "number", "min": 0, "max": 100},
            {"key": "co2_high", "label": "CO2: stuffy from (ppm)", "type": "number", "min": 400, "max": 5000},
            {"key": "cold_color", "label": "Cold color", "type": "color"},
            {"key": "comfy_color", "label": "Comfortable color", "type": "color"},
            {"key": "hot_color", "label": "Hot color", "type": "color"},
            {"key": "alert", "label": "Jump the queue when a reading turns bad", "type": "toggle",
             "help": "Unhealthy air, too hot or cold, stuffy, low battery. Once per reading per hour; "
                     "a tile with \"alert\": false never does."}])

KINDS = ("temp", "aqi", "humidity", "co2", "battery")
LABELS = {"temp": "TEMP", "aqi": "AIR", "humidity": "HUMIDITY", "co2": "CO2", "battery": "BATTERY"}
TREND_STEP = {"temp": 1.0, "aqi": 10, "humidity": 3, "co2": 100, "battery": 3}
SAMPLE_EVERY = 600   # seconds between history samples
HISTORY = 30         # samples kept: five hours
BAD = 3              # severity that jumps the queue


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tile_key(item):
    return f"{item.get('kind')}:{str(item.get('label') or '').upper()}"


def read(item, s):
    """How a reading feels: {word, severity (0-5), color, mood, amount, unit}, or None."""
    kind, v = item.get("kind"), _num(item.get("value"))
    if kind not in KINDS or v is None:
        return None
    if kind == "temp":
        unit = str(item.get("unit") or s.get("temp_unit") or "F").upper()[:1]
        to_f = (lambda c: c * 9 / 5 + 32) if unit == "C" else (lambda f: f)
        low = _num(s.get("comfy_low"))
        high = _num(s.get("comfy_high"))
        low = to_f(low if low is not None else (20 if unit == "C" else 68))
        high = to_f(high if high is not None else (24 if unit == "C" else 76))
        f = to_f(v)
        col = temp_color(f, gfx.hex_color(s.get("cold_color"), (90, 160, 255)),
                         gfx.hex_color(s.get("comfy_color"), (60, 220, 170)),
                         gfx.hex_color(s.get("hot_color"), (255, 60, 40)), low, high)
        if f < low - 8:
            return dict(word="COLD", severity=3, color=col, mood="frost", amount=1.0, unit=unit)
        if f < low:
            return dict(word="COOL", severity=1, color=col, mood="frost", amount=0.3, unit=unit)
        if f <= high:
            return dict(word="COMFY", severity=0, color=col, mood="calm", amount=0.3, unit=unit)
        if f <= high + 6:
            return dict(word="WARM", severity=1, color=col, mood="heat", amount=0.35, unit=unit)
        return dict(word="HOT", severity=3, color=col, mood="heat", amount=1.0, unit=unit)
    if kind == "aqi":   # US EPA bands
        for top, word, sev in ((50, "GOOD", 0), (100, "MODERATE", 1), (150, "POOR", 2),
                               (200, "BAD AIR", 3), (300, "VERY BAD", 4), (1e9, "DANGER", 5)):
            if v <= top:
                return dict(word=word, severity=sev, color=SEVERITY[sev], mood="haze",
                            amount=min(1.0, v / 300), unit="")
    if kind == "humidity":
        lo, hi = _num(s.get("humidity_low")) or 30, _num(s.get("humidity_high")) or 60
        if v < lo:
            return dict(word="DRY", severity=1, color=(255, 200, 120), mood="haze", amount=0.2, unit="%")
        if v <= hi:
            return dict(word="COMFY", severity=0, color=(80, 200, 255), mood="calm", amount=0.3, unit="%")
        if v <= hi + 10:
            return dict(word="HUMID", severity=1, color=(120, 170, 255), mood="droplets", amount=0.4, unit="%")
        return dict(word="MUGGY", severity=2, color=(150, 140, 255), mood="droplets", amount=1.0, unit="%")
    if kind == "co2":
        high = _num(s.get("co2_high")) or 1200
        if v < 800:
            return dict(word="FRESH", severity=0, color=SEVERITY[0], mood="bubbles", amount=0.1, unit="")
        if v < high:
            return dict(word="STUFFY", severity=1, color=SEVERITY[1], mood="bubbles",
                        amount=0.3 + 0.4 * (v - 800) / max(1, high - 800), unit="")
        return dict(word="OPEN A WINDOW", severity=3, color=SEVERITY[3], mood="bubbles", amount=1.0, unit="")
    if kind == "battery":
        sev = 0 if v > 50 else 1 if v > 20 else 3
        return dict(word="LOW" if sev == 3 else "OK" if sev == 0 else "HALF", severity=sev,
                    color=SEVERITY[sev], mood="calm", amount=0.3, unit="%")
    return None


def history(ctx, item):
    """Earlier values for a tile: what it sent itself, else what the board sampled."""
    sent = item.get("history")
    if isinstance(sent, list):
        return [v for v in (_num(x) for x in sent[-HISTORY:]) if v is not None]
    return list(ctx.store("tiles").get("history", {}).get(tile_key(item), []))


def _fmt(v, kind):
    return f"{v:.0f}" if kind != "temp" or abs(v) >= 10 or v == int(v) else f"{v:.1f}"


@plugin.scene("tiles", params={"focus": "text"}, empty_text="NO TILES YET")
def tiles(ctx, secs, focus=None):
    """Cards pushed from Home Assistant: readings with a mood, or {icon, text, color}."""
    data = ctx.data("tiles")
    items = (data or {}).get("items") or []
    if focus:   # a reading that just turned bad: show only that one
        items = [i for i in items if tile_key(i) == focus] or items
    if not items:
        return
    each = max(4.0, secs / len(items))
    s = ctx.settings("tiles")
    for item in items:
        feel = read(item, s)
        if feel:
            yield from _reading(ctx, item, feel, max(each, 4.0))
        else:
            yield from _card(item, each)


def _card(item, each):
    msg = str(item.get("text", "")).upper()
    col = gfx.hex_color(item.get("color"), (255, 255, 255))
    dur = max(each, scroll_seconds(msg, "5x7", 16) + 1)
    for i, t in ticks(dur, 10):
        img = gfx.blank()
        animated_icon(img, item.get("icon"), (12, 2), t, item.get("level"))
        scroll_text(img, 13, msg, col, "5x7", t, 16)
        if item.get("level") is not None:
            gauge(img, 23, item["level"], t, col)
        if item.get("sub"):
            gfx.text_center(img, 26, str(item["sub"]).upper()[:8], (120, 120, 140), "tom-thumb")
        yield img, 0.1


def _reading(ctx, item, feel, dur):
    kind, value = item["kind"], float(item["value"])
    s = ctx.settings("tiles")
    label = str(item.get("label") or LABELS[kind]).upper()
    mood = Mood(ctx.rng, feel["mood"], feel["amount"], feel["color"])
    past = history(ctx, item)
    if past and past[-1] != value:
        start = past[-1]          # moves across from the last reading
    elif kind == "temp":
        start = (value + 72) / 2 if feel["unit"] == "F" else (value + 22) / 2  # warms up or cools down
    else:
        start = 0.0
    trend = None
    if len(past) >= 3 and abs(value - past[-3]) >= TREND_STEP[kind]:
        trend = value > past[-3]
    spark = past + [value] if len(past) >= 2 else []
    spark_cols = [(read(dict(item, value=v), s) or feel)["color"] for v in spark]
    word = feel["word"]
    dur = max(dur, scroll_seconds(word, "tom-thumb", 14) + 1)
    for i, t in ticks(dur, 10):
        img = mood.frame(t)
        # the number counts up (or across from the last reading) and its color follows it
        e = 1 - (1 - min(1.0, t / 0.8)) ** 3
        shown = start + (value - start) * e
        col = (read(dict(item, value=shown), s) or feel)["color"] if e < 1 else feel["color"]
        if feel["severity"] >= 4 or (feel["severity"] >= BAD and kind != "temp"):
            pulse = 0.5 + 0.5 * abs((t * 2) % 2 - 1)
            edge = gfx.scale(feel["color"], pulse)
            px = img.load()
            for k in range(W):
                for x, y in ((k, 0), (k, W - 1), (0, k), (W - 1, k)):
                    px[x, y] = edge
        outlined_center(img, 1, label[:8], (170, 175, 200), "tom-thumb")
        num = _fmt(shown, kind)
        unit = feel["unit"]
        width = gfx.text_width(num, "6x10") + (gfx.text_width(unit, "tom-thumb") + 1 if unit else 0)
        x = (W - width) // 2
        outlined_text(img, (x, 8), num, col, "6x10")
        if unit:
            outlined_text(img, (x + gfx.text_width(num, "6x10") + 1, 8), unit, col, "tom-thumb")
        if trend is not None:
            arrow(img, min(W - 5, x + width + 1), 11, trend, (220, 220, 235))
        if gfx.text_width(word, "tom-thumb") <= W:
            outlined_center(img, 19, word, feel["color"], "tom-thumb")
        else:
            scroll_text(img, 19, word, feel["color"], "tom-thumb", t, 14)
        if spark:
            sparkline(img, spark, 26, 31, spark_cols)
        yield img, 0.1


@plugin.task
def watch(ctx, stop):
    """Sample readings for the sparklines and trends, and jump the queue when one turns bad."""
    store = ctx.store("tiles")
    hist = store.setdefault("history", {})
    worst = store.setdefault("severity", {})   # tile -> last severity seen
    alerted = store.setdefault("alerted", {})  # tile -> when it last jumped the queue
    last_sample = 0.0
    while not stop.wait(30):
        items = (ctx.data("tiles") or {}).get("items") or []
        s = ctx.settings("tiles")
        now = time.time()
        sample = now - last_sample >= SAMPLE_EVERY
        for item in items:
            feel = read(item, s)
            if not feel:
                continue
            key = tile_key(item)
            if sample:
                hist.setdefault(key, deque(maxlen=HISTORY)).append(float(item["value"]))
            was, worst[key] = worst.get(key, 0), feel["severity"]
            if (feel["severity"] >= BAD > was and s.get("alert", True) and item.get("alert", True)
                    and now - alerted.get(key, 0) > 3600):
                alerted[key] = now
                ctx.state.request("tiles", {"focus": key})
        if sample:
            last_sample = now
