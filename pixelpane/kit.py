"""Scene toolkit: everything a plugin needs to draw animated 32x32 scenes.

A scene is a generator  scene(ctx, secs, **params)  that yields
(image, seconds_to_hold) until its time is up. A scene with nothing to show
returns without yielding and the player moves on.
"""
import math

import numpy as np
from PIL import Image, ImageDraw

from . import gfx
from .gfx import H, W

def ticks(secs, fps):
    """(frame index, elapsed seconds) at a fixed rate for secs seconds."""
    for i in range(max(1, int(secs * fps))):
        yield i, i / fps


def scroll_text(img, y, s, color, font="5x7", t=0.0, speed=18):
    w = gfx.text_width(s, font)
    if w <= W:
        gfx.text(img, ((W - w) // 2, y), s, color, font)
    else:
        x = W - int(t * speed) % (w + W)
        gfx.text(img, (x, y), s, color, font)


def scroll_seconds(s, font="5x7", speed=18, passes=1):
    w = gfx.text_width(s, font)
    return 0 if w <= W else passes * (w + W) / speed


def time_color(now):
    """Warm in the morning, white by day, amber in the evening, dim red at night."""
    h = now.hour
    if h >= 22 or h < 6:
        return (140, 20, 10)
    if h < 9:
        return (255, 190, 90)
    if h < 18:
        return (220, 235, 255)
    return (255, 140, 40)


# --- animated icons ----------------------------------------------------------

def animated_icon(img, name, xy, t, level=None):
    """Draw an 8x8 icon with its own motion, so no status screen is ever still.

    level (0-1), when given, drives icons that show an amount (thermometer, air).
    """
    x, y = xy
    d = ImageDraw.Draw(img)
    if name == "air":
        # air flowing past: streak speed and color follow the level (AQI)
        lv = 0.3 if level is None else max(0.0, min(1.0, level))
        col = (60, 220, 90) if lv < 0.34 else (250, 204, 21) if lv < 0.67 else (248, 113, 113)
        for row in range(4):
            off = int(t * (8 + 14 * lv) + row * 5) % 18
            for k in range(4):
                px = x - 4 + (off + k) % 17
                if x - 4 <= px < x + 12:
                    img.putpixel((px, y + 1 + row * 2), gfx.scale(col, 1 - k * 0.22))
        return
    if name not in gfx.SPRITES:
        return
    sprite = gfx.sprite(name)
    if name == "bell":                      # rings: swings side to side
        x += (-1, 0, 1, 0)[int(t * 8) % 4]
    elif name in ("package", "mail", "home", "car", "cat", "fish"):
        y += -abs(round(math.sin(t * 4) * 2))  # hops
    elif name == "alert" and int(t * 4) % 2:
        return                              # blinks
    elif name == "heart":
        beat = 1 + 0.4 * max(0, math.sin(t * 6)) ** 6
        sprite = sprite.resize((max(1, int(8 * beat)), max(1, int(8 * beat))), Image.NEAREST)
        x, y = x - (sprite.width - 8) // 2, y - (sprite.height - 8) // 2
    elif name == "music":
        y += round(math.sin(t * 5))
    img.paste(sprite, (x, y), sprite)
    if name == "thermometer":               # mercury climbs to the level and shimmers
        lv = 0.6 if level is None else max(0.0, min(1.0, level))
        top = y + 5 - int(4 * lv * min(1, t / 1.0))
        d.line((x + 4, y + 5, x + 4, top), fill=(255, 60, 60))
        if int(t * 6) % 3 == 0:
            img.putpixel((x + 4, top), (255, 200, 200))
    elif name == "washer":                  # drum spins
        a = t * 8
        for k in range(3):
            px = x + 3.5 + 1.6 * math.cos(a + k * 2.1)
            py = y + 3.5 + 1.6 * math.sin(a + k * 2.1)
            img.putpixel((int(round(px)), int(round(py))), (30, 120, 170))
    elif name == "drop":                    # a drip falls
        dy = int(t * 10) % 8
        img.putpixel((x + 3, min(y + 7 + dy // 2, H - 1)), (80, 220, 255))
    elif name == "check":                   # sparkle
        k = int(t * 5) % 4
        img.putpixel((x + 7 - k, y + k), (200, 255, 200))
    elif name == "calendar":                # page corner flips
        if int(t * 2) % 2:
            d.line((x + 6, y + 6, x + 7, y + 5), fill=(150, 150, 150))
    elif name in ("info", "lock", "camera", "door"):
        if int(t * 3) % 4 == 0:
            img.putpixel((x + 7, y), (255, 255, 255))  # glint


def gauge(img, y, level, t, color):
    """A bar that fills to level (0-1) with a moving highlight."""
    d = ImageDraw.Draw(img)
    level = max(0.0, min(1.0, float(level)))
    d.rectangle((2, y, 29, y + 2), outline=(45, 48, 62))
    w = int(26 * level * min(1.0, t / 0.8))
    if w:
        d.rectangle((3, y + 1, 3 + w, y + 1), fill=color)
        hx = 3 + int(t * 20) % max(1, w + 1)
        img.putpixel((hx, y + 1), tuple(min(255, c + 90) for c in color))


def palette(stops, n=256):
    """A smooth n-color gradient through the given RGB stops (for numpy scenes)."""
    xs = np.linspace(0, 1, len(stops))
    cols = np.array(stops, dtype=float)
    t = np.linspace(0, 1, n)
    return np.stack([np.interp(t, xs, cols[:, c]) for c in range(3)], axis=1).astype(np.uint8)


class Particles:
    """Falling things with a little sideways sway, piling up on the ground."""

    def __init__(self, rng, n, colors, speed=(0.15, 0.4), sway=0.4, pile=True, max_pile=5, big=False):
        self.rng, self.colors, self.speed, self.sway, self.big = rng, colors, speed, sway, big
        self.items = [self._new(rng.uniform(-H, 0)) for _ in range(n)]
        self.ground = [0] * W if pile else None
        self.max_pile = max_pile

    def _new(self, y=-1.0):
        r = self.rng
        return [r.uniform(0, W), y, r.uniform(*self.speed), r.uniform(0, 6.28), r.choice(self.colors)]

    def step(self, img, t):
        px = img.load()
        for p in self.items:
            p[1] += p[2]
            x = int(p[0] + math.sin(t * 2 + p[3]) * self.sway * 2) % W
            floor = H - 1 - (self.ground[x] if self.ground else 0)
            if p[1] >= floor:
                if self.ground and self.ground[x] < self.max_pile and self.rng.random() < 0.5:
                    self.ground[x] += 1
                p[:] = self._new()
                continue
            if p[1] >= 0:
                px[x, int(p[1])] = p[4]
                if self.big and x + 1 < W:
                    px[x + 1, int(p[1])] = gfx.scale(p[4], 0.6)
        if self.ground:
            for x, h in enumerate(self.ground):
                for k in range(h):
                    px[x, H - 1 - k] = gfx.scale(self.colors[(x + k) % len(self.colors)], 0.6)


class Fireworks:
    def __init__(self, rng, colors):
        self.rng, self.colors, self.rockets, self.sparks = rng, colors, [], []

    def step(self, img):
        r = self.rng
        if r.random() < 0.06 or not (self.rockets or self.sparks):
            self.rockets.append([r.uniform(6, 26), H - 1.0, r.uniform(-1.1, -0.8), r.uniform(4, 14)])
        px = img.load()
        for rk in self.rockets[:]:
            rk[1] += rk[2]
            if rk[1] <= rk[3]:
                self.rockets.remove(rk)
                col = r.choice(self.colors)
                for k in range(32):
                    a = k / 32 * 6.28
                    v = r.uniform(0.4, 0.9)
                    self.sparks.append([rk[0], rk[1], math.cos(a) * v, math.sin(a) * v, 1.0, col])
            elif 0 <= rk[1] < H:
                px[int(rk[0]), int(rk[1])] = (255, 220, 160)
        for s in self.sparks[:]:
            s[0] += s[2]
            s[1] += s[3]
            s[3] += 0.04
            s[4] -= 0.02
            if s[4] <= 0 or not (0 <= s[0] < W and 0 <= s[1] < H):
                self.sparks.remove(s)
                continue
            px[int(s[0]), int(s[1])] = gfx.scale(s[5], s[4])


# --- moods: full-panel backgrounds that show how a reading feels ---------------

# How bad a reading is, 0 (fine) to 5 (hazardous), as a color.
SEVERITY = [(60, 220, 90), (250, 204, 21), (255, 140, 40), (248, 70, 70), (190, 80, 255), (235, 50, 120)]


def mix(a, b, f):
    """A color f of the way from a to b."""
    f = max(0.0, min(1.0, f))
    return tuple(int(x + (y - x) * f) for x, y in zip(a, b))


def temp_color(f, cold=(90, 160, 255), comfy=(60, 220, 170), hot=(255, 60, 40), low=68, high=76):
    """A temperature (F) as a color: cold below low, comfy between, hot above high."""
    if f < low:
        return mix(comfy, cold, (low - f) / 12)
    if f > high:
        return mix(mix(comfy, hot, 0.45), hot, (f - high) / 14) if f > high + 2 else mix(comfy, hot, 0.45 * (f - high) / 2)
    return comfy


def outlined_text(img, xy, s, color, font="5x7", outline=(0, 0, 0)):
    """Text with a dark edge, so it reads over a busy background."""
    x, y = xy
    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        gfx.text(img, (x + dx, y + dy), s, outline, font)
    gfx.text(img, xy, s, color, font)


def outlined_center(img, y, s, color, font="5x7"):
    outlined_text(img, ((W - gfx.text_width(s, font)) // 2, y), s, color, font)


def sparkline(img, values, y0, y1, colors=None, color=(150, 160, 190)):
    """The last up-to-32 values as a little area chart between rows y0 and y1."""
    vals = [float(v) for v in values][-W:]
    if len(vals) < 2:
        return
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    x0 = W - len(vals)
    px = img.load()
    for k, v in enumerate(vals):
        top = y1 - int(round((v - lo) / span * (y1 - y0)))
        col = colors[k] if colors else color
        px[x0 + k, top] = col
        for y in range(top + 1, y1 + 1):
            px[x0 + k, y] = gfx.scale(col, 0.25)


def arrow(img, x, y, up, color):
    """A 5x3 trend triangle pointing up or down, its top-left corner at (x, y)."""
    px = img.load()
    for row, (a, b) in enumerate(((2, 2), (1, 3), (0, 4))):
        for dx in range(a, b + 1):
            px[x + dx, y + (row if up else 2 - row)] = color


_YY, _XX = np.mgrid[0:H, 0:W].astype(float)
_EDGE = np.minimum(np.minimum(_XX, W - 1 - _XX), np.minimum(_YY, H - 1 - _YY))


class Mood:
    """A dim, moving full-panel background for a reading or the weather.

    name is one of calm, frost, heat, haze, bubbles, droplets, rain, snow, stars,
    glow, wind, fog. amount (0-1) is how strong it is: more particles, faster,
    brighter. Draw the text on top of frame(t) (outlined_text keeps it readable).
    """

    def __init__(self, rng, name, amount=0.5, color=(60, 220, 170), wind=0.0):
        self.rng, self.name, self.color, self.wind = rng, name, color, wind
        self.amount = max(0.0, min(1.0, float(amount)))
        a, r = self.amount, rng
        self.noise = np.array([[r.random() for _ in range(W)] for _ in range(H)])
        self.trail = np.zeros((H, W, 3))
        n = {"calm": 5, "frost": int(2 + a * 8), "heat": int(4 + a * 12), "haze": int(3 + a * 45),
             "bubbles": int(3 + a * 22), "droplets": 0, "rain": int(6 + a * 30), "snow": int(6 + a * 24),
             "stars": 22, "glow": 0, "wind": int(5 + a * 8), "fog": int(4 + a * 8)}.get(name, 0)
        self.items = [self._spawn(fresh=True) for _ in range(n)]
        self.drops = []

    def _spawn(self, fresh=False):
        r = self.rng
        y = r.uniform(0, H) if fresh else None
        if self.name in ("heat", "bubbles", "calm"):
            return [r.uniform(0, W), H + r.uniform(0, 4) if y is None else y, r.uniform(0.15, 0.5), r.uniform(0, 6.3)]
        if self.name in ("haze", "wind", "fog"):
            return [r.uniform(-4, 0) if y is None else r.uniform(0, W), r.uniform(0, H), r.uniform(0.2, 0.6), r.uniform(0, 6.3)]
        return [r.uniform(0, W), r.uniform(-4, 0) if y is None else y, r.uniform(0.4, 1.0), r.uniform(0, 6.3)]

    def frame(self, t):
        bg = np.zeros((H, W, 3))
        getattr(self, "_" + self.name, self._calm)(bg, t)
        return Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8), "RGB")

    def _dot(self, bg, x, y, col, f=1.0):
        xi, yi = int(x) % W, int(y)
        if 0 <= yi < H:
            bg[yi, xi] = np.maximum(bg[yi, xi], np.array(col) * f)

    # -- the moods --
    def _calm(self, bg, t):
        """A slow breathing glow from the bottom and a few motes floating up."""
        glow = (0.22 + 0.08 * math.sin(t * 1.4)) * np.clip(1 - np.hypot(_XX - 15.5, (_YY - 34) * 1.3) / 30, 0, 1)
        bg += glow[..., None] * np.array(self.color)
        for p in self.items:
            p[1] -= p[2] * 0.4
            if p[1] < -1:
                p[:] = self._spawn()
            self._dot(bg, p[0] + math.sin(t + p[3]), p[1], self.color, 0.35)

    def _glow(self, bg, t):
        """A warm light from the top-left corner (the sun)."""
        glow = (0.16 + 0.05 * math.sin(t * 1.1)) * np.clip(1 - np.hypot(_XX - 6, _YY - 6) / 26, 0, 1) ** 1.5
        bg += glow[..., None] * np.array(self.color)

    def _frost(self, bg, t):
        """Ice creeping in from the edges, with a sparkle and a few snowflakes."""
        reach = 0.6 + self.amount * 6 * min(1.0, t / 1.5) + 0.4 * math.sin(t * 0.8)
        frosted = _EDGE + self.noise * 2.5 < reach
        shade = np.where(frosted, 0.55 - 0.3 * _EDGE / max(reach, 1), 0)[..., None]
        bg += shade * np.array((120, 170, 255))
        ys, xs = np.nonzero(frosted)
        if len(xs) and int(t * 10) % 3 == 0:
            k = self.rng.randrange(len(xs))
            bg[ys[k], xs[k]] = (220, 240, 255)
        for p in self.items:
            p[1] += p[2] * 0.3
            if p[1] > H:
                p[:] = self._spawn()
            self._dot(bg, p[0] + math.sin(t * 2 + p[3]), p[1], (200, 220, 255), 0.5)

    def _heat(self, bg, t):
        """Warmth rising from the bottom, shimmering, with embers floating up."""
        a = self.amount
        grad = (0.06 + 0.4 * a) * (_YY / (H - 1)) ** 1.6
        bg += grad[..., None] * np.array(mix((255, 150, 40), (255, 50, 20), a))
        for y in range(H):  # heat haze: each row wobbles sideways
            shift = int(round(math.sin(y * 0.6 + t * 7) * a * 1.4))
            if shift:
                bg[y] = np.roll(bg[y], shift, axis=0)
        for p in self.items:
            p[1] -= p[2] * (0.5 + a)
            if p[1] < -1:
                p[:] = self._spawn()
            flicker = 0.5 + 0.5 * math.sin(t * 9 + p[3])
            self._dot(bg, p[0] + math.sin(t * 3 + p[3]) * 0.8, p[1], (255, 170, 60), 0.3 + 0.5 * flicker)

    def _haze(self, bg, t):
        """Air: clear and sparkling when good, thick drifting smog when bad."""
        a = self.amount
        tint = mix((8, 22, 55), (60, 40, 18), a / 0.7) if a < 0.7 else mix((60, 40, 18), (55, 12, 45), (a - 0.7) / 0.3)
        wave = 0.8 + 0.2 * np.sin(_XX * 0.3 + _YY * 0.15 + t * (0.5 + a))
        bg += wave[..., None] * np.array(tint) * (0.6 + 0.6 * a)
        speed = 0.3 + a * 1.2
        col = mix((220, 235, 255), (170, 120, 80), a * 1.4)
        for p in self.items:
            p[0] += p[2] * speed
            if p[0] > W + 1:
                p[:] = self._spawn()
            f = 0.55 if a > 0.3 else 0.25 + 0.6 * max(0.0, math.sin(t * 3 + p[3])) ** 4  # clean air twinkles
            self._dot(bg, p[0], p[1] + math.sin(t * 1.5 + p[3]) * (0.5 + a), col, f)

    def _bubbles(self, bg, t):
        """Bubbles rising: a few clear ones when fresh, many murky ones when stuffy."""
        a = self.amount
        bg += np.array(mix((5, 18, 30), (35, 38, 20), a)) * (0.7 + 0.3 * math.sin(t))
        col = mix((120, 210, 255), (160, 160, 100), a)
        for p in self.items:
            p[1] -= p[2] * (0.4 + a)
            if p[1] < -1:
                p[:] = self._spawn()
            x = p[0] + math.sin(t * 2 + p[3])
            self._dot(bg, x, p[1], col, 0.6)
            if p[2] > 0.35:  # bigger bubbles are two pixels
                self._dot(bg, x + 1, p[1], col, 0.35)

    def _droplets(self, bg, t):
        """Condensation: drops bead up, then run down leaving a trail."""
        a, r = self.amount, self.rng
        self.trail *= 0.94
        if r.random() < 0.12 + a * 0.5:
            self.drops.append([r.uniform(0, W), r.uniform(0, H * 0.6), 0.0, r.uniform(0.5, 2.5)])
        for d in self.drops[:]:
            d[3] -= 0.1
            if d[3] < 0:
                d[2] = min(1.2, d[2] + 0.08)  # heavy enough: it runs
            d[1] += d[2]
            if d[1] >= H:
                self.drops.remove(d)
                continue
            yi, xi = int(d[1]), int(d[0]) % W
            self.trail[yi, xi] = (70, 150, 230)
            bg[yi, xi] = (150, 210, 255)
        bg += self.trail * 0.75 + np.array((6, 16, 26)) * (0.5 + a)

    def _rain(self, bg, t):
        """Rain across the whole panel, slanted by the wind."""
        slant = max(-1.5, min(1.5, self.wind))
        for p in self.items:
            p[1] += 1.2 + p[2] * (1 + self.amount)
            p[0] += slant * 0.6
            if p[1] > H:
                p[:] = self._spawn()
            for k in range(3):
                self._dot(bg, p[0] - slant * k * 0.6, p[1] - k, (70, 140, 255), 0.9 - k * 0.3)

    def _snow(self, bg, t):
        for p in self.items:
            p[1] += p[2] * 0.35
            p[0] += self.wind * 0.3
            if p[1] > H:
                p[:] = self._spawn()
            self._dot(bg, p[0] + math.sin(t * 2 + p[3]) * 0.7, p[1], (220, 225, 255), 0.6 + 0.4 * p[2])

    def _stars(self, bg, t):
        for k, p in enumerate(self.items):
            f = 0.25 + 0.7 * max(0.0, math.sin(t * (1 + p[2]) + p[3])) ** 3
            self._dot(bg, p[0], (p[1] * 7 + k * 3) % H, (200, 200, 255), f)

    def _wind(self, bg, t):
        speed = 0.8 + self.amount * 2.5
        for p in self.items:
            p[0] += p[2] * speed
            if p[0] > W + 4:
                p[:] = self._spawn()
            for k in range(4):
                self._dot(bg, p[0] - k, p[1], (170, 180, 210), 0.85 - k * 0.18)

    def _fog(self, bg, t):
        band = 0.5 + 0.5 * np.sin(_YY * 0.5 + np.sin(_XX * 0.2 + t * 0.6) * 1.5 + t * 0.3)
        bg += (band * 0.16 * (0.6 + self.amount))[..., None] * np.array((170, 175, 190))
