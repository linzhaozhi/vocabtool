"""Stable card-based progress rendering for long Streamlit jobs."""

from __future__ import annotations

from typing import Any


class CardProgressDisplay:
    """Keep one progress line monotonic and measured only in cards."""

    def __init__(
        self,
        progress_widget: Any,
        status_widget: Any,
        total_cards: int,
        *,
        label: str = "制作进度",
    ) -> None:
        self.progress_widget = progress_widget
        self.status_widget = status_widget
        self.total_cards = max(0, int(total_cards))
        self.label = label
        self.completed_cards = 0
        self._render()

    def _render(self) -> None:
        ratio = self.completed_cards / self.total_cards if self.total_cards else 0.0
        self.progress_widget.progress(ratio)
        self.status_widget.text(
            f"{self.label}：{self.completed_cards} / {self.total_cards} 张卡片"
        )

    def update_cards(self, completed_cards: int) -> None:
        """Advance to an absolute card count without ever moving backwards."""
        completed = min(max(0, int(completed_cards)), self.total_cards)
        if completed <= self.completed_cards:
            return
        self.completed_cards = completed
        self._render()

    def update_ratio(self, ratio: float, _message: str = "") -> None:
        """Map a lower-level ratio to cards while reserving 100% for the final package."""
        bounded_ratio = min(max(float(ratio), 0.0), 1.0)
        completed = int(round(bounded_ratio * self.total_cards))
        if self.total_cards and completed >= self.total_cards:
            completed = self.total_cards - 1
        self.update_cards(completed)

    def complete(self) -> None:
        """Mark every card complete after the APKG file exists."""
        if self.completed_cards == self.total_cards:
            return
        self.completed_cards = self.total_cards
        self._render()
