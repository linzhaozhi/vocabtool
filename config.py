# Single config layer: Streamlit secrets + defaults.

import constants


def _get_secrets():
    try:
        import streamlit as st
        return getattr(st, "secrets", None) or {}
    except Exception:
        return {}


def _secret_value(secrets, key: str, default: str = "") -> str:
    """Read a Streamlit secret as a clean string."""
    value = secrets.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def _normalize_provider(raw_provider: str, secrets) -> str:
    """Pick one active AI provider to avoid sending keys to the wrong endpoint."""
    provider = raw_provider.lower().strip()
    if provider in {"openai", "deepseek"}:
        return provider

    if _secret_value(secrets, "OPENAI_API_KEY"):
        return "openai"
    if _secret_value(secrets, "DEEPSEEK_API_KEY"):
        return "deepseek"
    return "deepseek"


def _build_ai_config(secrets) -> dict:
    provider = _normalize_provider(_secret_value(secrets, "AI_PROVIDER"), secrets)

    if provider == "openai":
        return {
            "ai_provider": "openai",
            "ai_provider_label": "OpenAI",
            "ai_api_key": _secret_value(secrets, "OPENAI_API_KEY"),
            "ai_base_url": _secret_value(secrets, "OPENAI_BASE_URL"),
            "ai_model": _secret_value(secrets, "OPENAI_MODEL", constants.OPENAI_MODEL_DEFAULT),
            "ai_missing_key_message": "❌ 未找到 OPENAI_API_KEY。请在 .streamlit/secrets.toml 中配置。",
        }

    return {
        "ai_provider": "deepseek",
        "ai_provider_label": "DeepSeek",
        "ai_api_key": _secret_value(secrets, "DEEPSEEK_API_KEY"),
        "ai_base_url": _secret_value(secrets, "DEEPSEEK_BASE_URL", constants.DEEPSEEK_BASE_URL_DEFAULT),
        "ai_model": _secret_value(secrets, "DEEPSEEK_MODEL", constants.DEEPSEEK_MODEL_DEFAULT),
        "ai_missing_key_message": "❌ 未找到 DEEPSEEK_API_KEY。请在 .streamlit/secrets.toml 中配置。",
    }


def get_config():
    """Return app config from st.secrets with defaults. Use in Streamlit context."""
    s = _get_secrets()
    ai_config = _build_ai_config(s)
    return {
        **ai_config,
        "openai_api_key": _secret_value(s, "OPENAI_API_KEY"),
        "openai_base_url": _secret_value(s, "OPENAI_BASE_URL"),
        "openai_model": _secret_value(s, "OPENAI_MODEL", constants.OPENAI_MODEL_DEFAULT),
        "deepseek_api_key": _secret_value(s, "DEEPSEEK_API_KEY"),
        "deepseek_base_url": _secret_value(s, "DEEPSEEK_BASE_URL", constants.DEEPSEEK_BASE_URL_DEFAULT),
        "deepseek_model": _secret_value(s, "DEEPSEEK_MODEL", constants.DEEPSEEK_MODEL_DEFAULT),
    }
