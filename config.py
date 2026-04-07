# Single config layer: Streamlit secrets + defaults.

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
        "openai_api_key": s.get("OPENAI_API_KEY", ""),
        "openai_base_url": s.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "openai_model": s.get("OPENAI_MODEL", "deepseek-chat"),
    }
