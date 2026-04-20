"""Multi-provider LLM client — supports Gemini, OpenAI, Anthropic,
DeepSeek, OpenRouter, and custom OpenAI-compatible endpoints.

Users can store multiple API keys and switch between providers/models at
runtime via the ``/provider`` slash command.
"""

import re
import time
from typing import Tuple, Optional

from joomha.config import (
    get_api_key,
    get_active_provider,
    get_active_model,
    get_custom_base_url,
    LLM_TIMEOUT,
    PROVIDER_BASE_URLS,
)

# ---------------------------------------------------------------------------
# Bug 10: Regex patterns to detect credentials / secrets in code context
# ---------------------------------------------------------------------------

_SECRET_PATTERNS = [
    re.compile(
        r"""(?:api[_-]?key|token|secret|password|passwd|credentials?|auth)"""
        r"""\s*[:=]\s*['"][A-Za-z0-9+/=_\-]{16,}['"]""",
        re.IGNORECASE,
    ),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
]


def _sanitise_code(text: str) -> str:
    """Replace suspicious credential patterns with a placeholder."""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[CREDENTIAL_REDACTED]", text)
    return text


class LLMClient:
    """Thin wrapper that talks to whichever LLM provider is configured.

    Supports:
      - ``gemini``     — Google Generative AI SDK
      - ``openai``     — OpenAI Python SDK
      - ``anthropic``  — Anthropic Python SDK
      - ``deepseek``   — OpenAI-compatible (base_url = api.deepseek.com)
      - ``openrouter`` — OpenAI-compatible (base_url = openrouter.ai)
      - ``custom``     — Any OpenAI-compatible endpoint (user-defined URL)
    """

    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None):
        self.provider = provider or get_active_provider()
        self.model_id = model or get_active_model(self.provider)
        self.api_key = get_api_key(self.provider)
        if not self.api_key:
            raise ValueError(
                f"API key tidak ditemukan untuk provider '{self.provider}'. "
                f"Set environment variable atau jalankan 'joomha config set {self.provider} <key>'."
            )
        self._init_client()

    # ------------------------------------------------------------------
    # Provider categorisation
    # ------------------------------------------------------------------

    def _is_openai_compatible(self) -> bool:
        """DeepSeek, OpenRouter, custom → all use the OpenAI SDK."""
        return self.provider in ("openai", "deepseek", "openrouter", "custom")

    def _get_base_url(self) -> Optional[str]:
        """Return base_url override for OpenAI-compatible providers."""
        if self.provider in PROVIDER_BASE_URLS:
            return PROVIDER_BASE_URLS[self.provider]
        if self.provider == "custom":
            return get_custom_base_url()
        return None  # openai uses default

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Lazily import and initialise the chosen provider SDK."""

        if self.provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(self.model_id)

        elif self.provider == "anthropic":
            import anthropic
            self.client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=LLM_TIMEOUT,
            )

        elif self._is_openai_compatible():
            # OpenAI / DeepSeek / OpenRouter / Custom — all share the SDK
            from openai import OpenAI
            kwargs = {
                "api_key": self.api_key,
                "timeout": float(LLM_TIMEOUT),
            }
            base_url = self._get_base_url()
            if base_url:
                kwargs["base_url"] = base_url
            self.client = OpenAI(**kwargs)

        else:
            raise ValueError(f"Provider tidak dikenal: {self.provider}")

    # ------------------------------------------------------------------
    # Hot-swap (called from /provider command)
    # ------------------------------------------------------------------

    def switch(self, provider: str, model_id: Optional[str] = None) -> None:
        """Switch provider/model at runtime without recreating Orchestrator."""
        self.provider = provider
        self.model_id = model_id or get_active_model(provider)
        self.api_key = get_api_key(provider)
        if not self.api_key:
            raise ValueError(
                f"API key tidak ditemukan untuk provider '{provider}'. "
                f"Jalankan: joomha config set {provider} <key>"
            )
        self._init_client()

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, prompt: str) -> Tuple[str, float]:
        """Send prompt to LLM. Returns (response_text, latency_seconds)."""
        prompt = _sanitise_code(prompt)
        start = time.time()

        try:
            if self.provider == "gemini":
                response = self.model.generate_content(
                    prompt,
                    request_options={"timeout": LLM_TIMEOUT},
                )
                text = response.text

            elif self.provider == "anthropic":
                response = self.client.messages.create(
                    model=self.model_id,
                    max_tokens=2048,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = response.content[0].text

            elif self._is_openai_compatible():
                # Works for openai, deepseek, openrouter, custom
                extra_headers = {}
                if self.provider == "openrouter":
                    extra_headers["HTTP-Referer"] = "https://github.com/joomha-cli"
                    extra_headers["X-Title"] = "Joomha CLI"

                response = self.client.chat.completions.create(
                    model=self.model_id,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=2048,
                    extra_headers=extra_headers if extra_headers else None,
                )
                text = response.choices[0].message.content

            else:
                raise ValueError(f"Provider tidak dikenal: {self.provider}")

        except Exception as e:
            latency = time.time() - start
            return f"[Error dari LLM] {e!s}", latency

        latency = time.time() - start
        return text, latency

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

    def info(self) -> str:
        """Return a human-readable summary of the current provider & model."""
        return f"{self.provider} ({self.model_id})"
