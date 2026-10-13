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

plugin = Plugin(
    "effects", "Transitions, a clock over GIFs, status dots",
    data={"status": 120},
    defaults={"transition": "fade", "transition_seconds": 0.5,
              "overlay": "off", "overlay_corner": "auto", "overlay_mode": "always",
              "overlay_on": ["gif"], "overlay_color": "#ffffff", "status_dots": True},
    about="Polish that works on every scene. Transitions blend one scene into the next "
          "instead of cutting. The overlay puts the time, date, outside temperature or "
          "minutes to your next meeting in a corner of GIFs (and, if you like, generative "
          "and seasonal scenes), outlined so it stays readable; auto finds the calmest "
          "corner. Status dots are tiny lights along the top edge that stay on while "
          "something is true (laundry done, a door open): POST /api/data/status with "
          "{dots: [{color, blink}]}, and an empty list to clear them.",
    fields=[{"key": "transition", "label": "Transition", "type": "select",
             "options": [{"label": t.capitalize(), "value": t} for t in TRANSITIONS]},
            {"key": "transition_seconds", "label": "Transition length (seconds)", "type": "range",
             "min": 0.2, "max": 1.5, "step": 0.1},
            {"key": "overlay", "label": "Overlay", "type": "select",
             "options": [{"label": "Off", "value": "off"}, {"label": "Time", "value": "time"},
                         {"label": "Date", "value": "date"},
                         {"label": "Time and date, taking turns", "value": "time_date"},
                         {"label": "Outside temperature", "value": "temp"},
                         {"label": "Minutes to the next meeting", "value": "meeting"}],
             "help": "Temperature and meeting show the time when there is nothing to show."},
            {"key": "overlay_corner", "label": "Overlay corner", "type": "select",
             "options": [{"label": c.replace("_", " ").capitalize(), "value": c} for c in CORNERS],
             "help": "Auto picks the darkest, calmest corner of each scene."},
            {"key": "overlay_mode", "label": "Overlay shows", "type": "select",
             "options": [{"label": "All the time", "value": "always"},
                         {"label": "For 3 seconds every 20", "value": "peek"}]},
            {"key": "overlay_on", "label": "Overlay on", "type": "choices", "options": OVER_KINDS},
            {"key": "overlay_color", "label": "Overlay color", "type": "color"},
            {"key": "status_dots", "label": "Status dots", "type": "toggle",
             "text": "Show status dots on every scene"}])

STEP = 0.05           # seconds per transition frame
MAX_HOLD = 0.5        # long GIF frames are re-shown this often so the overlay keeps time
PEEK_EVERY, PEEK_FOR, PEEK_AT = 20.0, 3.0, 2.0
DOT_X0 = -2           # status dots run leftwards from the top-right corner


@plugin.frames
def effects(ctx, frames, info):
    cfg = ctx.settings("effects")
    kind = info.get("kind")
    over = cfg.get("overlay") if kind in (cfg.get("overlay_on") or []) else "off"
    dots = cfg.get("status_dots") and kind not in ("interrupt", "mode")
    if over != "off" or dots:
        frames = decorate(ctx, frames, cfg, over or "off", dots)
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

def decorate(ctx, frames, cfg, over, dots):
    """Draw the overlay and dots on a copy of every frame, splitting long holds so the
    clock, the peek window and blinking dots keep time."""
    color = gfx.hex_color(cfg.get("overlay_color"))
    peek = cfg.get("overlay_mode") == "peek"
    corner = Corner(cfg.get("overlay_corner", "auto"), avoid="top_right" if dots else None)
    elapsed = 0.0
    for img, hold in frames:
        corner.see(img, elapsed)
        left = hold
        while True:
            part = min(left, MAX_HOLD)
            out = img.copy() if img.mode == "RGB" else img.convert("RGB")
            if over != "off" and (not peek or (elapsed - PEEK_AT) % PEEK_EVERY < PEEK_FOR):
                text = overlay_text(ctx, over, elapsed)
                if text:
                    draw_label(out, text, corner.pick(out, text), color)
            if dots:
                draw_dots(out, ctx.data("status"), elapsed)
            yield out, part
            elapsed += part
            left -= part
            if left <= 1e-6:
                break


def overlay_text(ctx, what, t):
    now = ctx.now()
    clock = f"{now.hour % 12 or 12}:{now.minute:02d}"
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
def _glyphs(text):
    """(mask of the text, mask of its 1px outline), as L images of the label's size."""
    w = gfx.text_width(text, "tom-thumb")
    mask = Image.new("L", (w + 2, 7))
    gfx.text(mask, (1, 1), text, 255, "tom-thumb")
    return mask, mask.filter(ImageFilter.MaxFilter(3))


def label_size(text):
    return _glyphs(text)[0].size


def corner_xy(img, size, corner):
    w, h = size
    x = 0 if corner.endswith("left") else img.width - w
    y = 0 if corner.startswith("top") else img.height - h
    return x, y


def draw_label(img, text, corner, color):
    """Text with a black outline, so it reads over anything."""
    mask, outline = _glyphs(text)
    xy = corner_xy(img, mask.size, corner)
    img.paste((0, 0, 0), xy, outline)
    img.paste(color, xy, mask)


class Corner:
    """Where the overlay goes. A fixed corner, or auto: the corner that has been darkest
    and calmest so far, picked on the first frame and only changed (at most every 10 s)
    when another corner is clearly better, so the label doesn't hop about."""

    def __init__(self, choice, avoid=None):
        self.choice, self.avoid = choice, avoid
        self.scores = {c: 0.0 for c in CORNERS[1:] if c != avoid}
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

    def pick(self, img, text):
        if self.choice != "auto":
            return self.choice
        best = min(self.scores, key=lambda c: (self.scores[c], CORNERS.index(c)))
        if self.current is None:
            self.current, self.decided_at = best, self.t
        elif self.t - self.decided_at >= 10 and self.scores[best] < 0.75 * self.scores[self.current]:
            self.current, self.decided_at = best, self.t
        return self.current


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

