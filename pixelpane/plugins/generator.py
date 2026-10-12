"""Generator: settings for making GIFs from a text prompt (see pixelpane/generate.py)."""
from ..generate import PROVIDERS
from ..plugin import Plugin

plugin = Plugin(
    "generator", "GIFs from a text prompt",
    defaults={"provider": "openai", "base_url": "", "api_key": None, "model": "", "review": True},
    about="Describe an idea in Make a GIF (\"a cat chasing a laser dot\") or press Surprise me, "
          "and a chat model designs a looping 32x32 animation. You see it first: save it to the "
          "library, refine it (\"make the cat bigger\"), try again or throw it out. Works with any "
          "OpenAI-compatible server (LiteLLM, OpenRouter, OpenAI, Ollama, vLLM...) or Anthropic's "
          "API. Bigger models draw much better than small local ones.",
    fields=[{"key": "provider", "label": "Kind of server", "type": "select",
             "options": [{"value": k, "label": v} for k, v in PROVIDERS.items()]},
            {"key": "base_url", "label": "Server URL", "type": "text",
             "placeholder": "http://litellm:4000/v1",
             "help": "OpenAI-compatible: the API base, e.g. http://litellm:4000/v1, "
                     "https://openrouter.ai/api/v1 or https://api.openai.com/v1. "
                     "Anthropic: leave empty for https://api.anthropic.com."},
            {"key": "api_key", "label": "API key", "type": "secret", "reset_on": ["base_url", "provider"],
             "help": "Leave empty for servers without one (a local Ollama). Changing the server "
                     "clears it, so enter it again."},
            {"key": "model", "label": "Model", "type": "text", "placeholder": "cloud-smart",
             "help": "The model name the server knows, e.g. a LiteLLM alias, openai/gpt-4.1 or "
                     "claude-sonnet-4-5."},
            {"key": "review", "label": "Check its own work", "type": "toggle",
             "text": "Show the model its render and let it fix what's wrong",
             "help": "Better results for about twice the time and tokens. Needs a model that can "
                     "read images; with one that can't, you get the first draft."}])
