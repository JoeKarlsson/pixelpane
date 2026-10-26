"""Generative art: fire, plasma, life, lava, ripples, aquarium and more, computed live."""
import functools
import math
from collections import deque
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw

from .. import gfx
from ..gfx import H, W
from ..kit import palette, ticks
from ..plugin import SCENES, Plugin, enabled

SCENE_NAMES = ["fire", "plasma", "life", "matrix_rain", "starfield", "lava", "ripples", "reaction",
          "sand", "aurora", "fireflies", "aquarium", "snake", "hourglass", "smog"]

plugin = Plugin(
    "generative", "Endless generative art",
    defaults={"scenes": ["fire", "plasma", "life", "matrix_rain", "starfield", "lava", "ripples",
                         "aurora", "fireflies", "aquarium"], "speed": "normal"},
    about="Art that's computed, not stored: a fire, a plasma of drifting color, "
          "Conway's Game of Life, matrix rain, a starfield, a lava lamp, rain ripples, "
          "reaction-diffusion, falling sand, an aurora, fireflies, an aquarium (your living "
          "tank, while the aquatic plugin is on), a snake "
          "that plays itself, an hourglass that drains toward your next meeting and a murky "
          "smog. The playlist's \"generative\" slot picks one of the scenes you tick below. "
          "The \"ambient\" slot picks one that fits outside: ripples when it rains, fire "
          "when it's hot, an aurora or fireflies on a clear night, and smog whenever an "
          "air quality tile (kind aqi) is over 150.",
    fields=[{"key": "scenes", "label": "Scenes to pick from", "type": "choices",
             "options": SCENE_NAMES},
            {"key": "speed", "label": "Speed", "type": "select",
             "options": [{"label": "Slow and calm", "value": "slow"}, {"label": "Normal", "value": "normal"},
                         {"label": "Fast", "value": "fast"}]}])
SPEEDS = {"slow": 1.7, "normal": 1.0, "fast": 0.65}   # how long each frame is held, relative


@plugin.picker("generative")
def pick(ctx):
    """The playlist's "generative" slot: one of the ticked scenes."""
    return ctx.rng.choice(ctx.settings("generative").get("scenes") or ["fire"])


def _bad_air(ctx):
    for item in (ctx.data("tiles") or {}).get("items") or []:
        try:
            if str(item.get("kind")).lower() == "aqi" and float(item.get("value")) > 150:
                return True
        except (TypeError, ValueError):
            pass
    return False


def ambient_choices(ctx):
    """Scenes that suit the weather and air right now (before the ticked filter)."""
    if _bad_air(ctx):
        return ["smog"]
    wx = ctx.data("weather") or {}
    cond = str(wx.get("condition", ""))
    temp = None
    try:
        temp = float(wx["temp"])
        if str(wx.get("unit", "F")).upper().startswith("C"):
            temp = temp * 9 / 5 + 32
    except (KeyError, TypeError, ValueError):
        pass
    if cond in ("rainy", "pouring", "lightning-rainy", "lightning"):
        return ["ripples"]
    if cond in ("snowy", "snowy-rainy", "hail"):
        return ["starfield"]
    if temp is not None and temp >= 85:
        return ["fire"]
    if cond == "clear-night":
        return ["fireflies"] if temp is not None and temp >= 55 else ["aurora", "starfield"]
    if cond == "sunny":
        return ["lava", "plasma"]
    if cond in ("cloudy", "partlycloudy", "fog", "windy", "windy-variant"):
        return ["aquarium", "reaction", "life"]
    return []


@plugin.picker("ambient")
def pick_ambient(ctx):
    """The playlist's "ambient" slot: a scene that fits the weather and air outside.
    Bad air always shows smog; otherwise it keeps to your ticked scenes."""
    ticked = ctx.settings("generative").get("scenes") or ["fire"]
    options = ambient_choices(ctx)
    if options == ["smog"]:
        return "smog"
    return ctx.rng.choice([s for s in options if s in ticked] or ticked)


FIRE = palette([(0, 0, 0), (90, 0, 0), (220, 40, 0), (255, 140, 0), (255, 230, 80), (255, 255, 220)])


@plugin.scene("fire", "generative")
def fire(ctx, secs):
    rs = np.random.default_rng(ctx.rng.randrange(1 << 30))
    heat = np.zeros((H + 2, W))
    for i, t in ticks(secs, 20):
        heat[-2:] = rs.uniform(0.6, 1.0, (2, W))
        avg = (heat[1:-1] + heat[2:] + np.roll(heat[1:-1], 1, 1) + np.roll(heat[1:-1], -1, 1)) / 4
        heat[:-2] = np.clip(avg - rs.uniform(0, 0.07, (H, W)) - 0.016, 0, 1)
        yield Image.fromarray(FIRE[(heat[:H] * 255).astype(int)], "RGB"), 0.05


RAINBOW = np.array([gfx.hsv(i / 256, 0.9, 1) for i in range(256)], dtype=np.uint8)
YY, XX = np.mgrid[0:H, 0:W].astype(float)


@plugin.scene("plasma", "generative")
def plasma(ctx, secs):
    for i, t in ticks(secs, 20):
        cx, cy = 16 + 10 * math.sin(t / 3), 16 + 10 * math.cos(t / 2)
        v = (np.sin(XX * 0.25 + t) + np.sin(YY * 0.2 + t * 1.3) + np.sin((XX + YY) * 0.15 + t * 0.7)
             + np.sin(np.hypot(XX - cx, YY - cy) * 0.3))
        idx = ((v + 4) * 32 + t * 20).astype(int) % 256
        yield Image.fromarray(RAINBOW[idx], "RGB"), 0.05


@plugin.scene("life", "generative")
def life(ctx, secs):
    rs = np.random.default_rng(ctx.rng.randrange(1 << 30))
    grid = rs.random((H, W)) < 0.3
    trail = np.zeros((H, W))
    hue = rs.random()
    history = []
    for i, t in ticks(secs, 8):
        n = sum(np.roll(np.roll(grid, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                if (dy, dx) != (0, 0))
        grid = (n == 3) | (grid & (n == 2))
        key = grid.tobytes()
        if grid.sum() < 6 or key in history:
            grid = rs.random((H, W)) < 0.3
            hue = rs.random()
            history.clear()
        history = (history + [key])[-6:]
        trail = np.maximum(trail * 0.75, grid.astype(float))
        rgb = np.array(gfx.hsv(hue + t / 60, 0.8, 1), dtype=float)
        frame = (trail[..., None] * rgb).astype(np.uint8)
        frame[grid] = np.array(gfx.hsv(hue + t / 60, 0.3, 1), dtype=np.uint8)
        yield Image.fromarray(frame, "RGB"), 0.125


@plugin.scene("matrix_rain", "generative")
def matrix_rain(ctx, secs):
    rng = ctx.rng
    level = np.zeros((H, W))
    drops = [[x, rng.uniform(-30, 0), rng.uniform(8, 20)] for x in range(W)]
    for i, t in ticks(secs, 20):
        level *= 0.85
        heads = []
        for d in drops:
            d[1] += d[2] / 20
            y = int(d[1])
            if 0 <= y < H:
                level[y, d[0]] = 1.0
                heads.append((d[0], y))
            if d[1] > H + 8:
                d[1], d[2] = rng.uniform(-20, 0), rng.uniform(8, 20)
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        frame[..., 1] = (level * 230).astype(np.uint8)
        frame[..., 0] = (level ** 3 * 60).astype(np.uint8)
        for x, y in heads:
            frame[y, x] = (180, 255, 180)
        yield Image.fromarray(frame, "RGB"), 0.05


@plugin.scene("starfield", "generative")
def starfield(ctx, secs):
    rng = ctx.rng
    stars = [[rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(0.1, 1)] for _ in range(80)]
    for i, t in ticks(secs, 25):
        img = gfx.blank()
        px = img.load()
        for s in stars:
            s[2] -= 0.012
            if s[2] <= 0.02:
                s[:] = [rng.uniform(-1, 1), rng.uniform(-1, 1), 1.0]
            x, y = int(16 + s[0] / s[2] * 8), int(16 + s[1] / s[2] * 8)
            if 0 <= x < W and 0 <= y < H:
                v = int(80 + 175 * (1 - s[2]))
                px[x, y] = (v, v, min(255, v + 40))
        yield img, 0.04


# --- blobs: lava lamp and smog ------------------------------------------------

LAVA = palette([(10, 0, 20), (40, 0, 40), (150, 10, 30), (255, 80, 0), (255, 190, 40), (255, 250, 200)])
SMOG = palette([(12, 10, 6), (40, 34, 24), (80, 68, 48), (120, 104, 76), (150, 134, 100), (175, 160, 125)])


@plugin.scene("lava", "generative")
def lava(ctx, secs):
    """A lava lamp: warm blobs that drift, merge and split."""
    r = ctx.rng
    blobs = [(r.uniform(3, 6), r.uniform(0.2, 0.5), r.uniform(0.15, 0.4), r.uniform(0, 6.28),
              r.uniform(0, 6.28)) for _ in range(5)]
    for i, t in ticks(secs, 15):
        field = np.zeros((H, W))
        for rad, fx, fy, px, py in blobs:
            cx = 16 + 11 * math.sin(t * fx + px)
            cy = 16 + 13 * math.sin(t * fy + py)
            field += rad * rad / ((XX - cx) ** 2 + (YY - cy) ** 2 + 1)
        idx = (np.clip((field - 0.3) / 2.2, 0, 1) * 255).astype(int)
        yield Image.fromarray(LAVA[idx], "RGB"), 1 / 15


@plugin.scene("smog", "generative")
def smog(ctx, secs):
    """Slow, murky brown haze rolling past: the ambient slot's sign that the air is bad."""
    rs = np.random.default_rng(ctx.rng.randrange(1 << 30))
    grit = rs.random((H, W)) < 0.03
    ph = rs.uniform(0, 6.28, 4)
    for i, t in ticks(secs, 15):
        v = (np.sin(XX * 0.18 + t * 0.5 + ph[0]) + np.sin(YY * 0.23 - t * 0.3 + ph[1])
             + np.sin((XX + YY) * 0.11 + t * 0.4 + ph[2]) + np.sin((XX - YY) * 0.15 - t * 0.6 + ph[3]))
        frame = SMOG[((v + 4) / 8 * 255).astype(int)].copy()
        g = np.roll(grit, (i // 4, i // 2), (0, 1))   # specks drifting through the haze
        frame[g] = np.minimum(255, frame[g].astype(int) + 45)
        yield Image.fromarray(frame, "RGB"), 1 / 15


# --- water ripples --------------------------------------------------------------

@plugin.scene("ripples", "generative")
def ripples(ctx, secs):
    """Raindrops landing on a dark pond."""
    r = ctx.rng
    cur, prev = np.zeros((H, W)), np.zeros((H, W))
    base = np.array([4, 22, 55], dtype=float)
    splash = None
    for i, t in ticks(secs, 20):
        if r.random() < 0.08:   # a raindrop: a soft dent, not one pixel (that rings in a checkerboard)
            cy, cx = r.uniform(3, H - 3), r.uniform(3, W - 3)
            cur -= 8 * np.exp(-((XX - cx) ** 2 + (YY - cy) ** 2) / 1.5)
            splash = (int(cx), int(cy), 3)
        nxt = (np.roll(cur, 1, 0) + np.roll(cur, -1, 0) + np.roll(cur, 1, 1) + np.roll(cur, -1, 1)) / 2 - prev
        nxt = 0.6 * nxt + 0.1 * (np.roll(nxt, 1, 0) + np.roll(nxt, -1, 0) + np.roll(nxt, 1, 1) + np.roll(nxt, -1, 1))
        nxt *= 0.975
        prev, cur = cur, nxt
        shade = np.clip(cur - np.roll(cur, 1, 0), -1.5, 1.5)[..., None]   # light from above
        frame = base + shade * np.array([50, 100, 130]) + np.clip(cur, 0, 3)[..., None] * np.array([15, 35, 50])
        if splash and splash[2]:
            x, y, n = splash
            frame[y, x] = (200, 230, 255)   # the drop hitting the water
            splash = (x, y, n - 1)
        yield Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8), "RGB"), 0.05


# --- reaction-diffusion -----------------------------------------------------------

CORAL = palette([(0, 0, 10), (20, 10, 60), (0, 120, 140), (120, 230, 180), (255, 255, 220)])
REACTIONS = [(0.0545, 0.062), (0.0367, 0.0649), (0.029, 0.057), (0.039, 0.058)]   # coral, mitosis, spots, worms


def _laplace(a):
    return np.roll(a, 1, 0) + np.roll(a, -1, 0) + np.roll(a, 1, 1) + np.roll(a, -1, 1) - 4 * a


@plugin.scene("reaction", "generative")
def reaction(ctx, secs):
    """Gray-Scott reaction-diffusion: coral, spots and worms that grow and divide."""
    rs = np.random.default_rng(ctx.rng.randrange(1 << 30))
    f, k = REACTIONS[ctx.rng.randrange(len(REACTIONS))]

    def seed():
        u, v = np.ones((H, W)), np.zeros((H, W))
        for _ in range(5):
            y, x = rs.integers(2, H - 5), rs.integers(2, W - 5)
            v[y:y + 3, x:x + 3] = 1
        return u, v

    u, v = seed()
    for i, t in ticks(secs, 12):
        before = v.copy()
        for _ in range(10):
            uvv = u * v * v
            u += 0.2 * _laplace(u) - uvv + f * (1 - u)
            v += 0.1 * _laplace(v) + uvv - (f + k) * v
        if v.max() < 0.05 or v.mean() > 0.4:    # died out or filled up: start over
            u, v = seed()
        elif np.abs(v - before).max() < 0.005:  # settled: knock a hole in it so it regrows
            y, x = rs.integers(0, H - 8), rs.integers(0, W - 8)
            u[y:y + 8, x:x + 8], v[y:y + 8, x:x + 8] = 1, 0
            v[y + 3:y + 5, x + 3:x + 5] = 1
        idx = (np.clip(v * 3, 0, 1) * 255).astype(int)
        yield Image.fromarray(CORAL[idx], "RGB"), 1 / 12


# --- falling sand -----------------------------------------------------------------

@plugin.scene("sand", "generative")
def sand(ctx, secs):
    """Colored sand poured from a wandering spout; when it's full, the floor opens."""
    r = ctx.rng
    grid = np.zeros((H, W), dtype=bool)
    color = np.zeros((H, W, 3), dtype=np.uint8)
    hue, spout, draining = r.random(), r.uniform(4, 28), False
    for i, t in ticks(secs, 15):
        if draining:
            grid[1:], color[1:] = grid[:-1].copy(), color[:-1].copy()   # everything falls out
            grid[0], color[0] = False, 0
            draining = bool(grid.any())
        else:
            spout = min(W - 2.0, max(1.0, spout + r.uniform(-1.2, 1.2)))
            hue += 0.004
            for _ in range(3):
                x = int(spout) + r.choice((-1, 0, 0, 1))
                if not grid[0, x]:
                    grid[0, x] = True
                    color[0, x] = gfx.hsv(hue, 0.75, 1.0 - r.random() * 0.25)
            if grid[2].sum() > W // 2:
                draining = True
            for y in range(H - 2, -1, -1):        # bottom-up so a grain moves once a frame
                for x in np.flatnonzero(grid[y]):
                    for dx in ((0, -1, 1) if r.random() < 0.5 else (0, 1, -1)):
                        nx = x + dx
                        if 0 <= nx < W and not grid[y + 1, nx]:
                            grid[y + 1, nx], grid[y, x] = True, False
                            color[y + 1, nx], color[y, x] = color[y, x], 0
                            break
        yield Image.fromarray(color, "RGB"), 1 / 15


# --- aurora -----------------------------------------------------------------------

@plugin.scene("aurora", "generative")
def aurora(ctx, secs):
    """Northern lights rippling over a dark hill, under a few stars."""
    r = ctx.rng
    stars = [(r.randrange(W), r.randrange(H - 10), r.random()) for _ in range(18)]
    xs = np.arange(W, dtype=float)
    hill = (H - 4 - 2.5 * np.sin(xs / 7 + 1) - 1.5 * np.sin(xs / 3.1)).astype(int)
    for i, t in ticks(secs, 15):
        frame = np.zeros((H, W, 3))
        frame[..., 2] = 10 + YY * 0.8    # night sky, a little lighter near the horizon
        frame[..., 1] = 2 + YY * 0.3
        for x, y, ph in stars:
            frame[y, x] += 60 + 80 * (0.5 + 0.5 * math.sin(t * 2 + ph * 20))
        for band, (amp, speed, base, col) in enumerate((
                (4, 0.6, 9, (40, 255, 120)), (3, 0.9, 13, (60, 200, 255)), (3, 0.45, 7, (180, 80, 255)))):
            top = base + amp * np.sin(xs / (6 + band * 2) + t * speed) + 2 * np.sin(xs / 3 - t * speed * 1.7)
            bright = 0.55 + 0.45 * np.sin(xs / 4 + t * (1.2 + band * 0.4) + band * 2)  # curtains shimmer
            d = YY - top[None, :]
            glow = np.where(d >= 0, np.exp(-d / 5), np.exp(d * 1.5)) * bright[None, :]
            frame += glow[..., None] * np.array(col) * 0.7
        frame[YY >= hill[None, :]] = (4, 8, 6)
        yield Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8), "RGB"), 1 / 15


# --- fireflies --------------------------------------------------------------------

@plugin.scene("fireflies", "generative")
def fireflies(ctx, secs):
    """A loose swarm of fireflies blinking over tall grass."""
    r = ctx.rng
    flies = [[r.uniform(4, 28), r.uniform(4, 22), 0.0, 0.0, r.uniform(0, 6.28), r.uniform(1.5, 3)]
             for _ in range(12)]
    grass = [(x, r.randrange(3, 8), r.uniform(0, 6.28)) for x in range(0, W, 2)]
    for i, t in ticks(secs, 15):
        img = gfx.blank((2, 4, 14))
        d = ImageDraw.Draw(img)
        cx = sum(f[0] for f in flies) / len(flies)
        cy = sum(f[1] for f in flies) / len(flies)
        glow = np.zeros((H, W))
        for f in flies:
            f[2] += r.uniform(-0.12, 0.12) + (cx - f[0]) * 0.003 + (16 - f[0]) * 0.002
            f[3] += r.uniform(-0.12, 0.12) + (cy - f[1]) * 0.003 + (14 - f[1]) * 0.002
            sp = math.hypot(f[2], f[3])
            if sp > 0.5:
                f[2], f[3] = f[2] / sp * 0.5, f[3] / sp * 0.5
            f[0] = min(W - 1.0, max(0.0, f[0] + f[2]))
            f[1] = min(H - 6.0, max(0.0, f[1] + f[3]))
            lit = max(0.0, math.sin(t * f[5] + f[4])) ** 3
            x, y = int(f[0]), int(f[1])
            glow[y, x] += lit
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                if 0 <= x + dx < W and 0 <= y + dy < H:
                    glow[y + dy, x + dx] += lit * 0.3
            if lit < 0.1:
                img.putpixel((x, y), (14, 16, 12))   # a dark body between blinks
        for x, h, ph in grass:
            sway = round(math.sin(t * 1.5 + ph))
            d.line((x, H - 1, x + sway, H - 1 - h), fill=(10, 40, 15))
        a = np.asarray(img).astype(float)
        a += np.clip(glow, 0, 1)[..., None] * np.array([210, 255, 80])
        yield Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB"), 1 / 15


# --- aquarium ---------------------------------------------------------------------

@plugin.scene("aquarium", "generative")
def aquarium(ctx, secs):
    """Your living tank while the aquatic plugin is on; otherwise a few fish swimming past."""
    from . import aquatic
    if enabled(ctx.config, "aquatic"):
        yield from aquatic.aquatic(ctx, secs)
    else:
        yield from aquatic.render(ctx, secs, aquatic.visitors(ctx))


# --- snake ------------------------------------------------------------------------

def _snake_step(body, food, n):
    """The next head: the shortest path to the food, else whichever safe move leaves most room."""
    blocked = set(list(body)[:-1])
    head = body[0]

    def moves(p):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            q = (p[0] + dx, p[1] + dy)
            if 0 <= q[0] < n and 0 <= q[1] < n and q not in blocked:
                yield q

    first, seen, queue = {}, {head}, deque([head])
    while queue:
        p = queue.popleft()
        if p == food:
            while first[p] != head:
                p = first[p]
            return p
        for q in moves(p):
            if q not in seen:
                seen.add(q)
                first[q] = p
                queue.append(q)

    def room(q):
        seen, stack = {q}, [q]
        while stack:
            for s in moves(stack.pop()):
                if s not in seen:
                    seen.add(s)
                    stack.append(s)
        return len(seen)
    options = list(moves(head))
    return max(options, key=room) if options else None


@plugin.scene("snake", "generative")
def snake(ctx, secs):
    """Snake playing itself: it chases the food, grows, and starts over when it's stuck."""
    r, n = ctx.rng, 16

    def new_food(body):
        free = [(x, y) for x in range(n) for y in range(n) if (x, y) not in body]
        return r.choice(free) if free else None

    body = deque([(8, 8), (7, 8), (6, 8)])
    food, dead = new_food(body), 0
    hue = r.random()
    for i, t in ticks(secs, 12):
        img = gfx.blank()
        d = ImageDraw.Draw(img)
        if dead:
            dead -= 1
            if not dead:
                body = deque([(8, 8), (7, 8), (6, 8)])
                food, hue = new_food(body), r.random()
        else:
            nxt = _snake_step(body, food, n) if food else None
            if nxt is None:
                dead = 12
            else:
                body.appendleft(nxt)
                if nxt == food:
                    food = new_food(body)
                else:
                    body.pop()
        for k, (x, y) in enumerate(body):
            col = gfx.hsv(hue + k * 0.01, 0.8, 1.0 if k == 0 else max(0.35, 0.9 - k * 0.01))
            if dead and dead % 4 < 2:
                col = (255, 40, 40)
            d.rectangle((x * 2, y * 2, x * 2 + 1, y * 2 + 1), fill=col)
        if food and not dead:
            fx, fy = food
            d.rectangle((fx * 2, fy * 2, fx * 2 + 1, fy * 2 + 1),
                        fill=(255, 60, 60) if i % 6 < 4 else (255, 160, 160))
        yield img, 1 / 12


# --- hourglass --------------------------------------------------------------------

GLASS_TOP, NECK, GLASS_BOTTOM = 1, 12, 23


def _half_width(y):
    """Half the inside width of the glass at row y: wide at the ends, 1 at the neck."""
    return max(1, round(1 + 6 * abs(y - NECK) / (NECK - GLASS_TOP)))


def _minutes_to_event(ctx):
    ev = ctx.data("next_event") or {}
    try:
        start = datetime.fromisoformat(str(ev["start"]))
    except (KeyError, ValueError):
        return None
    if start.tzinfo:
        start = start.astimezone().replace(tzinfo=None)
    mins = (start - ctx.now()).total_seconds() / 60
    return mins if 0 <= mins <= 120 else None


@plugin.scene("hourglass", "generative")
def hourglass(ctx, secs):
    """An hourglass: it drains toward your next meeting when one is under two hours
    away, otherwise it empties once an hour, from the top of the hour."""
    rows_top = range(GLASS_TOP, NECK)
    rows_bottom = range(NECK + 1, GLASS_BOTTOM + 1)
    cap = sum(2 * _half_width(y) - 1 for y in rows_top)
    for i, t in ticks(secs, 10):
        mins = _minutes_to_event(ctx)
        now = ctx.now()
        left = mins / 120 if mins is not None else 1 - (now.minute * 60 + now.second) / 3600
        left = min(1.0, max(0.0, left))
        sand_col = (255, 190, 80) if mins is None or mins > 10 else (255, 80, 50)
        img = gfx.blank()
        d = ImageDraw.Draw(img)
        d.line((8, GLASS_TOP - 1, 23, GLASS_TOP - 1), fill=(130, 80, 40))   # the wooden ends
        d.line((8, GLASS_BOTTOM + 1, 23, GLASS_BOTTOM + 1), fill=(130, 80, 40))
        for y in range(GLASS_TOP, GLASS_BOTTOM + 1):
            hw = _half_width(y)
            img.putpixel((16 - hw - 1, y), (90, 110, 140))
            img.putpixel((15 + hw, y), (90, 110, 140))
        grains = round(cap * left)
        for y in reversed(rows_top):            # the top's sand sits on the neck
            hw = _half_width(y)
            take = min(grains, 2 * hw - 1)
            off = (2 * hw - 1 - take) // 2
            for k in range(take):
                img.putpixel((16 - hw + off + k, y), sand_col)
            grains -= take
        grains, surface = cap - round(cap * left), GLASS_BOTTOM + 1
        for y in reversed(rows_bottom):         # the pile grows from the bottom up
            if grains <= 0:
                break
            hw = _half_width(y)
            take = min(grains, 2 * hw - 1)
            off = (2 * hw - 1 - take) // 2
            for k in range(take):
                img.putpixel((16 - hw + off + k, y), gfx.scale(sand_col, 0.8))
            grains -= take
            surface = y
        if 0 < left < 1:                        # the falling stream
            for y in range(NECK, surface):
                if (y + i) % 3:
                    img.putpixel((15, y), sand_col)
        if mins is not None:
            gfx.text_center(img, 26, f"{int(mins)}M", sand_col, "tom-thumb")
        yield img, 0.1


# --- speed: every scene above plays slower or faster by holding its frames longer or shorter

def _paced(fn):
    @functools.wraps(fn)   # keeps .kind, .plugin and the rest that plugin.scene set
    def run(ctx, secs, **params):
        f = SPEEDS.get(ctx.settings("generative").get("speed"), 1.0)
        for img, hold in fn(ctx, secs / f, **params):
            yield img, hold * f
    return run


for _name in plugin.scenes:
    SCENES[_name] = _paced(SCENES[_name])
