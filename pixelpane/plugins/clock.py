"""Clock: time, date and outside temperature, colored by time of day."""

from PIL import ImageDraw

from .. import gfx
from ..gfx import W
from ..kit import ticks, time_color
from ..plugin import Plugin

plugin = Plugin(
    "clock", "Time, date and temperature",
    about="Big digits with a blinking colon, the date, the outside temperature (from the "
          "weather plugin) and a seconds bar along the bottom. The color follows the "
          "day: warm in the morning, white by day, amber in the evening and dim red at "
          "night so it never lights up a dark room.")


@plugin.scene("clock")
def clock(ctx, secs):
    for i, t in ticks(secs, 4):
        now = ctx.now()
        img = gfx.blank()
        col = time_color(now)
        hh = str(now.hour % 12 or 12)
        mm = f"{now.minute:02d}"
        f = "6x10"
        w = gfx.text_width(hh, f) + 3 + gfx.text_width(mm, f)
        x = (W - w) // 2
        gfx.text(img, (x, 2), hh, col, f)
        x += gfx.text_width(hh, f)
        if i % 4 < 2:  # colon blinks once a second (frames are 0.25 s apart)
            img.putpixel((x + 1, 5), col)
            img.putpixel((x + 1, 9), col)
        gfx.text(img, (x + 3, 2), mm, col, f)
        date_s = now.strftime("%a %d").upper().replace(" 0", " ")
        gfx.text_center(img, 15, date_s, gfx.scale(col, 0.7), "4x6")
        wx = ctx.data("weather")
        if wx and wx.get("temp") is not None:
            gfx.text_center(img, 23, f"{round(float(wx['temp']))}{wx.get('unit', 'F')}",
                            gfx.scale(col, 0.55), "tom-thumb")
        bar = int((now.second + (i % 4) / 4) / 60 * W)
        ImageDraw.Draw(img).line((0, 31, bar, 31), fill=gfx.scale(col, 0.35))
        yield img, 0.25
