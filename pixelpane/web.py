"""HTTP API + control page. LAN only (the board lives on the IoT VLAN)."""
import io
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, Response, abort, jsonify, request, send_file
from PIL import Image
from werkzeug.utils import secure_filename

import hmac
import os

from . import generate, gfx, plugin, schema, seasons
from .display import compose, panel_size
from .plugin import SCENES
from .state import VAR, convert_upload
from .state import now as local_now

INDEX = Path(__file__).with_name("index.html")
PINNABLE = {"on_air", "message", "clock", "weather", "now_playing", "calendar", "fire", "plasma",
            "life", "matrix_rain", "starfield", "homelab", "tiles", "seasonal",
            "generative"} | set(seasons.THEMES)


def valid_scene(name, config=None):
    """A known scene (or seasonal/generative/gif:<category>), from an enabled plugin if config is given."""
    if not schema.valid_scene(name):
        return False
    base = str(name).partition(":")[0]
    if config is None:
        return True
    if base in ("seasonal", "generative"):
        return plugin.enabled(config, base)
    return plugin.scene_enabled(config, base)


def create_app(state, gifs, health):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

    @app.before_request
    def same_origin_writes():
        """Refuse cross-site writes: a web page open in someone's browser on the LAN must
        not be able to drive the board. Browsers send Origin on cross-site requests;
        Home Assistant, curl and scripts send none and are allowed."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return None
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403, "cross-site request refused")
        token = state.config.get("api_token") or os.environ.get("PIXELPANE_TOKEN")
        if token:  # optional: when set, every write needs it
            given = request.headers.get("X-PixelPane-Token") or ""
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                given = auth[7:]
            if not hmac.compare_digest(given.encode(), token.encode()):
                return jsonify(error="token required"), 401
        return None

    @app.after_request
    def one_date_header(response):
        """The HTTP server adds Date itself; file responses would carry a second one,
        which reverse proxies (nginx) log as a warning on every request."""
        response.headers.pop("Date", None)
        return response

    def body():
        return request.get_json(silent=True) or {}

    @app.get("/")
    def index():
        return INDEX.read_text(), 200, {"Content-Type": "text/html; charset=utf-8"}

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
            "scenes": kinds, "theme_names": seasons.THEMES, "icons": gfx.ICONS,
            "pinnable": sorted(PINNABLE), "categories": gifs.categories(),
            "plugins": plugin.describe(state.config), "panel": panel_size(state.config),
            "auth": bool(state.config.get("api_token") or os.environ.get("PIXELPANE_TOKEN")),
            "data": {k: int(time.time() - v[0]) for k, v in state.data.items()}})

    @app.post("/api/state")
    def api_set():
        b = body()
        state.set(power=b.get("power"), brightness=b.get("brightness"))
        return jsonify(ok=True, power=state.power, brightness=state.brightness)

    @app.post("/api/pin")
    def api_pin():
        b = body()
        if b.get("scene") not in PINNABLE or not valid_scene(b.get("scene"), state.config):
            abort(400, "scene cannot be pinned")
        state.pin(b["scene"], b.get("params"), b.get("minutes"))
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
        state.request(b["scene"], b.get("params"))
        return jsonify(ok=True)

    @app.post("/api/notify")
    def api_notify():
        b = body()
        if not str(b.get("text", "")).strip():
            abort(400, "text required")
        state.notify({"text": str(b["text"])[:200], "icon": b.get("icon", "bell"),
                      "color": b.get("color", "#ffffff"), "flash": bool(b.get("flash")),
                      "sub": str(b.get("sub", ""))[:80],
                      "seconds": min(120, max(3, float(b.get("seconds", 10))))})
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
        state.update_config(changes)
        state.wake.set()
        return jsonify(schema.masked(state.config))

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

    @app.post("/api/gifs/generate")
    def api_generate():
        """Start making a GIF from {"prompt": "...", "theme": "all"}; an empty prompt lets
        the model pick an idea for the season. Poll GET /api/gifs/generate/<job>."""
        b = body()
        prompt = str(b.get("prompt") or "")[:500]
        try:
            theme = schema.theme_name(b.get("theme") or "all")
        except schema.ConfigError as e:
            abort(400, str(e))
        settings = plugin.settings(state.config, "generator")
        if not settings.get("enabled", True):
            abort(400, "the generator plugin is off")

        def work():
            spec = generate.ask(settings, prompt, generate.season_words(local_now().date()))
            frames = generate.render(spec)
            try:
                category = schema.category_name(spec.get("category") or "generated")
            except schema.ConfigError:
                category = "generated"
            name = generate.slug(spec.get("name") or prompt)
            dest = VAR / "uploads" / theme / f"{category}-{name}.gif"
            n = 1
            while dest.exists():
                dest = dest.with_name(f"{category}-{name}-{n}.gif")
                n += 1
            dest.parent.mkdir(parents=True, exist_ok=True)
            imgs = [f for f, _ in frames]
            imgs[0].save(dest, save_all=True, append_images=imgs[1:], loop=0,
                         duration=[int(d * 1000) for _, d in frames], disposal=1)
            return {"id": gifs.gif_id(dest), "name": dest.name, "category": category,
                    "title": str(spec.get("name") or name)[:60], "frames": len(imgs)}
        return jsonify(job=jobs.start(work))

    @app.get("/api/gifs/generate/<job>")
    def api_generate_job(job):
        j = jobs.get(job)
        if not j:
            abort(404)
        return jsonify(j)

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
        def gen():
            last, sent_at, until = None, 0.0, time.monotonic() + 30 * 60
            while time.monotonic() < until:
                frame = state.last_frame if state.power else None
                now = time.monotonic()
                if frame is not last or now - sent_at > 5:
                    cols, rows = panel_size(state.config)
                    img = compose(frame if frame is not None else Image.new("RGB", (32, 32)), cols, rows)
                    yield cols.to_bytes(2, "big") + rows.to_bytes(2, "big") + img.convert("RGB").tobytes()
                    last, sent_at = frame, now
                time.sleep(1 / 40)
        return Response(gen(), mimetype="application/octet-stream",
                        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get("/preview.png")
    def preview():
        cols, rows = panel_size(state.config)
        img = compose(state.last_frame if state.power else Image.new("RGB", (32, 32)), cols, rows)
        scale = max(1, min(16, int(request.args.get("scale", max(1, 320 // cols)))))
        buf = io.BytesIO()
        img.resize((cols * scale, rows * scale), Image.NEAREST).save(buf, "PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png", max_age=0)

    return app
