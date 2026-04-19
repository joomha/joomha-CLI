"""Multi-provider LLM client — Gemini (default), OpenAI, Anthropic."""

import time
from typing import Tuple, Optional

from joomha.config import get_api_key, get_active_provider


class LLMClient:
    """Thin wrapper that talks to whichever LLM provider is configured."""

    def __init__(self, provider: Optional[str] = None):
        self.provider = provider or get_active_provider()
        self.api_key = get_api_key(self.provider)
        if not self.api_key:
            raise ValueError(
                f"API key tidak ditemukan untuk provider '{self.provider}'. "
                f"Set environment variable atau jalankan 'joomha config set {self.provider} <key>'."
            )
        self._init_client()

    def _init_client(self) -> None:
        """Lazily import and initialise the chosen provider SDK."""
        if self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel("gemini-flash-latest")

        elif self.provider == "openai":
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)

        elif self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)

        else:
            raise ValueError(f"Provider tidak dikenal: {self.provider}")

    def generate(self, prompt: str) -> Tuple[str, float]:
        """Send prompt to LLM. Returns (response_text, latency_seconds)."""
        start = time.time()

        try:
            if self.provider == "gemini":
                response = self.model.generate_content(prompt)
                text = response.text

            elif self.provider == "openai":
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048,
                )
                text = response.choices[0].message.content

            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text

            else:
                raise ValueError(f"Provider tidak dikenal: {self.provider}")

        except Exception as e:
            latency = time.time() - start
            return f"[Error dari LLM] {e!s}", latency

        latency = time.time() - start
        return text, latency
