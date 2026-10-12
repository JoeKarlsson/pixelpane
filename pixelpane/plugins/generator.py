"""Generator: settings for making GIFs from a text prompt (see pixelpane/generate.py)."""
from ..plugin import Plugin

plugin = Plugin(
    "generator", "GIFs from a text prompt",
    defaults={"base_url": "", "api_key": None, "model": ""},
    about="Type an idea in the GIF library (\"a cat chasing a laser dot\") or press "
          "Surprise me, and a chat model designs a looping 32x32 animation that is saved to "
          "your library like an upload. Works with any OpenAI-compatible server: LiteLLM, "
          "OpenRouter, OpenAI, Ollama. Bigger models draw better; small local ones work "
          "but get simpler. Each GIF is one request of a few thousand tokens.",
    fields=[{"key": "base_url", "label": "Server", "type": "text",
             "help": "The OpenAI-compatible API base, e.g. http://litellm:4000/v1 or https://openrouter.ai/api/v1"},
            {"key": "api_key", "label": "API key", "type": "secret",
             "help": "Sent as a Bearer token. Leave empty for servers without one."},
            {"key": "model", "label": "Model", "type": "text",
             "help": "The model name the server knows, e.g. claude-sonnet or openai/gpt-4.1"}])
