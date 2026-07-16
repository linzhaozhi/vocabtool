"""Tests for stable card-based progress information."""

from ui.progress import CardProgressDisplay


class FakeProgress:
    def __init__(self):
        self.values = []

    def progress(self, value):
        self.values.append(value)


class FakeStatus:
    def __init__(self):
        self.messages = []

    def text(self, message):
        self.messages.append(message)


def test_card_progress_uses_one_stable_monotonic_format():
    progress = FakeProgress()
    status = FakeStatus()
    display = CardProgressDisplay(progress, status, 10)

    display.update_ratio(0.31, "internal TTS message")
    display.update_ratio(0.10, "a later retry message")
    display.update_ratio(1.0, "packaging")
    display.complete()

    assert status.messages == [
        "制作进度：0 / 10 张卡片",
        "制作进度：3 / 10 张卡片",
        "制作进度：9 / 10 张卡片",
        "制作进度：10 / 10 张卡片",
    ]
    assert progress.values == [0.0, 0.3, 0.9, 1.0]
