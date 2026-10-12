"""Make a GIF from a text prompt with any OpenAI-compatible chat model.

The model doesn't draw pixels one by one (chat models are bad at that). It writes
a small animation as JSON: a background, layers (shapes, pixel sprites, text)
that can move, bob, sway, spin, blink or pulse, and looping effects such as
snow or stars. render() turns that into a seamless 32x32 loop, which is saved to
the library like an upload.
"""
from __future__ import annotations

import base64
import io
import json
import math
import random
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import date

from PIL import Image, ImageDraw

from . import gfx, seasons
from .gfx import H, W

SPEC = """You design looping pixel-art animations for a 32x32 LED panel seen from across a room
through a two-way mirror. Reply with ONE compact JSON object (no comments, no prose).

FORMAT
{"name": "3-5 word title", "category": "one lowercase word: animal, space, food, nature, retro, weather, holiday, sports, abstract...",
 "seconds": 2-4 (one loop), "fps": 8-15,
 "background": "#rrggbb" or ["#top", "#bottom"],
 "effects": [{"type": "stars|snow|rain|confetti|bubbles|sparkles|fire", "color": "#rrggbb", "count": 1-60}],
 "layers": [...]}   drawn in order, later on top
Layer types (coordinates 0-31, (0,0) top left; shapes may start off the panel, down to -32):
 {"type":"rect","x":0,"y":0,"w":4,"h":4,"color":"#rrggbb","fill":true}
 {"type":"circle","x":16,"y":16,"r":5,"color":"#rrggbb","fill":true}
 {"type":"line","x1":0,"y1":31,"x2":31,"y2":31,"color":"#rrggbb"}
 {"type":"pixels","points":[[x,y],...],"color":"#rrggbb"}
 {"type":"sprite","x":10,"y":8,"palette":{"o":"#rrggbb",...},"frames":[[rows...],[rows...]],"scale":1}
   rows are strings, one character per pixel, "." transparent, every row of a frame the same length.
   Frames are animation poses (legs, wings, flames); they cycle automatically every ~0.15 s.
 {"type":"text","text":"HI","y":24,"color":"#rrggbb","font":"tom-thumb|4x6|5x7"}   (centered unless x is given)
 {"type":"group","layers":[...],"motion":{...}}   parts that move together
Any layer can have "motion" (all optional):
 "move":[dx,dy]   travel this many pixels over one loop; add "wrap":true to leave one side and re-enter the other
 "path":[[x,y],...]   a closed route of offsets it follows once per loop at steady speed (back to the start)
 "phase":-0.2   start later along its motion: same motion + negative phase = trailing behind (chases, trains)
 "face":true   mirror the layer when it travels left (draw sprites facing RIGHT)
 "bob":3, "sway":2   up-down / side-to-side swing in pixels; "bounce":true makes bob hop off the ground
 "swing":30, "pivot":[x,y]   rock back and forth by that many degrees around a point (tails, pendulums, wings).
   pivot is in panel coordinates (like x and y), on the joint where the part meets the body,
   e.g. a tail drawn at x 24-26, y 14-20 that joins the body at its bottom has pivot [24,20].
 "spin":360   degrees per loop around "pivot" (or its own middle)
 "blink":true, "pulse":true   on/off, or a soft glow
 "times":3   repeat bob/sway/swing/blink/pulse that many times per loop

WHAT MAKES IT GOOD
- The subject is a sprite 12-20 px tall, with a dark outline, 3-6 bold saturated colors, and a clear
  silhouette. Eyes are single bright or black pixels. Spend your detail here, not on the background.
- The motion IS the idea: whatever the prompt says happens (chasing, launching, swimming, wagging)
  must visibly happen, big enough to see on 32 pixels. Things that travel use move or path; legs,
  wings and flames get 2-4 frames; a living thing never just sits still.
- Keep parts attached: a tail or flame that moves on its own body goes in a group with that body and
  swings around a pivot at the joint, so it never floats away. Draw the part pointing AWAY from
  the body (a tail out to the side or up and back) and keep swing to 15-35 degrees, so it never
  sweeps across the body.
- Chases and followers: give both the SAME start position and motion, the follower a negative phase.
  Small things that matter (a ball, a laser dot, a bee) are at least 3x3 and drawn AFTER, on top.
- Something that wraps across the panel stays under 24 px wide, or two copies show at once.
- It loops forever: paths return to their start, moves wrap or come back, nothing jumps at the seam.
- Dark, simple background; ground or horizon as one or two rects; at most one effect unless asked.
- Text only if the prompt asks for words.

EXAMPLE for "a puppy chasing a ball across the grass" (the puppy trails the bouncing ball):
{"name":"Puppy Chases Ball","category":"animal","seconds":3,"fps":12,"background":["#0b1d3a","#24426b"],"effects":[{"type":"stars","color":"#ffffff","count":10}],"layers":[{"type":"rect","x":0,"y":26,"w":32,"h":6,"color":"#2f7a32"},{"type":"line","x1":0,"y1":26,"x2":31,"y2":26,"color":"#5fbf4a"},{"type":"circle","x":4,"y":22,"r":2,"color":"#ff3a3a","motion":{"move":[32,0],"wrap":true,"bob":5,"bounce":true,"times":3}},{"type":"sprite","x":-2,"y":17,"palette":{"o":"#3a1f0a","b":"#d08c46","w":"#f6e2c0","k":"#000000"},"frames":[["........oo...",".......obbo..","o.....obbkbo.","bo...obbbbbww",".bo.obbbbbbo.","..obbbbbbbo..","..obbbbbbbo..","..ob.o..ob.o.","..o..o..o..o."],["........oo...","..o....obbo..",".obo..obbkbo.","..bo.obbbbbww","...obbbbbbbo.","..obbbbbbbo..","..obbbbbbbo..","...obo...obo.","...o.o...o.o."]],"motion":{"move":[32,0],"wrap":true,"phase":-0.28,"bob":1,"bounce":true,"times":6}}]}
"""

IDEA = ("Invent one delightful idea for the panel yourself, from the world of {topic}. "
        "It's {when}, which you may nod to or ignore. Surprise me: skip the obvious first "
        "idea. Then design it.")
TOPICS = ["animals", "outer space", "food and drink", "weather", "the ocean", "retro video games",
          "robots and machines", "music", "sports", "plants and gardens", "vehicles", "birds",
          "insects", "cozy home life", "cities at night", "mythical creatures", "dinosaurs",
          "optical illusions and patterns", "camping and the outdoors", "the season and its holidays"]

EFFECTS = {"stars", "snow", "rain", "confetti", "bubbles", "sparkles", "fire"}
FONTS = {"tom-thumb", "4x6", "5x7", "5x8", "6x10"}


class GenerateError(Exception):
    pass


# --- talking to the model ------------------------------------------------------

PROVIDERS = {"openai": "OpenAI-compatible (LiteLLM, OpenRouter, OpenAI, Ollama...)",
             "anthropic": "Anthropic (Claude API)"}
ANTHROPIC_URL = "https://api.anthropic.com"

REVIEW = """Above is how your design actually rendered, 4x bigger. Top row: {n} frames in a
row ({ms} ms apart), to judge fast motion. Bottom row: {n} frames spread evenly over the whole
loop. Look hard at it against the request "{prompt}":
- Can you tell what the subject is at a glance? Is it big and clear enough?
- Does the requested action visibly happen, the right way round (who moves, who follows,
  which way things face)? Is anything hidden behind another layer, too small, or off the panel?
- Do parts stay attached as they move? A swinging part must turn around its joint: if it
  sweeps across the body or flies off, fix its pivot, point it away from the body, or make the
  swing smaller (15-35 degrees).
- Does the loop look smooth, with no pop at the seam?
Fix only what is actually wrong and keep everything that works; don't redesign a good
animation, and don't just make things bigger. Keep the subject 12-22 px wide; anything that
wraps must be narrower than 24 px or two copies show at once.
Reply with the design as ONE JSON object in the same format (no prose), unchanged if it is
already good."""


def _chat(settings: dict, system: str, turns: list, timeout: float) -> str:
    """One reply from the model. turns: [(role, [str or PNG bytes, ...]), ...]."""
    provider = settings.get("provider") or "openai"
    key, model = settings.get("api_key"), settings.get("model")
    base = (settings.get("base_url") or (ANTHROPIC_URL if provider == "anthropic" else "")).rstrip("/")
    if not base or not model:
        raise GenerateError("set the generator's server and model first (Plugins, generator)")
    if provider == "anthropic":
        def part(x):
            if isinstance(x, bytes):
                return {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                    "data": base64.b64encode(x).decode()}}
            return {"type": "text", "text": x}
        url = (base[:-3] if base.endswith("/v1") else base) + "/v1/messages"
        headers = {"x-api-key": key or "", "anthropic-version": "2023-06-01"}
        body = {"model": model, "max_tokens": 8000, "temperature": 0.8, "system": system,
                "messages": [{"role": r, "content": [part(x) for x in xs]} for r, xs in turns]}
    else:
        def part(x):
            if isinstance(x, bytes):
                return {"type": "image_url",
                        "image_url": {"url": "data:image/png;base64," + base64.b64encode(x).decode()}}
            return {"type": "text", "text": x}

        def content(xs):   # plain text stays a plain string: the widest-supported form
            return xs[0] if len(xs) == 1 and isinstance(xs[0], str) else [part(x) for x in xs]
        url = base + "/chat/completions"
        headers = {"Authorization": "Bearer " + key} if key else {}
        body = {"model": model, "max_tokens": 8000, "temperature": 0.8,
                "messages": [{"role": "system", "content": system}]
                + [{"role": r, "content": content(xs)} for r, xs in turns]}
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise GenerateError(f"the model server said {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GenerateError(f"could not reach {base}: {getattr(e, 'reason', e)}") from e
    try:
        if provider == "anthropic":
            return "".join(c.get("text", "") for c in reply["content"] if c.get("type") == "text")
        return reply["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        raise GenerateError("the model's reply had no message") from e


def contact_sheet(frames, n: int = 8, zoom: int = 4) -> bytes:
    """What the model reviews, as PNG: the top row is n frames in a row (fast motion such
    as wags and flaps), the bottom row n frames spread over the whole loop."""
    k = min(n, len(frames))
    rows = [[frames[i][0] for i in range(k)], [frames[int(i * len(frames) / k)][0] for i in range(k)]]
    gap = 3
    cell = W * zoom + gap
    sheet = Image.new("RGB", (k * cell - gap, 2 * cell - gap), (90, 90, 90))
    for r, row in enumerate(rows):
        for i, f in enumerate(row):
            sheet.paste(f.resize((W * zoom, H * zoom), Image.NEAREST), (i * cell, r * cell))
    buf = io.BytesIO()
    sheet.save(buf, "PNG")
    return buf.getvalue()


def ask(settings: dict, prompt: str, when: str, timeout: float = 150, log=None,
        base: dict | None = None, change: str = "") -> dict:
    """Design an animation for prompt (or the model's own idea when prompt is empty), or
    with base and change, rework an earlier design ("make the cat bigger").

    Draft, render, then (if review is on) show the model its own render and let it fix
    what it sees. Returns {"spec", "frames", "draft"}; frames are rendered and ready."""
    say = log or (lambda msg: None)
    user = prompt.strip() or IDEA.format(when=when, topic=random.choice(TOPICS))
    # A fresh tag each time: gateways like LiteLLM cache identical requests, which
    # would make Try again and Surprise me repeat themselves.
    tag = f"\n\n(variation {uuid.uuid4().hex[:8]})"
    turns = [("user", [user + tag])]
    if base is not None:
        turns = [("user", [user]), ("assistant", [json.dumps(base, separators=(",", ":"))]),
                 ("user", [f"Change it: {change.strip()}\nKeep everything else as it is. Reply with "
                           f"the whole updated design as ONE JSON object.{tag}"])]
    say("drafting")
    for attempt in (1, 2):   # one retry: an occasional reply is broken JSON
        try:
            spec = parse(_chat(settings, SPEC, turns, timeout))
            frames = render(spec)
            break
        except GenerateError as e:
            if attempt == 2 or "server" in str(e) or "reach" in str(e):
                raise
            say(f"draft unusable ({e}), asking again")
    draft, checked = spec, False
    if settings.get("review", True) is not False:
        say("reviewing")
        try:
            asked = prompt.strip() or "your own idea"
            if change.strip():
                asked += f", changed: {change.strip()}"
            fixed = parse(_chat(settings, SPEC, turns + [
                ("assistant", [json.dumps(spec, separators=(",", ":"))]),
                ("user", [contact_sheet(frames), REVIEW.format(n=min(8, len(frames)), ms=round(frames[0][1] * 1000),
                                                       prompt=asked)]),
            ], timeout))
            frames, spec, checked = render(fixed), fixed, True
        except GenerateError as e:   # a failed review keeps the draft rather than losing it
            say(f"review skipped: {e}")
    return {"spec": spec, "frames": frames, "draft": draft, "checked": checked}


def parse(text: str) -> dict:
    """The JSON object in a reply, even wrapped in prose or a code fence, and even with
    a bracket or two missing at the end (models slip on long nested JSON)."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = text.find("{")
    if start < 0:
        raise GenerateError("the model didn't answer with JSON")
    stack, in_str, esc = [], False, False
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
            if not stack:
                return _load(text[start:i + 1])
    # ran out of text with brackets still open: close them and try
    tail = text[start:].rstrip().rstrip(",")
    if in_str:
        tail += '"'
    return _load(tail + "".join(reversed(stack)), cut=True)


def _load(s: str, cut: bool = False) -> dict:
    try:
        spec = json.loads(s)
    except json.JSONDecodeError as e:
        raise GenerateError(("the model's JSON was cut off" if cut else "the model's JSON didn't parse")
                            + f" ({e.msg})") from e
    if not isinstance(spec, dict):
        raise GenerateError("the model didn't answer with a JSON object")
    return spec


# --- drawing -------------------------------------------------------------------

def _num(v, default, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) else max(lo, min(hi, v))


def _color(v, default=(255, 255, 255)):
    return gfx.hex_color(str(v or "").lstrip("#"), default) if v else default


# Layers draw on a canvas with a 32-pixel margin on every side, so a shape that starts
# off the panel and travels on (or wraps around) is not clipped before it moves.
PAD = 32
BIG = W + 2 * PAD


def _draw_static(layer: dict, frame: int) -> Image.Image | None:
    """One layer, still, in panel coordinates on the padded canvas."""
    img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    kind, col = layer.get("type"), _color(layer.get("color")) + (255,)
    fill = layer.get("fill", True) is not False
    n = lambda k, dflt=0, lo=-PAD, hi=W + PAD: _num(layer.get(k), dflt, lo, hi)  # noqa: E731
    P = PAD
    if kind == "rect":
        x, y = n("x"), n("y")
        w, h = n("w", 1, 1, 96), n("h", 1, 1, 96)
        d.rectangle((P + x, P + y, P + x + w - 1, P + y + h - 1), fill=col if fill else None, outline=col)
    elif kind == "circle":
        x, y, r = n("x", 16), n("y", 16), n("r", 3, 0, 48)
        d.ellipse((P + x - r, P + y - r, P + x + r, P + y + r), fill=col if fill else None, outline=col)
    elif kind == "line":
        d.line((P + n("x1"), P + n("y1"), P + n("x2"), P + n("y2")), fill=col, width=int(n("width", 1, 1, 4)))
    elif kind == "pixels":
        for p in (layer.get("points") or [])[:800]:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                x, y = _num(p[0], -999, -P, W + P - 1), _num(p[1], -999, -P, H + P - 1)
                if x > -999 and y > -999:
                    img.putpixel((int(P + x), int(P + y)), col)
    elif kind == "sprite":
        frames = _frames_of(layer)
        if not frames:
            return None
        rows = frames[frame % len(frames)][:48]
        pal = {str(k)[:1]: _color(v) + (255,) for k, v in (layer.get("palette") or {}).items()}
        scale = int(n("scale", 1, 1, 4))
        x0, y0 = int(P + n("x")), int(P + n("y"))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row[:48]):
                c = pal.get(ch)
                if c:
                    d.rectangle((x0 + x * scale, y0 + y * scale, x0 + x * scale + scale - 1,
                                 y0 + y * scale + scale - 1), fill=c)
    elif kind == "text":
        s = str(layer.get("text") or "")[:24].upper()
        font = layer.get("font") if layer.get("font") in FONTS else "5x7"
        y = int(n("y", 12))
        x = int(n("x")) if layer.get("x") is not None else (W - gfx.text_width(s, font)) // 2
        gfx.text(img, (P + x, P + y), s, col[:3], font)
    else:
        return None
    if layer.get("flip"):
        img = _mirror(img, layer)
    return img


def _mirror(img: Image.Image, layer: dict) -> Image.Image:
    """Flip left-right in place (around the layer's own middle, not the panel's)."""
    box = img.getbbox()
    if not box:
        return img
    part = img.crop(box).transpose(Image.FLIP_LEFT_RIGHT)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(part, box[:2])
    return out


def _frames_of(layer):
    frames = layer.get("frames") or ([layer["rows"]] if layer.get("rows") else [])
    return [f for f in frames if isinstance(f, list) and f and all(isinstance(r, str) for r in f)][:12]


def _path_point(path, u):
    """Position at u (0..1) along a closed path of [x, y] points, at constant speed."""
    pts = [(_num(p[0], 0, -96, 96), _num(p[1], 0, -96, 96)) for p in path
           if isinstance(p, (list, tuple)) and len(p) >= 2][:32]
    if not pts:
        return 0.0, 0.0
    if len(pts) == 1:
        return pts[0]
    loop = pts + [pts[0]]
    segs = [math.dist(a, b) for a, b in zip(loop, loop[1:])]
    total = sum(segs) or 1.0
    want = (u % 1.0) * total
    for (a, b), s in zip(zip(loop, loop[1:]), segs):
        if want <= s and s > 0:
            f = want / s
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        want -= s
    return pts[0]


def _offset(m: dict, t: float):
    """Where the motion puts a layer at loop position t, as (dx, dy)."""
    times = int(_num(m.get("times"), 1, 1, 8))
    u = (t + _num(m.get("phase"), 0, -1, 1)) % 1.0
    dx = dy = 0.0
    move = m.get("move") if isinstance(m.get("move"), (list, tuple)) else None
    if move:
        dx += _num(move[0], 0, -256, 256) * u
        dy += _num(move[1] if len(move) > 1 else 0, 0, -256, 256) * u
    if isinstance(m.get("path"), list):
        px, py = _path_point(m["path"], u)
        dx, dy = dx + px, dy + py
    wave = math.sin(2 * math.pi * u * times)
    dx += _num(m.get("sway"), 0, -16, 16) * wave
    dy += _num(m.get("bob"), 0, -16, 16) * (-abs(wave) if m.get("bounce") else wave)
    return dx, dy


def _render_layer(layer: dict, t: float, loop: float, depth: int = 0) -> Image.Image | None:
    """A layer (or a group of them) drawn at loop position t, motion applied."""
    m = layer.get("motion") if isinstance(layer.get("motion"), dict) else {}
    if layer.get("type") == "group":
        if depth > 2:
            return None
        img = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
        for child in [c for c in (layer.get("layers") or []) if isinstance(c, dict)][:30]:
            part = _render_layer(child, t, loop, depth + 1)
            if part is not None:
                img.alpha_composite(part)
        if layer.get("flip"):
            img = _mirror(img, layer)
    else:
        frames = len(_frames_of(layer)) if layer.get("type") == "sprite" else 1
        # sprite frames: by default each shows ~0.15 s, cycling as often as fits the loop
        cycles = int(_num(layer.get("cycles"), max(1, round(loop / (0.15 * max(1, frames)))), 1, 40))
        frame = int(((t + _num(m.get("phase"), 0, -1, 1)) % 1.0) * cycles * frames) % frames
        img = _draw_static(layer, frame)
    if img is None or not img.getbbox():
        return None
    times = int(_num(m.get("times"), 1, 1, 8))
    u = (t + _num(m.get("phase"), 0, -1, 1)) % 1.0
    angle = _num(m.get("spin"), 0, -1440, 1440) * u
    angle += _num(m.get("swing"), 0, -90, 90) * math.sin(2 * math.pi * u * times)
    if angle:
        pv = m.get("pivot")
        if isinstance(pv, (list, tuple)) and len(pv) >= 2:
            center = (PAD + _num(pv[0], 16, -PAD, W + PAD), PAD + _num(pv[1], 16, -PAD, H + PAD))
        else:
            box = img.getbbox()
            center = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        img = img.rotate(-angle, Image.NEAREST, center=center)
    if m.get("face"):   # sprites are drawn facing right; turn them toward where they're heading
        x0, _ = _offset(m, t)
        x1, _ = _offset(m, t + 0.02)
        if x1 < x0 - 0.01:
            img = _mirror(img, layer)
    alpha = 1.0
    if m.get("blink"):
        alpha = 1.0 if (u * times) % 1.0 < 0.5 else 0.0
    elif m.get("pulse"):
        alpha = 0.7 + 0.3 * (0.5 + 0.5 * math.cos(2 * math.pi * u * times))   # a glow, never a fade-out
    if alpha < 1:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img = img.copy()
        img.putalpha(a)
    dx, dy = _offset(m, t)
    ox, oy = round(dx), round(dy)
    if m.get("wrap"):
        # re-enter on the other side: draw the copies that can be on the panel
        out = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
        ox, oy = ox % W, oy % H
        for i in (-1, 0):
            for j in (-1, 0):
                out.alpha_composite(_shift(img, ox + i * W, oy + j * H))
        return out
    return _shift(img, ox, oy) if (ox or oy) else img


def _shift(img: Image.Image, dx: int, dy: int) -> Image.Image:
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (dx, dy), img)
    return out


def _effect(canvas: Image.Image, fx: dict, t: float, rng_seed: int):

    kind = fx.get("type")
    if kind not in EFFECTS:
        return
    rng = random.Random(rng_seed)
    count = int(_num(fx.get("count"), 20, 1, 60))
    base = _color(fx.get("color"), {"fire": (255, 120, 20), "rain": (90, 140, 255)}.get(kind, (255, 255, 255)))
    px = canvas.load()

    def put(x, y, c, a=1.0):
        x, y = int(x) % W, int(y)
        if 0 <= y < H:
            old = px[x, y]
            px[x, y] = tuple(int(old[i] * (1 - a) + c[i] * a) for i in range(3)) + (255,)

    for i in range(count):
        x0, y0, ph = rng.uniform(0, W), rng.uniform(0, H), rng.random()
        speed = rng.choice((1, 1, 2))          # whole laps per loop keep the loop seamless
        hue_col = gfx.hsv(rng.random()) if kind == "confetti" else base
        if kind == "stars":
            put(x0, y0, base, 0.25 + 0.75 * (0.5 + 0.5 * math.sin(2 * math.pi * (t * speed + ph))))
        elif kind == "sparkles":
            a = max(0.0, math.sin(2 * math.pi * (t * speed + ph))) ** 2
            put(x0, y0, base, a)
            if a > 0.7:
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    put(x0 + ddx, y0 + ddy, base, a * 0.5)
        elif kind in ("snow", "confetti"):
            y = (y0 + t * H * speed) % H
            put(x0 + 1.5 * math.sin(2 * math.pi * (t + ph)), y, hue_col)
        elif kind == "rain":
            y = (y0 + t * H * (speed + 1)) % H
            put(x0, y, base)
            put(x0, y - 1, base, 0.5)
        elif kind == "bubbles":
            y = (y0 - t * H * speed) % H
            put(x0 + math.sin(2 * math.pi * (t * 2 + ph)), y, base, 0.8)
        elif kind == "fire":
            h = 3 + 5 * (0.5 + 0.5 * math.sin(2 * math.pi * (t * speed + ph)))
            x = int(x0)
            for k in range(int(h)):
                f = k / max(1, h)
                put(x, H - 1 - k, (255, int(200 * (1 - f)), 0) if not fx.get("color") else gfx.scale(base, 1 - f * 0.6),
                    1 - f * 0.5)


def render(spec: dict) -> list[tuple[Image.Image, float]]:
    """The animation as (frame, seconds) pairs."""
    secs = _num(spec.get("seconds"), 2, 0.5, 4)
    fps = int(_num(spec.get("fps"), 10, 4, 15))
    n = max(2, int(secs * fps))
    bg = spec.get("background")
    if isinstance(bg, list) and len(bg) >= 2:
        top, bottom = _color(bg[0], (0, 0, 0)), _color(bg[1], (0, 0, 0))
        backdrop = Image.new("RGBA", (W, H))
        for y in range(H):
            f = y / (H - 1)
            ImageDraw.Draw(backdrop).line((0, y, W, y), fill=tuple(int(top[i] * (1 - f) + bottom[i] * f) for i in range(3)))
    else:
        backdrop = Image.new("RGBA", (W, H), _color(bg, (0, 0, 0)) + (255,))
    layers = [ly for ly in (spec.get("layers") or []) if isinstance(ly, dict)][:40]
    effects = [fx for fx in (spec.get("effects") or []) if isinstance(fx, dict)][:4]
    frames = []
    for i in range(n):
        t = i / n
        canvas = backdrop.copy()
        for k, fx in enumerate(effects):
            if fx.get("type") in ("stars", "sparkles"):   # behind everything
                _effect(canvas, fx, t, 1000 + k)
        big = Image.new("RGBA", (BIG, BIG), (0, 0, 0, 0))
        for layer in layers:
            part = _render_layer(layer, t, n / fps)
            if part is not None:
                big.alpha_composite(part)
        canvas.alpha_composite(big.crop((PAD, PAD, PAD + W, PAD + H)))
        for k, fx in enumerate(effects):
            if fx.get("type") not in ("stars", "sparkles"):
                _effect(canvas, fx, t, 1000 + k)
        frames.append((canvas.convert("RGB"), 1 / fps))
    if not any(f.getbbox() for f, _ in frames):
        raise GenerateError("the design came out blank")
    return frames


def slug(text: str, fallback: str = "generated") -> str:
    s = "-".join(re.findall(r"[a-z0-9]+", str(text).lower()))[:40].strip("-")
    return s or fallback


def season_words(d: date) -> str:
    names = [seasons.THEMES[t].split(" (")[0] for t in seasons.active_themes(d)]
    return f"{d:%B}, " + " and ".join(names)


# --- drafts: what was made, waiting for Save or Discard ------------------------

class Drafts:
    """Generated GIFs live here until you save them to the library or throw them out,
    each with its prompt and design, so nothing lands in the library on its own and an
    old idea can be reopened, refined or saved later. Keeps the newest KEEP."""
    KEEP = 60

    def __init__(self, root):
        self.root = root
        self.lock = threading.Lock()

    def _path(self, did: str, ext: str):
        if not re.fullmatch(r"[0-9a-f]{12}", did or ""):
            return None
        return self.root / f"{did}.{ext}"

    def add(self, frames, record: dict) -> dict:
        did = uuid.uuid4().hex[:12]
        self.root.mkdir(parents=True, exist_ok=True)
        imgs = [f for f, _ in frames]
        imgs[0].save(self.root / f"{did}.gif", save_all=True, append_images=imgs[1:], loop=0,
                     duration=[int(d * 1000) for _, d in frames], disposal=1)
        rec = {"id": did, "created": time.time(), "frames": len(imgs),
               "seconds": round(sum(d for _, d in frames), 2), "saved": None, **record}
        with self.lock:
            (self.root / f"{did}.json").write_text(json.dumps(rec))
            for old in self._records()[self.KEEP:]:
                self.delete(old["id"])
        return rec

    def _records(self) -> list:
        out = []
        for p in self.root.glob("*.json") if self.root.is_dir() else []:
            try:
                out.append(json.loads(p.read_text()))
            except (OSError, ValueError):
                continue
        return sorted(out, key=lambda r: r.get("created", 0), reverse=True)

    def list(self) -> list:
        return [{k: v for k, v in r.items() if k != "spec"} for r in self._records()]

    def get(self, did: str) -> dict | None:
        p = self._path(did, "json")
        try:
            return json.loads(p.read_text()) if p and p.is_file() else None
        except (OSError, ValueError):
            return None

    def gif(self, did: str):
        p = self._path(did, "gif")
        return p if p and p.is_file() else None

    def update(self, did: str, **changes) -> dict | None:
        with self.lock:
            rec = self.get(did)
            if rec is None:
                return None
            rec.update(changes)
            self._path(did, "json").write_text(json.dumps(rec))
            return rec

    def delete(self, did: str) -> bool:
        found = False
        for ext in ("gif", "json"):
            p = self._path(did, ext)
            if p and p.is_file():
                p.unlink()
                found = True
        return found


# --- jobs: a model can take a minute, longer than a proxy waits for a reply ----

class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}

    def start(self, work) -> str:
        """Run work(say) in the background; say(text) reports progress to whoever polls."""
        jid = uuid.uuid4().hex[:12]
        with self.lock:
            self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v["started"] < 3600}
            self.jobs[jid] = {"state": "working", "started": time.time(), "step": "starting"}

        def say(text):
            with self.lock:
                self.jobs[jid]["step"] = text

        def run():
            try:
                result = {"state": "done", **work(say)}
            except GenerateError as e:
                result = {"state": "failed", "error": str(e)}
            except Exception as e:  # a bug shouldn't leave the page waiting forever
                result = {"state": "failed", "error": f"{type(e).__name__}: {e}"}
            with self.lock:
                self.jobs[jid].update(result)
        threading.Thread(target=run, daemon=True, name=f"generate-{jid}").start()
        return jid

    def get(self, jid: str) -> dict | None:
        with self.lock:
            j = self.jobs.get(jid)
            return dict(j) if j else None
