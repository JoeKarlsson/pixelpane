"""Alerts: notifications that jump the queue, ON AIR and message modes."""
import math

from PIL import Image, ImageDraw

from .. import gfx
from ..gfx import H, W
from ..kit import animated_icon, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

STYLES = ["classic", "banner", "burst", "ticker"]

plugin = Plugin(
    "alerts", "Notifications, ON AIR and messages",
    defaults={"style": "classic", "seconds": 10, "color": "#ffffff", "flash": False, "pulse": False},
    about="Things that need your attention right now. A notification (POST /api/notify) "
          "jumps the queue, plays to the end with an animated icon, then the playlist "
          "resumes. ON AIR and messages are modes: they stay up until cleared or until "
          "their minutes run out. Home Assistant uses these for the doorbell, laundry, "
          "meetings and weather warnings. The settings below are what a notification looks "
          "like when it doesn't say; one can pick its own style, color and seconds.",
    fields=[{"key": "style", "label": "Style", "type": "select",
             "options": [{"label": "Classic: icon and scrolling text", "value": "classic"},
                         {"label": "Banner: a bar slides down from the top", "value": "banner"},
                         {"label": "Burst: the icon pops in with ripples", "value": "burst"},
                         {"label": "Ticker: big text crawls across", "value": "ticker"}]},
            {"key": "seconds", "label": "Seconds on screen", "type": "number", "min": 3, "max": 120, "step": 1,
             "help": "At least long enough for the text to scroll past twice."},
            {"key": "color", "label": "Color", "type": "color"},
            {"key": "flash", "label": "Flash", "type": "toggle", "text": "Flash the edge for the first few seconds"},
            {"key": "pulse", "label": "Border", "type": "toggle", "text": "Pulse a border the whole time"}])


def _ink(col):
    """Black or white, whichever reads on col."""
    return (0, 0, 0) if 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2] > 140 else (255, 255, 255)


def _clip_scroll(img, box, s, color, font, t, speed):
    """Text scrolling inside box (x0, y, x1) only, so it slides under an icon or edge."""
    x0, y, x1 = box
    w, width = gfx.text_width(s, font), x1 - x0
    x = x0 + (width - w) // 2 if w <= width else x1 - int(t * speed) % (w + width)
    mask = Image.new("L", (W, H))
    ImageDraw.Draw(mask).text((x, y), gfx.plain(s), font=gfx.font(font), fill=255)
    mask.paste(0, (0, 0, x0, H))
    mask.paste(0, (x1, 0, W, H))
    img.paste(color, (0, 0, W, H), mask)


def big_icon(img, name, center, t, scale=2.0):
    """An animated 8x8 icon drawn larger (nearest neighbour, so it stays pixel art)."""
    layer = gfx.blank()
    animated_icon(layer, name, (12, 12), t)
    part = layer.crop((10, 10, 22, 22))
    size = max(1, int(round(12 * scale)))
    part = part.resize((size, size), Image.NEAREST)
    mask = part.convert("L").point(lambda v: 255 if v else 0)
    img.paste(part, (center[0] - size // 2, center[1] - size // 2), mask)


def _classic(img, d, i, t, msg, icon, col, sub):
    animated_icon(img, icon, (12, 3), t)
    scroll_text(img, 14, msg, col, "5x7", t, 16)
    if sub:
        scroll_text(img, 24, str(sub).upper(), (150, 150, 170), "tom-thumb", t, 14)


def _banner(img, d, i, t, msg, icon, col, sub):
    drop = min(1.0, t / 0.35)
    top = int(-12 + 12 * (1 - (1 - drop) ** 3))          # eases down from above the panel
    d.rectangle((0, top, W - 1, top + 11), fill=col)
    d.line((0, top + 12, W - 1, top + 12), fill=gfx.scale(col, 0.4))
    ink = _ink(col)
    if drop >= 1:
        _clip_scroll(img, (11, top + 3, W - 1), msg, ink, "5x7", t - 0.35, 16)
    d.rectangle((0, top, 10, top + 11), fill=gfx.scale(col, 0.3))   # a dark tab for the icon
    layer = gfx.blank()                                    # the icon rides in with the bar
    animated_icon(layer, icon, (1, 2), t)
    mask = layer.convert("L").point(lambda v: 255 if v else 0)
    img.paste(layer, (0, top), mask)
    # below the bar: the icon again, big and gently bobbing, in a soft glow
    glow_r = 9 + math.sin(t * 3)
    for y in range(14, H):
        for x in range(W):
            dist = math.hypot(x - 15.5, y - 23)
            if dist < glow_r:
                img.putpixel((x, y), gfx.scale(col, 0.18 * (1 - dist / glow_r)))
    if sub:
        _clip_scroll(img, (0, 26, W), str(sub).upper(), (170, 170, 190), "tom-thumb", t, 14)
    else:
        big_icon(img, icon, (16, 23 + round(math.sin(t * 2.5))), t, 1.5 if drop >= 1 else 1.5 * drop)


def _burst(img, d, i, t, msg, icon, col, sub):
    c = (16, 11)
    for k in range(3):                                     # rings ripple out, again and again
        age = (t - k * 0.45) % 1.5
        if t >= k * 0.45:
            r = 3 + age * 14
            d.ellipse((c[0] - r, c[1] - r, c[0] + r, c[1] + r), outline=gfx.scale(col, max(0.0, 1 - age / 1.5) * 0.8))
    pop = min(1.0, t / 0.4)
    scale = 2.0 * (pop + 0.35 * math.sin(pop * math.pi))   # overshoots, then settles
    big_icon(img, icon, c, t, max(0.2, scale))
    if t > 0.6:
        scroll_text(img, 24, msg, col, "5x7", t - 0.6, 16)


def _ticker(img, d, i, t, msg, icon, col, sub):
    # big text: the 6x10 font drawn twice as tall, crawling right to left
    w = gfx.text_width(msg, "6x10")
    layer = Image.new("RGB", (w + 2, 10))
    gfx.text(layer, (0, 0), msg, col, "6x10")
    tall = layer.resize((w + 2, 20), Image.NEAREST)
    x = W - int(t * 20) % (w + W)
    mask = tall.convert("L").point(lambda v: 255 if v else 0)
    img.paste(tall, (x, 6), mask)
    for k in range(0, W, 4):                                # marching lights above and below
        on = (k // 4 + int(t * 8)) % 2
        dim = col if on else gfx.scale(col, 0.25)
        img.putpixel(((k + int(t * 8)) % W, 1), dim)
        img.putpixel(((k - int(t * 8)) % W, H - 2), dim)


DRAW = {"classic": _classic, "banner": _banner, "burst": _burst, "ticker": _ticker}


def _seconds_for(style, msg):
    if style == "ticker":
        return 2 * (gfx.text_width(msg, "6x10") + W) / 20 + 1
    return scroll_seconds(msg, "5x7", 16, passes=2) + (1.5 if style in ("banner", "burst") else 1)


@plugin.scene("notify", "interrupt")
def notify(ctx, secs, text="", icon="bell", color=None, flash=None, sub="", style=None):
    """A notification. Anything not given (color, flash, style) comes from the alerts settings."""
    cfg = ctx.settings("alerts")
    style = style if style in STYLES else cfg.get("style") if cfg.get("style") in STYLES else "classic"
    col = gfx.hex_color(color or cfg.get("color") or "#ffffff")
    flash = cfg.get("flash") if flash is None else flash
    msg = str(text).upper()
    secs = max(secs, _seconds_for(style, msg))
    for i, t in ticks(secs, 10):
        img = gfx.blank()
        d = ImageDraw.Draw(img)
        DRAW[style](img, d, i, t, msg, icon, col, sub)
        if cfg.get("pulse"):
            d.rectangle((0, 0, W - 1, H - 1), outline=gfx.scale(col, 0.35 + 0.35 * math.sin(t * 4)))
        if flash and t < 3 and i % 4 < 2:
            d.rectangle((0, 0, W - 1, H - 1), outline=col)
        yield img, 0.1


@plugin.scene("on_air", "mode", params={"text": "text"})
def on_air(ctx, secs, text="ON AIR"):
    words = str(text).upper().split(maxsplit=1) + [""]
    for i, t in ticks(secs, 10):
        img = gfx.blank()
        pulse = 0.6 + 0.4 * math.sin(t * 3)
        ImageDraw.Draw(img).rounded_rectangle((0, 2, W - 1, H - 3), radius=4,
                                              outline=gfx.scale((255, 30, 30), pulse), width=2)
        gfx.text_center(img, 6, words[0], (255, 255, 255), "6x10")
        gfx.text_center(img, 17, words[1], gfx.scale((255, 40, 40), 0.7 + 0.3 * pulse), "6x10")
        yield img, 0.1


@plugin.scene("message", "mode", params={"text": "text", "color": "color"})
def message(ctx, secs, text="HELLO", color="#ffcc00"):
    msg = str(text).upper()
    col = gfx.hex_color(color)
    for i, t in ticks(secs, 10):
        img = gfx.blank()
        scroll_text(img, 12, msg, col, "5x7", t, 16)
        yield img, 0.1
