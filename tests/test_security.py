"""The API's defenses: library paths, host names, secrets, params, headers and limits."""
import json
import random
import unittest

from tests import support

support.load_plugins()
from pixelpane import generate  # noqa: E402
from pixelpane.app import health  # noqa: E402
from pixelpane.plugins.now_playing import ArtCache  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app, host_allowed  # noqa: E402


class SecurityTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        support.VAR.mkdir(parents=True, exist_ok=True)
        (support.VAR / "config.json").write_text(json.dumps({"api_token": "s3cret-token"}))
        self.state = State()
        self.gifs = GifLibrary(self.state, random.Random(0))
        self.restarts = []
        self.client = create_app(self.state, self.gifs, health,
                                 restart=lambda: self.restarts.append(1)).test_client()
        self.outside = support.ROOT / "outside.gif"
        support.make_gif(self.outside)

    def test_gif_ids_never_leave_the_library(self):
        for gid in (f"upload/{self.outside}", f"upload//{self.outside}", f"repo/{self.outside}",
                    "upload/../config.json", "upload/../../outside.gif", f"upload/%2F{self.outside}"):
            self.assertIsNone(self.gifs.resolve(gid), gid)
        r = self.client.get("/gif/upload/" + str(self.outside).replace("/", "%2F"))
        self.assertEqual(r.status_code, 404)
        r = self.client.delete("/api/gifs/upload/" + str(self.outside).replace("/", "%2F"),
                               headers={"X-PixelPane-Token": "s3cret-token"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(self.outside.exists())
        # a symlink inside the library that points out of it doesn't count either
        link = support.VAR / "uploads" / "all" / "sneaky.gif"
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(self.outside)
        self.assertIsNone(self.gifs.resolve("upload/all/sneaky.gif"))
        self.assertIsNotNone(self.gifs.resolve("repo/retro-mario-run.gif"))

    def test_only_our_host_names(self):
        self.assertTrue(host_allowed("192.168.1.20"))
        self.assertTrue(host_allowed("[fe80::1]:8080"))
        self.assertTrue(host_allowed("localhost:8080"))
        self.assertFalse(host_allowed("attacker.example"))
        self.assertTrue(host_allowed("pane.example.com", ["pane.example.com"]))
        r = self.client.get("/api/health", headers={"Host": "rebind.attacker.example"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("allowed host", r.get_json()["error"].lower())
        self.assertEqual(self.client.get("/api/health", headers={"Host": "10.0.0.5"}).status_code, 200)

    def test_changing_the_server_clears_the_saved_key(self):
        tok = {"X-PixelPane-Token": "s3cret-token"}
        self.client.put("/api/config", headers=tok, json={"plugins": {"generator": {
            "base_url": "http://litellm:4000/v1", "api_key": "sk-real", "model": "m"}}})
        # the page sends everything back with the key masked: unchanged server keeps it
        self.client.put("/api/config", headers=tok, json={"plugins": {"generator": {
            "base_url": "http://litellm:4000/v1", "api_key": "••••••••", "model": "m2"}}})
        self.assertEqual(self.state.config["plugins"]["generator"]["api_key"], "sk-real")
        # a new server without a new key: the key is dropped, not sent to the new server
        self.client.put("/api/config", headers=tok, json={"plugins": {"generator": {
            "base_url": "http://attacker:9999/v1", "api_key": "••••••••"}}})
        self.assertIsNone(self.state.config["plugins"]["generator"]["api_key"])

    def test_scene_params_are_declared(self):
        tok = {"X-PixelPane-Token": "s3cret-token"}
        bad = self.client.post("/api/play", headers=tok, json={"scene": "gif", "params": {"path": str(self.outside)}})
        self.assertEqual(bad.status_code, 400)
        ok = self.client.post("/api/play", headers=tok, json={"scene": "gif", "params": {"id": "repo/retro-mario-run.gif"}})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.post("/api/pin", headers=tok, json={
            "scene": "message", "params": {"text": "HI", "color": "#ff0000"}}).status_code, 200)
        self.assertEqual(self.client.post("/api/pin", headers=tok, json={
            "scene": "message", "params": {"text": 5}}).status_code, 400)
        self.assertEqual(self.client.post("/api/pin", headers=tok, json={
            "scene": "on_air", "minutes": "soon"}).status_code, 400)
        self.assertEqual(self.client.post("/api/notify", headers=tok, json={
            "text": "x", "seconds": "lots"}).status_code, 400)

    def test_security_headers(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", r.headers["Content-Security-Policy"])
        self.assertIn("script-src 'self'", self.client.get("/settings").headers["Content-Security-Policy"])

    def test_private_reads_and_system_need_the_token(self):
        self.assertEqual(self.client.get("/api/logs").status_code, 401)
        self.assertEqual(self.client.get("/api/backup").status_code, 401)
        self.assertEqual(self.client.post("/api/system/restart").status_code, 401)
        self.assertEqual(self.restarts, [])
        tok = {"X-PixelPane-Token": "s3cret-token"}
        self.assertEqual(self.client.get("/api/logs", headers=tok).status_code, 200)
        self.assertEqual(self.client.post("/api/system/restart", headers=tok).status_code, 200)
        self.assertEqual(self.restarts, [1])

    def test_one_generate_job_at_a_time(self):
        jobs = generate.Jobs()
        import threading
        gate = threading.Event()
        jobs.start(lambda say: gate.wait(5) and {})
        self.assertTrue(jobs.busy())
        gate.set()


class ArtHostTest(unittest.TestCase):
    def test_hosts_match_exactly(self):
        art = ArtCache(lambda: ["http://ha.local:8123/", "https://art.example/covers"])
        for url in ("http://ha.local:8123/api/media_player_proxy/x", "https://art.example/covers/1.jpg"):
            self.assertTrue(art.allowed(url), url)
        for url in ("http://ha.local:8123.evil.example/x", "http://ha.local:9000/x", "https://ha.local:8123/x",
                    "https://art.example/other/1.jpg", "file:///etc/passwd", "http://evil.example/x", None):
            self.assertFalse(art.allowed(url), url)
        # a host written without a trailing slash still only matches itself
        self.assertFalse(ArtCache(lambda: ["http://ha.local:8123"]).allowed("http://ha.local:8123.evil.example/"))


class BackupTest(unittest.TestCase):
    def setUp(self):
        support.reset()
        self.state = State()
        self.client = create_app(self.state, GifLibrary(self.state, random.Random(0)), health).test_client()

    def test_backup_leaves_secrets_out_and_restores(self):
        self.client.put("/api/config", json={"rotation": ["clock", "gif"], "dwell": {"gif": 9},
                                             "plugins": {"generator": {"base_url": "http://x/v1", "api_key": "sk-1"}}})
        r = self.client.get("/api/backup")
        self.assertIn("attachment", r.headers["Content-Disposition"])
        doc = r.get_json()
        self.assertNotIn("sk-1", r.get_data(as_text=True))
        self.assertEqual(doc["config"]["rotation"], ["clock", "gif"])
        self.client.put("/api/config", json={"rotation": ["moon"]})
        self.assertEqual(self.client.post("/api/restore", json={"rotation": []}).status_code, 400)
        self.assertEqual(self.client.post("/api/restore", json=doc).status_code, 200)
        self.assertEqual(self.state.config["rotation"], ["clock", "gif"])
        self.assertEqual(self.state.config["plugins"]["generator"]["api_key"], "sk-1")   # kept


if __name__ == "__main__":
    unittest.main()
