"""Compatibility wrapper for older imports.

The Streamlit app imports the extraction logic from vocab_logic.py to avoid
collisions with generic environment modules named "vocab".
"""

from vocab_logic import analyze_logic, get_lemma, is_valid_word

__all__ = ["analyze_logic", "get_lemma", "is_valid_word"]
