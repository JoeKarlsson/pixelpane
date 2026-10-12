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
        Stub.seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        text = "Here you go:\n```json\n" + Stub.reply + "\n```"
        if self.path.endswith("/messages"):   # Anthropic's API
            out = {"content": [{"type": "text", "text": text}]}
        else:
            out = {"choices": [{"message": {"content": text}}]}
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(out).encode())

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
        for bad in ("no json here", '{"a": }', '["a"]'):
            with self.assertRaises(generate.GenerateError):
                generate.parse(bad)
        # a reply that stops a bracket or two short is repaired
        self.assertEqual(generate.parse('{"a": [1, {"b": "x'), {"a": [1, {"b": "x"}]})

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

    def test_ask_drafts_then_reviews_its_render(self):
        Stub.seen.clear()
        r = generate.ask({"base_url": self.base + "/", "api_key": "k-123", "model": "m1"}, "", "October")
        self.assertEqual(r["spec"]["name"], "Test Rocket")
        self.assertEqual(len(r["frames"]), 20)
        (path, headers, body), (_, _, review) = Stub.seen[-2:]
        self.assertEqual((path, headers["authorization"], body["model"]), ("/v1/chat/completions", "Bearer k-123", "m1"))
        self.assertIn("October", body["messages"][1]["content"])   # empty prompt: the model picks an idea
        # the review shows the model a picture of its own render
        last = review["messages"][-1]["content"]
        self.assertEqual(last[0]["type"], "image_url")
        self.assertTrue(last[0]["image_url"]["url"].startswith("data:image/png;base64,"))
        generate.ask({"base_url": self.base, "model": "m1", "review": False}, "", "October")
        self.assertNotEqual(Stub.seen[-1][2]["messages"], body["messages"])   # never a cache hit
        self.assertEqual(len(Stub.seen), 3)                                    # review off: one call
        with self.assertRaises(generate.GenerateError):
            generate.ask({"base_url": "", "model": "m"}, "x", "")
        with self.assertRaises(generate.GenerateError) as e:
            generate.ask({"base_url": "http://127.0.0.1:9/v1", "model": "m"}, "x", "", timeout=2)
        self.assertIn("could not reach", str(e.exception))

    def test_anthropic_provider(self):
        Stub.seen.clear()
        base = self.base[:-3]   # without /v1: the client adds /v1/messages
        r = generate.ask({"provider": "anthropic", "base_url": base, "api_key": "sk-ant", "model": "claude-x"},
                         "a rocket", "", log=None)
        self.assertEqual(r["spec"]["name"], "Test Rocket")
        (path, headers, body), (_, _, review) = Stub.seen
        self.assertEqual((path, headers["x-api-key"], headers["anthropic-version"]), ("/v1/messages", "sk-ant", "2023-06-01"))
        self.assertIn("32x32", body["system"])
        self.assertEqual(review["messages"][-1]["content"][0]["type"], "image")

    def test_refine_sends_the_earlier_design(self):
        Stub.seen.clear()
        generate.ask({"base_url": self.base, "model": "m", "review": False}, "a rocket", "",
                     base={"name": "old"}, change="make it red")
        msgs = Stub.seen[-1][2]["messages"]
        self.assertEqual(msgs[2], {"role": "assistant", "content": '{"name":"old"}'})
        self.assertIn("make it red", msgs[3]["content"])

    def test_api_drafts_then_save_or_discard(self):
        support.reset()
        state = State()
        client = create_app(state, GifLibrary(state, random.Random(0)), health).test_client()

        def run(**body):
            r = client.post("/api/gifs/generate", json=body)
            self.assertEqual(r.status_code, 200, r.data)
            for _ in range(200):
                j = client.get("/api/gifs/generate/" + r.get_json()["job"]).get_json()
                if j["state"] != "working":
                    return j
                time.sleep(0.05)
            self.fail("job never finished")

        self.assertIn("server and model", run(prompt="a rocket")["error"])     # not set up yet
        state.update_config({"plugins": {"generator": {"base_url": self.base, "model": "m1"}}})
        j = run(prompt="a rocket")
        d = j["draft"]
        self.assertEqual((j["state"], d["title"], d["category"], d["prompt"], d["saved"]),
                         ("done", "Test Rocket", "space", "a rocket", None))
        self.assertIs(d["checked"], True)               # the review pass ran
        # a draft is NOT in the library, but it is listed, viewable and playable
        self.assertFalse(any(g["upload"] for g in client.get("/api/gifs").get_json()))
        self.assertEqual([x["id"] for x in client.get("/api/drafts").get_json()], [d["id"]])
        self.assertEqual(client.get(f"/draft/{d['id']}.gif").status_code, 200)
        self.assertIn("spec", client.get(f"/api/drafts/{d['id']}").get_json())
        self.assertEqual(client.post("/api/play", json={"scene": "gif", "params": {"id": f"draft/{d['id']}.gif"}}).status_code, 200)
        # save it, with a name, category and theme of your choosing
        r = client.post(f"/api/drafts/{d['id']}/save", json={"name": "Blast Off", "category": "rockets", "theme": "july4"})
        self.assertEqual(r.get_json()["id"], "upload/july4/rockets-blast-off.gif")
        listed = {g["id"]: g for g in client.get("/api/gifs").get_json()}
        self.assertEqual(listed["upload/july4/rockets-blast-off.gif"]["theme"], "july4")
        self.assertEqual(client.get(f"/api/drafts/{d['id']}").get_json()["saved"], "upload/july4/rockets-blast-off.gif")
        self.assertEqual(client.post(f"/api/drafts/{d['id']}/save", json={"theme": "nope"}).status_code, 400)
        # refine makes a new draft from the old one
        j2 = run(**{"from": d["id"], "change": "make it red"})
        self.assertEqual((j2["draft"]["parent"], j2["draft"]["change"]), (d["id"], "make it red"))
        self.assertEqual(client.post("/api/gifs/generate", json={"from": d["id"]}).status_code, 400)
        self.assertEqual(client.post("/api/gifs/generate", json={"from": "0" * 12, "change": "x"}).status_code, 404)
        # discard drops the draft but not the saved copy
        self.assertEqual(client.delete(f"/api/drafts/{d['id']}").status_code, 200)
        self.assertEqual(client.get(f"/draft/{d['id']}.gif").status_code, 404)
        self.assertIn("upload/july4/rockets-blast-off.gif", {g["id"] for g in client.get("/api/gifs").get_json()})
        self.assertEqual(client.delete("/api/drafts/../../x").status_code, 404)
        self.assertEqual(client.get("/api/gifs/generate/nope").status_code, 404)

if __name__ == "__main__":
    unittest.main()
