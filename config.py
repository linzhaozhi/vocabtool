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
        "openai_api_key": s.get("OPENAI_API_KEY") or s.get("DEEPSEEK_API_KEY", ""),
        "openai_base_url": (
            s.get("OPENAI_BASE_URL")
            or s.get("DEEPSEEK_BASE_URL")
            or constants.DEEPSEEK_BASE_URL_DEFAULT
        ),
        "openai_model": s.get("OPENAI_MODEL") or s.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "deepseek_api_key": s.get("DEEPSEEK_API_KEY") or s.get("OPENAI_API_KEY", ""),
        "deepseek_base_url": (
            s.get("DEEPSEEK_BASE_URL")
            or s.get("OPENAI_BASE_URL")
            or constants.DEEPSEEK_BASE_URL_DEFAULT
        ),
        "deepseek_model": s.get("DEEPSEEK_MODEL") or s.get("OPENAI_MODEL", "deepseek-chat"),
    }
