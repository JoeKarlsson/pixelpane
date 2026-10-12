"""Sky: tonight's moon (phase, full moon names) and the zodiac. No network needed."""
import math

from .. import astro, gfx
from ..gfx import W
from ..kit import scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

plugin = Plugin(
    "sky", "Moon phase and zodiac",
    about="The moon scene draws tonight's moon with its real shape among twinkling stars, "
          "with the phase, how much is lit and the days to the next full moon. On a full "
          "moon it names it (Wolf, Snow, Worm, Pink, Flower, Strawberry, Buck, Sturgeon, "
          "Corn, Harvest, Hunter's, Beaver, Cold) and calls out a supermoon or a blue moon. "
          "The zodiac scene shows the sun sign's symbol, its dates and element, and the sign "
          "the moon is in. Everything is calculated on the board; the weather plugin's "
          "latitude, when set, flips the moon for the southern hemisphere.")

LIT = (235, 228, 200)
EARTHSHINE = (22, 22, 34)
# darker patches (the maria) as (dx, dy) from the disc center, radius 9
MARIA = {(-3, -4), (-2, -4), (-3, -3), (-4, -2), (-1, -2), (2, -3), (3, -3), (2, -2),
         (-2, 1), (-1, 1), (-2, 2), (1, 3), (2, 3), (4, 0), (4, 1), (-5, 2)}
TINT = {"harvest": (255, 196, 120), "hunter's": (255, 180, 110)}


def phase_shade(frac, x, y, southern=False):
    """How lit (0..1) the point (x, y) of a unit disc is at phase `frac` (0 new, 0.5 full).

    Seen from the north the moon lights up from the right while waxing and darkens
    from the right while waning; the south sees it mirrored."""
    if southern:
        x = -x
    w = math.sqrt(max(0.0, 1 - y * y))
    if w == 0:
        return 0.0
    k = math.cos(2 * math.pi * frac)
    return 1.0 if (x / w > k if frac <= 0.5 else x / w < -k) else 0.0


def draw_moon(img, cx, cy, r, frac, southern=False, color=LIT, glow=0.0):
    px = img.load()
    for y in range(int(cy - r - 2), int(cy + r + 3)):
        for x in range(int(cx - r - 2), int(cx + r + 3)):
            if not (0 <= x < img.width and 0 <= y < img.height):
                continue
            # 3x3 supersampling: soft edges and a soft terminator at 32 pixels
            inside = lit = 0
            for sy in (-1 / 3, 0, 1 / 3):
                for sx in (-1 / 3, 0, 1 / 3):
                    nx, ny = (x + sx - cx) / r, (y + sy - cy) / r
                    if nx * nx + ny * ny <= 1:
                        inside += 1
                        lit += phase_shade(frac, nx, ny, southern)
            if inside:
                a, l = inside / 9, lit / 9
                c = color
                if (round((x - cx) * 9 / r), round((y - cy) * 9 / r)) in MARIA:
                    c = gfx.scale(color, 0.72)
                px[x, y] = tuple(int(EARTHSHINE[i] * (a - l) + c[i] * l) for i in range(3))
            elif glow:
                d = math.hypot(x - cx, y - cy) - r
                if d < 2.5:
                    px[x, y] = gfx.scale(color, glow * (2.5 - d) / 2.5 * 0.35)


def stars(rng, n, avoid):
    out = []
    while len(out) < n:
        x, y = rng.randrange(W), rng.randrange(17)
        if math.hypot(x - avoid[0], y - avoid[1]) > avoid[2] + 2:
            out.append((x, y, rng.random() * 6.28, rng.uniform(1.5, 3.5)))
    return out


def _days(td):
    return td.total_seconds() / 86400


def _southern(ctx):
    lat = ctx.settings("weather").get("latitude")
    return isinstance(lat, (int, float)) and lat < 0


def _page_times(pages):
    return [max(3.0, max(scroll_seconds(s, "tom-thumb", 14) for s in pg) + 0.5) for pg in pages]


def _page(img, y, page, top, bottom, t):
    scroll_text(img, y, page[0], top, "tom-thumb", t, 14)
    scroll_text(img, y + 7, page[1], bottom, "tom-thumb", t, 14)


def _turn(per, t):
    """Which of several lines is showing at time t, and for how long it has shown."""
    k, left = 0, t % sum(per)
    while k < len(per) - 1 and left >= per[k]:
        left -= per[k]
        k += 1
    return k, left


@plugin.scene("moon")
def moon(ctx, secs):
    now = ctx.now().astimezone()
    info = astro.moon_phase(now)
    full = info.get("full")
    cx, cy, r = 15.5, 8.5, 7
    color = LIT
    if full:
        color = (175, 205, 255) if full["blue"] else TINT.get(full["name"], LIT)
        pages = [(full["name"].upper(), "MOON")]
        pages += [("SUPER", "MOON")] * full["super"] + [("BLUE", "MOON")] * full["blue"]
    else:
        first, _, second = info["phase"].upper().partition(" ")
        to_full = _days(info["next_full"] - now)
        pages = [(first, second), (f"{round(info['illumination'] * 100)}%", "LIT"),
                 ("FULL", "TONIGHT" if to_full < 1 else f"IN {math.ceil(to_full)}D")]
    sky = stars(ctx.rng, 9, (cx, cy, r))
    per = _page_times(pages)
    secs = max(secs, min(sum(per), 30))
    southern = _southern(ctx)
    for i, t in ticks(secs, 10):
        img = gfx.blank((0, 0, 6))
        for x, y, ph, sp in sky:
            v = 0.25 + 0.75 * (0.5 + 0.5 * math.sin(t * sp + ph))
            img.putpixel((x, y), gfx.scale((200, 210, 255), v))
        glow = (0.6 + 0.4 * math.sin(t * 2)) if full else 0.0
        draw_moon(img, cx, cy, r, info["fraction"], southern, color, glow)
        k, left = _turn(per, t)
        _page(img, 18, pages[k], gfx.scale(color, 0.95) if full else (190, 200, 230),
              (255, 170, 90) if full else (120, 140, 190), left)
        yield img, 0.1


# 9x9 symbols for the signs
GLYPHS = {
    "aries": [".##...##.", "#..#.#..#", "#..#.#..#", "....#....", "....#....",
              "....#....", "....#....", "....#....", "........."],
    "taurus": ["##.....##", "..#...#..", "...###...", "..#...#..", ".#.....#.",
               ".#.....#.", ".#.....#.", "..#...#..", "...###..."],
    "gemini": ["#########", "..#...#..", "..#...#..", "..#...#..", "..#...#..",
               "..#...#..", "..#...#..", "..#...#..", "#########"],
    "cancer": ["...######", ".##......", "#..#.....", "#..#.....", ".##......",
               "......##.", ".....#..#", ".....#..#", "######..."],
    "leo": ["...###...", "..#...#..", "..#....#.", "..#....#.", ".##....#.",
            "#.#....#.", "#.#....#.", ".#.....#.", ".......##"],
    "virgo": ["##.#..#..", "#.#.#.#..", "#..#..#..", "#..#..#.#", "#..#..#.#",
              "#..#..##.", "#..#..#..", ".....##..", "....#...."],
    "libra": [".........", "...###...", "..#...#..", "..#...#..", "###...###",
              ".........", "#########", ".........", "........."],
    "scorpio": ["##.#..#..", "#.#.#.#..", "#..#..#..", "#..#..#..", "#..#..#..",
                "#..#..#.#", "#..#...##", "#..#..###", "........."],
    "sagittarius": ["....#####", ".......##", "......#.#", ".....#..#", ".#..#....",
                    "..##.....", "..##.....", ".#..#....", "#........"],
    "capricorn": ["#...#....", "#...#....", ".#.#.#...", "..#..#...", ".....#.##",
                  ".....##.#", ".....#.##", "....#.#..", "...#....."],
    "aquarius": [".........", ".#...#...", "#.#.#.#.#", "...#...#.", ".........",
                 ".#...#...", "#.#.#.#.#", "...#...#.", "........."],
    "pisces": ["#.......#", ".#.....#.", "..#...#..", "..#...#..", "#########",
               "..#...#..", "..#...#..", ".#.....#.", "#.......#"],
}
ELEMENT_COLORS = {"fire": (255, 110, 40), "earth": (110, 200, 90), "air": (150, 200, 255),
                  "water": (60, 140, 255)}
MONTHS = "JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split()


def sign_dates(sign):
    i = [s for _, s in astro.SIGN_STARTS].index(sign)
    (m1, d1), (m2, d2) = astro.SIGN_STARTS[i][0], astro.SIGN_STARTS[(i + 1) % 12][0]
    end_m, end_d = (m2, d2 - 1)
    return f"{MONTHS[m1 - 1]} {d1}", f"{MONTHS[end_m - 1]} {end_d}"


@plugin.scene("zodiac")
def zodiac(ctx, secs):
    now = ctx.now().astimezone()
    sign = astro.sun_sign(now.date())
    element = astro.ELEMENTS[sign]
    col = ELEMENT_COLORS[element]
    moon_sign = astro.moon_sign(now)
    sparks = stars(ctx.rng, 12, (16, 5, 6))
    start, end = sign_dates(sign)
    pages = [(start + " -", end), (element.upper(), "SIGN"), ("MOON IN", moon_sign.upper())]
    per = _page_times(pages)
    secs = max(secs, min(sum(per), 30))
    glyph = GLYPHS[sign]
    for i, t in ticks(secs, 10):
        img = gfx.blank((0, 0, 6))
        for x, y, ph, sp in sparks:
            v = max(0.0, math.sin(t * sp + ph))
            img.putpixel((x, y), gfx.scale(col, 0.15 + 0.5 * v))
        # the symbol draws itself in, row by row, then breathes
        shown = min(9, int(t * 6) + 1)
        pulse = 0.8 + 0.2 * math.sin(t * 2.5)
        for gy, row in enumerate(glyph[:shown]):
            for gx, ch in enumerate(row):
                if ch == "#":
                    img.putpixel((12 + gx, 1 + gy), gfx.scale(col, pulse))
        scroll_text(img, 11, sign.upper(), (255, 255, 255), "5x7", t, 14)
        k, left = _turn(per, t)
        _page(img, 19, pages[k], gfx.scale(col, 0.9), gfx.scale(col, 0.6), left)
        yield img, 0.1
