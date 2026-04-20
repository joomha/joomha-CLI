import base64
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Optional, Dict, List

# ---------------------------------------------------------------------------
# Directory & file paths
# ---------------------------------------------------------------------------

CONFIG_DIR = Path.home() / ".joomha"
CONFIG_FILE = CONFIG_DIR / "config.json"

# ---------------------------------------------------------------------------
# Centralised model / retrieval constants  (Bug A, Bug 12)
# ---------------------------------------------------------------------------

EMBED_MODEL = "all-MiniLM-L6-v2"
EMBED_DIM = 384
TOP_K = 5                # default number of retrieval results
LLM_TIMEOUT = 60         # seconds — applies to all LLM HTTP calls (Bug N)
CHUNK_SIZE = 40           # lines per vector chunk
CHUNK_OVERLAP = 10        # overlap between consecutive chunks
MIN_CHUNK_LENGTH = 30     # minimum characters for a chunk to be kept

# ---------------------------------------------------------------------------
# Provider & model registry
# ---------------------------------------------------------------------------

PROVIDER_ENV_KEYS = {
    "gemini":     "GEMINI_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "anthropic":  "ANTHROPIC_API_KEY",
    "deepseek":   "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "custom":     "CUSTOM_LLM_API_KEY",
}

# Each provider has a list of available models with metadata.
# The first model in the list is the default.
MODEL_REGISTRY: Dict[str, List[Dict]] = {
    "gemini": [
        {"id": "gemini-2.0-flash",      "label": "Gemini 2.0 Flash (gratis)",      "tier": "free"},
        {"id": "gemini-2.0-flash-lite", "label": "Gemini 2.0 Flash Lite",          "tier": "free"},
        {"id": "gemini-2.5-flash",      "label": "Gemini 2.5 Flash",               "tier": "paid"},
        {"id": "gemini-3-flash",        "label": "Gemini 3 Flash (tercepat)",      "tier": "paid"},
        {"id": "gemini-3.1-pro",        "label": "Gemini 3.1 Pro (terbaik)",       "tier": "paid"},
    ],
    "openai": [
        {"id": "gpt-4o-mini",    "label": "GPT-4o Mini (hemat)",     "tier": "free"},
        {"id": "gpt-4o",         "label": "GPT-4o (standar)",        "tier": "paid"},
        {"id": "gpt-4.1",        "label": "GPT-4.1 (terbaru)",       "tier": "paid"},
        {"id": "o3-mini",        "label": "o3-mini (reasoning)",     "tier": "paid"},
        {"id": "o4-mini",        "label": "o4-mini (reasoning)",     "tier": "paid"},
    ],
    "anthropic": [
        # Fallback versi 3.x yang dijamin stabil 100%
        {"id": "claude-3-haiku-20240307",     "label": "Claude 3 Haiku (sangat cepat)", "tier": "paid"},
        {"id": "claude-3-5-sonnet-20241022",  "label": "Claude 3.5 Sonnet (stabil)",    "tier": "paid"},
        # Terbaru 4.x sesuai kueri MCP Perplexity
        {"id": "claude-haiku-4-5-20251001-v1", "label": "Claude Haiku 4.5", "tier": "paid"},
        {"id": "claude-sonnet-4-6",            "label": "Claude Sonnet 4.6", "tier": "paid"},
        {"id": "claude-opus-4-7",              "label": "Claude Opus 4.7",   "tier": "paid"},
    ],
    "deepseek": [
        {"id": "deepseek-chat",      "label": "DeepSeek Chat V3 (standar)",  "tier": "paid"},
        {"id": "deepseek-reasoner",  "label": "DeepSeek R1 (reasoning)",     "tier": "paid"},
    ],
    # OpenRouter: daftar ini hanya SARAN populer. User boleh ketik model ID
    # apa saja dari openrouter.ai/models (format: provider/model-name).
    "openrouter": [
        {"id": "google/gemini-pro-1.5",                "label": "Gemini 1.5 Pro (via OR)",      "tier": "paid"},
        {"id": "google/gemini-2.0-flash-exp:free",     "label": "Gemini 2.0 Flash (gratis OR)", "tier": "free"},
        {"id": "deepseek/deepseek-r1:free",            "label": "DeepSeek R1 (gratis OR)",      "tier": "free"},
        {"id": "anthropic/claude-3.5-sonnet",          "label": "Claude 3.5 Sonnet (via OR)",   "tier": "paid"},
        {"id": "openai/gpt-4o",                        "label": "GPT-4o (via OR)",              "tier": "paid"},
    ],
    "custom": [
        {"id": "default", "label": "Model default di endpoint kustom", "tier": "free"},
    ],
}

# Providers that accept ANY model ID (not limited to MODEL_REGISTRY list)
# For these providers, the registry is just a "suggestions" list.
OPEN_MODEL_PROVIDERS = {"openrouter", "custom"}

# Base URLs for OpenAI-compatible providers
PROVIDER_BASE_URLS = {
    "deepseek":   "https://api.deepseek.com",
    "openrouter": "https://openrouter.ai/api/v1",
    # "custom" is read from config.json → custom_base_url
}


# ---------------------------------------------------------------------------
# API key obfuscation helpers  (Bug 9)
# ---------------------------------------------------------------------------

def _machine_key() -> bytes:
    """Derive a deterministic key from the machine's hostname + username."""
    raw = f"{platform.node()}-{os.getlogin()}".encode()
    return hashlib.sha256(raw).digest()


def _obfuscate(plain: str) -> str:
    """XOR plain text with a machine key, then base64-encode."""
    key = _machine_key()
    xored = bytes(b ^ key[i % len(key)] for i, b in enumerate(plain.encode("utf-8")))
    return base64.b64encode(xored).decode("ascii")


def _deobfuscate(token: str) -> str:
    """Reverse of _obfuscate."""
    key = _machine_key()
    xored = base64.b64decode(token)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(xored)).decode("utf-8")


# ---------------------------------------------------------------------------
# Config I/O
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    """Load config from disk."""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_config(config: dict) -> None:
    """Persist config to disk."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Public API — API keys
# ---------------------------------------------------------------------------

def get_api_key(provider: str) -> Optional[str]:
    """Get API key — env var takes priority over stored config."""
    env_key = PROVIDER_ENV_KEYS.get(provider)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val
    config = _load_config()
    stored = config.get("api_keys", {}).get(provider)
    if stored:
        try:
            return _deobfuscate(stored)
        except Exception:
            # Backwards compat: if stored value is still plain text, use it
            return stored
    return None


def set_api_key(provider: str, key: str) -> None:
    """Store API key in config file (obfuscated)."""
    config = _load_config()
    if "api_keys" not in config:
        config["api_keys"] = {}
    config["api_keys"][provider] = _obfuscate(key)
    _save_config(config)


def get_active_provider() -> str:
    """Detect active LLM provider from env vars or config.

    Priority: 1. config.json active_provider, 2. env vars, 3. stored keys
    """
    config = _load_config()
    # Check if user explicitly set an active provider
    active = config.get("active_provider")
    if active and active in PROVIDER_ENV_KEYS:
        if get_api_key(active):
            return active

    for provider, env_key in PROVIDER_ENV_KEYS.items():
        if os.environ.get(env_key):
            return provider
    for provider in PROVIDER_ENV_KEYS:
        if config.get("api_keys", {}).get(provider):
            return provider
    return "gemini"


def set_active_provider(provider: str) -> None:
    """Persist the active provider choice."""
    config = _load_config()
    config["active_provider"] = provider
    _save_config(config)


# ---------------------------------------------------------------------------
# Public API — Model selection
# ---------------------------------------------------------------------------

def get_active_model(provider: str) -> str:
    """Get the selected model for a given provider.

    Falls back to the first model in MODEL_REGISTRY if nothing is configured.
    """
    config = _load_config()
    stored = config.get("active_models", {}).get(provider)
    if stored:
        return stored
    # Default: first model in registry
    models = MODEL_REGISTRY.get(provider, [])
    return models[0]["id"] if models else "default"


def set_active_model(provider: str, model_id: str) -> None:
    """Persist the selected model for a provider."""
    config = _load_config()
    if "active_models" not in config:
        config["active_models"] = {}
    config["active_models"][provider] = model_id
    _save_config(config)


def get_custom_base_url() -> Optional[str]:
    """Get the base URL for custom OpenAI-compatible endpoint."""
    config = _load_config()
    return config.get("custom_base_url")


def set_custom_base_url(url: str) -> None:
    """Persist a custom OpenAI-compatible base URL."""
    config = _load_config()
    config["custom_base_url"] = url
    _save_config(config)


def get_all_configured_providers() -> List[str]:
    """Return a list of providers that have an API key configured."""
    configured = []
    for provider in PROVIDER_ENV_KEYS:
        if get_api_key(provider):
            configured.append(provider)
    return configured


# ---------------------------------------------------------------------------
# Auto .gitignore for .joomha/  (Bug Q)
# ---------------------------------------------------------------------------

_GITIGNORE_CONTENT = """\
# Auto-generated by Joomha — prevent sensitive data from being committed.
*
"""


def ensure_joomha_gitignore(joomha_dir: Path) -> None:
    """Create a .gitignore inside the .joomha directory if it doesn't exist."""
    gi = joomha_dir / ".gitignore"
    if not gi.exists():
        joomha_dir.mkdir(parents=True, exist_ok=True)
        gi.write_text(_GITIGNORE_CONTENT, encoding="utf-8")
