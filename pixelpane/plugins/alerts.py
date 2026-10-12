"""Alerts: notifications that jump the queue, ON AIR and message modes."""
import math

from PIL import ImageDraw

from .. import gfx
from ..gfx import H, W
from ..kit import animated_icon, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

plugin = Plugin(
    "alerts", "Notifications, ON AIR and messages",
    about="Things that need your attention right now. A notification (POST /api/notify) "
          "jumps the queue, plays to the end with an animated icon, then the playlist "
          "resumes. ON AIR and messages are modes: they stay up until cleared or until "
          "their minutes run out. Home Assistant uses these for the doorbell, laundry, "
          "meetings and weather warnings.")


@plugin.scene("notify", "interrupt")
def notify(ctx, secs, text="", icon="bell", color="#ffffff", flash=False, sub=""):
    msg = str(text).upper()
    col = gfx.hex_color(color)
    secs = max(secs, scroll_seconds(msg, "5x7", 16, passes=2) + 1)
    for i, t in ticks(secs, 10):
        img = gfx.blank()
        if flash and t < 3 and i % 4 < 2:
            ImageDraw.Draw(img).rectangle((0, 0, W - 1, H - 1), outline=col)
        animated_icon(img, icon, (12, 3), t)
        scroll_text(img, 14, msg, col, "5x7", t, 16)
        if sub:
            scroll_text(img, 24, str(sub).upper(), (150, 150, 170), "tom-thumb", t, 14)
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
