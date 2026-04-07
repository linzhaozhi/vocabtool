# Centralized error handling and progress callback protocol.

import logging
from typing import Any, Protocol

import streamlit as st

logger = logging.getLogger(__name__)


class ProgressCallback(Protocol):
    """Protocol for progress reporting callbacks."""

    def __call__(self, ratio: float, message: str) -> None:
        ...


class ErrorHandler:
    """Centralized error handling for consistent user feedback."""

    @staticmethod
    def handle(error: Exception, context: str, show_user: bool = True) -> None:
        """Handle errors consistently with logging and user feedback."""
        logger.error(f"{context}: {error}", exc_info=True)
        if show_user:
            st.error(f"❌ {context}: {str(error)}")

    @staticmethod
    def handle_with_fallback(error: Exception, fallback_value: Any, context: str = "") -> Any:
        """Handle error and return fallback value."""
        logger.warning(f"Error in {context}: {error}")
        return fallback_value

    @staticmethod
    def handle_file_error(error: Exception, file_type: str) -> str:
        """Handle file processing errors."""
        error_msg = f"Error processing {file_type}: {error}"
        logger.error(error_msg)
        return error_msg
