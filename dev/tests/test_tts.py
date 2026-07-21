"""Tests for fair TTS retry queue behavior."""

import asyncio
import time
from collections import Counter

import tts


def _configure_fast_retries(monkeypatch, *, attempts: int = 3) -> None:
    monkeypatch.setattr(tts.constants, "TTS_RETRY_ATTEMPTS", attempts)
    monkeypatch.setattr(tts.constants, "TTS_REQUEST_SPACING_SECONDS", 0.0)
    monkeypatch.setattr(tts.constants, "TTS_RETRY_BASE_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(tts.constants, "TTS_RETRY_MAX_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(tts.constants, "TTS_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(tts.constants, "TTS_TASK_TIMEOUT_SECONDS", 0.2)


def test_transient_failure_moves_to_later_round_without_blocking_queue(monkeypatch, tmp_path):
    _configure_fast_retries(monkeypatch, attempts=3)
    attempts = Counter()
    attempt_order = []
    messages = []

    class FakeCommunicate:
        def __init__(self, text, voice):
            self.text = text

        async def save(self, path):
            attempts[self.text] += 1
            attempt_order.append(self.text)
            if self.text == "retry me" and attempts[self.text] == 1:
                raise RuntimeError("temporary throttle")
            with open(path, "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
    tasks = [
        {"text": "retry me", "path": str(tmp_path / "retry.mp3"), "voice": "voice"},
        {"text": "later one", "path": str(tmp_path / "later.mp3"), "voice": "voice"},
        {"text": "later two", "path": str(tmp_path / "last.mp3"), "voice": "voice"},
    ]

    result = asyncio.run(
        tts._generate_audio_batch(
            tasks,
            concurrency=1,
            progress_callback=lambda ratio, message: messages.append((ratio, message)),
        )
    )

    assert result.succeeded == 3
    assert result.failed == 0
    assert attempts == {"retry me": 2, "later one": 1, "later two": 1}
    assert attempt_order.index("later one") < len(attempt_order) - 1
    assert attempt_order[-1] == "retry me"
    assert any("移到队尾" in message for _, message in messages)
    assert messages[-1][1] == "语音全部生成完成（3/3）。"


def test_permanent_failure_does_not_prevent_other_audio(monkeypatch, tmp_path):
    _configure_fast_retries(monkeypatch, attempts=2)
    messages = []

    class FakeCommunicate:
        def __init__(self, text, voice):
            self.text = text

        async def save(self, path):
            if self.text == "always fails":
                raise RuntimeError("service unavailable")
            with open(path, "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
    tasks = [
        {"text": "always fails", "path": str(tmp_path / "failed.mp3"), "voice": "voice"},
        {"text": "still succeeds", "path": str(tmp_path / "success.mp3"), "voice": "voice"},
    ]

    result = asyncio.run(
        tts._generate_audio_batch(
            tasks,
            concurrency=1,
            progress_callback=lambda ratio, message: messages.append((ratio, message)),
        )
    )

    assert result.succeeded == 1
    assert result.failed == 1
    assert result.failed_tasks[0]["text"] == "always fails"
    assert (tmp_path / "success.mp3").exists()
    assert not (tmp_path / "failed.mp3").exists()
    assert messages[-1] == (1.0, "语音队列结束：成功 1/2，仍有 1 个音频失败。")


def test_slow_request_emits_heartbeat_instead_of_looking_stuck(monkeypatch, tmp_path):
    _configure_fast_retries(monkeypatch, attempts=1)
    messages = []

    class SlowCommunicate:
        def __init__(self, text, voice):
            pass

        async def save(self, path):
            await asyncio.sleep(0.04)
            with open(path, "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(tts.edge_tts, "Communicate", SlowCommunicate)
    tasks = [{"text": "slow", "path": str(tmp_path / "slow.mp3"), "voice": "voice"}]

    result = asyncio.run(
        tts._generate_audio_batch(
            tasks,
            concurrency=1,
            progress_callback=lambda ratio, message: messages.append((ratio, message)),
        )
    )

    assert result.failed == 0
    assert any("仍在等待" in message for _, message in messages)


def test_timeout_cleanup_cannot_hold_the_remaining_audio_queue(monkeypatch, tmp_path):
    _configure_fast_retries(monkeypatch, attempts=1)
    monkeypatch.setattr(tts.constants, "TTS_TASK_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(tts.constants, "TTS_CANCEL_GRACE_SECONDS", 0.005)
    monkeypatch.setattr(tts.constants, "TTS_HEARTBEAT_SECONDS", 0.002)

    class SlowToCancelCommunicate:
        def __init__(self, text, voice):
            self.text = text

        async def save(self, path):
            if self.text == "stuck":
                try:
                    await asyncio.sleep(1)
                except asyncio.CancelledError:
                    # Simulate a websocket close that needs a little longer
                    # than the cancellation grace period to finish.
                    await asyncio.sleep(0.03)
                    return
            with open(path, "wb") as audio_file:
                audio_file.write(b"audio" * 30)

    monkeypatch.setattr(tts.edge_tts, "Communicate", SlowToCancelCommunicate)
    tasks = [
        {"text": "stuck", "path": str(tmp_path / "stuck.mp3"), "voice": "voice"},
        {"text": "later", "path": str(tmp_path / "later.mp3"), "voice": "voice"},
    ]

    started = time.monotonic()
    result = asyncio.run(tts._generate_audio_batch(tasks, concurrency=1))
    elapsed = time.monotonic() - started

    assert elapsed < 0.2
    assert result.succeeded == 1
    assert result.failed == 1
    assert (tmp_path / "later.mp3").exists()
