"""Seasonal: a scene per season and holiday, picked by date."""
import math

from PIL import ImageDraw

from .. import gfx
from ..gfx import H, W
from ..kit import Fireworks, Particles, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

plugin = Plugin("seasonal", "Seasons, holidays and a birthday",
                defaults={"holiday_share": 0.7, "birthday": None})


LEAVES = [(230, 90, 10), (200, 40, 10), (240, 170, 20), (150, 70, 20)]


@plugin.scene("autumn", "seasonal")
def autumn(ctx, secs, caption=None):
    leaves = Particles(ctx.rng, 18, LEAVES, (0.12, 0.3), 0.6, max_pile=4, big=True)
    for i, t in ticks(secs, 15):
        img = gfx.blank((4, 2, 10))
        leaves.step(img, t)
        if caption:
            scroll_text(img, 10, caption, (255, 170, 60), "5x7", t, 16)
        yield img, 1 / 15


@plugin.scene("thanksgiving", "seasonal")
def thanksgiving(ctx, secs):
    yield from autumn(ctx, secs, caption="HAPPY THANKSGIVING")


@plugin.scene("winter", "seasonal")
def winter(ctx, secs):
    snow = Particles(ctx.rng, 22, [(255, 255, 255), (200, 220, 255)], (0.1, 0.3), 0.4, max_pile=4)
    for i, t in ticks(secs, 15):
        img = gfx.blank((0, 0, 12))
        gfx.paste(img, "snowman", (2, H - 13))
        snow.step(img, t)
        yield img, 1 / 15


@plugin.scene("spring", "seasonal")
def spring(ctx, secs):
    rng = ctx.rng
    flowers = [(x, rng.randint(7, 15), rng.choice([(255, 90, 160), (255, 210, 0), (160, 70, 230),
                                                   (255, 255, 255), (255, 120, 0)]))
               for x in (3, 9, 16, 22, 28)]
    rain = Particles(rng, 10, [(70, 130, 255)], (0.6, 0.9), 0.0, pile=False)
    bee = [0.0, 10.0]
    for i, t in ticks(secs, 15):
        img = gfx.blank((0, 5, 15) if t < 4 else (20, 50, 90))
        d = ImageDraw.Draw(img)
        if t < 4:
            rain.step(img, t)
        else:
            gfx.paste(img, "sun", (19, 1))
        grow = min(1.0, t / 5)
        for x, h, col in flowers:
            top = H - 1 - int(h * grow)
            d.line((x, H - 1, x, top), fill=(40, 170, 50))
            if grow >= 1:
                for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
                    img.putpixel((x + dx, top + dy), col)
                img.putpixel((x, top), (255, 230, 120))
        if t > 5:
            bee[0] = (bee[0] + 0.5) % W
            bee[1] = 12 + math.sin(t * 3) * 3
            img.putpixel((int(bee[0]), int(bee[1])), (255, 220, 0) if i % 2 else (40, 40, 40))
        d.line((0, H - 1, W - 1, H - 1), fill=(30, 120, 40))
        yield img, 1 / 15


@plugin.scene("summer", "seasonal")
def summer(ctx, secs):
    night = not 6 <= ctx.now().hour < 20
    rng = ctx.rng
    flies = [[rng.uniform(0, W), rng.uniform(8, 26), rng.uniform(0, 6.28)] for _ in range(8)]
    for i, t in ticks(secs, 15):
        if night:
            img = gfx.blank((0, 0, 10))
            gfx.paste(img, "moon", (19, 1))
            d = ImageDraw.Draw(img)
            d.rectangle((0, 28, W - 1, H - 1), fill=(5, 35, 10))
            for f in flies:
                f[0] = (f[0] + math.sin(t + f[2]) * 0.3) % W
                f[1] = min(27, max(6, f[1] + math.cos(t * 1.3 + f[2]) * 0.2))
                b = max(0.0, math.sin(t * 2 + f[2] * 3))
                if b > 0.2:
                    img.putpixel((int(f[0]), int(f[1])), gfx.scale((200, 255, 60), b))
        else:
            img = gfx.blank((40, 120, 220))
            gfx.paste(img, "sun", (2, 2))
            px = img.load()
            for x in range(W):
                for row, col in ((0, (20, 80, 200)), (1, (10, 50, 160)), (2, (5, 30, 110))):
                    top = 22 + row * 3 + int(math.sin(x * 0.4 + t * (2 - row * 0.5) + row) * 1.5)
                    for y in range(max(0, top), H):
                        px[x, y] = col
        yield img, 1 / 15


@plugin.scene("halloween", "seasonal")
def halloween(ctx, secs):
    rng = ctx.rng
    bats = [[rng.uniform(-30, 0), rng.uniform(2, 12), rng.uniform(0.3, 0.7)] for _ in range(3)]
    pumpkin = gfx.sprite("pumpkin")
    for i, t in ticks(secs, 12):
        img = gfx.blank((8, 0, 16))
        gfx.paste(img, "moon", (20, 1))
        glow = 0.55 + 0.45 * rng.random()
        face = pumpkin.copy()
        px = face.load()
        for y in range(face.height):
            for x in range(face.width):
                r, g, b, a = px[x, y]
                if a and (r, g, b) == gfx.PALETTE["Y"]:
                    px[x, y] = gfx.scale((255, 220, 40), glow) + (255,)
        img.paste(face, (8, H - face.height), face)
        for b in bats:
            b[0] += b[2]
            if b[0] > W + 8:
                b[0], b[1] = rng.uniform(-30, -8), rng.uniform(2, 12)
            gfx.paste(img, "bat1" if (i // 3) % 2 else "bat2", (int(b[0]), int(b[1] + math.sin(t * 4 + b[2]) * 2)))
        yield img, 1 / 12


@plugin.scene("christmas", "seasonal")
def christmas(ctx, secs):
    rng = ctx.rng
    snow = Particles(rng, 10, [(255, 255, 255)], (0.1, 0.25), 0.4, pile=False)
    tree = []
    for y in range(5, 27):
        half = 1 + (y - 5) * 11 // 22 - (2 if y in (12, 13, 19, 20) else 0)
        tree.append((y, max(1, half)))
    lights = []
    for y, half in tree[2::3]:
        for _ in range(max(1, half // 3)):
            lights.append((16 + rng.randint(-half + 1, half - 1), y, rng.random()))
    for i, t in ticks(secs, 10):
        img = gfx.blank((0, 0, 12))
        d = ImageDraw.Draw(img)
        for y, half in tree:
            d.line((16 - half, y, 16 + half, y), fill=(20, 120, 40))
        d.rectangle((15, 27, 17, 30), fill=(110, 60, 20))
        star = (255, 230, 60) if i % 10 < 7 else (255, 255, 200)
        for x, y in ((16, 2), (15, 3), (16, 3), (17, 3), (16, 4)):
            img.putpixel((x, y), star)
        for x, y, ph in lights:
            if math.sin(t * 3 + ph * 6.28) > -0.3:
                img.putpixel((x, y), gfx.hsv(ph + int(t) * 0.1, 0.9, 1))
        snow.step(img, t)
        yield img, 0.1


@plugin.scene("new_year", "seasonal")
def new_year(ctx, secs):
    now = ctx.now()
    year = str(now.year + 1 if now.month == 12 else now.year)
    fw = Fireworks(ctx.rng, [(255, 215, 0), (255, 255, 255), (255, 80, 200), (80, 200, 255)])
    for i, t in ticks(secs, 20):
        img = gfx.blank()
        fw.step(img)
        gfx.text_center(img, 24, year, gfx.hsv(t / 4, 0.6, 1), "5x7")
        yield img, 0.05


@plugin.scene("july4", "seasonal")
def july4(ctx, secs):
    fw = Fireworks(ctx.rng, [(230, 30, 30), (255, 255, 255), (40, 90, 255)])
    for i, t in ticks(secs, 20):
        img = gfx.blank()
        fw.step(img)
        yield img, 0.05


def _heart(img, cx, cy, size, color):
    px = img.load()
    for y in range(H):
        for x in range(W):
            u, v = (x - cx) / size, -(y - cy) / size
            if (u * u + v * v - 1) ** 3 - u * u * v ** 3 <= 0:
                px[x, y] = color


@plugin.scene("valentines", "seasonal")
def valentines(ctx, secs):
    rng = ctx.rng
    floaters = [[rng.uniform(0, W), rng.uniform(0, H + 10)] for _ in range(5)]
    for i, t in ticks(secs, 12):
        img = gfx.blank((10, 0, 6))
        for f in floaters:
            f[1] -= 0.4
            if f[1] < -8:
                f[:] = [rng.uniform(0, W - 8), H + 2]
            gfx.paste(img, "heart", (int(f[0]), int(f[1])))
        beat = 1 + 0.12 * max(0, math.sin(t * 6)) ** 4
        _heart(img, 16, 15, 9 * beat, (230, 20, 60))
        yield img, 1 / 12


@plugin.scene("st_patricks", "seasonal")
def st_patricks(ctx, secs):
    rng = ctx.rng
    for i, t in ticks(secs, 12):
        img = gfx.blank((0, 8, 0))
        for _ in range(4):
            img.putpixel((rng.randrange(W), rng.randrange(H)), (255, 215, 0))
        gfx.paste(img, "shamrock", (10, 10 + int(math.sin(t * 2) * 2)))
        yield img, 1 / 12


@plugin.scene("birthday", "seasonal")
def birthday(ctx, secs):
    name = str((ctx.settings("seasonal").get("birthday") or {}).get("name", "")).upper()
    msg = f"HAPPY BIRTHDAY {name}!" if name else "HAPPY BIRTHDAY!"
    secs = max(secs, scroll_seconds(msg, "5x7", 16, passes=2))
    confetti = Particles(ctx.rng, 16, [gfx.hsv(k / 8) for k in range(8)], (0.2, 0.5), 0.5, pile=False)
    cake = gfx.sprite("cake")
    cx, cy = (W - cake.width) // 2, H - cake.height
    for i, t in ticks(secs, 15):
        img = gfx.blank((6, 0, 14))
        confetti.step(img, t)
        img.paste(cake, (cx, cy), cake)
        for k, x in enumerate((cx + 4, cx + 9, cx + 14)):
            img.putpixel((x, cy + 3), (120, 200, 255))
            img.putpixel((x, cy + 2), (120, 200, 255))
            flicker = (i + k * 2) % 4
            img.putpixel((x, cy + 1), (255, 200, 0) if flicker else (255, 120, 0))
            if flicker > 1:
                img.putpixel((x, cy), (255, 240, 150))
        w = gfx.text_width(msg, "5x7")
        x0 = W - int(t * 16) % (w + W)
        f = gfx.font("5x7")
        d = ImageDraw.Draw(img)
        for j, ch in enumerate(msg):
            d.text((x0 + j * 5, 2), ch, font=f, fill=gfx.hsv(j / len(msg) + t / 3))
        yield img, 1 / 15
