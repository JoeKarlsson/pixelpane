"""Little animated previews of scenes for the Play now buttons.

Each scene is run for a few seconds with the board's real data and turned into a
small looping GIF, one at a time and cached, so the pages can show what a button
plays before you press it.
"""
import io
import random
import threading
import time

from PIL import Image

from . import gfx, plugin
from .plugin import PICKERS, SCENES

SECONDS = 3.0      # how much of the scene a thumbnail shows
STEP = 0.125       # seconds per thumbnail frame (8 fps is plenty at button size)
WALL = 2.5         # stop rendering after this long, however far the scene got
# Scenes that follow live data go stale; art and seasons only change with the date.
TTL = {"widget": 600, "mode": 3600}
LONG_TTL = 6 * 3600
SKIP_KINDS = {"gif", "interrupt"}   # GIFs would take a turn from the playlist; interrupts need a message
WARMUP = {"generative": 1.5}   # art that starts empty (sand, snake) shows from a little way in
# What a button shows when its scene has nothing to show (no song playing) or can't be previewed.
ICONS = {"gif": "camera", "now_playing": "music", "calendar": "calendar", "weather": "partly"}


class Thumbs:
    def __init__(self, state, gifs):
        from .app import Ctx   # the same view of the board a playing scene gets
        self.state = state
        self.ctx = Ctx(state, gifs, random.Random(7))
        self.cache = {}        # name -> (made at, gif bytes or None)
        self.lock = threading.Lock()

    def get(self, name):
        """The thumbnail GIF for a scene or playlist entry, or None if it has nothing to show."""
        hit = self.cache.get(name)
        if hit and time.time() - hit[0] < self._ttl(name):
            return hit[1]
        with self.lock:   # one render at a time: the Pi is also busy playing scenes
            hit = self.cache.get(name)
            if hit and time.time() - hit[0] < self._ttl(name):
                return hit[1]
            data = self._render(name) or self._icon(name)
            self.cache[name] = (time.time(), data)
            return data

    def _scene(self, name):
        pick = PICKERS.get(name)
        if pick:
            if not plugin.enabled(self.state.config, pick.plugin):
                return None
            name = pick(self.ctx)
        fn = SCENES.get(name)
        if not fn or fn.kind in SKIP_KINDS or not plugin.enabled(self.state.config, fn.plugin):
            return None
        return fn

    def _ttl(self, name):
        fn = SCENES.get(name)
        return TTL.get(getattr(fn, "kind", None), LONG_TTL) if fn else TTL["widget"]

    def _icon(self, name):
        icon = ICONS.get(name)
        fn = SCENES.get(name)
        if not icon or (fn and not plugin.enabled(self.state.config, fn.plugin)):
            return None
        sprite = gfx.sprite(icon)
        k = min((gfx.W - 4) // sprite.width, (gfx.H - 4) // sprite.height)
        sprite = sprite.resize((sprite.width * k, sprite.height * k), Image.NEAREST)
        img = gfx.blank()
        img.paste(sprite, ((gfx.W - sprite.width) // 2, (gfx.H - sprite.height) // 2), sprite)
        buf = io.BytesIO()
        img.save(buf, "GIF")
        return buf.getvalue()

    def _render(self, name):
        fn = self._scene(name)
        if not fn:
            return None
        frames, times = [], []
        skip = WARMUP.get(fn.kind, 0.0)
        shown, next_at, start = -skip, 0.0, time.monotonic()
        gen = fn(self.ctx, SECONDS + skip)
        try:
            for img, hold in gen:
                if shown >= next_at:     # keep a frame every STEP seconds of scene time
                    frames.append(img.convert("RGB"))
                    times.append(shown)
                    next_at = shown + STEP
                shown += hold
                if shown >= SECONDS or time.monotonic() - start > WALL + skip:
                    break
        except Exception:   # a broken scene just gets no thumbnail
            return None
        finally:
            gen.close()
        if not frames:
            return None
        durations = [b - a for a, b in zip(times, times[1:])] + [max(STEP, shown - times[-1])]
        buf = io.BytesIO()
        frames[0].save(buf, "GIF", save_all=True, append_images=frames[1:], loop=0,
                       duration=[max(20, round(d * 1000)) for d in durations], disposal=1)
        return buf.getvalue()
