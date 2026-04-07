# Shared utility functions.

import gc
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

import constants
from errors import ErrorHandler

logger = __import__("logging").getLogger(__name__)


def safe_str_clean(value: Any) -> str:
    """Convert to string and clean whitespace safely."""
    if value is None:
        return ""
    return str(value).strip()


def render_copy_button(text: str, key: str = "copy_words") -> None:
    """Render a right-aligned copy button using Clipboard API."""
    payload = json.dumps(text).replace("</", "<\\/")
    html_block = f"""
    <style>
      .copy-btn {{
        width: 36px;
        height: 36px;
        border: 1px solid #d1d5db;
        background: #ffffff;
        border-radius: 10px;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        transition: transform .12s ease, box-shadow .12s ease, border-color .12s ease;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
      }}
      .copy-btn:hover {{
        transform: translateY(-1px);
        border-color: #9ca3af;
      }}
      .copy-btn svg {{
        width: 18px;
        height: 18px;
        fill: none;
        stroke: #4b5563;
        stroke-width: 1.9;
        stroke-linecap: round;
        stroke-linejoin: round;
      }}
      .copy-btn.success {{
        border-color: #16a34a;
        background: #f0fdf4;
      }}
      .copy-btn.success svg {{
        stroke: #15803d;
      }}
    </style>
    <div style="text-align:right;">
        <button id="{key}" class="copy-btn" title="复制">
            <span id="{key}_copy">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <rect x="9" y="9" width="10" height="10" rx="2"></rect>
                    <rect x="5" y="5" width="10" height="10" rx="2"></rect>
                </svg>
            </span>
            <span id="{key}_ok" style="display:none;">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M5 12l4 4L19 6"></path>
                </svg>
            </span>
        </button>
    </div>
    <script>
    const btn = document.getElementById("{key}");
    const iconCopy = document.getElementById("{key}_copy");
    const iconOk = document.getElementById("{key}_ok");
    if (btn) {{
        btn.onclick = async () => {{
            try {{
                await navigator.clipboard.writeText({payload});
                btn.classList.add("success");
                if (iconCopy) iconCopy.style.display = "none";
                if (iconOk) iconOk.style.display = "inline-flex";
            }} catch (e) {{
                btn.style.borderColor = "#dc2626";
                setTimeout(() => {{
                    btn.style.borderColor = "";
                }}, 1200);
            }}
        }};
    }}
    </script>
    """
    components.html(html_block, height=48)


def run_gc() -> None:
    """Run garbage collection to reduce memory pressure after heavy tasks."""
    try:
        gc.collect()
    except Exception:
        pass


def get_beijing_time_str() -> str:
    """Get current Beijing time as formatted string."""
    utc_now = datetime.now(timezone.utc)
    beijing_now = utc_now + timedelta(hours=constants.BEIJING_TIMEZONE_OFFSET)
    return beijing_now.strftime('%m%d_%H%M')


def detect_file_encoding(bytes_data: bytes) -> str:
    """Detect file encoding using chardet if available, fallback to priority list."""
    try:
        import chardet
        detected = chardet.detect(bytes_data)
        encoding = detected.get('encoding')
        if encoding and detected.get('confidence', 0) > 0.7:
            return encoding
    except ImportError:
        logger.debug("chardet not available, using fallback encodings")
    for encoding in constants.ENCODING_PRIORITY:
        try:
            bytes_data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            continue
    return 'latin-1'
