"""Now playing: album art, equalizer bars, title and artist."""
import io
import logging
import threading
import urllib.request
from collections import OrderedDict

from PIL import Image, ImageDraw

from .. import gfx
from ..kit import animated_icon, scroll_seconds, scroll_text, ticks
from ..plugin import Plugin

log = logging.getLogger("pixelpane.now_playing")

plugin = Plugin("now_playing", "What's playing, with album art",
                data={"now_playing": 360}, defaults={"art_hosts": []})


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
        with urllib.request.urlopen(url, timeout=6) as r:
            return r.read(5_000_001)

    def allowed(self, url):
        return isinstance(url, str) and any(url.startswith(h) for h in self.hosts() or [])

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


@plugin.scene("now_playing")
def now_playing(ctx, secs):
    np_ = ctx.data("now_playing")
    if not np_ or np_.get("state", "playing") != "playing" or not np_.get("title"):
        return
    title = str(np_["title"]).upper()
    artist = str(np_.get("artist") or "").upper()
    room = str(np_.get("player") or "").upper()
    secs = max(secs, scroll_seconds(title, "5x7", 16) + 1)
    levels = [3.0] * 5
    rng = ctx.rng
    art_secs = min(6.0, secs * 0.4)  # with album art: show it full size first
    for i, t in ticks(secs + art_secs, 10):
        art = album_art(ctx, np_.get("art"))
        for b in range(5):
            levels[b] = max(1, min(8, levels[b] + rng.uniform(-2, 2)))
        if art is not None and t < art_secs:
            img = art.copy()
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
        for b in range(5):
            x = 12 + b * 4
            d.rectangle((x, 9 - int(levels[b]), x + 2, 8), fill=gfx.hsv(0.45 + b * 0.05, 0.8, 1))
        scroll_text(img, 12, title, (80, 220, 255), "5x7", t, 16)
        scroll_text(img, 21, artist, (220, 220, 220), "tom-thumb", t, 14)
        if room:
            gfx.text_center(img, 27, room[:8], (90, 90, 110), "tom-thumb")
        yield img, 0.1


def album_art(ctx, url):
    """The 32x32 cover for url once fetched (None until then, or if not allowed)."""
    store = ctx.store("now_playing")
    if "art" not in store:
        store["art"] = ArtCache(lambda: ctx.settings("now_playing").get("art_hosts"))
    return store["art"].get(url)
