# Single config layer: Streamlit secrets + defaults.

import constants


def _get_secrets():
    try:
        import streamlit as st
        return getattr(st, "secrets", None) or {}
    except Exception:
        return {}


def get_config():
    """Return app config from st.secrets with defaults. Use in Streamlit context."""
    s = _get_secrets()
    return {
        "deepseek_api_key": s.get("DEEPSEEK_API_KEY", ""),
        "deepseek_base_url": s.get("DEEPSEEK_BASE_URL", constants.DEEPSEEK_BASE_URL_DEFAULT),
        "deepseek_model": s.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "deepseek_chat_model": s.get("DEEPSEEK_CHAT_MODEL", constants.DEEPSEEK_CHAT_MODEL_DEFAULT),
    }
