"""Make a GIF from a text prompt with any OpenAI-compatible chat model.

The model doesn't draw pixels one by one (chat models are bad at that). It writes
a small animation as JSON: a background, layers (shapes, pixel sprites, text)
that can move, bob, sway, spin, blink or pulse, and looping effects such as
snow or stars. render() turns that into a seamless 32x32 loop, which is saved to
the library like an upload.
"""
from __future__ import annotations

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

SPEC = """You design animated pixel art for a 32x32 LED panel behind a two-way mirror.
Answer with ONE JSON object and nothing else:
{
 "name": "3-5 word title", "category": "one lowercase word such as animal, space, food, nature, retro, weather, holiday, abstract",
 "seconds": 1-4 (one loop), "fps": 6-15,
 "background": "#rrggbb" or ["#top", "#bottom"] (a vertical gradient),
 "effects": [{"type": "stars|snow|rain|confetti|bubbles|sparkles|fire", "color": "#rrggbb", "count": 1-60}],
 "layers": [ drawn in order, each one of:
   {"type": "rect", "x": 0, "y": 0, "w": 4, "h": 4, "color": "#rrggbb", "fill": true},
   {"type": "circle", "x": 16, "y": 16, "r": 5, "color": "#rrggbb", "fill": true},
   {"type": "line", "x1": 0, "y1": 31, "x2": 31, "y2": 31, "color": "#rrggbb"},
   {"type": "pixels", "points": [[x, y], ...], "color": "#rrggbb"},
   {"type": "sprite", "x": 10, "y": 8, "palette": {"a": "#rrggbb", "b": "#rrggbb"},
    "frames": [["..aa..", ".abba.", "..aa.."], ["..aa..", "abbbba", "..aa.."]]},
   {"type": "text", "text": "HI", "y": 24, "color": "#rrggbb", "font": "tom-thumb|4x6|5x7"}
 ] }
Any layer may add "motion": {"move": [dx, dy], "wrap": true, "bob": 2, "sway": 2, "spin": 360,
 "blink": true, "pulse": true}. move is pixels per loop (with wrap it re-enters on the other side);
bob and sway are up-down and side-to-side swings in pixels; spin is degrees per loop.
Sprite frames play in order through the loop; "." is transparent; every row of a frame
has the same length, at most 32. Coordinates are 0-31, (0,0) is the top left.
Make it read from across a room: one big clear subject, bold saturated colors, dark
background, simple shapes, smooth motion that loops seamlessly."""

IDEA = ("Invent one delightful idea for the panel yourself, something that suits {when} "
        "and looks great as tiny pixel art. Then design it.")

EFFECTS = {"stars", "snow", "rain", "confetti", "bubbles", "sparkles", "fire"}
FONTS = {"tom-thumb", "4x6", "5x7", "5x8", "6x10"}


class GenerateError(Exception):
    pass


# --- talking to the model ------------------------------------------------------

def ask(settings: dict, prompt: str, when: str, timeout: float = 120) -> dict:
    """The model's animation for prompt (or its own idea when prompt is empty)."""
    base = (settings.get("base_url") or "").rstrip("/")
    if not base or not settings.get("model"):
        raise GenerateError("set the generator's server and model first (Plugins, generator)")
    user = prompt.strip() or IDEA.format(when=when)
    # A fresh tag each time: gateways like LiteLLM cache identical requests, which
    # would make Try again and Surprise me repeat themselves.
    user += f"\n\n(variation {uuid.uuid4().hex[:8]})"
    body = {"model": settings["model"], "temperature": 0.8, "max_tokens": 4000,
            "messages": [{"role": "system", "content": SPEC}, {"role": "user", "content": user}]}
    req = urllib.request.Request(base + "/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json",
                                  **({"Authorization": "Bearer " + settings["api_key"]}
                                     if settings.get("api_key") else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            reply = json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode("utf-8", "replace")
        raise GenerateError(f"the model server said {e.code}: {detail}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise GenerateError(f"could not reach {base}: {getattr(e, 'reason', e)}") from e
    try:
        text = reply["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise GenerateError("the model's reply had no message") from e
    return parse(text)


def parse(text: str) -> dict:
    """The JSON object in a reply, even wrapped in prose or a code fence."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    start = text.find("{")
    if start < 0:
        raise GenerateError("the model didn't answer with JSON")
    depth, in_str, esc = 0, False, False
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
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    spec = json.loads(text[start:i + 1])
                except json.JSONDecodeError as e:
                    raise GenerateError(f"the model's JSON didn't parse: {e}") from e
                if not isinstance(spec, dict):
                    break
                return spec
    raise GenerateError("the model's JSON was cut off")


# --- drawing -------------------------------------------------------------------

def _num(v, default, lo, hi):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(v) else max(lo, min(hi, v))


def _color(v, default=(255, 255, 255)):
    return gfx.hex_color(str(v or "").lstrip("#"), default) if v else default


def _layer_image(layer: dict, frame: int) -> Image.Image | None:
    """One layer drawn still on a transparent 32x32 canvas."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    kind, col = layer.get("type"), _color(layer.get("color")) + (255,)
    fill = layer.get("fill", True) is not False
    n = lambda k, dflt=0, lo=-64, hi=96: _num(layer.get(k), dflt, lo, hi)  # noqa: E731
    if kind == "rect":
        x, y = n("x"), n("y")
        w, h = n("w", 1, 1, 64), n("h", 1, 1, 64)
        d.rectangle((x, y, x + w - 1, y + h - 1), fill=col if fill else None, outline=col)
    elif kind == "circle":
        x, y, r = n("x", 16), n("y", 16), n("r", 3, 0, 48)
        d.ellipse((x - r, y - r, x + r, y + r), fill=col if fill else None, outline=col)
    elif kind == "line":
        d.line((n("x1"), n("y1"), n("x2"), n("y2")), fill=col, width=int(n("width", 1, 1, 4)))
    elif kind == "pixels":
        for p in (layer.get("points") or [])[:600]:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                x, y = _num(p[0], -1, -1, 99), _num(p[1], -1, -1, 99)
                if 0 <= x < W and 0 <= y < H:
                    img.putpixel((int(x), int(y)), col)
    elif kind == "sprite":
        frames = layer.get("frames") or ([layer["rows"]] if layer.get("rows") else [])
        frames = [f for f in frames if isinstance(f, list) and f and all(isinstance(r, str) for r in f)]
        if not frames:
            return None
        rows = frames[frame % len(frames)][:32]
        pal = {str(k)[:1]: _color(v) + (255,) for k, v in (layer.get("palette") or {}).items()}
        scale = int(n("scale", 1, 1, 4))
        x0, y0 = int(n("x")), int(n("y"))
        for y, row in enumerate(rows):
            for x, ch in enumerate(row[:32]):
                c = pal.get(ch)
                if c:
                    d.rectangle((x0 + x * scale, y0 + y * scale, x0 + x * scale + scale - 1,
                                 y0 + y * scale + scale - 1), fill=c)
    elif kind == "text":
        s = str(layer.get("text") or "")[:24].upper()
        font = layer.get("font") if layer.get("font") in FONTS else "5x7"
        y = int(n("y", 12))
        x = int(n("x")) if layer.get("x") is not None else (W - gfx.text_width(s, font)) // 2
        gfx.text(img, (x, y), s, col[:3], font)
    else:
        return None
    return img


def _sprite_frames(layer):
    frames = layer.get("frames") if layer.get("type") == "sprite" else None
    return len(frames) if isinstance(frames, list) and frames else 1


def _place(canvas: Image.Image, layer_img: Image.Image, motion: dict, t: float):
    """Paste a layer moved to where its motion puts it at loop position t (0..1)."""
    m = motion if isinstance(motion, dict) else {}
    img = layer_img
    if m.get("spin"):
        box = img.getbbox()
        if box:
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            img = img.rotate(-_num(m["spin"], 0, -1440, 1440) * t, Image.NEAREST, center=(cx, cy))
    alpha = 1.0
    if m.get("blink"):
        alpha = 1.0 if t < 0.5 else 0.0
    elif m.get("pulse"):
        alpha = 0.7 + 0.3 * (0.5 + 0.5 * math.cos(2 * math.pi * t))   # a glow, never a fade-out
    if alpha < 1:
        a = img.getchannel("A").point(lambda v: int(v * alpha))
        img = img.copy()
        img.putalpha(a)
    move = m.get("move") if isinstance(m.get("move"), (list, tuple)) else [0, 0]
    dx = _num(move[0] if move else 0, 0, -256, 256) * t
    dy = _num(move[1] if len(move) > 1 else 0, 0, -256, 256) * t
    dx += _num(m.get("sway"), 0, -16, 16) * math.sin(2 * math.pi * t)
    dy += _num(m.get("bob"), 0, -16, 16) * math.sin(2 * math.pi * t)
    ox, oy = round(dx), round(dy)
    spots = [(ox, oy)]
    if m.get("wrap"):
        ox, oy = ox % W, oy % H
        spots = [(ox + i * W, oy + j * H) for i in (-1, 0) for j in (-1, 0)]
    for x, y in spots:
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        layer.paste(img, (x, y), img)
        canvas.alpha_composite(layer)


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
    cache = {}
    frames = []
    for i in range(n):
        t = i / n
        canvas = backdrop.copy()
        for k, fx in enumerate(effects):
            if fx.get("type") in ("stars", "sparkles"):   # behind everything
                _effect(canvas, fx, t, 1000 + k)
        for j, layer in enumerate(layers):
            f = int(t * _sprite_frames(layer))
            key = (j, f)
            if key not in cache:
                cache[key] = _layer_image(layer, f)
            if cache[key] is not None:
                _place(canvas, cache[key], layer.get("motion"), t)
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


# --- jobs: a model can take a minute, longer than a proxy waits for a reply ----

class Jobs:
    def __init__(self):
        self.lock = threading.Lock()
        self.jobs: dict[str, dict] = {}

    def start(self, work) -> str:
        jid = uuid.uuid4().hex[:12]
        with self.lock:
            self.jobs = {k: v for k, v in self.jobs.items() if time.time() - v["started"] < 3600}
            self.jobs[jid] = {"state": "working", "started": time.time()}

        def run():
            try:
                result = {"state": "done", **work()}
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
