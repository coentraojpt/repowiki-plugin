"""
repowiki provider abstraction layer.

v1 uses Claude Code's native tools (no external API calls).
This module is the extension point for v2 multi-provider support.

To add a new provider:
1. Subclass BaseProvider
2. Implement generate()
3. Register in PROVIDERS dict
4. Invoke via: python -m repowiki.providers --provider <name> --input <json> --output <md>
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path


class BaseProvider(ABC):
    """Common interface for all repowiki AI providers."""

    name: str = "base"

    @abstractmethod
    def generate(self, section: dict, source_files: dict[str, str]) -> str:
        """
        Generate wiki markdown for a section.

        Args:
            section: Section definition from _architecture.json
            source_files: Mapping of {file_path: file_content} for key files

        Returns:
            Markdown string for the wiki page
        """

    def supports_streaming(self) -> bool:
        return False


class ClaudeProvider(BaseProvider):
    """
    Default provider: uses the Anthropic API directly.
    Requires ANTHROPIC_API_KEY environment variable.
    """

    name = "claude"

    def generate(self, section: dict, source_files: dict[str, str]) -> str:
        try:
            import anthropic
        except ImportError:
            raise RuntimeError("anthropic package required: pip install anthropic")

        client = anthropic.Anthropic()
        files_block = "\n\n".join(
            f"### {path}\n```\n{content}\n```"
            for path, content in source_files.items()
        )
        prompt = (
            f"Generate a comprehensive wiki page for the '{section['title']}' section.\n\n"
            f"Context: {section.get('context', '')}\n\n"
            f"Source files:\n{files_block}"
        )
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider stub. Requires OPENAI_API_KEY environment variable.
    """

    name = "openai"

    def generate(self, section: dict, source_files: dict[str, str]) -> str:
        raise NotImplementedError("OpenAI provider not yet implemented")


class OllamaProvider(BaseProvider):
    """
    Local Ollama provider stub. Requires Ollama running at localhost:11434.
    """

    name = "ollama"

    def generate(self, section: dict, source_files: dict[str, str]) -> str:
        raise NotImplementedError("Ollama provider not yet implemented")


PROVIDERS: dict[str, type[BaseProvider]] = {
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
}


def get_provider(name: str) -> BaseProvider:
    if name not in PROVIDERS:
        raise ValueError(f"Unknown provider '{name}'. Available: {list(PROVIDERS)}")
    return PROVIDERS[name]()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="repowiki provider CLI")
    parser.add_argument("--provider", default="claude", choices=list(PROVIDERS))
    parser.add_argument("--input", required=True, help="Path to section JSON file")
    parser.add_argument("--output", required=True, help="Path to write wiki markdown")
    args = parser.parse_args()

    section = json.loads(Path(args.input).read_text(encoding="utf-8"))
    provider = get_provider(args.provider)
    result = provider.generate(section, source_files={})
    Path(args.output).write_text(result, encoding="utf-8")
    print(f"Written to {args.output}")
