"""Aquatic: a fish tank that lives. Fish hatch from eggs, grow up, lay eggs of their own
and grow old over days, and they go pale and sluggish when the room's air is stale."""
import math
import threading

import numpy as np
from PIL import Image, ImageDraw

from .. import gfx
from ..gfx import H, W
from ..kit import mix, ticks
from ..plugin import Plugin
from .tiles import read

plugin = Plugin(
    "aquatic", "A living fish tank",
    defaults={"cycle_days": 7, "max_fish": 8},
    about="A fish tank that keeps living when it's not on screen. Fish hatch from eggs, "
          "grow from fry to adults, lay eggs and grow old over about a week (the life "
          "cycle below), and the tank restocks itself if it ever empties. They feel the "
          "room: when a CO2, temperature or air quality tile is out of its comfy range "
          "(the Tiles settings), they turn pale, slow down, sink low and stop laying eggs, "
          "and the water clouds over. Open a window and they come back. Feed them from "
          "Home Assistant or a script (POST /api/play with {\"scene\": \"aquatic\", "
          "\"params\": {\"feed\": true}}); a fed fish perks up.",
    fields=[{"key": "cycle_days", "label": "Life cycle (days)", "type": "range", "min": 1, "max": 30,
             "step": 1, "help": "Egg to egg-laying adult; fish live about twice this"},
            {"key": "max_fish", "label": "Most fish (and eggs) in the tank", "type": "range",
             "min": 2, "max": 12, "step": 1}])

DAY = 86400
STEP = 600                 # the tank is simulated in ten-minute steps
CATCH_UP = 30 * DAY        # after a long power cut, only the last month is simulated
HATCH, FRY, JUVENILE = 0.07, 0.15, 0.45   # stage ends, as fractions of the life cycle
HUES = (0.07, 0.13, 0.93, 0.52, 0.3, 0.78, 0.0)   # orange, gold, pink, cyan, green, violet, red
PALE = (215, 225, 235)
LOCK = threading.Lock()    # the background task and the scene share the tank

# Facing right. X: body, T: tail and fins, E: the eye.
SPRITES = {
    "fry": ["TX"],
    "juvenile": ["T.XX.",
                 "TXXEX",
                 "T.XX."],
    "adult": ["...XX..",
              "T.XXXX.",
              "TTXXXEX",
              "T.XXXX.",
              "...XX.."],
}
SPRITES["elder"] = SPRITES["adult"]
SPEED = {"fry": 0.5, "juvenile": 0.35, "adult": 0.25, "elder": 0.15}   # pixels a frame


def stage(fish, now, cycle):
    """fry, juvenile, adult or elder, from the fish's age."""
    age = (now - fish["born"]) / (cycle * DAY)
    if age < FRY:
        return "fry"
    if age < JUVENILE:
        return "juvenile"
    return "elder" if age > fish["life"] * 0.8 else "adult"


def air_stress(ctx):
    """0 (fresh air, comfy room) to 1 (open a window), from the worst CO2, temperature or
    air quality tile. Uses the tiles plugin's thresholds; no readings means fine."""
    s = ctx.settings("tiles")
    worst = 0.0
    for item in (ctx.data("tiles") or {}).get("items") or []:
        if isinstance(item, dict) and item.get("kind") in ("co2", "temp", "aqi"):
            r = read(item, s)
            if r:
                worst = max(worst, min(1.0, r["severity"] / 3))
    return worst


def _hue(rng, near=None):
    if near is None:
        return rng.choice(HUES)
    return (near + rng.uniform(-0.04, 0.04)) % 1.0   # babies look like their parent


def _seed(tank, rng, now, cycle):
    """A new tank: a few fish of different ages and a clutch of eggs."""
    tank["next_id"] = tank.get("next_id", 1)
    for age in (0.5, 0.3, 0.1):
        _add_fish(tank, rng, now - age * cycle * DAY, _hue(rng))
    _lay(tank, rng, now, _hue(rng), 2)


def _add_fish(tank, rng, born, hue):
    tank["fish"].append({"id": tank["next_id"], "born": born, "hue": hue,
                         "life": rng.uniform(1.6, 2.4), "health": 1.0})
    tank["next_id"] += 1


def _lay(tank, rng, now, hue, n):
    x = rng.randrange(3, W - 4)
    for _ in range(n):
        tank["eggs"].append({"laid": now, "hue": hue, "x": max(1, min(W - 2, x + rng.randint(-2, 2)))})


def _step(tank, rng, t, cycle, room, stress):
    """One ten-minute step: eggs hatch, health drifts toward the air, adults lay, old fish die."""
    for egg in tank["eggs"][:]:
        if t - egg["laid"] >= HATCH * cycle * DAY:
            tank["eggs"].remove(egg)
            _add_fish(tank, rng, t, _hue(rng, egg["hue"]))
    target = 1 - stress
    for f in tank["fish"][:]:
        if (t - f["born"]) / (cycle * DAY) >= f["life"]:
            tank["fish"].remove(f)
            continue
        # Bad air bites in about two hours; getting better takes about six.
        rate = STEP / (2 * 3600) if target < f["health"] else STEP / (6 * 3600)
        f["health"] += (target - f["health"]) * min(1.0, rate)
        lay_chance = STEP / (0.4 * cycle * DAY)
        if (stage(f, t, cycle) == "adult" and f["health"] > 0.6
                and len(tank["fish"]) + len(tank["eggs"]) < room and rng.random() < lay_chance):
            space = room - len(tank["fish"]) - len(tank["eggs"])
            _lay(tank, rng, t, f["hue"], min(space, rng.randint(1, 3)))
    if not tank["fish"] and not tank["eggs"]:
        _lay(tank, rng, t, _hue(rng), 3)   # the tank restocks itself


def advance(ctx):
    """Bring the tank up to now and save it. Returns a copy of it to draw from."""
    s = ctx.settings("aquatic")
    cycle = max(1.0, float(s.get("cycle_days") or 7))
    room = max(2, int(s.get("max_fish") or 8))
    now = ctx.now().timestamp()
    stress = air_stress(ctx)
    with LOCK:
        tank = ctx.saved("aquatic")
        tank.setdefault("fish", [])
        tank.setdefault("eggs", [])
        if "last" not in tank:
            _seed(tank, ctx.rng, now, cycle)
            tank["last"] = now
            ctx.save("aquatic")
        t = max(tank["last"], now - CATCH_UP)
        steps = int((now - t) // STEP)
        for _ in range(steps):
            t += STEP
            _step(tank, ctx.rng, t, cycle, room, stress)
        if steps:
            tank["last"] = t
            ctx.save("aquatic")
        return {"fish": [dict(f) for f in tank["fish"]], "eggs": [dict(e) for e in tank["eggs"]],
                "cycle": cycle, "now": now, "stress": stress}


def fed(ctx, ids):
    """Fish that ate a pellet perk up."""
    with LOCK:
        tank = ctx.saved("aquatic")
        for f in tank.get("fish", []):
            if f["id"] in ids:
                f["health"] = min(1.0, f["health"] + 0.15 * ids.count(f["id"]))
        ctx.save("aquatic")


@plugin.task
def live(ctx, stop):
    """Keep the tank living while it's off screen, so births follow the air at the time."""
    advance(ctx)
    while not stop.wait(STEP):
        advance(ctx)


class Swimmer:
    def __init__(self, fish, now, cycle, stress, rng):
        self.id, self.stage = fish["id"], stage(fish, now, cycle)
        self.sprite = SPRITES[self.stage]
        self.w, self.h = len(self.sprite[0]), len(self.sprite)
        health = fish["health"]
        body = gfx.hsv(fish["hue"], 0.9 if self.stage != "fry" else 0.6, 1.0)
        body = mix(body, PALE, (0.9 - health) / 0.6)                  # stale air: pale
        if self.stage == "elder":
            body = gfx.scale(mix(body, (150, 150, 150), 0.4), 0.8)    # old age: grey
        self.body, self.tail = body, gfx.scale(body, 0.55)
        self.speed = SPEED[self.stage] * (0.3 + 0.7 * health)
        self.top = 3 + stress * 12                                    # sluggish fish sink
        self.bottom = H - 3 - self.h
        self.x = rng.uniform(0, W - self.w)
        self.y = self.ty = rng.uniform(self.top, self.bottom)
        self.dir = rng.choice((-1, 1))
        self.phase = rng.uniform(0, 6.28)

    def move(self, t, rng, pellets):
        speed = self.speed
        if self.stage == "fry":   # fry dart about
            speed *= 0.3 + 1.4 * max(0.0, math.sin(t * 3 + self.phase))
        food = min(pellets, key=lambda p: abs(p[0] - self.x) + abs(p[1] - self.y), default=None)
        if food:
            self.dir = 1 if food[0] > self.x + self.w / 2 else -1
            self.ty = food[1] - self.h / 2
            speed *= 1.6
        elif rng.random() < 0.004:
            self.dir = -self.dir
        if not food and rng.random() < 0.01:
            self.ty = rng.uniform(self.top, self.bottom)
        self.x += self.dir * speed
        if self.x < 0 or self.x > W - self.w:
            self.x = max(0, min(W - self.w, self.x))
            self.dir = -self.dir
        self.y += max(-speed, min(speed, (self.ty - self.y) * 0.08))
        self.y = max(0, min(self.bottom, self.y))

    def mouth(self):
        return (self.x + (self.w - 1 if self.dir > 0 else 0), self.y + self.h // 2)

    def draw(self, img, t):
        y0 = int(self.y + math.sin(t * 2 + self.phase) * 0.6 * self.speed / 0.25)
        for row, line in enumerate(self.sprite):
            for col, ch in enumerate(line if self.dir > 0 else line[::-1]):
                px, py = int(self.x) + col, y0 + row
                if ch != "." and 0 <= px < W and 0 <= py < H:
                    img.putpixel((px, py), {"X": self.body, "T": self.tail, "E": (0, 0, 0)}[ch])


def _water(stress):
    """Clear blue water that clouds green-grey as the air goes stale."""
    yy = np.arange(H, dtype=float)[:, None].repeat(W, 1)
    bg = np.zeros((H, W, 3))
    bg[..., 1] = (40 - yy).clip(8)
    bg[..., 2] = (90 - yy * 2).clip(20)
    murk = np.array([45, 52, 30], dtype=float)
    bg = bg + (murk - bg) * stress * 0.7
    return bg.astype(np.uint8)


@plugin.scene("aquatic", "generative", params={"feed": "bool"})
def aquatic(ctx, secs, feed=False):
    """The tank: fish at their ages, eggs on the sand, weed, bubbles, and pellets if fed."""
    tank = advance(ctx)
    r, stress = ctx.rng, tank["stress"]
    fish = [Swimmer(f, tank["now"], tank["cycle"], stress, r) for f in tank["fish"]]
    fish.sort(key=lambda f: f.w)   # little ones behind
    hatch = HATCH * tank["cycle"] * DAY
    weeds = [(x, r.randrange(7, 14), r.uniform(0, 6.28)) for x in (3, 9, 22, 28)]
    weed = mix((30, 150, 60), (90, 90, 40), stress)
    bubble = mix((170, 220, 255), (110, 120, 90), stress)
    rays = gfx.scale((20, 60, 120), 1 - stress * 0.7)
    bg = _water(stress)
    bubbles = []
    pellets = [[r.uniform(4, W - 5), r.uniform(-8, 0)] for _ in range(5)] if feed else []
    ate = []
    for i, t in ticks(secs, 15):
        img = Image.fromarray(bg, "RGB")
        d = ImageDraw.Draw(img)
        for x in range(W):                        # light rays wobbling from the surface
            if int(x + t * 3) % 11 == 0:
                d.line((x, 0, x - 3, 10), fill=rays)
        d.rectangle((0, H - 2, W - 1, H - 1), fill=(150, 120, 70))   # sand
        for x, h, ph in weeds:
            sway = 0.4 + 0.6 * (1 - stress)
            for k in range(h):
                s = round(math.sin(t * 1.4 * sway + ph + k * 0.4) * k / 6)
                img.putpixel(((x + s) % W, H - 3 - k), gfx.scale(weed, 1 - k * 0.03))
        for egg in tank["eggs"]:                   # eggs wiggle when they're about to hatch
            due = (tank["now"] - egg["laid"]) / hatch
            wiggle = round(math.sin(t * 9 + egg["x"])) if due > 0.8 else 0
            glow = 0.6 + 0.3 * math.sin(t * 2 + egg["x"])
            img.putpixel((egg["x"] + wiggle, H - 3), gfx.scale(mix((255, 235, 190), gfx.hsv(egg["hue"], 0.6), 0.3), glow))
        if r.random() < 0.03 + 0.12 * (1 - stress):
            bubbles.append([r.choice((5, 12, 25)) + r.uniform(-1, 1), H - 3.0])
        for b in bubbles[:]:
            b[1] -= 0.35
            if b[1] < 0:
                bubbles.remove(b)
                continue
            img.putpixel((int(b[0] + math.sin(b[1]) * 0.6) % W, int(b[1])), bubble)
        for p in pellets:
            p[1] = min(H - 3, p[1] + 0.15)
            if p[1] >= 0:
                img.putpixel((int(p[0]), int(p[1])), (200, 120, 60))
        for f in fish:
            f.move(t, r, [p for p in pellets if p[1] >= 0])
            mx, my = f.mouth()
            for p in pellets[:]:
                if p[1] >= 0 and abs(p[0] - mx) < 1.5 and abs(p[1] - my) < 1.5:
                    pellets.remove(p)
                    ate.append(f.id)
            f.draw(img, t)
        yield img, 1 / 15
    if ate:
        fed(ctx, ate)
