"""Generative art: fire, plasma, Game of Life, matrix rain, starfield."""
import math

import numpy as np
from PIL import Image

from .. import gfx
from ..gfx import H, W
from ..kit import palette, ticks
from ..plugin import Plugin

plugin = Plugin(
    "generative", "Endless generative art",
    defaults={"scenes": ["fire", "plasma", "life", "matrix_rain", "starfield"]},
    about="Art that's computed, not stored: a fire, a plasma of drifting color, "
          "Conway's Game of Life, matrix rain and a starfield. The playlist's "
          "\"generative\" slot picks one of the scenes you tick below.",
    fields=[{"key": "scenes", "label": "Scenes to pick from", "type": "choices",
             "options": ["fire", "plasma", "life", "matrix_rain", "starfield"]}])


@plugin.picker("generative")
def pick(ctx):
    """The playlist's "generative" slot: one of the ticked scenes."""
    return ctx.rng.choice(ctx.settings("generative").get("scenes") or ["fire"])


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


# --- seasonal ----------------------------------------------------------------
