import json
import random
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from tests import support

support.load_plugins()
from pixelpane import generate  # noqa: E402
from pixelpane.app import health  # noqa: E402
from pixelpane.state import GifLibrary, State  # noqa: E402
from pixelpane.web import create_app  # noqa: E402

SPEC = {
    "name": "Test Rocket", "category": "Space", "seconds": 2, "fps": 10,
    "background": ["#000010", "#100030"],
    "effects": [{"type": "stars", "count": 20}, {"type": "snow"}, {"type": "fire"}, {"type": "nope"}],
    "layers": [
        {"type": "rect", "x": 0, "y": 30, "w": 32, "h": 2, "color": "#205020"},
        {"type": "circle", "x": 26, "y": 5, "r": 3, "color": "#ffffaa", "motion": {"pulse": True}},
        {"type": "line", "x1": 0, "y1": 29, "x2": 31, "y2": 29, "color": "#00ff00"},
        {"type": "pixels", "points": [[1, 1], [2, 2], [99, 99], "bad"], "color": "#ff00ff"},
        {"type": "sprite", "x": 10, "y": 10, "palette": {"a": "#ff4040", "b": "#ffffff"},
         "frames": [[".a.", "aba", ".a."], ["a.a", ".b.", "a.a"]], "motion": {"move": [32, 0], "wrap": True}},
        {"type": "text", "text": "go", "y": 20, "color": "#ffaa00", "font": "4x6", "motion": {"blink": True}},
        {"type": "rect", "x": 4, "y": 4, "w": 3, "h": 3, "color": "#00ffff", "motion": {"spin": 90, "bob": 2, "sway": 1}},
        {"type": "mystery"},
    ],
}


class Stub(BaseHTTPRequestHandler):
    """A tiny OpenAI-compatible chat endpoint."""
    reply = json.dumps(SPEC)
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Stub.seen.append((self.path, self.headers.get("Authorization"), body))
        out = json.dumps({"choices": [{"message": {"content": "Here you go:\n```json\n" + Stub.reply + "\n```"}}]})
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out.encode())

    def log_message(self, *a):
        pass


class GenerateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_parse_finds_the_json(self):
        self.assertEqual(generate.parse('<think>{"no": 1}</think> sure: {"a": "x}y", "b": {"c": 1}} bye'),
                         {"a": "x}y", "b": {"c": 1}})
        self.assertEqual(generate.parse('{"q": "say \\"hi\\" }"}'), {"q": 'say "hi" }'})
        for bad in ("no json here", '{"a": 1', '{"a": }'):
            with self.assertRaises(generate.GenerateError):
                generate.parse(bad)

    def test_render_every_layer_and_effect(self):
        frames = generate.render(SPEC)
        self.assertEqual(len(frames), 20)
        self.assertTrue(all(f.size == (32, 32) and abs(d - 0.1) < 1e-9 for f, d in frames))
        self.assertGreater(len({f.tobytes() for f, _ in frames}), 10)   # it moves
        self.assertEqual(frames[0][0].getpixel((1, 1)), (255, 0, 255))
        # halfway through the loop the sprite has moved half the panel
        self.assertNotEqual(frames[0][0].tobytes(), frames[10][0].tobytes())

    def test_render_rejects_blank_and_clamps_nonsense(self):
        with self.assertRaises(generate.GenerateError):
            generate.render({"layers": []})
        frames = generate.render({"seconds": 999, "fps": "fast", "background": "#zzzzzz",
                                  "layers": [{"type": "circle", "r": 1e9, "x": float("nan"), "color": "#fff"}]})
        self.assertEqual(len(frames), 40)   # 4 s at the default 10 fps

    def test_ask_sends_key_and_model(self):
        Stub.seen.clear()
        spec = generate.ask({"base_url": self.base + "/", "api_key": "k-123", "model": "m1"}, "", "October")
        self.assertEqual(spec["name"], "Test Rocket")
        path, auth, body = Stub.seen[-1]
        self.assertEqual((path, auth, body["model"]), ("/v1/chat/completions", "Bearer k-123", "m1"))
        self.assertIn("October", body["messages"][1]["content"])   # empty prompt: the model picks an idea
        generate.ask({"base_url": self.base, "model": "m1"}, "", "October")
        self.assertNotEqual(Stub.seen[-1][2]["messages"], body["messages"])   # never a cache hit
        with self.assertRaises(generate.GenerateError):
            generate.ask({"base_url": "", "model": "m"}, "x", "")
        with self.assertRaises(generate.GenerateError) as e:
            generate.ask({"base_url": "http://127.0.0.1:9/v1", "model": "m"}, "x", "", timeout=2)
        self.assertIn("could not reach", str(e.exception))

    def test_api_makes_a_gif_in_the_library(self):
        support.reset()
        state = State()
        client = create_app(state, GifLibrary(state, random.Random(0)), health).test_client()

        def run(prompt, theme="all"):
            r = client.post("/api/gifs/generate", json={"prompt": prompt, "theme": theme})
            self.assertEqual(r.status_code, 200)
            for _ in range(100):
                j = client.get("/api/gifs/generate/" + r.get_json()["job"]).get_json()
                if j["state"] != "working":
                    return j
                time.sleep(0.05)
            self.fail("job never finished")

        self.assertIn("server and model", run("a rocket")["error"])     # not set up yet
        state.update_config({"plugins": {"generator": {"base_url": self.base, "model": "m1"}}})
        j = run("a rocket", "halloween")
        self.assertEqual((j["state"], j["category"], j["title"]), ("done", "space", "Test Rocket"))
        self.assertEqual(j["id"], "upload/halloween/space-test-rocket.gif")
        listed = {g["id"]: g for g in client.get("/api/gifs").get_json()}
        self.assertEqual(listed[j["id"]]["theme"], "halloween")
        self.assertEqual(run("again", "halloween")["id"], "upload/halloween/space-test-rocket-1.gif")
        self.assertEqual(client.post("/api/gifs/generate", json={"theme": "easter"}).status_code, 400)
        self.assertEqual(client.get("/api/gifs/generate/nope").status_code, 404)


if __name__ == "__main__":
    unittest.main()
