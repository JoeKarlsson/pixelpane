"""HTTP API + control page. LAN only (the board lives on the IoT VLAN)."""
import io
import time
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, abort, jsonify, request, send_file
from PIL import Image
from werkzeug.utils import secure_filename

import hmac
import os

from . import gfx, plugin, schema, seasons
from .display import compose, panel_size
from .plugin import SCENES
from .state import VAR, convert_upload

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
