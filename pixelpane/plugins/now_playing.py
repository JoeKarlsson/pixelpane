"""Now playing: album art, equalizer bars, title and artist, in the album's colors."""
import colorsys
import io
import logging
import threading
import time
import urllib.request
from collections import OrderedDict
from urllib.parse import urlsplit

from PIL import Image, ImageDraw

from .. import gfx
from ..kit import animated_icon, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

log = logging.getLogger("pixelpane.now_playing")

plugin = Plugin(
    "now_playing", "What's playing, with album art",
    data={"now_playing": 360},
    defaults={"art_hosts": [], "art_seconds": 6, "equalizer": True, "show_room": True,
              "title_color": "#50dcff", "artist_color": "#dcdcdc", "art_colors": True, "boost": True},
    about="Shows the album art full screen for a few seconds, then the title and artist "
          "beside dancing equalizer bars, in colors taken from the album art. While music "
          "plays it comes round every few minutes, not just at its turn in the playlist. "
          "Paused, it shows dimmed with a pause sign for a quarter of an hour, then skips "
          "itself like it does when nothing is playing. For art, the board downloads the "
          "image itself, so list the hosts it may fetch from (usually your Home Assistant).",
    fields=[{"key": "art_hosts", "label": "Album art may come from", "type": "list",
             "placeholder": "http://homeassistant.local:8123/",
             "help": "One URL prefix per line. Anything else is never fetched."},
            {"key": "art_seconds", "label": "Full-screen album art (seconds)", "type": "number",
             "min": 0, "max": 60, "step": 1,
             "help": "How long the cover fills the panel first, up to 40% of the scene. 0: never."},
            {"key": "equalizer", "label": "Equalizer", "type": "toggle", "text": "Dancing bars"},
            {"key": "show_room", "label": "Room", "type": "toggle", "text": "Show which player it's on"},
            {"key": "title_color", "label": "Title color", "type": "color"},
            {"key": "artist_color", "label": "Artist color", "type": "color"},
            {"key": "art_colors", "label": "Album colors", "type": "toggle",
             "text": "Color the bars, title and glow from the album art (else the colors above)"},
            {"key": "boost", "label": "While music plays", "type": "toggle",
             "text": "Show it every few minutes, not just at its turn"}])

PAUSED_FOR = 15 * 60   # a paused song stays on the board this long, dimmed


class ArtCache:
    """Album art fetched in the background and shrunk to the panel.

    Only URLs under the plugin's art_hosts setting are fetched: anyone on the LAN
    can push now_playing data, and the board must not fetch arbitrary URLs for them.
    """

    def __init__(self, hosts, fetch=None):
        self.hosts = hosts  # callable returning the allowed URL prefixes
        self.images, self.pending = OrderedDict(), set()
        self.fetch = fetch or self._download
        self.lock = threading.Lock()

    @staticmethod
    def _download(url):
        # No redirects: an allowed host must not be able to bounce the board elsewhere.
        with _NO_REDIRECTS.open(url, timeout=6) as r:
            return r.read(5_000_001)

    def allowed(self, url):
        """Same scheme, host and port as one of the allowed prefixes, and under its path.
        (A plain startswith would let "http://ha.local:8123" match "http://ha.local:8123.evil.com".)"""
        if not isinstance(url, str):
            return False
        u = _origin(url)
        return bool(u) and any((a := _origin(h)) and u[:3] == a[:3] and u[3].startswith(a[3])
                               for h in self.hosts() or [])

    def get(self, url):
        """The 32x32 image if ready; otherwise start fetching it and return None."""
        if not self.allowed(url):
            return None
        with self.lock:
            if url in self.images:
                return self.images[url]
            if url in self.pending:
                return None
            self.pending.add(url)
        threading.Thread(target=self._load, args=(url,), daemon=True).start()
        return None

    def _load(self, url):
        img = None
        try:
            data = self.fetch(url)
            if len(data) <= 5_000_000:
                from PIL import ImageEnhance
                from ..state import fit
                with Image.open(io.BytesIO(data)) as im:
                    img = ImageEnhance.Color(fit(im.convert("RGB"), smooth=True)).enhance(1.3)
        except Exception as e:  # bad art just means no art
            log.info("album art %s: %s", url[:60], e)
        with self.lock:
            self.pending.discard(url)
            self.images[url] = img
            while len(self.images) > 20:
                self.images.popitem(last=False)


class _Refuse(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None   # urllib then raises HTTPError for the 3xx


_NO_REDIRECTS = urllib.request.build_opener(_Refuse)
_PORTS = {"http": 80, "https": 443}


def _origin(url):
    """(scheme, host, port, path) of an http(s) URL, or None."""
    try:
        u = urlsplit(url.strip() if "://" in url else "http://" + url.strip())
        if u.scheme not in _PORTS or not u.hostname:
            return None
        return u.scheme, u.hostname, u.port or _PORTS[u.scheme], u.path or "/"
    except ValueError:
        return None


def _playing(ctx):
    """The now_playing data if something is playing (noting when), else None."""
    np_ = ctx.data("now_playing")
    if np_ and np_.get("state", "playing") == "playing" and np_.get("title"):
        ctx.store("now_playing")["last_playing"] = time.time()
        return np_
    return None


@plugin.boost
def playing_now(ctx):
    """Music on: the scene comes round every few minutes."""
    if _playing(ctx) and ctx.settings("now_playing").get("boost", True):
        return ("now_playing", 4)
    return None


def art_palette(art):
    """Up to three vivid colors from the album art, brightest-and-most-colorful first,
    lifted so they read on LEDs. None for a grey cover."""
    small = art.quantize(8)
    pal = small.getpalette()[:24]
    picks = []
    for count, idx in sorted(small.getcolors(), reverse=True):
        r, g, b = pal[idx * 3:idx * 3 + 3]
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        if s > 0.25 and v > 0.2 and count > 8:
            picks.append((s * v * (count ** 0.3), h, s))
    picks.sort(reverse=True)
    out = []
    for _, h, sat in picks:
        if all(min(abs(h - o), 1 - abs(h - o)) > 0.08 for o in out):
            out.append(h)
        if len(out) == 3:
            break
    return [gfx.hsv(h, max(0.55, sat), 1.0) for h in out] or None


@plugin.scene("now_playing")
def now_playing(ctx, secs):
    np_ = _playing(ctx)
    paused = False
    if not np_:
        np_ = ctx.data("now_playing")
        recent = time.time() - ctx.store("now_playing").get("last_playing", 0) < PAUSED_FOR
        if not (np_ and np_.get("state") == "paused" and np_.get("title") and recent):
            return
        paused = True
    title = str(np_["title"]).upper()
    artist = str(np_.get("artist") or "").upper()
    cfg = ctx.settings("now_playing")
    room = str(np_.get("player") or "").upper() if cfg.get("show_room", True) else ""
    eq = cfg.get("equalizer", True)
    title_col = gfx.hex_color(cfg.get("title_color"), (80, 220, 255))
    artist_col = gfx.hex_color(cfg.get("artist_color"), (220, 220, 220))
    secs = max(secs, scroll_seconds(title, "5x7", 16) + 1)
    levels = [1.0 if paused else 3.0] * 5
    rng = ctx.rng
    full = cfg.get("art_seconds")
    art_secs = min(6.0 if full is None else float(full), secs * 0.4)  # with album art: show it full size first
    colors = None
    dim = 0.4 if paused else 1.0
    for i, t in ticks(secs + art_secs, 10):
        art = album_art(ctx, np_.get("art"))
        if colors is None and art is not None and cfg.get("art_colors", True):
            colors = art_palette(art) or False
        bars = [colors[b % len(colors)] for b in range(5)] if colors else \
            [gfx.hsv(0.45 + b * 0.05, 0.8, 1) for b in range(5)]
        if not paused:
            for b in range(5):
                levels[b] = max(1, min(8, levels[b] + rng.uniform(-2, 2)))
        if art is not None and t < art_secs:
            img = art.copy() if not paused else Image.eval(art, lambda v: int(v * dim))
            d = ImageDraw.Draw(img)
            if paused:
                _pause_sign(d, 13, 12)
            elif eq:
                d.rectangle((19, 23, 31, 31), fill=(0, 0, 0))  # mini equalizer over the art
                for b in range(4):
                    h = int(levels[b] * 0.8)
                    d.rectangle((20 + b * 3, 30 - h, 21 + b * 3, 30), fill=bars[b])
            yield img, 0.1
            continue
        t -= art_secs if art is not None else 0
        img = gfx.blank()
        if colors and not paused:   # a soft glow of the album's color that breathes with the bars
            beat = sum(levels) / 40
            glow = gfx.scale(colors[0], 0.06 + 0.06 * beat)
            ImageDraw.Draw(img).rectangle((0, 10, 31, 31), fill=glow)
        d = ImageDraw.Draw(img)
        if art is not None:
            img.paste(Image.eval(art.resize((10, 10), Image.LANCZOS), lambda v: int(v * dim)), (0, 0))
        else:
            animated_icon(img, "music", (1, 1), t)
        if paused:
            _pause_sign(d, 18, 2)
        elif eq:
            for b in range(5):
                x = 12 + b * 4
                d.rectangle((x, 9 - int(levels[b]), x + 2, 8), fill=bars[b])
        tc = colors[0] if colors else title_col
        scroll_text(img, 12, title, gfx.scale(tc, dim), "5x7", t, 16)
        scroll_text(img, 21, artist, gfx.scale(artist_col, dim), "tom-thumb", t, 14)
        if room:
            gfx.text_center(img, 27, room[:8], (90, 90, 110), "tom-thumb")
        yield img, 0.1


def _pause_sign(d, x, y):
    d.rectangle((x, y, x + 1, y + 6), fill=(230, 230, 230))
    d.rectangle((x + 4, y, x + 5, y + 6), fill=(230, 230, 230))


def album_art(ctx, url):
    """The 32x32 cover for url once fetched (None until then, or if not allowed)."""
    store = ctx.store("now_playing")
    if "art" not in store:
        store["art"] = ArtCache(lambda: ctx.settings("now_playing").get("art_hosts"))
    return store["art"].get(url)
