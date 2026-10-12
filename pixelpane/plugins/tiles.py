"""Tiles: generic info cards with animated icons and gauges."""


from .. import gfx
from ..kit import animated_icon, gauge, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

plugin = Plugin(
    "tiles", "Info cards (temperature, AQI, anything)", data={"tiles": 240},
    about="Small cards pushed from anywhere: an animated icon, a line of text and an "
          "optional gauge. Good for room temperature, air quality, laundry, weather "
          "warnings. POST /api/data/tiles with {items: [{icon, text, color, level}]}.")


@plugin.scene("tiles", empty_text="NO TILES YET")
def tiles(ctx, secs):
    """Generic info cards pushed from Home Assistant: [{icon, text, color}]."""
    data = ctx.data("tiles")
    items = (data or {}).get("items") or []
    if not items:
        return
    each = max(4.0, secs / len(items))
    for item in items:
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
