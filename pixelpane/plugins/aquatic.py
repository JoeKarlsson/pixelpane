"""Aquatic: a fish tank that lives. Fish hatch from eggs, grow up, lay eggs of their own
and grow old over days, and they go pale and sluggish when the room's air is stale.
Rare colors turn up as generations pass, the tank earns decorations, it follows the sun,
feeds itself, and the fish greet you or scatter when the glass is tapped."""
import math
import threading

import numpy as np
from PIL import Image, ImageDraw

from .. import astro, gfx
from ..gfx import H, W
from ..kit import mix, ticks
from ..plugin import Plugin
from .tiles import read

plugin = Plugin(
    "aquatic", "A living fish tank",
    defaults={"cycle_days": 7, "max_fish": 8, "feed_times": ["08:00", "18:00"], "alerts": True},
    about="A fish tank that keeps living when it's not on screen. Fish hatch from eggs, "
          "grow from fry to adults, lay eggs and grow old over about a week (the life "
          "cycle below), and the tank restocks itself if it ever empties. Babies take after "
          "their parents, and now and then a rare one hatches (striped, two-tone, gold or "
          "albino) and passes it on. The tank earns decorations: a starfish for the first "
          "rare fish, a castle at the third generation, a treasure chest after 20 hatchings "
          "and a snail after a whole life cycle of good air. They feel the room: when a CO2, "
          "temperature or air quality tile is out of its comfy range (the Tiles settings), "
          "they turn pale, slow down, sink low and stop laying eggs, and the water clouds "
          "over. The tank follows the sun (from the weather plugin's latitude and longitude; "
          "7:00 to 19:30 without them): the fish rest low at night. It feeds itself at the "
          "feeding times below. Home Assistant can make the fish greet you (POST /api/play "
          "with {\"scene\": \"aquatic\", \"params\": {\"greet\": true}}, say on office "
          "motion) or tap the glass to scatter them ({\"tap\": true}).",
    fields=[{"key": "cycle_days", "label": "Life cycle (days)", "type": "range", "min": 1, "max": 30,
             "step": 1, "help": "Egg to egg-laying adult; fish live about twice this"},
            {"key": "max_fish", "label": "Most fish (and eggs) in the tank", "type": "range",
             "min": 2, "max": 12, "step": 1},
            {"key": "feed_times", "label": "Feeding times", "type": "list", "placeholder": "08:00",
             "help": "One per line (HH:MM). Food drops the first time the tank shows after each"},
            {"key": "alerts", "label": "Announce rare fish and new decorations", "type": "toggle"}])

DAY = 86400
STEP = 600                 # the tank is simulated in ten-minute steps
CATCH_UP = 30 * DAY        # after a long power cut, only the last month is simulated
RECENT = 2 * 3600          # announce what happened in the last two hours, not a whole catch-up
HATCH, FRY, JUVENILE = 0.07, 0.15, 0.45   # stage ends, as fractions of the life cycle
HUES = (0.07, 0.13, 0.93, 0.52, 0.3, 0.78, 0.0)   # orange, gold, pink, cyan, green, violet, red
PALE = (215, 225, 235)
TRAITS = ("striped", "twotone", "gold", "albino")
MUTATE, INHERIT = 0.04, 0.5   # a hatchling's chance of a new rare look, and of its parent's
GOOD_AIR = 1 / 3              # stress under this counts toward the snail
LOCK = threading.Lock()       # the background task and the scene share the tank

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
FRONT = {   # looking out of the glass at you
    "fry": ["X"],
    "juvenile": [".X.",
                 "EXE",
                 ".T."],
    "adult": [".XXX.",
              "XEXEX",
              "XXXXX",
              ".XXX.",
              "..T.."],
}
FRONT["elder"] = FRONT["adult"]
SPEED = {"fry": 0.5, "juvenile": 0.35, "adult": 0.25, "elder": 0.15}   # pixels a frame

# Decorations the tank earns: (name, what it took, test on the tank's stats).
UNLOCKS = [
    ("starfish", "the first rare fish", lambda st, cycle: st["rare"] >= 1),
    ("castle", "a third generation", lambda st, cycle: st["gen"] >= 3),
    ("chest", "20 fish hatched", lambda st, cycle: st["hatched"] >= 20),
    ("snail", "a life cycle of good air", lambda st, cycle: st["best_air"] >= cycle * DAY),
]
DECOR = {   # S/s: stone, K: dark, F: flag, Y/y: gold, N/n: wood, P: pink, o: shell, g: body
    "castle": ["...F...",
               "...s...",
               "S.SsS.S",
               "SSSSSSS",
               ".SSSSS.",
               ".SKSKS.",
               ".SSSSS.",
               ".SSKSS.",
               ".SSKSS."],
    "chest": ["yYYYy",
              "nNYNn",
              "nNNNn"],
    "starfish": [".P.",
                 "PPP",
                 "P.P"],
    "snail": [".oo.",
              "gggo"],
}
DECOR_COLORS = {"S": (110, 110, 125), "s": (80, 80, 95), "K": (10, 10, 20), "F": (230, 60, 60),
                "Y": (255, 210, 0), "y": (180, 130, 0), "N": (140, 80, 30), "n": (80, 45, 15),
                "P": (255, 110, 140), "o": (170, 100, 40), "g": (190, 200, 120)}
WEEDS = (3, 9, 22, 28)


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


def daylight(ctx, now):
    """1 by day, 0 at night, easing over the hour around sunrise and sunset."""
    w = ctx.settings("weather")
    times = None
    try:
        times = astro.sun_times(now.date(), float(w["latitude"]), float(w["longitude"]))
    except (KeyError, TypeError, ValueError):
        pass
    rise, sets = times or (now.replace(hour=7, minute=0, second=0, microsecond=0),
                           now.replace(hour=19, minute=30, second=0, microsecond=0))
    hours = min((now - rise).total_seconds(), (sets - now).total_seconds()) / 3600
    return max(0.0, min(1.0, hours + 0.5))


def _hue(rng, near=None):
    if near is None:
        return rng.choice(HUES)
    return (near + rng.uniform(-0.04, 0.04)) % 1.0   # babies look like their parent


def _seed(tank, rng, now, cycle):
    """A new tank: a few fish of different ages and a clutch of eggs."""
    for age in (0.5, 0.3, 0.1):
        _add_fish(tank, rng, now - age * cycle * DAY, _hue(rng), None, 1)
    _lay(tank, rng, now, {"hue": _hue(rng), "trait": None, "gen": 0}, 2)


def _add_fish(tank, rng, born, hue, trait, gen):
    tank["fish"].append({"id": tank["next_id"], "born": born, "hue": hue, "trait": trait, "gen": gen,
                         "life": rng.uniform(1.6, 2.4), "health": 1.0})
    tank["next_id"] += 1


def _lay(tank, rng, now, parent, n):
    x = rng.randrange(3, W - 4)
    for _ in range(n):
        tank["eggs"].append({"laid": now, "hue": parent["hue"], "trait": parent.get("trait"),
                             "gen": parent.get("gen", 1) + 1,
                             "x": max(1, min(W - 2, x + rng.randint(-2, 2)))})


def _hatch(tank, rng, egg, t, events):
    trait = egg.get("trait") if rng.random() < INHERIT else None
    if not trait and rng.random() < MUTATE:
        trait = rng.choice(TRAITS)
        tank["stats"]["rare"] += 1
        events.append((t, "rare", trait))
    _add_fish(tank, rng, t, _hue(rng, egg["hue"]), trait, egg.get("gen", 1))
    tank["stats"]["hatched"] += 1
    tank["stats"]["gen"] = max(tank["stats"]["gen"], egg.get("gen", 1))


def _step(tank, rng, t, cycle, room, stress, events):
    """One ten-minute step: eggs hatch, health drifts toward the air, adults lay, old fish
    die, and the tank earns decorations."""
    stats = tank["stats"]
    for egg in tank["eggs"][:]:
        if t - egg["laid"] >= HATCH * cycle * DAY:
            tank["eggs"].remove(egg)
            _hatch(tank, rng, egg, t, events)
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
            _lay(tank, rng, t, f, min(space, rng.randint(1, 3)))
    if not tank["fish"] and not tank["eggs"]:
        _lay(tank, rng, t, {"hue": _hue(rng), "trait": None, "gen": 0}, 3)   # the tank restocks itself
    stats["air"] = stats["air"] + STEP if stress < GOOD_AIR else 0
    stats["best_air"] = max(stats["best_air"], stats["air"])
    for name, _, earned in UNLOCKS:
        if name not in tank["unlocked"] and earned(stats, cycle):
            tank["unlocked"].append(name)
            events.append((t, "unlock", name))


def _announce(ctx, events, now):
    """Rare hatchings and new decorations from the last couple of hours, as notifications."""
    state = getattr(ctx, "state", None)
    if not state or not ctx.settings("aquatic").get("alerts", True):
        return
    for t, kind, what in events:
        if now - t > RECENT:
            continue
        if kind == "rare":
            text = {"twotone": "A TWO-TONE FISH HATCHED"}.get(what, f"A RARE {what.upper()} FISH HATCHED")
            state.notify({"text": text, "icon": "fish", "color": "#ffd166"})
        else:
            why = next(why for name, why, _ in UNLOCKS if name == what)
            state.notify({"text": f"NEW IN THE TANK: {what.upper()}", "sub": why, "icon": "fish",
                          "color": "#58e0c8"})


def _new_tank(tank):
    tank.setdefault("fish", [])
    tank.setdefault("eggs", [])
    tank.setdefault("unlocked", [])
    tank.setdefault("next_id", 1)
    stats = tank.setdefault("stats", {})
    for key in ("hatched", "rare", "gen", "air", "best_air"):
        stats.setdefault(key, 0)
    stats["gen"] = max(stats["gen"], max((f.get("gen", 1) for f in tank["fish"]), default=1))


def advance(ctx):
    """Bring the tank up to now and save it. Returns a copy of it to draw from."""
    s = ctx.settings("aquatic")
    cycle = max(1.0, float(s.get("cycle_days") or 7))
    room = max(2, int(s.get("max_fish") or 8))
    when = ctx.now()
    now = when.timestamp()
    stress = air_stress(ctx)
    events = []
    with LOCK:
        tank = ctx.saved("aquatic")
        _new_tank(tank)
        if "last" not in tank:
            _seed(tank, ctx.rng, now, cycle)
            tank["last"] = now
            ctx.save("aquatic")
        t = max(tank["last"], now - CATCH_UP)
        steps = int((now - t) // STEP)
        for _ in range(steps):
            t += STEP
            _step(tank, ctx.rng, t, cycle, room, stress, events)
        if steps:
            tank["last"] = t
            ctx.save("aquatic")
        snap = {"fish": [dict(f) for f in tank["fish"]], "eggs": [dict(e) for e in tank["eggs"]],
                "unlocked": list(tank["unlocked"]), "cycle": cycle, "now": now, "stress": stress,
                "light": daylight(ctx, when)}
    _announce(ctx, events, now)
    return snap


def feeding_due(ctx):
    """True the first time the tank shows after a feeding time; marks it fed."""
    when = ctx.now()
    due = []
    for hhmm in ctx.settings("aquatic").get("feed_times") or []:
        try:
            h, m = (int(x) for x in str(hhmm).strip().split(":"))
            due.append(when.replace(hour=h, minute=m, second=0, microsecond=0).timestamp())
        except ValueError:
            continue
    latest = max((d for d in due if d <= when.timestamp()), default=None)
    with LOCK:
        tank = ctx.saved("aquatic")
        if latest is None or tank.get("fed", 0) >= latest:
            return False
        tank["fed"] = when.timestamp()
        ctx.save("aquatic")
    return True


@plugin.task
def live(ctx, stop):
    """Keep the tank living while it's off screen, so births follow the air at the time."""
    advance(ctx)
    while not stop.wait(STEP):
        advance(ctx)


class Swimmer:
    def __init__(self, fish, tank, rng):
        stress, light = tank["stress"], tank["light"]
        self.id, self.stage = fish["id"], stage(fish, tank["now"], tank["cycle"])
        self.trait = fish.get("trait")
        self.sprite = SPRITES[self.stage]
        self.w, self.h = len(self.sprite[0]), len(self.sprite)
        health = fish["health"]
        if self.trait == "albino":
            body = (240, 232, 232)
        elif self.trait == "gold":
            body = (255, 196, 30)
        else:
            body = gfx.hsv(fish["hue"], 0.9 if self.stage != "fry" else 0.6, 1.0)
        self.second = gfx.hsv(fish["hue"] + 0.5, 0.9, 1.0)          # two-tone's back half
        body = mix(body, PALE, (0.9 - health) / 0.6)                  # stale air: pale
        self.second = mix(self.second, PALE, (0.9 - health) / 0.6)
        if self.stage == "elder":
            body = gfx.scale(mix(body, (150, 150, 150), 0.4), 0.8)    # old age: grey
            self.second = gfx.scale(mix(self.second, (150, 150, 150), 0.4), 0.8)
        self.body, self.tail = body, gfx.scale(body, 0.55)
        self.eye = (230, 40, 60) if self.trait == "albino" else (0, 0, 0)
        self.speed = SPEED[self.stage] * (0.3 + 0.7 * health) * (0.35 + 0.65 * light)
        self.top = 3 + max(stress * 12, (1 - light) * 16)             # sluggish or sleepy fish sink
        self.bottom = H - 3 - self.h
        self.x = rng.uniform(0, W - self.w)
        self.y = self.ty = rng.uniform(self.top, self.bottom)
        self.dir = rng.choice((-1, 1))
        self.phase = rng.uniform(0, 6.28)
        self.goal = None     # (x, y) to swim to and look out from while greeting
        self.front = False
        self.flee = 0.0      # 1 right after a tap on the glass, easing to 0

    def move(self, t, rng, pellets):
        speed = self.speed
        if self.stage == "fry":   # fry dart about
            speed *= 0.3 + 1.4 * max(0.0, math.sin(t * 3 + self.phase))
        if self.flee > 0:
            speed = max(speed, 0.2) * (1 + 4 * self.flee)
            self.flee = max(0.0, self.flee - 1 / 30)
            self.front = False
        food = min(pellets, key=lambda p: abs(p[0] - self.x) + abs(p[1] - self.y), default=None)
        if self.goal and not self.flee:
            gx, gy = self.goal
            self.front = abs(self.x - gx) < 1 and abs(self.y - gy) < 1
            if self.front:
                return
            self.dir = 1 if gx > self.x else -1
            self.ty = gy
            speed = max(speed, 0.25) * 1.5
            step = min(speed, abs(gx - self.x))
        elif food and not self.flee:
            self.dir = 1 if food[0] > self.x + self.w / 2 else -1
            self.ty = food[1] - self.h / 2
            step = speed * 1.6
        else:
            if rng.random() < 0.004:
                self.dir = -self.dir
            if rng.random() < 0.01:
                self.ty = rng.uniform(self.top, self.bottom)
            step = speed
        self.x += self.dir * step
        if self.x < 0 or self.x > W - self.w:
            self.x = max(0, min(W - self.w, self.x))
            self.dir = -self.dir
        rise = max(step, speed)   # up and down isn't held back by being level with the goal
        self.y += max(-rise, min(rise, (self.ty - self.y) * (0.08 + 0.1 * self.flee)))
        self.y = max(0, min(self.bottom, self.y))

    def mouth(self):
        return (self.x + (self.w - 1 if self.dir > 0 else 0), self.y + self.h // 2)

    def color(self, ch, col, w, t):
        if ch == "E":
            return self.eye
        if ch == "T":
            return self.tail
        if self.trait == "striped" and col % 2 == 1 and 0 < col < w - 1:
            return gfx.scale(self.body, 0.5)
        if self.trait == "twotone" and col < w / 2:
            return self.second
        if self.trait == "gold" and col == int(t * 6 + self.phase) % (w + 6):
            return (255, 250, 210)   # a glint running along the scales
        return self.body

    def draw(self, img, t):
        if self.front:   # looking out at you, bobbing
            rows = FRONT[self.stage]
            fw = len(rows[0])
            x0 = int(self.x + (self.w - fw) / 2)
            y0 = int(self.y) + round(math.sin(t * 5 + self.phase))
        else:
            rows, fw = self.sprite, self.w
            x0 = int(self.x)
            y0 = int(self.y + math.sin(t * 2 + self.phase) * 0.6 * min(1.0, self.speed / 0.25))
        for row, line in enumerate(rows):
            for col, ch in enumerate(line):
                if ch == ".":
                    continue
                # Sprites face right; columns count from the tail so traits follow the body.
                px = x0 + (col if self.dir > 0 or self.front else fw - 1 - col)
                py = y0 + row
                if 0 <= px < W and 0 <= py < H:
                    img.putpixel((px, py), self.color(ch, col, fw, t))


def _water(stress, light):
    """Clear blue water that clouds green-grey as the air goes stale and darkens at night."""
    yy = np.arange(H, dtype=float)[:, None].repeat(W, 1)
    bg = np.zeros((H, W, 3))
    bg[..., 1] = (40 - yy).clip(8)
    bg[..., 2] = (90 - yy * 2).clip(20)
    murk = np.array([45, 52, 30], dtype=float)
    bg = (bg + (murk - bg) * stress * 0.7) * (0.3 + 0.7 * light)
    return bg.astype(np.uint8)


def _put(img, rows, x, y, colors=DECOR_COLORS, flip=False):
    for r, line in enumerate(rows):
        for c, ch in enumerate(line[::-1] if flip else line):
            if ch in colors and 0 <= x + c < W and 0 <= y + r < H:
                img.putpixel((x + c, y + r), colors[ch])


def visitors(ctx, n=4):
    """A tank of a few grown fish that remembers nothing (the aquarium when this plugin is off)."""
    now, r = ctx.now(), ctx.rng
    return {"fish": [{"id": i, "born": now.timestamp() - 3.5 * DAY, "hue": r.choice(HUES), "life": 2.0,
                      "health": 1.0} for i in range(n)],
            "eggs": [], "unlocked": [], "cycle": 7.0, "now": now.timestamp(), "stress": 0.0,
            "light": daylight(ctx, now)}


def render(ctx, secs, tank, feed=False, greet=False, tap=False):
    """The tank: fish at their ages, eggs on the sand, decorations, weed, bubbles, food."""
    r, stress, light = ctx.rng, tank["stress"], tank["light"]
    fish = [Swimmer(f, tank, r) for f in tank["fish"]]
    fish.sort(key=lambda f: f.w)   # little ones behind
    if greet:   # line up along the middle of the glass, big ones in front
        for k, f in enumerate(sorted(fish, key=lambda f: -f.w)):
            f.goal = (3 + (k % 4) * 7, min(f.bottom, 7 + (k // 4) * 9 + (k % 2) * 2))
    hatch = HATCH * tank["cycle"] * DAY
    weed = mix((30, 150, 60), (90, 90, 40), stress)
    weed = gfx.scale(weed, 0.4 + 0.6 * light)
    bubble = gfx.scale(mix((170, 220, 255), (110, 120, 90), stress), 0.5 + 0.5 * light)
    rays = gfx.scale(mix((20, 60, 120), (40, 45, 70), 1 - light), (1 - stress * 0.7) * max(0.35, light))
    sand = gfx.scale((150, 120, 70), 0.45 + 0.55 * light)
    sway = (0.4 + 0.6 * (1 - stress)) * (0.5 + 0.5 * light)
    weeds = [(x, r.randrange(7, 14), r.uniform(0, 6.28)) for x in WEEDS]
    unlocked = set(tank["unlocked"])
    snail = [r.uniform(0, W - 4), r.choice((-1, 1))]
    bg = _water(stress, light)
    bubbles = []
    pellets = [[r.uniform(4, W - 5), r.uniform(-8, 0)] for _ in range(6)] if feed else []
    for f in fish if tap else ():
        f.flee = 1.0
        f.dir = 1 if f.x + f.w / 2 >= W / 2 else -1
        f.ty = f.top if f.y < H / 2 else f.bottom
    for i, t in ticks(secs, 15):
        if greet and t > max(6.0, secs - 3):   # they've said hello: back to swimming
            for f in fish:
                f.goal, f.front = None, False
        img = Image.fromarray(bg, "RGB")
        d = ImageDraw.Draw(img)
        for x in range(W):                        # light rays wobbling from the surface
            if int(x + t * 3 * (0.4 + 0.6 * light)) % 11 == 0:
                d.line((x, 0, x - 3, 10), fill=rays)
        d.rectangle((0, H - 2, W - 1, H - 1), fill=sand)
        if "castle" in unlocked:
            colors = dict(DECOR_COLORS, F=gfx.scale(DECOR_COLORS["F"], 0.6 + 0.4 * light))
            flag = DECOR["castle"] if int(t * 2) % 2 else ["....F.."] + DECOR["castle"][1:]
            _put(img, flag, 12, H - 3 - 8, colors)
        for x, h, ph in weeds:
            for k in range(h):
                s = round(math.sin(t * 1.4 * sway + ph + k * 0.4) * k / 6)
                img.putpixel(((x + s) % W, H - 3 - k), gfx.scale(weed, 1 - k * 0.03))
        if "starfish" in unlocked:
            _put(img, DECOR["starfish"], 5, H - 5,
                 {"P": gfx.scale(DECOR_COLORS["P"], (0.75 + 0.25 * math.sin(t * 1.5)) * (0.5 + 0.5 * light))})
        if "chest" in unlocked:
            opening = t % 8 > 6.5   # the lid lifts every eight seconds and lets out a burst
            if opening:
                _put(img, DECOR["chest"][:1], 24, H - 6)
                _put(img, ["KYWYK"], 24, H - 5, {"K": (20, 12, 4), "Y": (255, 210, 0), "W": (255, 250, 210)})
                if r.random() < 0.5:
                    bubbles.append([26 + r.uniform(-1, 1), H - 6.0])
            else:
                _put(img, DECOR["chest"][:1], 24, H - 5)
            _put(img, DECOR["chest"][1:], 24, H - 4)
        for egg in tank["eggs"]:                   # eggs wiggle when they're about to hatch
            due = (tank["now"] - egg["laid"]) / hatch
            wiggle = round(math.sin(t * 9 + egg["x"])) if due > 0.8 else 0
            glow = 0.6 + 0.3 * math.sin(t * 2 + egg["x"])
            img.putpixel((egg["x"] + wiggle, H - 3), gfx.scale(mix((255, 235, 190), gfx.hsv(egg["hue"], 0.6), 0.3), glow))
        if "snail" in unlocked:
            snail[0] += snail[1] * 0.04 * (0.3 + 0.7 * light)
            if snail[0] < 0 or snail[0] > W - 4:
                snail[1] = -snail[1]
                snail[0] = max(0, min(W - 4, snail[0]))
            _put(img, DECOR["snail"], int(snail[0]), H - 4, flip=snail[1] < 0)
        if r.random() < (0.03 + 0.12 * (1 - stress)) * (0.4 + 0.6 * light):
            bubbles.append([r.choice((5, 12, 25)) + r.uniform(-1, 1), H - 3.0])
        if tap and i == 0:
            bubbles += [[r.uniform(8, 24), r.uniform(10, 26)] for _ in range(10)]
        for b in bubbles[:]:
            b[1] -= 0.35
            if b[1] < 0:
                bubbles.remove(b)
                continue
            img.putpixel((int(b[0] + math.sin(b[1]) * 0.6) % W, int(b[1])), bubble)
        if tap and t < 0.6:                        # the knock: a ring spreading from the glass
            rad = 2 + t * 30
            d.ellipse((16 - rad, 16 - rad, 16 + rad, 16 + rad),
                      outline=mix(tuple(bg[16, 16]), (200, 230, 255), 1 - t / 0.6))   # fades into the water
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
            f.draw(img, t)
        yield img, 1 / 15


@plugin.scene("aquatic", "generative", params={"feed": "bool", "greet": "bool", "tap": "bool"})
def aquatic(ctx, secs, feed=False, greet=False, tap=False):
    """Your tank as it is now. feed drops food (it also comes at the feeding times), greet
    brings the fish to the glass to look at you, tap scatters them."""
    tank = advance(ctx)
    yield from render(ctx, secs, tank, feed=feed or feeding_due(ctx), greet=greet, tap=tap)
