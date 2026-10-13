"""Effects: transitions between scenes, a small clock over GIFs, and status dots."""
from datetime import datetime
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter

from .. import gfx
from ..plugin import Plugin

TRANSITIONS = ["none", "fade", "wipe", "slide", "dissolve"]
OVERLAYS = ["off", "time", "date", "time_date", "temp", "meeting"]
CORNERS = ["auto", "top_left", "top_right", "bottom_left", "bottom_right"]
OVER_KINDS = ["gif", "generative", "seasonal"]

SHOWS = [("time", "Time"), ("date", "Date"), ("time_date", "Time and date, taking turns"),
         ("temp", "Outside temperature"), ("reading", "A tile reading"),
         ("meeting", "Minutes to the next meeting"), ("text", "Your own text")]
READINGS = ["temp", "aqi", "humidity", "co2", "battery"]

plugin = Plugin(
    "effects", "Transitions, overlays and status dots",
    data={"status": 120},
    defaults={"transition": "fade", "transition_seconds": 0.5, "status_dots": True, "overlays": None,
              # the single overlay from before "overlays"; used while overlays is unset
              "overlay": "off", "overlay_corner": "auto", "overlay_mode": "always",
              "overlay_on": ["gif"], "overlay_color": "#ffffff"},
    about="Polish that works on every scene. Transitions blend one scene into the next "
          "instead of cutting. Overlays put the time, date, outside temperature, a tile "
          "reading (office temperature, CO2...), minutes to your next meeting or your own "
          "text in a corner of GIFs, art or seasonal scenes, outlined so they stay "
          "readable; auto finds the calmest free corner. Status dots are tiny lights along "
          "the top edge that stay on while something is true (laundry done, a door open): "
          "POST /api/data/status with {dots: [{color, blink}]}, and an empty list to clear them.",
    fields=[{"key": "transition", "label": "Transition", "type": "select",
             "options": [{"label": t.capitalize(), "value": t} for t in TRANSITIONS]},
            {"key": "transition_seconds", "label": "Transition length (seconds)", "type": "range",
             "min": 0.2, "max": 1.5, "step": 0.1},
            {"key": "status_dots", "label": "Status dots", "type": "toggle",
             "text": "Show status dots on every scene"},
            {"key": "overlays", "label": "Overlays", "type": "items", "max": 4,
             "add_label": "Add an overlay", "item_label": "Overlay",
             "help": "Up to four, one per corner. Temperature, readings and meetings show "
                     "nothing while there's nothing to show.",
             "fields": [
                 {"key": "show", "label": "Show", "type": "select", "default": "time",
                  "options": [{"label": label, "value": v} for v, label in SHOWS]},
                 {"key": "reading", "label": "Reading", "type": "select", "default": "temp",
                  "options": [{"label": r.upper() if r in ("aqi", "co2") else r.capitalize(), "value": r}
                              for r in READINGS],
                  "show_when": {"show": ["reading"]}},
                 {"key": "label", "label": "Tile label", "type": "text", "default": "",
                  "placeholder": "office", "maxlength": 24, "show_when": {"show": ["reading"]},
                  "help": "Empty: the first tile of that kind."},
                 {"key": "text", "label": "Text", "type": "text", "default": "", "maxlength": 8,
                  "placeholder": "HI JOE", "show_when": {"show": ["text"]}},
                 {"key": "corner", "label": "Corner", "type": "select", "default": "auto",
                  "options": [{"label": c.replace("_", " ").capitalize(), "value": c} for c in CORNERS]},
                 {"key": "mode", "label": "Shows", "type": "select", "default": "always",
                  "options": [{"label": "All the time", "value": "always"},
                              {"label": "For 3 seconds every 20", "value": "peek"}]},
                 {"key": "size", "label": "Size", "type": "select", "default": "small",
                  "options": [{"label": "Small", "value": "small"}, {"label": "Large", "value": "large"}]},
                 {"key": "style", "label": "Style", "type": "select", "default": "outline",
                  "options": [{"label": "Outlined", "value": "outline"}, {"label": "On a dark box", "value": "box"},
                              {"label": "Plain", "value": "plain"}]},
                 {"key": "color", "label": "Color", "type": "color", "default": "#ffffff"},
                 {"key": "color_by_value", "label": "Color by value", "type": "toggle", "default": True,
                  "text": "Blue when cold, red when hot or bad",
                  "show_when": {"show": ["reading", "temp"]}},
                 {"key": "on", "label": "On", "type": "choices", "default": ["gif"], "options": OVER_KINDS},
             ]}])

FONTS = {"small": "tom-thumb", "large": "5x7"}


def overlays(cfg):
    """The configured overlays, or the single overlay from before there were several."""
    if cfg.get("overlays") is not None:
        return [o for o in cfg["overlays"] if isinstance(o, dict)]
    if cfg.get("overlay", "off") == "off":
        return []
    return [{"show": cfg["overlay"], "corner": cfg.get("overlay_corner", "auto"),
             "mode": cfg.get("overlay_mode", "always"), "color": cfg.get("overlay_color", "#ffffff"),
             "on": cfg.get("overlay_on") or ["gif"], "legacy": True}]


STEP = 0.05           # seconds per transition frame
MAX_HOLD = 0.5        # long GIF frames are re-shown this often so the overlay keeps time
PEEK_EVERY, PEEK_FOR, PEEK_AT = 20.0, 3.0, 2.0
DOT_X0 = -2           # status dots run leftwards from the top-right corner


@plugin.frames
def effects(ctx, frames, info):
    cfg = ctx.settings("effects")
    kind = info.get("kind")
    over = [o for o in overlays(cfg) if kind in (o.get("on") or [])]
    dots = cfg.get("status_dots") and kind not in ("interrupt", "mode")
    if over or dots:
        frames = decorate(ctx, frames, over, dots)
    style = cfg.get("transition", "none")
    if style != "none" and info.get("prev") is not None:
        frames = transition(frames, info["prev"], style, float(cfg.get("transition_seconds") or 0.5),
                            seed=ctx.rng.randrange(1 << 30))
    return frames


# --- transitions ---------------------------------------------------------------

def transition(frames, prev, style, secs, seed=0):
    """Blend from prev into the scene's first frame, then play the scene as it is.
    The blend takes its time out of the first frame's hold where it can."""
    it = iter(frames)
    try:
        first, hold = next(it)
    except StopIteration:
        return
    if prev.size != first.size:
        prev = prev.resize(first.size, Image.NEAREST)
    n = max(1, round(secs / STEP))
    order = np.random.default_rng(seed).permutation(first.width * first.height)
    for k in range(1, n):
        yield blend(prev, first, k / n, style, order), STEP
    yield first, max(STEP, hold - (n - 1) * STEP)
    yield from it


def blend(a, b, p, style, order=None):
    """One in-between frame, p of the way from a to b."""
    w, h = b.size
    if style == "fade":
        return Image.blend(a.convert("RGB"), b.convert("RGB"), p)
    out = a.convert("RGB").copy()
    edge = round(w * p)
    if style == "wipe":
        out.paste(b.crop((0, 0, edge, h)), (0, 0))
    elif style == "slide":           # the new scene pushes the old one out to the left
        out = Image.new("RGB", (w, h))
        out.paste(a.crop((edge, 0, w, h)), (0, 0))
        out.paste(b.crop((0, 0, edge, h)), (w - edge, 0))
    else:                            # dissolve: pixels flip over in a random order
        flat_a = np.asarray(a.convert("RGB")).reshape(-1, 3).copy()
        flat_b = np.asarray(b.convert("RGB")).reshape(-1, 3)
        pick = order[:round(len(order) * p)]
        flat_a[pick] = flat_b[pick]
        out = Image.fromarray(flat_a.reshape(h, w, 3), "RGB")
    return out


# --- overlay and status dots ----------------------------------------------------

def decorate(ctx, frames, over, dots):
    """Draw the overlays and dots on a copy of every frame, splitting long holds so the
    clock, the peek window and blinking dots keep time."""
    fixed = {o.get("corner") for o in over if o.get("corner", "auto") != "auto"}
    avoid = fixed | ({"top_right"} if dots else set())
    corners = [Corner(o.get("corner", "auto"), avoid) for o in over]
    elapsed = 0.0
    for img, hold in frames:
        for c in corners:
            c.see(img, elapsed)
        left = hold
        while True:
            part = min(left, MAX_HOLD)
            out = img.copy() if img.mode == "RGB" else img.convert("RGB")
            placed = []   # rectangles already drawn this frame; fixed corners go first
            for o, corner in sorted(zip(over, corners), key=lambda oc: oc[1].choice == "auto"):
                if o.get("mode") == "peek" and (elapsed - PEEK_AT) % PEEK_EVERY >= PEEK_FOR:
                    continue
                shown = overlay_value(ctx, o, elapsed)
                if shown:
                    text, color = shown
                    font = FONTS.get(o.get("size"), "tom-thumb")
                    size = label_size(text, font)
                    spot = corner.pick(out, size, placed)
                    if spot:      # no free corner it fits in: skip it rather than overlap
                        placed.append(rect(out, size, spot))
                        draw_label(out, text, spot, color, font, o.get("style", "outline"))
            if dots:
                draw_dots(out, ctx.data("status"), elapsed)
            yield out, part
            elapsed += part
            left -= part
            if left <= 1e-6:
                break


def overlay_value(ctx, o, t):
    """(text, color) for one overlay, or None when it has nothing to show right now."""
    what = o.get("show", "time")
    color = gfx.hex_color(o.get("color"), (255, 255, 255))
    if what == "reading":
        item = find_reading(ctx.data("tiles"), o.get("reading", "temp"), o.get("label"))
        if not item:
            return None
        from .tiles import read   # the tiles plugin knows how a reading feels
        feel = read(item, ctx.settings("tiles")) or {}
        if o.get("color_by_value", True) and feel.get("color"):
            color = feel["color"]
        return reading_text(item, feel), color
    if what == "temp" and o.get("color_by_value", True) and not o.get("legacy"):
        wx = ctx.data("weather")
        if wx and wx.get("temp") is not None:
            f = float(wx["temp"]) * 9 / 5 + 32 if str(wx.get("unit", "F")).upper().startswith("C") else float(wx["temp"])
            from ..kit import temp_color
            color = temp_color(f)
    if what == "text":
        text = str(o.get("text") or "").upper()[:8]
        return (text, color) if text else None
    text = overlay_text(ctx, what, t)
    if text is None:
        return None
    return text, color


def find_reading(tiles, kind, label=None):
    """The first tile reading of that kind (and label, if given)."""
    want = str(label or "").strip().upper()
    for item in (tiles or {}).get("items") or []:
        if isinstance(item, dict) and item.get("kind") == kind and item.get("value") is not None:
            if not want or str(item.get("label") or "").upper() == want:
                return item
    return None


def reading_text(item, feel):
    v = float(item["value"])
    kind = item["kind"]
    if kind == "temp":
        return f"{v:.0f}{feel.get('unit') or 'F'}"
    if kind == "aqi":
        return f"AQI{v:.0f}"
    if kind == "co2":
        return f"{v:.0f}"    # colored by how stuffy it is; "PPM" won't fit beside another label
    return f"{v:.0f}%"


def overlay_text(ctx, what, t):
    now = ctx.now()
    from .clock import hour_text   # 12 or 24 hours, as the clock plugin is set
    clock = f"{hour_text(now, ctx.settings('clock'))}:{now.minute:02d}"
    if what == "time":
        return clock
    if what == "date":
        return date_text(now)
    if what == "time_date":
        return clock if t % 10 < 5 else date_text(now)
    if what == "temp":
        wx = ctx.data("weather")
        if wx and wx.get("temp") is not None:
            return f"{round(float(wx['temp']))}{wx.get('unit', 'F')}"
        return clock
    if what == "meeting":
        mins = minutes_to(ctx.data("next_event"), now)
        return f"IN {mins}M" if mins is not None and 0 <= mins < 120 else clock
    return None


def date_text(now):
    return now.strftime("%b %d").upper().replace(" 0", " ")


def minutes_to(ev, now):
    if not ev or not ev.get("start"):
        return None
    try:
        start = datetime.fromisoformat(str(ev["start"]))
    except ValueError:
        return None
    if start.tzinfo:
        start = start.astimezone().replace(tzinfo=None)
    return int((start - now).total_seconds() // 60)


@lru_cache(maxsize=64)
def _glyphs(text, font="tom-thumb"):
    """(mask of the text, mask of its 1px outline), as L images of the label's size."""
    w = gfx.text_width(text, font)
    mask = Image.new("L", (w + 2, gfx.FONT_METRICS[font][0] + 1))
    gfx.text(mask, (1, 1), text, 255, font)
    return mask, mask.filter(ImageFilter.MaxFilter(3))


def label_size(text, font="tom-thumb"):
    return _glyphs(text, font)[0].size


def corner_xy(img, size, corner):
    w, h = size
    x = 0 if corner.endswith("left") else img.width - w
    y = 0 if corner.startswith("top") else img.height - h
    return x, y


def draw_label(img, text, corner, color, font="tom-thumb", style="outline"):
    """Text that reads over anything: outlined in black, on a dark box, or plain."""
    mask, outline = _glyphs(text, font)
    xy = corner_xy(img, mask.size, corner)
    if style == "box":
        box = img.crop((*xy, xy[0] + mask.width, xy[1] + mask.height))
        img.paste(Image.blend(box, Image.new("RGB", box.size), 0.75), xy)
    elif style != "plain":
        img.paste((0, 0, 0), xy, outline)
    img.paste(color, xy, mask)


class Corner:
    """Where an overlay goes. A fixed corner, or auto: the free corner that has been
    darkest and calmest so far, picked on the first frame and only changed (at most
    every 10 s) when another is clearly better, so the label doesn't hop about."""

    def __init__(self, choice, avoid=()):
        self.choice = choice
        self.scores = {c: 0.0 for c in CORNERS[1:] if c not in avoid} or {c: 0.0 for c in CORNERS[1:]}
        self.current, self.decided_at, self.t = None, 0.0, 0.0

    def see(self, img, t):
        self.t = t
        if self.choice != "auto":
            return
        arr = np.asarray(img.convert("L"), dtype=float)
        h, w = arr.shape
        for c in self.scores:
            ys = slice(0, 8) if c.startswith("top") else slice(h - 8, h)
            xs = slice(0, 18) if c.endswith("left") else slice(w - 18, w)
            patch = arr[ys, xs]
            self.scores[c] += patch.mean() + patch.std()

    def pick(self, img, size=(18, 7), placed=()):
        """The corner to draw a label of this size in, clear of the rectangles already
        placed; None when no corner has room."""
        if self.choice != "auto":
            return self.choice
        fits = lambda c: not any(overlaps(rect(img, size, c), r) for r in placed)  # noqa: E731
        free = [c for c in self.scores if fits(c)] or [c for c in CORNERS[1:] if fits(c)]
        if not free:
            return None
        best = min(free, key=lambda c: (self.scores.get(c, 1e9), CORNERS.index(c)))
        if self.current not in free:
            self.current, self.decided_at = best, self.t
        elif self.t - self.decided_at >= 10 and self.scores.get(best, 1e9) < 0.75 * self.scores.get(self.current, 1e9):
            self.current, self.decided_at = best, self.t
        return self.current


def rect(img, size, corner):
    x, y = corner_xy(img, size, corner)
    return x, y, x + size[0], y + size[1]


def overlaps(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def draw_dots(img, status, t):
    """Up to four 1-pixel lights from the top-right corner leftwards, 2px apart."""
    if not isinstance(status, dict):
        return
    dots = status.get("dots")
    for k, dot in enumerate(dots[:4] if isinstance(dots, list) else []):
        if not isinstance(dot, dict):
            continue
        if dot.get("blink") and t % 1 >= 0.5:
            continue
        x = img.width - 1 + DOT_X0 * k
        img.putpixel((x, 0), gfx.hex_color(dot.get("color"), (255, 255, 255)))
        for px, py in ((x - 1, 0), (x, 1), (x - 1, 1)):   # a dark rim so it shows on bright scenes
            img.putpixel((px, py), (0, 0, 0))

