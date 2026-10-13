"""Now playing: album art, equalizer bars, title and artist."""
import io
import logging
import threading
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
              "title_color": "#50dcff", "artist_color": "#dcdcdc"},
    about="Shows the album art full screen for a few seconds, then the title and artist "
          "beside dancing equalizer bars. It skips itself when nothing is playing. For "
          "art, the board downloads the image itself, so list the hosts it may fetch "
          "from (usually your Home Assistant).",
    fields=[{"key": "art_hosts", "label": "Album art may come from", "type": "list",
             "placeholder": "http://homeassistant.local:8123/",
             "help": "One URL prefix per line. Anything else is never fetched."},
            {"key": "art_seconds", "label": "Full-screen album art (seconds)", "type": "number",
             "min": 0, "max": 60, "step": 1,
             "help": "How long the cover fills the panel first, up to 40% of the scene. 0: never."},
            {"key": "equalizer", "label": "Equalizer", "type": "toggle", "text": "Dancing bars"},
            {"key": "show_room", "label": "Room", "type": "toggle", "text": "Show which player it's on"},
            {"key": "title_color", "label": "Title color", "type": "color"},
            {"key": "artist_color", "label": "Artist color", "type": "color"}])


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


@plugin.scene("now_playing")
def now_playing(ctx, secs):
    np_ = ctx.data("now_playing")
    if not np_ or np_.get("state", "playing") != "playing" or not np_.get("title"):
        return
    title = str(np_["title"]).upper()
    artist = str(np_.get("artist") or "").upper()
    cfg = ctx.settings("now_playing")
    room = str(np_.get("player") or "").upper() if cfg.get("show_room", True) else ""
    eq = cfg.get("equalizer", True)
    title_col = gfx.hex_color(cfg.get("title_color"), (80, 220, 255))
    artist_col = gfx.hex_color(cfg.get("artist_color"), (220, 220, 220))
    secs = max(secs, scroll_seconds(title, "5x7", 16) + 1)
    levels = [3.0] * 5
    rng = ctx.rng
    full = cfg.get("art_seconds")
    art_secs = min(6.0 if full is None else float(full), secs * 0.4)  # with album art: show it full size first
    for i, t in ticks(secs + art_secs, 10):
        art = album_art(ctx, np_.get("art"))
        for b in range(5):
            levels[b] = max(1, min(8, levels[b] + rng.uniform(-2, 2)))
        if art is not None and t < art_secs:
            img = art.copy()
            if eq:
                d = ImageDraw.Draw(img)
                d.rectangle((19, 23, 31, 31), fill=(0, 0, 0))  # mini equalizer over the art
                for b in range(4):
                    h = int(levels[b] * 0.8)
                    d.rectangle((20 + b * 3, 30 - h, 21 + b * 3, 30), fill=gfx.hsv(0.45 + b * 0.05, 0.8, 1))
            yield img, 0.1
            continue
        t -= art_secs if art is not None else 0
        img = gfx.blank()
        d = ImageDraw.Draw(img)
        if art is not None:
            img.paste(art.resize((10, 10), Image.LANCZOS), (0, 0))
        else:
            animated_icon(img, "music", (1, 1), t)
        if eq:
            for b in range(5):
                x = 12 + b * 4
                d.rectangle((x, 9 - int(levels[b]), x + 2, 8), fill=gfx.hsv(0.45 + b * 0.05, 0.8, 1))
        scroll_text(img, 12, title, title_col, "5x7", t, 16)
        scroll_text(img, 21, artist, artist_col, "tom-thumb", t, 14)
        if room:
            gfx.text_center(img, 27, room[:8], (90, 90, 110), "tom-thumb")
        yield img, 0.1


def album_art(ctx, url):
    """The 32x32 cover for url once fetched (None until then, or if not allowed)."""
    store = ctx.store("now_playing")
    if "art" not in store:
        store["art"] = ArtCache(lambda: ctx.settings("now_playing").get("art_hosts"))
    return store["art"].get(url)
