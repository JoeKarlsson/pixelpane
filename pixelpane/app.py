"""The display controller: one process owns the panel, plays scenes, serves the API.

    python -m pixelpane.app            # on the Pi (root; drops to the pixelpane user)
    PIXELPANE_FAKE=1 python -m pixelpane.app --port 8080   # anywhere, no panel
"""
import argparse
import grp
import logging
import os
import pwd
import random
import subprocess
import threading
import time
from datetime import date

from . import logbuf, plugin
from .display import FakeDisplay
from .plugin import PICKERS, SCENES
from .state import HOME, GifLibrary, State, now

log = logging.getLogger("pixelpane")


class Ctx:
    """What a scene can see."""

    def __init__(self, state, gifs, rng):
        self.state, self.gifs, self.rng = state, gifs, rng
        self.label = ""
        self._stores = {}

    def settings(self, name):
        """A plugin's settings (its defaults with config["plugins"][name] on top)."""
        return plugin.settings(self.state.config, name)

    def store(self, name):
        """A dict a plugin can keep things in (caches) for the life of the process."""
        return self._stores.setdefault(name, {})

    def saved(self, name):
        """A dict a plugin keeps across restarts (a fish tank's fish); save(name) writes it."""
        return self.state.saved(name)

    def save(self, name):
        self.state.save(name)

    @property
    def config(self):
        return self.state.config

    def now(self):
        return now()

    def data(self, key):
        return self.state.get_data(key)

    def next_gif(self, category=None):
        return self.gifs.next(category)

    def gif_frames(self, path):
        return self.gifs.frames(path)

    def gif_played(self, path):
        self.gifs.played(path)


class Player:
    def __init__(self, state, display, gifs, rng=None):
        self.state, self.display, self.gifs = state, display, gifs
        self.rng = rng or random.Random()
        self.ctx = Ctx(state, gifs, self.rng)
        self.position = 0
        self.played = 0
        self.slot = None
        self.shown_at = 0.0   # when the last frame shown stops being current
        self.stop = threading.Event()   # run()'s, so a scene ends as soon as we're told to stop

    # -- choosing what to play --
    def resolve(self, name, params=None):
        """Turn a rotation entry into (label, generator, seconds)."""
        cfg = self.state.config
        dwell = cfg["dwell"]
        params = dict(params or {})
        name, _, category = name.partition(":")  # "gif:retro" = a GIF from one category
        secs = float(params.pop("seconds", 0)) or dwell.get(name, 15)
        pick = PICKERS.get(name)   # "seasonal", "generative": the plugin picks a scene
        if pick:
            if not plugin.enabled(cfg, pick.plugin):
                return None
            name = pick(self.ctx)
            if not name:
                return None
        fn = SCENES.get(name)
        if not fn:
            log.warning("unknown scene %s", name)
            return None
        if not plugin.enabled(cfg, fn.plugin):
            return None
        if name == "gif":   # only ever a library id or a category, never a raw path
            gid = params.pop("id", None)
            params = {"path": self.gifs.resolve(gid)} if gid else {"category": category} if category else {}
        return name, fn(self.ctx, secs, **params), secs

    def next_item(self):
        """The next playlist entry; sets self.slot to its index (None for a birthday extra)."""
        rot = self.state.rotation()
        self.played += 1
        if "birthday" in self.state.themes() and self.played % 4 == 0:
            self.slot = None
            return "seasonal"
        self.slot = self.position % len(rot)
        self.position += 1
        return rot[self.slot]

    def mark(self, source, entry, secs=None, index=None, **extra):
        """Record what is on now and why, for the page's live view (state.now)."""
        rot = self.state.rotation()
        self.state.now = dict(extra, source=source, entry=entry, index=index, started=time.time(),
                              seconds=secs, next=rot[self.position % len(rot)], length=len(rot))

    # -- playing --
    def play(self, label, gen, interruptible=True, scene=None):
        """Show frames until the scene ends; returns early when something wakes us."""
        st = self.state
        self.ctx.label = label
        shown = False
        scene = scene or label
        fn = SCENES.get(scene)
        # the frame before, for transitions: only if it is still on screen
        prev = st.last_frame if time.monotonic() - self.shown_at < 2 else None
        info = {"scene": scene, "kind": getattr(fn, "kind", None), "prev": prev}
        frames = plugin.wrap(st.config, self.ctx, gen, info)
        try:
            for img, hold in frames:
                if not shown:
                    st.label = self.ctx.label or label
                    shown = True
                if not st.effective_power():   # scheduled off time began
                    return shown
                self.display.brightness = st.effective_brightness()
                self.display.show(img)
                st.last_frame = img
                deadline = time.monotonic() + hold
                self.shown_at = deadline
                while (left := deadline - time.monotonic()) > 0:
                    if st.wake.wait(left):
                        st.wake.clear()
                        if self.stop.is_set() or not st.effective_power() or (interruptible and (
                                st.skip or st.notifications or st.play_next or st.active_pin() != self.pin_seen)):
                            return shown
        except Exception:  # a broken scene must never take the board down
            log.exception("scene %s failed", label)
            time.sleep(1)
        finally:
            frames.close()
            gen.close()
        return shown

    def placeholder(self, name, secs=4):
        """A requested scene had nothing to show: say so if that is unusual, else skip."""
        fn = SCENES.get(name.partition(":")[0])
        text = getattr(fn, "empty_text", None)
        if not text:
            return False
        return self.play(f"empty: {name}", SCENES["message"](self.ctx, secs, text=text, color="#8b8fa3"),
                         scene="message")

    def run(self, stop):
        st = self.state
        self.stop = stop
        self.pin_seen = None
        empty = 0
        while not stop.is_set():
            st.skip = False
            if not st.effective_power():
                st.label = "off" if not st.power else "scheduled off"
                st.now = {"source": "off" if not st.power else "schedule"}
                self.display.clear()
                st.wake.wait(5)
                st.wake.clear()
                continue
            if st.notifications:
                n = dict(st.notifications.popleft())
                secs = float(n.pop("seconds", None) or plugin.settings(st.config, "alerts").get("seconds") or 10)
                self.mark("notification", "notify", secs, text=n.get("text", ""))
                self.play("notify", SCENES["notify"](self.ctx, secs, **n), interruptible=False)
                continue
            pin = st.active_pin()
            self.pin_seen = pin
            if pin:
                item = self.resolve(pin["scene"], dict(pin.get("params") or {}, seconds=60))
                self.mark("pinned", pin["scene"], None, until=pin.get("until"))
                if not (item and self.play(item[0], item[1])) and not self.placeholder(pin["scene"], 10):
                    self.state.label = f"waiting: {pin['scene']}"  # pinned but nothing to show yet
                    st.wake.wait(5)
                    st.wake.clear()
                continue
            if st.play_next:
                req, st.play_next = st.play_next, None
                item = self.resolve(req["scene"], req.get("params"))
                self.mark("requested", req["scene"], item[2] if item else None)
                if not (item and self.play(item[0], item[1])):
                    self.placeholder(req["scene"])  # asked for on purpose: say why it is blank
                continue
            entry = self.next_item()
            item = self.resolve(entry)
            if item:
                self.mark("playlist" if self.slot is not None else "birthday", entry, item[2], self.slot)
            shown = bool(item) and self.play(item[0], item[1])
            empty = 0 if shown else empty + 1
            if empty > 2 * len(st.rotation()):
                st.request("clock")  # nothing in the rotation has anything to show
                empty = 0


# -- background helpers --

_throttled = {"t": 0, "v": None}


def _now(state):
    now = dict(state.now or {})
    if now.get("started"):
        now["elapsed"] = round(time.time() - now["started"], 1)  # server clock, so no skew
    return now


def health(state):
    try:
        temp = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
    except OSError:
        temp = None
    if time.time() - _throttled["t"] > 60:
        try:
            out = subprocess.run(["vcgencmd", "get_throttled"], capture_output=True, text=True, timeout=5)
            _throttled["v"] = out.stdout.strip().split("=")[-1] or None
        except (OSError, subprocess.SubprocessError):
            _throttled["v"] = None
        _throttled["t"] = time.time()
    try:
        version = (HOME / "VERSION").read_text().strip()
    except OSError:
        version = "dev"
    return {"ok": True, "power": state.power, "brightness": state.brightness,
            "scene": state.label, "now": _now(state), "pinned": state.active_pin(), "themes": state.themes(),
            "on": state.effective_power(), "schedule": state.schedule_status(),
            "temp_c": temp, "throttled": _throttled["v"], "uptime_s": int(time.time() - state.started),
            "version": version, "date": date.today().isoformat()}


def drop_privileges(user="pixelpane"):
    if os.geteuid() != 0:
        return
    try:
        pw = pwd.getpwnam(user)
    except KeyError:
        log.warning("user %s missing, staying root", user)
        return
    groups = [pw.pw_gid] + [g.gr_gid for g in grp.getgrall() if user in g.gr_mem]
    os.setgroups(groups)
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    os.environ["HOME"] = pw.pw_dir
    log.info("dropped privileges to %s", user)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PIXELPANE_PORT", 80)))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logbuf.install()   # the last few hundred lines, for the Settings page

    from werkzeug.serving import make_server
    from .web import create_app

    plugin.load()
    state = State()
    rng = random.Random()
    gifs = GifLibrary(state, rng)
    # Bind the port first: port 80 needs root, and we drop root right after the panel opens.
    server = make_server("0.0.0.0", args.port, create_app(state, gifs, health), threaded=True)
    if os.environ.get("PIXELPANE_FAKE"):
        display = FakeDisplay()
    else:
        from .display import open_display
        display = open_display(state.config, state.brightness)
    drop_privileges()

    stop = threading.Event()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    player = Player(state, display, gifs, rng)
    plugin.run_tasks(player.ctx, stop)
    log.info("serving on :%d with plugins %s", args.port,
             ", ".join(n for n in plugin.PLUGINS if plugin.enabled(state.config, n)))
    try:
        player.run(stop)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        display.clear()


if __name__ == "__main__":
    main()
