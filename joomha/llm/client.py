"""[PENANDA]"""


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
# Regex pendeteksi kredensial/rahasia
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
    """Ganti kredensial dengan teks placeholder"""
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[CREDENTIAL_REDACTED]", text)
    return text


class LLMClient:
    """[PENANDA]"""


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
    # Kategori provider
    # ------------------------------------------------------------------

    def _is_openai_compatible(self) -> bool:
        """[PENANDA]"""
        return self.provider in ("openai", "deepseek", "openrouter", "custom")

    def _get_base_url(self) -> Optional[str]:
        """Ambil URL dasar custom"""
        if self.provider in PROVIDER_BASE_URLS:
            return PROVIDER_BASE_URLS[self.provider]
        if self.provider == "custom":
            return get_custom_base_url()
        return None  # OpenAI menggunakan default

    # ------------------------------------------------------------------
    # Inisialisasi
    # ------------------------------------------------------------------

    def _init_client(self) -> None:
        """Muat SDK provider yang dipilih"""

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
            # [INFO] OpenAI / DeepSeek / OpenRouter / Custom — all share the SDK
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
    # Ganti kilat provider
    # ------------------------------------------------------------------

    def switch(self, provider: str, model_id: Optional[str] = None) -> None:
        """Ganti model tanpa memuat ulang sistem"""
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
    # Proses pembuatan kode
    # ------------------------------------------------------------------

    def generate(self, prompt: str) -> Tuple[str, float]:
        """Kirim pertanyaan ke LLM"""
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
                # Kompatibel beragam provider
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
    # Pembantu Tampilan
    # ------------------------------------------------------------------

    def info(self) -> str:
        """Ringkasan model aktif"""
        return f"{self.provider} ({self.model_id})"
