"""
repowiki provider abstraction — AI backend for standalone CLI mode.

Each provider receives a fully-formed prompt string and returns markdown text.
The caller (cli.py) is responsible for building prompts.

Usage (CLI):
  python cli.py --provider ollama --model gemma4
  python cli.py --provider ollama --model gemma4:9b --host http://localhost:11434
  python cli.py --provider claude          # needs ANTHROPIC_API_KEY
  python cli.py --provider openai          # needs OPENAI_API_KEY

Adding a new provider:
  1. Subclass BaseProvider, implement generate(prompt) -> str
  2. Add to PROVIDERS dict at the bottom
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from abc import ABC, abstractmethod


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Send prompt to AI and return the generated text."""

    def check_available(self) -> tuple[bool, str]:
        """Return (available, reason). Override for pre-flight checks."""
        return True, "ok"


# ── Ollama ──────────────────────────────────────────────────────────────────

class OllamaProvider(BaseProvider):
    """
    Local Ollama provider. Requires Ollama running at `host`.

    Recommended models for wiki generation:
      gemma4         (2B  — fast, limited quality)
      gemma4:9b      (9B  — good balance, 128K context)
      gemma4:27b     (27B — best local quality)
      llama3.2       (3B  — fast)
      llama3.1:8b    (8B  — good general purpose)
      qwen2.5:7b     (7B  — strong code understanding)
      phi4           (14B — Microsoft, good docs)

    Install a model: ollama pull gemma4:9b
    """

    name = "ollama"

    def __init__(self, model: str = "gemma4", host: str = "http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def check_available(self) -> tuple[bool, str]:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
            models = [m["name"].split(":")[0] for m in data.get("models", [])]
            model_base = self.model.split(":")[0]
            if model_base not in models and self.model not in [m["name"] for m in data.get("models", [])]:
                available = ", ".join(m["name"] for m in data.get("models", [])) or "none"
                return False, f"Model '{self.model}' not found in Ollama. Available: {available}\nRun: ollama pull {self.model}"
            return True, "ok"
        except urllib.error.URLError:
            return False, f"Ollama not running at {self.host}\nStart with: ollama serve"
        except Exception as e:
            return False, f"Ollama check failed: {e}"

    def generate(self, prompt: str) -> str:
        payload = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,      # lower = more factual, less creative
                "num_predict": 4096,     # max tokens to generate
                "num_ctx": 8192,         # context window (increase if model supports)
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                result = json.loads(resp.read())
                return result.get("response", "")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama request failed: {e}")


# ── Claude (Anthropic API) ──────────────────────────────────────────────────

class ClaudeProvider(BaseProvider):
    """
    Anthropic Claude API provider.
    Requires: pip install anthropic  +  ANTHROPIC_API_KEY env var.
    Uses prompt caching on the system prompt for cost efficiency.
    """

    name = "claude"
    DEFAULT_MODEL = "claude-sonnet-4-6"

    def __init__(self, model: str = DEFAULT_MODEL, **_):
        self.model = model

    def check_available(self) -> tuple[bool, str]:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False, "ANTHROPIC_API_KEY environment variable not set"
        try:
            import anthropic  # noqa: F401
            return True, "ok"
        except ImportError:
            return False, "anthropic package not installed. Run: pip install anthropic"

    def generate(self, prompt: str) -> str:
        import anthropic

        client = anthropic.Anthropic()
        message = client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


# ── OpenAI ──────────────────────────────────────────────────────────────────

class OpenAIProvider(BaseProvider):
    """
    OpenAI API provider.
    Requires: pip install openai  +  OPENAI_API_KEY env var.
    """

    name = "openai"
    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(self, model: str = DEFAULT_MODEL, **_):
        self.model = model

    def check_available(self) -> tuple[bool, str]:
        if not os.environ.get("OPENAI_API_KEY"):
            return False, "OPENAI_API_KEY environment variable not set"
        try:
            import openai  # noqa: F401
            return True, "ok"
        except ImportError:
            return False, "openai package not installed. Run: pip install openai"

    def generate(self, prompt: str) -> str:
        from openai import OpenAI

        client = OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        return response.choices[0].message.content


# ── Registry ─────────────────────────────────────────────────────────────────

PROVIDERS: dict[str, type[BaseProvider]] = {
    "ollama": OllamaProvider,
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
}


def get_provider(name: str, **kwargs) -> BaseProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {list(PROVIDERS)}")
    provider = PROVIDERS[name](**kwargs)
    ok, reason = provider.check_available()
    if not ok:
        raise RuntimeError(f"Provider '{name}' not available:\n  {reason}")
    return provider
