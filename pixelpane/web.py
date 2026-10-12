"""HTTP API + control page. LAN only (the board lives on the IoT VLAN)."""
import hmac
import io
import ipaddress
import json
import os
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlparse, urlsplit

from flask import Flask, Response, abort, jsonify, request, send_file
from PIL import Image
from werkzeug.utils import secure_filename

from . import generate, gfx, logbuf, plugin, schema, seasons
from .display import compose, panel_size
from .plugin import PICKERS, SCENES
from .state import VAR, _read, convert_upload
from .state import now as local_now

PAGES = {name: Path(__file__).with_name(f"{name}.html") for name in ("index", "library", "settings")}
MAX_STREAMS = 6   # live previews at once; each one costs the Pi a little CPU
# Reads that give away more than the board's status: when a token is set they need it too.
PRIVATE_READS = {"/api/logs", "/api/backup"}
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
       "connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; "
       "frame-ancestors 'none'")


def valid_scene(name, config=None):
    """A known scene (or seasonal/generative/gif:<category>), from an enabled plugin if config is given."""
    if not schema.valid_scene(name):
        return False
    base = str(name).partition(":")[0]
    if config is None:
        return True
    return plugin.scene_enabled(config, base)


def local_names():
    """Host names the board answers to without being told: its own name, and that name
    under the usual home-network suffixes."""
    me = socket.gethostname().split(".")[0].lower()
    return {"localhost", me} | {f"{me}.{tld}" for tld in ("local", "lan", "home", "home.arpa", "internal")}


def host_allowed(host, extra=()):
    """Is the Host header one of ours? Any IP address is (DNS rebinding needs a name);
    names must be the board's own or listed in allowed_hosts / PIXELPANE_ALLOWED_HOSTS."""
    try:
        name = urlsplit("//" + (host or "")).hostname
    except ValueError:
        return False
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    env = {h.strip().lower() for h in os.environ.get("PIXELPANE_ALLOWED_HOSTS", "").split(",") if h.strip()}
    return name.rstrip(".") in local_names() | env | {h.lower() for h in extra}


def on_accent(hex_color):
    """Text color that reads on the accent: near-black on a light accent, white on a dark one."""
    r, g, b = gfx.hex_color(hex_color)
    return "#0a0a0a" if 0.2126 * r + 0.7152 * g + 0.0722 * b > 140 else "#ffffff"


def _exit_soon():
    """Restart: exit and let systemd (Restart=always) start the service again."""
    threading.Timer(0.5, os._exit, args=(0,)).start()


def create_app(state, gifs, health, restart=_exit_soon):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
    streams = {}   # stream -> when it last ran; the dev server never closes a dropped
    streams_lock = threading.Lock()   # stream, so a stream that stops running is gone

    def token():
        return state.config.get("api_token") or os.environ.get("PIXELPANE_TOKEN")

    def token_ok():
        given = request.headers.get("X-PixelPane-Token") or ""
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            given = auth[7:]
        return hmac.compare_digest(given.encode(), token().encode())

    @app.before_request
    def guard():
        """1. Only answer to our own host names: a web page on some other name that it
        re-points at the board's IP (DNS rebinding) is turned away, reads included.
        2. Refuse cross-site writes: a web page open in someone's browser on the LAN must
        not be able to drive the board. Browsers send Origin on cross-site requests;
        Home Assistant, curl and scripts send none and are allowed.
        3. When an api_token is set, every write (and the private reads) needs it."""
        if not host_allowed(request.host, state.config.get("allowed_hosts") or ()):
            return jsonify(error=f"this board doesn't answer to the name {request.host!r}. Open it by "
                                 "its IP address and add the name under Settings, Allowed host names "
                                 "(or set PIXELPANE_ALLOWED_HOSTS)."), 403
        write = request.method not in ("GET", "HEAD", "OPTIONS")
        if write:
            origin = request.headers.get("Origin")
            if origin and urlparse(origin).netloc != request.host:
                abort(403, "cross-site request refused")
        if token() and (write or request.path in PRIVATE_READS) and not token_ok():
            return jsonify(error="token required"), 401
        return None

    @app.after_request
    def headers(response):
        """The HTTP server adds Date itself; file responses would carry a second one,
        which reverse proxies (nginx) log as a warning on every request. Also: no
        framing (clickjacking), no MIME sniffing, and a strict content policy."""
        response.headers.pop("Date", None)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if response.mimetype == "text/html":
            response.headers.setdefault("Content-Security-Policy", CSP)
        return response

    def body():
        return request.get_json(silent=True) or {}

    def page(name):
        """A page with the look from config["ui"] on <html>, so it paints in the right
        colors at once. Both values were validated (a theme name, a #rrggbb color)."""
        ui = state.config.get("ui") or {}
        accent = ui.get("accent") or "#fdae84"
        html = PAGES[name].read_text().replace(
            '<html lang="en">', f'<html lang="en" data-theme="{ui.get("theme") or "dark"}" '
                                f'style="--accent:{accent};--on-accent:{on_accent(accent)}">', 1)
        return html, 200, {"Content-Type": "text/html; charset=utf-8"}

    @app.get("/")
    def index():
        return page("index")

    @app.get("/library")
    def library_page():
        return page("library")

    @app.get("/settings")
    def settings_page():
        return page("settings")

    @app.get("/favicon.ico")
    def favicon():
        return send_file(Path(__file__).with_name("static") / "favicon.ico", max_age=86400)

    @app.get("/api/health")
    def api_health():
        return jsonify(health(state))

    @app.get("/api/state")
    def api_state():
        kinds = {}
        for name, fn in SCENES.items():
            if plugin.enabled(state.config, fn.plugin):
                kinds.setdefault(fn.kind, []).append(name)
        return jsonify(health(state) | {
            "scenes": kinds, "theme_names": seasons.THEMES, "holidays": seasons.HOLIDAYS, "icons": gfx.ICONS,
            "pinnable": sorted(s for s in [*SCENES, *PICKERS] if plugin.pinnable(s)),
            "categories": gifs.categories(),
            "plugins": plugin.describe(state.config), "plugin_errors": plugin.ERRORS,
            "panel": panel_size(state.config), "auth": bool(token()), "host_names": sorted(local_names()),
            "data": {k: int(time.time() - v[0]) for k, v in state.data.items()}})

    @app.post("/api/state")
    def api_set():
        b = body()
        state.set(power=b.get("power"), brightness=b.get("brightness"))
        return jsonify(ok=True, power=state.power, brightness=state.brightness)

    def params_of(b):
        try:
            return plugin.check_params(b.get("scene"), b.get("params"))
        except ValueError as e:
            abort(400, str(e))

    @app.post("/api/pin")
    def api_pin():
        b = body()
        if not valid_scene(b.get("scene"), state.config) or not plugin.pinnable(b["scene"]):
            abort(400, "scene cannot be pinned")
        minutes = b.get("minutes")
        if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, (int, float))
                                    or not 0 <= minutes <= 7 * 24 * 60):
            abort(400, "minutes must be a number up to a week, or null")
        state.pin(b["scene"], params_of(b), minutes)
        return jsonify(ok=True)

    @app.delete("/api/pin")
    def api_unpin():
        state.pin(None)
        return jsonify(ok=True)

    @app.post("/api/skip")
    def api_skip():
        state.skip_scene()
        return jsonify(ok=True)

    @app.post("/api/play")
    def api_play():
        b = body()
        if not valid_scene(b.get("scene"), state.config):
            abort(400, "unknown or disabled scene")
        state.request(b["scene"], params_of(b))
        return jsonify(ok=True)

    @app.post("/api/notify")
    def api_notify():
        b = body()
        if not str(b.get("text", "")).strip():
            abort(400, "text required")
        try:
            seconds = min(120, max(3, float(b.get("seconds", 10))))
        except (TypeError, ValueError):
            abort(400, "seconds must be a number")
        state.notify({"text": str(b["text"])[:200], "icon": str(b.get("icon", "bell"))[:20],
                      "color": str(b.get("color", "#ffffff"))[:20], "flash": bool(b.get("flash")),
                      "sub": str(b.get("sub", ""))[:80], "seconds": seconds})
        return jsonify(ok=True, queued=len(state.notifications))

    @app.post("/api/data/<key>")
    def api_data(key):
        if plugin.data_ttl(state.config, key) is None:
            abort(400, "no enabled plugin takes this data key")
        state.put_data(key, body())
        return jsonify(ok=True)

    @app.get("/api/config")
    def api_config():
        return jsonify(schema.masked(state.config))

    @app.put("/api/config")
    def api_put_config():
        try:
            changes = schema.validate(body())
        except schema.ConfigError as e:
            return jsonify(error=str(e)), 400
        state.update_config(schema.reset_secrets(changes, state.config))
        state.wake.set()
        return jsonify(schema.masked(state.config))

    @app.get("/api/backup")
    def api_backup():
        """Your settings as a file (secrets left out: they stay on the board)."""
        saved = schema.masked(_read(state.config_path))
        for name, s in list(saved.get("plugins", {}).items()):
            saved["plugins"][name] = {k: v for k, v in s.items() if v != schema.MASK}
        saved.pop("api_token", None)
        doc = {"pixelpane_backup": 1, "created": local_now().isoformat(timespec="seconds"),
               "version": health(state).get("version"), "config": saved}
        stamp = local_now().strftime("%Y%m%d-%H%M")
        return Response(json.dumps(doc, indent=2), mimetype="application/json", headers={
            "Content-Disposition": f'attachment; filename="pixelpane-settings-{stamp}.json"'})

    @app.post("/api/restore")
    def api_restore():
        """Put a backup's settings back (merged over what's there; secrets are kept)."""
        b = body()
        cfg = b.get("config") if isinstance(b, dict) and b.get("pixelpane_backup") else None
        if not isinstance(cfg, dict):
            return jsonify(error="not a PixelPane settings backup"), 400
        try:
            changes = schema.validate(cfg)
        except schema.ConfigError as e:
            return jsonify(error=str(e)), 400
        state.update_config(changes, replace=[k for k in changes if k not in ("plugins",)])
        state.wake.set()
        return jsonify(schema.masked(state.config))

    @app.get("/api/logs")
    def api_logs():
        try:
            since = float(request.args.get("since", 0))
        except ValueError:
            since = 0.0
        return jsonify(logbuf.lines(since))

    @app.post("/api/system/restart")
    def api_restart():
        restart()
        return jsonify(ok=True)

    @app.get("/api/gifs")
    def api_gifs():
        return jsonify(gifs.listing())

    @app.get("/gif/<path:gid>")
    def gif_file(gid):
        p = gifs.resolve(gid)
        if not p:
            abort(404)
        return send_file(p, mimetype="image/gif", max_age=3600)

    @app.post("/api/gifs")
    def api_upload():
        theme = request.form.get("theme", "all")
        if theme != "all" and theme not in seasons.THEMES:
            abort(400, "unknown theme")
        smooth = request.form.get("smooth") in ("1", "true", "on")
        saved = []
        for f in request.files.getlist("file"):
            name = secure_filename(Path(f.filename or "upload").stem) or "upload"
            dest = VAR / "uploads" / theme / f"{name}.gif"
            n = 1
            while dest.exists():
                dest = dest.with_name(f"{name}-{n}.gif")
                n += 1
            try:
                frames = convert_upload(io.BytesIO(f.read()), dest, smooth)
            except Exception as e:
                abort(400, f"{f.filename}: not an image ({e})")
            saved.append({"id": gifs.gif_id(dest), "frames": frames})
        return jsonify(saved=saved)

    @app.delete("/api/gifs/<path:gid>")
    def api_delete(gid):
        p = gifs.resolve(gid)
        if not p or not gid.startswith("upload/"):
            abort(400, "only uploads can be deleted; remove repo GIFs in git")
        p.unlink()
        return jsonify(ok=True)

    @app.post("/api/gifs/hide")
    def api_hide():
        b = body()
        if not isinstance(b.get("id"), str) or not gifs.resolve(b["id"]):
            abort(400, "no such GIF")
        hidden = set(state.config.get("hidden_gifs", []))
        (hidden.add if b.get("hidden", True) else hidden.discard)(b.get("id"))
        state.update_config({"hidden_gifs": sorted(h for h in hidden if h)})
        return jsonify(ok=True)

    @app.patch("/api/gifs/<path:gid>")
    def api_classify_one(gid):
        if not gifs.resolve(gid):
            abort(404)
        return classify([gid], body())

    @app.post("/api/gifs/classify")
    def api_classify():
        b = body()
        ids = b.get("ids")
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            abort(400, "ids must be a list of GIF ids")
        return classify(ids, b)

    def classify(ids, b):
        """Body: {category, theme} to move GIFs (theme "all" = every day), or {reset: true}."""
        try:
            category = schema.category_name(b["category"]) if b.get("category") is not None else None
            theme = schema.theme_name(b["theme"]) if b.get("theme") is not None else None
        except schema.ConfigError as e:
            abort(400, str(e))
        n = gifs.classify(ids, category, theme, reset=bool(b.get("reset")))
        return jsonify(ok=True, changed=n)

    jobs = generate.Jobs()
    drafts = generate.Drafts(VAR / "generated")

    @app.post("/api/gifs/generate")
    def api_generate():
        """Start a draft from {"prompt": "..."} (empty: the model picks an idea), or rework
        one with {"from": draft_id, "change": "make the cat bigger"}. Nothing goes in the
        library until it is saved. Poll GET /api/gifs/generate/<job>."""
        b = body()
        prompt = str(b.get("prompt") or "")[:500]
        change = str(b.get("change") or "")[:500]
        base = None
        if b.get("from"):
            base = drafts.get(str(b["from"]))
            if not base:
                abort(404, "no such draft")
            if not change.strip():
                abort(400, "say what to change")
            prompt = base.get("prompt", "")
        settings = plugin.settings(state.config, "generator")
        if not settings.get("enabled", True):
            abort(400, "the generator plugin is off")
        if jobs.busy():
            return jsonify(error="already making one; wait for it to finish"), 429

        def work(say):
            r = generate.ask(settings, prompt, generate.season_words(local_now().date()), log=say,
                             base=base["spec"] if base else None, change=change)
            spec = r["spec"]
            try:
                category = schema.category_name(spec.get("category") or "generated")
            except schema.ConfigError:
                category = "generated"
            rec = drafts.add(r["frames"], {
                "prompt": prompt, "change": change, "parent": base["id"] if base else None,
                "title": str(spec.get("name") or prompt or "untitled")[:60], "category": category,
                "model": settings.get("model"), "provider": settings.get("provider") or "openai",
                "checked": r["checked"], "spec": spec})
            return {"draft": {k: v for k, v in rec.items() if k != "spec"}}
        return jsonify(job=jobs.start(work))

    @app.get("/api/gifs/generate/<job>")
    def api_generate_job(job):
        j = jobs.get(job)
        if not j:
            abort(404)
        return jsonify(j)

    @app.get("/api/drafts")
    def api_drafts():
        return jsonify(drafts.list())

    @app.get("/api/drafts/<did>")
    def api_draft(did):
        rec = drafts.get(did)
        if not rec:
            abort(404)
        return jsonify(rec)

    @app.get("/draft/<did>.gif")
    def draft_gif(did):
        p = drafts.gif(did)
        if not p:
            abort(404)
        return send_file(p, mimetype="image/gif", max_age=3600)

    @app.post("/api/drafts/<did>/save")
    def api_draft_save(did):
        """Into the library: {"name": "...", "category": "...", "theme": "all"}."""
        rec, src = drafts.get(did), drafts.gif(did)
        if not rec or not src:
            abort(404)
        b = body()
        try:
            category = schema.category_name(b.get("category") or rec.get("category") or "generated")
            theme = schema.theme_name(b.get("theme") or "all")
        except schema.ConfigError as e:
            abort(400, str(e))
        name = generate.slug(b.get("name") or rec.get("title") or "generated")
        dest = VAR / "uploads" / theme / f"{category}-{name}.gif"
        n = 1
        while dest.exists():
            dest = dest.with_name(f"{category}-{name}-{n}.gif")
            n += 1
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        gid = gifs.gif_id(dest)
        drafts.update(did, saved=gid)
        return jsonify(ok=True, id=gid, name=dest.name)

    @app.delete("/api/drafts/<did>")
    def api_draft_delete(did):
        """Throw a draft away (a copy already saved to the library stays there)."""
        if not drafts.delete(did):
            abort(404)
        return jsonify(ok=True)

    @app.post("/api/categories/rename")
    def api_rename_category():
        b = body()
        try:
            old, new = schema.category_name(b.get("from"), "from"), schema.category_name(b.get("to"), "to")
        except schema.ConfigError as e:
            abort(400, str(e))
        n = gifs.rename_category(old, new)
        if not n:
            abort(404, f"no GIFs in category {old}")
        return jsonify(ok=True, changed=n)

    @app.get("/api/frames")
    def frames_stream():
        """Every frame the panel shows, as it shows it: per frame two big-endian uint16s
        (cols, rows) then cols*rows RGB bytes. The control page draws these on a canvas,
        so the preview plays at the board's real speed. Ends after 30 minutes (clients
        reconnect) and sends the frame again every few seconds so a dead client is noticed."""
        me = object()
        with streams_lock:
            for s, seen in list(streams.items()):
                if time.monotonic() - seen > 10:   # its client went away
                    del streams[s]
            if len(streams) >= MAX_STREAMS:
                return jsonify(error="too many live previews open"), 503
            streams[me] = time.monotonic()

        def gen():
            last, sent_at, until = None, 0.0, time.monotonic() + 30 * 60
            try:
                while time.monotonic() < until:
                    now = streams[me] = time.monotonic()
                    frame = state.last_frame if state.effective_power() else None
                    if frame is not last or now - sent_at > 5:
                        cols, rows = panel_size(state.config)
                        img = compose(frame if frame is not None else Image.new("RGB", (32, 32)), cols, rows)
                        yield cols.to_bytes(2, "big") + rows.to_bytes(2, "big") + img.convert("RGB").tobytes()
                        last, sent_at = frame, now
                    time.sleep(1 / 40)
            finally:
                streams.pop(me, None)
        return Response(gen(), mimetype="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/preview.png")
    def preview():
        cols, rows = panel_size(state.config)
        img = compose(state.last_frame if state.effective_power() else Image.new("RGB", (32, 32)), cols, rows)
        scale = max(1, min(16, int(request.args.get("scale", max(1, 320 // cols)))))
        buf = io.BytesIO()
        img.resize((cols * scale, rows * scale), Image.NEAREST).save(buf, "PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png", max_age=0)

    return app
