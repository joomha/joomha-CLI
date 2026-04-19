"""Configuration management for Joomha — API keys & provider settings."""

import json
import os
from pathlib import Path
from typing import Optional

CONFIG_DIR = Path.home() / ".joomha"
CONFIG_FILE = CONFIG_DIR / "config.json"

PROVIDER_ENV_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}


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


def get_api_key(provider: str) -> Optional[str]:
    """Get API key — env var takes priority over stored config."""
    env_key = PROVIDER_ENV_KEYS.get(provider)
    if env_key:
        val = os.environ.get(env_key)
        if val:
            return val
    config = _load_config()
    return config.get("api_keys", {}).get(provider)


def set_api_key(provider: str, key: str) -> None:
    """Store API key in config file."""
    config = _load_config()
    if "api_keys" not in config:
        config["api_keys"] = {}
    config["api_keys"][provider] = key
    _save_config(config)


def get_active_provider() -> str:
    """Detect active LLM provider from env vars or config."""
    for provider, env_key in PROVIDER_ENV_KEYS.items():
        if os.environ.get(env_key):
            return provider
    config = _load_config()
    for provider in PROVIDER_ENV_KEYS:
        if config.get("api_keys", {}).get(provider):
            return provider
    return "gemini"
