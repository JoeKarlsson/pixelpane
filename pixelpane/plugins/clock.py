"""Clock: time, date and outside temperature, on one of several animated faces."""
import math
from functools import lru_cache

from PIL import Image, ImageDraw

from .. import gfx
from ..gfx import H, W
from ..kit import palette, ticks, time_color
from ..plugin import Plugin

FACES = ["classic", "frame", "arcade", "sky"]

plugin = Plugin(
    "clock", "Time, date and temperature",
    defaults={"faces": list(FACES), "color_mode": "day", "color": "#ffffff"},
    about="Big digits with a blinking colon, the date and the outside temperature (from the "
          "weather plugin), on a face picked from the ones you tick below each time the clock "
          "comes up. Classic has a seconds bar; frame sends a comet around a glowing border "
          "once a minute; arcade has a little hero running, hopping slimes and grabbing coins; "
          "sky paints the real sky behind it, with the sun or moon crossing it. The color "
          "follows the day: warm in the morning, white by day, amber in the evening and dim "
          "red at night, or one color you pick (dimmed at night). At night (10 pm to 6 am) frame "
          "and arcade switch to classic so the board never lights up a dark room.",
    fields=[{"key": "faces", "label": "Faces to pick from", "type": "choices", "options": FACES},
            {"key": "color_mode", "label": "Digit color", "type": "select",
             "options": [{"label": "Follows the time of day", "value": "day"},
                         {"label": "The color below", "value": "fixed"}]},
            {"key": "color", "label": "Color", "type": "color",
             "help": "Used when Digit color is set to it. Dimmed at night."}])


def is_night(now):
    return now.hour >= 22 or now.hour < 6


def face_color(ctx, now):
    """The digits' color: the time of day's, or the one picked in settings (dimmed at night)."""
    cfg = ctx.settings("clock")
    if cfg.get("color_mode") != "fixed":
        return time_color(now)
    col = gfx.hex_color(cfg.get("color"))
    return gfx.scale(col, 0.4) if is_night(now) else col


def draw_time(img, now, col, y, t, shadow=None):
    """HH:MM in the big font, centered, with a colon that blinks once a second."""
    hh, mm, f = str(now.hour % 12 or 12), f"{now.minute:02d}", "6x10"
    w = gfx.text_width(hh, f) + 3 + gfx.text_width(mm, f)
    x = (W - w) // 2
    parts = [(x, hh), (x + gfx.text_width(hh, f) + 3, mm)]
    colon = t % 1 < 0.5
    cx = x + gfx.text_width(hh, f) + 1
    for c, dx in ((shadow, 1), (col, 0)) if shadow else ((col, 0),):
        for px, s in parts:
            gfx.text(img, (px + dx, y + dx), s, c, f)
        if colon:
            img.putpixel((cx + dx, y + 3 + dx), c)
            img.putpixel((cx + dx, y + 7 + dx), c)


def date_text(now):
    return now.strftime("%a %d").upper().replace(" 0", " ")


def temp_text(ctx):
    wx = ctx.data("weather")
    if wx and wx.get("temp") is not None:
        return f"{round(float(wx['temp']))}{wx.get('unit', 'F')}"
    return None


@plugin.scene("clock")
def clock(ctx, secs, face=None):
    faces = [f for f in ctx.settings("clock").get("faces") or [] if f in FACES] or ["classic"]
    face = face if face in FACES else ctx.rng.choice(faces)
    if face in ("frame", "arcade") and is_night(ctx.now()):
        face = "classic"
    yield from DRAW[face](ctx, secs)


def classic(ctx, secs):
    for i, t in ticks(secs, 4):
        now = ctx.now()
        img = gfx.blank()
        col = face_color(ctx, now)
        draw_time(img, now, col, 2, t)
        gfx.text_center(img, 15, date_text(now), gfx.scale(col, 0.7), "4x6")
        temp = temp_text(ctx)
        if temp:
            gfx.text_center(img, 23, temp, gfx.scale(col, 0.55), "tom-thumb")
        bar = int((now.second + (i % 4) / 4) / 60 * W)
        ImageDraw.Draw(img).line((0, 31, bar, 31), fill=gfx.scale(col, 0.35))
        yield img, 0.25


# --- frame: a glowing border with a comet that laps it once a minute ---------

def _perimeter():
    """Every border pixel, clockwise from the top middle (12 o'clock)."""
    edge = ([(x, 0) for x in range(W)] + [(W - 1, y) for y in range(1, H)]
            + [(x, H - 1) for x in range(W - 2, -1, -1)] + [(0, y) for y in range(H - 2, 0, -1)])
    k = edge.index((W // 2, 0))
    return edge[k:] + edge[:k]


PERIMETER = _perimeter()


def frame(ctx, secs):
    n = len(PERIMETER)
    for i, t in ticks(secs, 12):
        now = ctx.now()
        img = gfx.blank()
        px = img.load()
        col = face_color(ctx, now)
        for k, xy in enumerate(PERIMETER):  # a rainbow that slowly turns around the edge
            px[xy] = gfx.hsv(k / n - t / 20, 0.85, 0.45)
        head = (now.second + now.microsecond / 1e6) / 60 * n
        for k in range(10):  # the comet: a bright head and a fading tail
            xy = PERIMETER[int(head - k) % n]
            px[xy] = gfx.scale(gfx.hsv(head / n - t / 20, 0.5 if k else 0.1, 1), 1 - k / 10)
        draw_time(img, now, col, 4, t)
        gfx.text_center(img, 17, date_text(now), gfx.scale(col, 0.7), "4x6")
        temp = temp_text(ctx)
        if temp:
            gfx.text_center(img, 24, temp, gfx.scale(col, 0.5), "tom-thumb")
        yield img, 1 / 12


# --- arcade: a tiny hero runs along under the time and hops the slimes -------

HERO_RUN = [[
    "..CCCC..",
    ".CCCCCC.",
    "..SKSK..",
    "..SSSS..",
    ".VVVVVV.",
    "S.VVVV.S",
    "..V..V..",
    ".nn...n.",
], [
    "..CCCC..",
    ".CCCCCC.",
    "..SKSK..",
    "..SSSS..",
    ".VVVVVV.",
    ".SVVVVS.",
    "...VV...",
    "..nn.n..",
]]
HERO_JUMP = [
    "..CCCC..",
    ".CCCCCC.",
    "S.SKSK.S",
    ".SSSSSS.",
    "..VVVV..",
    "..VVVV..",
    ".V....V.",
    "n......n",
]
SLIME = [[
    "..LLLL..",
    ".LKLLKL.",
    "LLLLLLLL",
    "GGGGGGGG",
], [
    "........",
    "..LLLL..",
    ".LKLLKL.",
    "GGGGGGGG",
]]
COIN = [["..YY..", ".YWYY.", ".YYYy.", "..yy.."], ["..YY..", "..WY..", "..Yy..", "..yy.."],
        ["...Y..", "...Y..", "...y..", "...y.."], ["..YY..", "..YW..", "..yY..", "..yy.."]]


@lru_cache(maxsize=None)
def pix(rows):
    """A sprite from rows of gfx.PALETTE letters, '.' being see-through."""
    img = Image.new("RGBA", (len(rows[0]), len(rows)), (0, 0, 0, 0))
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch in gfx.PALETTE:
                img.putpixel((x, y), gfx.PALETTE[ch] + (255,))
    return img


def put(img, rows, x, y):
    s = pix(tuple(rows))
    img.paste(s, (int(x), int(y)), s)


GROUND = 28    # top row of the grass
HERO_X = 5
SPEED = 14     # world scroll, pixels a second
JUMP = 1.2     # seconds in the air, long enough to clear a slime


def arcade(ctx, secs):
    rng = ctx.rng
    slimes = [W + 6.0, W + 26.0]
    jump_at = -9.0
    coins = [[W + 14.0, GROUND - 14]]
    clouds = [[rng.uniform(0, W), rng.choice((13, 16))] for _ in range(2)]
    for i, t in ticks(secs, 12):
        now = ctx.now()
        img = gfx.blank()
        d = ImageDraw.Draw(img)
        col = face_color(ctx, now)
        dx = SPEED / 12
        for c in clouds:  # far clouds drift at a quarter of the speed
            c[0] -= dx / 4
            if c[0] < -6:
                c[0], c[1] = W + rng.uniform(0, 10), rng.choice((13, 16))
            d.line((c[0] + 1, c[1], c[0] + 3, c[1]), fill=(50, 56, 86))
            d.line((c[0], c[1] + 1, c[0] + 5, c[1] + 1), fill=(50, 56, 86))
        scroll = int(t * SPEED)
        for x in range(W):  # grass, then a dirt checker that scrolls with the world
            img.putpixel((x, GROUND), (40, 170, 60) if (x + scroll) % 6 else (90, 220, 90))
            for y in range(GROUND + 1, H):
                img.putpixel((x, y), (95, 55, 20) if ((x + scroll) // 3 + y // 2) % 2 else (70, 40, 14))
        for k, s in enumerate(slimes):
            slimes[k] = s - dx
            if slimes[k] < -8:
                slimes[k] = max(slimes) + rng.uniform(16, 30)
            if HERO_X + 7 < slimes[k] < HERO_X + 10 and t - jump_at > JUMP:
                jump_at = t  # hop as a slime comes close
            put(img, SLIME[int(t * 4 + k) % 2], slimes[k], GROUND - 4)
        air = t - jump_at
        hy = GROUND - 8
        if air < JUMP:
            hy -= round(math.sin(math.pi * air / JUMP) * 8)
        for c in coins[:]:  # coins float at jump height; the hero grabs them on the way up
            c[0] -= dx
            if c[0] < -6:
                c[0] = W + rng.uniform(4, 20)
            if abs(c[0] + 3 - (HERO_X + 4)) < 4 and hy < c[1] + 4:
                c[0] = W + rng.uniform(4, 20)
                continue
            put(img, COIN[int(t * 8) % 4], c[0], c[1])
        put(img, HERO_JUMP if air < JUMP else HERO_RUN[int(t * 8) % 2], HERO_X, hy)
        draw_time(img, now, col, 1, t, shadow=gfx.scale(col, 0.25))
        yield img, 1 / 12


# --- sky: the real sky for the hour, the sun or moon crossing it -------------

# (hour, top color, horizon color), dim on purpose: a lit sky washes out the digits
SKY = [(0, (2, 2, 10), (8, 8, 26)), (5.5, (2, 2, 10), (8, 8, 26)), (6.5, (24, 14, 50), (130, 60, 40)),
       (8, (10, 40, 90), (50, 100, 140)), (17, (10, 40, 90), (50, 100, 140)),
       (18.5, (30, 14, 50), (150, 60, 25)), (19.7, (2, 2, 10), (8, 8, 26)), (24, (2, 2, 10), (8, 8, 26))]


def sky_colors(h):
    for (h0, t0, b0), (h1, t1, b1) in zip(SKY, SKY[1:]):
        if h0 <= h <= h1:
            f = (h - h0) / (h1 - h0)
            return (tuple(int(a + (b - a) * f) for a, b in zip(t0, t1)),
                    tuple(int(a + (b - a) * f) for a, b in zip(b0, b1)))
    return SKY[0][1], SKY[0][2]


def hills(x):
    return int(27 + 2 * math.sin(x / 5) + math.sin(x / 2.3 + 1))


def sky(ctx, secs):
    rng = ctx.rng
    stars = [(rng.randrange(W), rng.randrange(22), rng.uniform(0, 6.28)) for _ in range(18)]
    for i, t in ticks(secs, 6):
        now = ctx.now()
        h = now.hour + now.minute / 60
        top, bottom = sky_colors(h)
        grad = palette([top, bottom], H)
        img = Image.fromarray(grad[:, None, :].repeat(W, 1), "RGB")
        px = img.load()
        dark = 1 - min(1, sum(top) / 120)
        for x, y, ph in stars:  # stars come out as it gets dark, and twinkle
            v = dark * (0.35 + 0.35 * math.sin(t * 2.5 + ph))
            if v > 0.05:
                px[x, y] = gfx.scale((255, 240, 210), v)
        day = 6 <= h < 18
        f = ((h - 6) if day else (h - 18) % 24) / 12  # 0 at rise, 1 at set
        bx, by = 2 + f * 27, 26 - math.sin(math.pi * f) * 6  # stays under the date
        if day:
            ImageDraw.Draw(img).ellipse((bx - 2, by - 2, bx + 2, by + 2), fill=(255, 200, 60))
            for k in range(8):  # rays pulse
                a = k * math.pi / 4 + t / 3
                r = 3.6 + 0.6 * math.sin(t * 3)
                x, y = int(round(bx + r * math.cos(a))), int(round(by + r * math.sin(a)))
                if 0 <= x < W and 0 <= y < H:
                    px[x, y] = (200, 130, 30)
        else:
            ImageDraw.Draw(img).ellipse((bx - 2, by - 2, bx + 2, by + 2), fill=(110, 108, 90))
            behind = tuple(int(c) for c in grad[max(0, min(H - 1, int(by)))])
            ImageDraw.Draw(img).ellipse((bx - 1, by - 3, bx + 3, by + 1), fill=behind)  # a crescent
        ground = (6, 26, 12) if day else (3, 8, 5)
        for x in range(W):
            for y in range(hills(x + t * 0.5), H):
                px[x, y] = ground
        col = face_color(ctx, now)
        draw_time(img, now, col, 2, t, shadow=(0, 0, 0))
        gfx.text_center(img, 13, date_text(now), gfx.scale(col, 0.75), "4x6")
        yield img, 1 / 6


DRAW = {"classic": classic, "frame": frame, "arcade": arcade, "sky": sky}
