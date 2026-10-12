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
    elif name in ("package", "mail", "home", "car", "cat"):
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
