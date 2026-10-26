"""Window: a pixel landscape whose sky is the real one outside. The sun and moon (in its
phase) sit where they are, clouds cover as much sky as they do, rain and snow fall as
hard as they are, the wind bends the tree and blows the chimney smoke, the tree follows
the season, haze rises when the air is bad, and the house lights up at dusk."""
import math
import time
from datetime import date, timedelta

import numpy as np
from PIL import Image, ImageDraw

from .. import astro, gfx
from ..gfx import H, W
from ..kit import Fireworks, mix, outlined_text, sun_times, temp_color, ticks
from ..plugin import Plugin

plugin = Plugin(
    "window", "A window to outside",
    defaults={"show_temp": True, "visitors": True, "boost": True},
    about="A little landscape that shows what it's like outside without a single word: "
          "the sun and the moon (in its real phase) cross the sky where they are, from "
          "sunrise to sunset at the weather plugin's location. Clouds cover as much sky as "
          "they do, rain, snow and hail fall as hard as they are and slant in the wind, "
          "lightning flashes in storms and fog rolls in. The wind bends the tree and blows "
          "the chimney smoke (lit when it's cold), the tree follows the season (blossom, "
          "green, autumn color, bare), snow lies on the ground in snowy weather, the "
          "horizon shimmers when it's hot and goes hazy when an air quality tile (kind "
          "aqi) is bad, and the house's windows light up at dusk. When rain is likely "
          "(a high chance in the forecast) dark clouds build on the horizon before it "
          "comes. Visitors follow the calendar: birds at dawn, fireflies on summer nights, "
          "bats and a jack-o'-lantern at Halloween, lights on the house at Christmas, a "
          "snowman after snow, fireworks on the Fourth of July and New Year's Eve. When "
          "the weather turns (rain or snow starts or stops, a storm, fog) it comes round "
          "every so often for half an hour. Uses the weather that Home Assistant pushes "
          "(or Open-Meteo); skips itself without any.",
    fields=[{"key": "show_temp", "label": "Temperature", "type": "toggle",
             "text": "Show the temperature in the corner"},
            {"key": "visitors", "label": "Visitors", "type": "toggle",
             "text": "Birds, fireflies, bats, a snowman, holiday lights and fireworks"},
            {"key": "boost", "label": "When the weather turns", "type": "toggle",
             "text": "Show it every so often for half an hour"}])

HORIZON = 22
COVER = {"sunny": 0.0, "clear-night": 0.0, "partlycloudy": 0.4, "cloudy": 0.85, "fog": 0.6,
         "rainy": 0.9, "pouring": 1.0, "snowy": 0.9, "snowy-rainy": 0.9, "hail": 0.9,
         "lightning": 0.8, "lightning-rainy": 1.0, "windy": 0.3, "windy-variant": 0.6,
         "exceptional": 0.8}
RAIN = {"rainy": 0.4, "pouring": 1.0, "lightning-rainy": 0.8, "snowy-rainy": 0.3}
SNOW = {"snowy": 0.6, "snowy-rainy": 0.4}
STORM = {"lightning", "lightning-rainy"}
# Which changes count as the weather turning: into or out of rain, snow, storms or fog.
KIND = {"rainy": "rain", "pouring": "rain", "lightning-rainy": "storm", "lightning": "storm",
        "snowy": "snow", "snowy-rainy": "snow", "hail": "snow", "fog": "fog"}
DAY_SKY = ((40, 100, 210), (120, 180, 240))       # (top, horizon)
DUSK_SKY = ((40, 40, 110), (240, 120, 60))
NIGHT_SKY = ((2, 4, 16), (10, 16, 40))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sun_place(ctx, now):
    """(progress across today's sky 0-1 or None at night, elevation -1 to 1): elevation
    is the sun's height by day and how deep into the night it is after dark."""
    rise, sets = sun_times(ctx, now)
    if rise <= now <= sets:
        p = (now - rise) / (sets - rise)
        return p, math.sin(math.pi * p)
    after = (now - sets).total_seconds() if now > sets else (now - rise + timedelta(days=1)).total_seconds()
    before = (rise - now).total_seconds() if now < rise else (rise + timedelta(days=1) - now).total_seconds()
    return None, -min(1.0, min(after, before) / 5400)   # an hour and a half of twilight


def moon_place(ctx, now, frac):
    """Where the moon is: it runs the sun's path, late by its age (full = opposite the sun)."""
    p, _ = sun_place(ctx, now - timedelta(hours=24.84 * frac))
    return p


def sky_colors(elev, cover, fog):
    """(top, horizon) colors for the sun's elevation, dulled by cloud and fog."""
    if elev >= 0.15:
        top, hor = DAY_SKY
    elif elev >= 0:
        f = elev / 0.15
        top, hor = mix(DUSK_SKY[0], DAY_SKY[0], f), mix(DUSK_SKY[1], DAY_SKY[1], f)
    else:
        top, hor = mix(DUSK_SKY[0], NIGHT_SKY[0], -elev), mix(DUSK_SKY[1], NIGHT_SKY[1], -elev)
    light = max(0.08, min(1.0, elev + 0.6))
    grey = gfx.scale((150, 155, 165), light)
    top, hor = mix(top, grey, cover * 0.7), mix(hor, grey, cover * 0.7)
    fogc = gfx.scale((140, 145, 150), light)
    return mix(top, fogc, fog * 0.8), mix(hor, fogc, fog * 0.9)


def season(now):
    m, d = now.month, now.day
    if (m, d) >= (11, 10) or m <= 3:
        return "winter"
    if m in (4, 5):
        return "spring"
    if (m, d) >= (9, 20):
        return "autumn"
    return "summer"


@plugin.boost
def weather_turned(ctx):
    """Rain or snow starting or stopping, a storm or fog rolling in: the window comes
    round every so often for half an hour after."""
    cond = str((ctx.data("weather") or {}).get("condition") or "")
    if not cond:
        return None
    store = ctx.store("window")
    kind = KIND.get(cond, "dry")
    if store.get("kind") not in (None, kind):
        store["turned"] = time.time()
    store["kind"] = kind
    recent = time.time() - store.get("turned", 0) < 1800
    return ("window", 10) if recent and ctx.settings("window").get("boost", True) else None


def visitors(now, elev, sun_p, wet, temp_f, snowy_ground):
    """Who's out today: a set of birds, fireflies, bats, pumpkin, lights, snowman, fireworks."""
    d = now.date()
    out = set()
    if sun_p is not None and sun_p < 0.12 and not wet and 3 <= d.month <= 10:
        out.add("birds")
    if 6 <= d.month <= 8 and elev < -0.2 and not wet and (temp_f or 0) >= 60:
        out.add("fireflies")
    if date(d.year, 10, 15) <= d <= date(d.year, 10, 31):
        out.add("pumpkin")
        if -0.7 < elev < 0.1 and not wet:
            out.add("bats")
    if (d.month == 12 or (d.month == 1 and d.day <= 6)) and elev < 0.1:
        out.add("lights")
    if snowy_ground:
        out.add("snowman")
    if ((d.month, d.day) == (7, 4) and now.hour >= 21) or ((d.month, d.day) == (12, 31) and now.hour >= 22) \
            or ((d.month, d.day) == (1, 1) and now.hour < 1):
        out.add("fireworks")
    return out


def _flyer(img, x, y, t, color, flap):
    """A bird or bat: two wings that beat."""
    up = int(t * flap) % 2
    for dx, dy in ((-1, -up), (0, 0), (1, -up)):
        if 0 <= x + dx < W and 0 <= y + dy < H:
            img.putpixel((x + dx, y + dy), color)


def _front(img, amount, light, t):
    """A bank of dark cloud building on the western horizon: rain on the way."""
    d = ImageDraw.Draw(img)
    reach = 3 + amount * 10
    color = gfx.scale((70, 72, 82), max(0.25, light))
    for y in range(0, HORIZON - 2):
        edge = reach - y * 0.25 + math.sin(y * 1.3 + t * 0.4) * 1.2
        if edge > 0:
            d.line((0, y, int(edge), y), fill=color)


def _disc(img, cx, cy, r, color):
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r + r and 0 <= cx + dx < W and 0 <= cy + dy < H:
                img.putpixel((cx + dx, cy + dy), color)


def draw_moon(img, cx, cy, frac, elev):
    """A 5x5 moon lit on the side the phase says (waxing: right, northern hemisphere).
    elev: the sun's (see sun_place); by day the moon is paler and its dark side is sky."""
    r = 2
    c = math.cos(2 * math.pi * frac)
    light = max(0.0, elev)
    bright = gfx.scale((235, 235, 210), 1 - 0.5 * light)
    dark = (40, 44, 60)
    for dy in range(-r, r + 1):
        h = math.sqrt(max(0, r * r + r - dy * dy))
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy > r * r + r or not (0 <= cx + dx < W and 0 <= cy + dy < H):
                continue
            lit = dx >= h * c if frac < 0.5 else dx <= -h * c
            if lit or elev < -0.3:   # until it's properly dark, the dark side is just sky
                img.putpixel((cx + dx, cy + dy), bright if lit else dark)


def _put(img, rows, x, y, colors):
    for dy, line in enumerate(rows):
        for dx, ch in enumerate(line):
            if ch in colors and 0 <= x + dx < W and 0 <= y + dy < H:
                img.putpixel((x + dx, y + dy), colors[ch])


def arc(p, top=3):
    """Pixel position along a sky arc for progress p (0 at sunrise, 1 at sunset)."""
    return round(2 + p * (W - 5)), round(HORIZON - 3 - math.sin(math.pi * p) * (HORIZON - 3 - top))


class Clouds:
    def __init__(self, rng, cover, wind):
        n = round(cover * 7)
        self.items = [[rng.uniform(-6, W), rng.uniform(1, 12 if cover < 0.8 else 9), rng.randrange(6, 13),
                       rng.uniform(0.7, 1.3)] for _ in range(n)]
        self.speed = 0.02 + wind / 250

    def draw(self, img, color, shade):
        d = ImageDraw.Draw(img)
        for c in self.items:
            c[0] += self.speed * c[3]
            if c[0] > W + 2:
                c[0] = -c[2] - 2
            x, y, w = c[0], c[1], c[2]
            d.ellipse((x, y + 1, x + w, y + 4), fill=shade)          # a darker belly
            d.ellipse((x + 1, y, x + w - 1, y + 3), fill=color)
            d.ellipse((x + w * 0.25, y - 1.5, x + w * 0.7, y + 2), fill=color)


def _tree(img, x, t, sway, look, light, rng_pick):
    trunk = gfx.scale((90, 60, 35), 0.3 + 0.7 * light)
    for y in range(HORIZON - 5, HORIZON + 2):
        img.putpixel((x, y), trunk)
    top = HORIZON - 9
    lean = round(math.sin(t * (1 + sway)) * sway * 1.5)
    if look == "winter":   # bare branches
        for bx, by in ((-1, 3), (-2, 2), (1, 2), (2, 1), (0, 1), (-1, 0), (1, 0)):
            img.putpixel((x + bx + (lean if by < 2 else 0), top + by + 1), trunk)
        return
    leaf = {"spring": (90, 190, 70), "summer": (40, 140, 50), "autumn": (220, 110, 30)}[look]
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            if dx * dx + dy * dy <= 10:
                c = leaf
                pick = rng_pick[(dx + 3) * 7 + dy + 3]
                if look == "spring" and pick < 0.2:
                    c = (255, 170, 200)                      # blossom
                elif look == "autumn" and pick < 0.45:
                    c = (200, 40, 30) if pick < 0.2 else (240, 190, 40)
                elif pick < 0.3:
                    c = gfx.scale(c, 0.75)
                px = x + dx + (lean if dy < 1 else 0)
                img.putpixel((px, top + dy + 1), gfx.scale(c, 0.25 + 0.75 * light))


def _house(img, x, lit, snow, light):
    wall = gfx.scale((150, 95, 70), 0.25 + 0.75 * light)
    roof = gfx.scale((110, 40, 40), 0.25 + 0.75 * light)
    d = ImageDraw.Draw(img)
    d.rectangle((x, HORIZON - 2, x + 7, HORIZON + 3), fill=wall)
    for row in range(3):   # the roof
        d.line((x - 1 + row, HORIZON - 3 - row, x + 8 - row, HORIZON - 3 - row),
               fill=(230, 235, 240) if snow and row == 2 else roof)
    d.rectangle((x + 6, HORIZON - 7, x + 6, HORIZON - 5), fill=roof)   # chimney
    glow = (255, 200, 90) if lit else gfx.scale((60, 90, 130), 0.3 + 0.7 * light)
    d.rectangle((x + 1, HORIZON, x + 2, HORIZON + 1), fill=glow)
    d.rectangle((x + 4, HORIZON + 1, x + 5, HORIZON + 3), fill=gfx.scale((90, 55, 30), 0.3 + 0.7 * light))


@plugin.scene("window", empty_text="NO WEATHER YET")
def window(ctx, secs):
    """What it's like outside, as a landscape."""
    wx = ctx.data("weather")
    if not wx:
        return
    r = ctx.rng
    now = ctx.now()
    cond = str(wx.get("condition") or "")
    temp = _num(wx.get("temp"))
    unit = str(wx.get("unit") or "F").upper()[:1]
    temp_f = None if temp is None else temp * 9 / 5 + 32 if unit == "C" else temp
    wind = _num(wx.get("wind")) or 0.0
    cover = COVER.get(cond, 0.3)
    fog = 1.0 if cond == "fog" else 0.0
    rain, snow = RAIN.get(cond, 0.0), SNOW.get(cond, 0.0)
    hail = cond == "hail"
    aqi = max((_num(i.get("value")) or 0 for i in (ctx.data("tiles") or {}).get("items") or []
               if isinstance(i, dict) and i.get("kind") == "aqi"), default=0)
    haze = max(0.0, min(1.0, (aqi - 50) / 200))
    look = season(now)
    snowy_ground = snow > 0 or hail or (look == "winter" and temp_f is not None and temp_f <= 32)
    sun_p, elev = sun_place(ctx, now)
    light = max(0.08, min(1.0, elev + 0.6)) * (1 - 0.35 * cover)
    moon = astro.moon_phase(now)
    moon_p = moon_place(ctx, now, moon["fraction"])
    wet = bool(rain or snow or hail or cond in STORM)
    chance = _num(wx.get("precip")) or 0
    coming = 0.0 if wet else max(0.0, (chance - 40) / 60)   # rain likely but not here yet
    guests = visitors(now, elev, sun_p, wet, temp_f, snowy_ground) \
        if ctx.settings("window").get("visitors", True) else set()
    birds = [[r.uniform(-6, W - 4), r.uniform(4, 12), r.uniform(0.15, 0.3)] for _ in range(3)]
    bats = [[r.uniform(4, 28), r.uniform(4, 14), r.uniform(0, 6.28)] for _ in range(2)]
    flies = [(r.uniform(2, 30), r.uniform(15, 27), r.uniform(0, 6.28)) for _ in range(7)]
    fireworks = Fireworks(r, [(230, 30, 30), (255, 255, 255), (40, 90, 255), (255, 215, 0)])

    top, hor = sky_colors(elev, cover, fog)
    rows = np.linspace(0, 1, HORIZON + 1)[:, None]
    sky = np.zeros((H, W, 3), dtype=float)
    sky[:HORIZON + 1] = (np.array(top) * (1 - rows) + np.array(hor) * rows)[:, None, :]
    if haze:
        rows = np.clip((np.arange(H) - 6) / (HORIZON - 6), 0, 1)[:, None, None]
        sky = sky + (np.array([190, 160, 100]) * max(0.3, light) - sky) * rows * haze * 0.85
    sky = sky.astype(np.uint8)
    stars = [(r.randrange(W), r.randrange(HORIZON - 4), r.uniform(0, 6.28)) for _ in range(30)]
    see_stars = max(0.0, -elev - 0.3) / 0.7 * (1 - cover)
    clouds = Clouds(r, cover, wind)
    cloud = mix(gfx.scale((235, 235, 240), light), (110, 115, 125), 0.6 if rain or snow or cond in STORM else 0)
    if -0.5 < elev < 0.15 and cover < 0.9:
        cloud = mix(cloud, (240, 140, 120), 0.4)                   # pink at sunrise and sunset
    shade = gfx.scale(cloud, 0.8)
    ground = {"spring": (70, 150, 50), "summer": (40, 120, 40), "autumn": (120, 100, 40),
              "winter": (95, 88, 62)}[look]
    ground = (225, 230, 240) if snowy_ground else ground
    ground = gfx.scale(ground, 0.25 + 0.75 * light)
    hills = gfx.scale(mix(ground, hor, 0.5), 0.8)
    picks = [r.random() for _ in range(49)]
    smoke = []
    drops = [[r.uniform(-8, W + 8), r.uniform(0, H)] for _ in range(round(rain * 45 + snow * 30 + hail * 20))]
    slant = max(-1.5, min(1.5, wind / 25))
    flash = 0
    leaves = []
    for i, t in ticks(secs, 15):
        img = Image.fromarray(sky, "RGB")
        d = ImageDraw.Draw(img)
        if flash == 0 and cond in STORM and r.random() < 0.02:
            flash = 4
        if see_stars > 0:
            for x, y, ph in stars:
                tw = 0.5 + 0.5 * math.sin(t * 2 + ph)
                if (ph * 10) % 1 < see_stars:
                    img.putpixel((x, y), gfx.scale((200, 210, 255), 0.35 + 0.5 * tw))
        if moon_p is not None and moon["illumination"] > 0.03 and cover < 0.9:
            draw_moon(img, *arc(moon_p, 4), moon["fraction"], elev)
        if sun_p is not None:
            sx, sy = arc(sun_p)
            low = 1 - math.sin(math.pi * sun_p)
            col = mix((255, 230, 90), (255, 120, 40), low)
            if cover < 0.95:
                _disc(img, sx, sy, 2, mix(col, cloud, cover * 0.8))
        if coming:
            _front(img, coming, light, t)
        clouds.draw(img, cloud, shade)
        if "fireworks" in guests:
            fireworks.step(img)
        if "birds" in guests:
            for b in birds:
                b[0] += b[2]
                if b[0] > W + 2:
                    b[0] = r.uniform(-25, -3)
                _flyer(img, int(b[0]), int(b[1] + math.sin(t + b[2] * 9)), t, gfx.scale((40, 40, 50), 1), 4)
        if "bats" in guests:
            for b in bats:
                b[0] = (b[0] + math.cos(t * 1.7 + b[2]) * 0.4) % W
                b[1] = max(2, min(HORIZON - 4, b[1] + math.sin(t * 2.3 + b[2]) * 0.3))
                _flyer(img, int(b[0]), int(b[1]), t, (20, 14, 28), 8)
        if flash:
            img = Image.blend(img, Image.new("RGB", (W, H), (230, 230, 255)), 0.5 * flash / 4)
            d = ImageDraw.Draw(img)
            if flash == 4:
                bolt_x = r.randrange(6, W - 6)
            x, y = bolt_x, 6
            while y < HORIZON:
                nx, ny = x + r.choice((-1, 0, 1)), y + 2
                d.line((x, y, nx, ny), fill=(255, 255, 230))
                x, y = nx, ny
            flash -= 1
        for x in range(W):     # far hills, then the ground
            hy = HORIZON - 2 + round(math.sin(x * 0.22 + 1) * 1.5)
            d.line((x, hy, x, HORIZON), fill=hills)
            gy = HORIZON + 1 + round(math.sin(x * 0.3) * 0.7)
            d.line((x, gy, x, H - 1), fill=ground)
        if temp_f is not None and temp_f >= 90:   # heat shimmer along the horizon
            a = np.asarray(img).copy()
            for y in range(HORIZON - 3, HORIZON + 2):
                a[y] = np.roll(a[y], round(math.sin(t * 6 + y)), axis=0)
            img = Image.fromarray(a, "RGB")
            d = ImageDraw.Draw(img)
        sway = min(1.0, wind / 30)
        _tree(img, 6, t, sway, look, light, picks)
        _house(img, 21, elev < 0.1, snowy_ground, light)
        if "lights" in guests:   # Christmas lights along the eaves
            for k, x in enumerate(range(20, 31, 2)):
                on = (k + int(t * 2)) % 3
                img.putpixel((x, HORIZON - 3), ((230, 40, 40), (40, 200, 60), (255, 200, 60))[on])
        if "pumpkin" in guests:
            glow = (255, 210, 60) if elev < 0.1 else (90, 50, 10)
            _put(img, ["oo", "oo"], 18, HORIZON + 2, {"o": gfx.scale((240, 110, 10), 0.4 + 0.6 * max(light, 0.5))})
            img.putpixel((18, HORIZON + 2), glow)
        if "snowman" in guests:
            _put(img, [".W.", "KWO", ".W.", "WWW", "WWW"], 15, HORIZON - 2,
                 {"W": gfx.scale((250, 252, 255), 0.4 + 0.6 * light), "O": (255, 130, 30), "K": (20, 20, 25)})
        if "fireflies" in guests:
            for x, y, ph in flies:
                glow = max(0.0, math.sin(t * 1.5 + ph * 3))
                if glow > 0.3:
                    img.putpixel((int(x + math.sin(t * 0.5 + ph) * 2), int(y)), gfx.scale((210, 255, 80), glow))
        if temp_f is not None and temp_f < 45 and r.random() < 0.25:   # the heating's on
            smoke.append([27.0, HORIZON - 8.0])
        for s in smoke[:]:
            s[0] += 0.05 + wind / 60
            s[1] -= 0.12
            if s[1] < 2 or s[0] >= W:
                smoke.remove(s)
                continue
            img.putpixel((int(s[0]), int(s[1])), gfx.scale((150, 150, 160), (0.3 + 0.5 * light) * (s[1] / HORIZON)))
        if look == "autumn" and wind >= 10 and r.random() < 0.05 + wind / 400:
            leaves.append([5.0, HORIZON - 9.0, r.uniform(0, 6.28)])
        for lf in leaves[:]:
            lf[0] += 0.2 + wind / 60
            lf[1] += 0.06 + 0.15 * math.sin(t * 3 + lf[2])
            if lf[0] >= W or lf[1] >= H - 1:
                leaves.remove(lf)
                continue
            img.putpixel((int(lf[0]), int(lf[1])), (220, 110 + int(60 * math.sin(lf[2])), 30))
        for k, p in enumerate(drops):
            is_snow = snow and (not rain or k % 2)
            if hail:
                p[1] += 1.4
                p[0] += slant * 0.3
                color = (230, 235, 245)
            elif is_snow:
                p[1] += 0.25
                p[0] += slant * 0.25 + math.sin(t * 2 + k) * 0.15
                color = gfx.scale((235, 240, 250), 0.4 + 0.6 * light)
            else:
                p[1] += 1.1
                p[0] += slant * 1.1
                color = gfx.scale((120, 150, 220), 0.5 + 0.5 * light)
            if p[1] >= H or not -8 <= p[0] <= W + 8:
                p[0], p[1] = r.uniform(-8, W + 8), r.uniform(-4, 0)
            x, y = int(p[0]), int(p[1])
            if 0 <= x < W and 0 <= y < H:
                img.putpixel((x, y), color)
                if not is_snow and not hail and 0 <= x - round(slant) < W and y >= 1:
                    img.putpixel((x - round(slant), y - 1), gfx.scale(color, 0.6))   # a streak
        if fog:
            a = np.asarray(img).astype(float)
            band = (0.35 + 0.15 * np.sin(np.arange(H) * 0.7 + t * 0.6))[:, None, None]
            a = a + (np.array(gfx.scale((150, 155, 160), max(0.3, light))) - a) * band
            img = Image.fromarray(a.clip(0, 255).astype(np.uint8), "RGB")
        if temp is not None and ctx.settings("window").get("show_temp", True):
            s = f"{temp:.0f}"
            outlined_text(img, (1, H - 6), s, temp_color(temp_f) if temp_f is not None else (255, 255, 255), "tom-thumb")
            img.putpixel((2 + gfx.text_width(s, "tom-thumb"), H - 6), (230, 230, 230))   # degree mark
        yield img, 1 / 15
