# TTS audio generation (edge_tts, async batch).

import asyncio
import contextlib
import logging
import os
import random
from dataclasses import dataclass
from typing import Dict, List, Optional

import edge_tts

import constants
from errors import ProgressCallback

logger = logging.getLogger(__name__)


@dataclass
class TTSBatchResult:
    """Outcome of a complete TTS queue including all recovery rounds."""

    total: int
    succeeded: int
    failed_tasks: List[Dict[str, str]]

    @property
    def failed(self) -> int:
        return len(self.failed_tasks)


def _audio_file_is_valid(path: str) -> bool:
    return bool(
        path
        and os.path.exists(path)
        and os.path.getsize(path) > constants.MIN_AUDIO_FILE_SIZE
    )


def _remove_audio_file(path: str) -> None:
    if not path or not os.path.exists(path):
        return
    try:
        os.remove(path)
    except OSError:
        pass


def _notify_progress(
    callback: Optional[ProgressCallback],
    ratio: float,
    message: str,
) -> None:
    if not callback:
        return
    try:
        callback(min(max(float(ratio), 0.0), 1.0), message)
    except Exception as exc:
        logger.debug("TTS progress callback failed: %s", exc)


async def _save_with_heartbeat(
    communicator: edge_tts.Communicate,
    path: str,
    *,
    round_number: int,
    total_rounds: int,
    completed_ratio: float,
    progress_callback: Optional[ProgressCallback],
) -> None:
    """Save one audio file while keeping long network waits visible in the UI."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + constants.TTS_TASK_TIMEOUT_SECONDS
    save_task = asyncio.create_task(communicator.save(path))
    try:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise asyncio.TimeoutError(
                    f"TTS request exceeded {constants.TTS_TASK_TIMEOUT_SECONDS} seconds"
                )
            heartbeat = max(0.01, min(constants.TTS_HEARTBEAT_SECONDS, remaining))
            done, _ = await asyncio.wait({save_task}, timeout=heartbeat)
            if save_task in done:
                await save_task
                return
            _notify_progress(
                progress_callback,
                completed_ratio,
                f"语音服务响应较慢，仍在等待（重试轮次 {round_number}/{total_rounds}）...",
            )
    finally:
        if not save_task.done():
            save_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await save_task


async def _generate_audio_batch(
    tasks: List[Dict[str, str]],
    concurrency: int = constants.TTS_CONCURRENCY,
    progress_callback: Optional[ProgressCallback] = None
) -> TTSBatchResult:
    """Generate audio through fair retry rounds so one failure cannot block the queue."""
    total_files = len(tasks)
    if not tasks:
        return TTSBatchResult(total=0, succeeded=0, failed_tasks=[])

    succeeded_paths = {
        str(task.get("path", ""))
        for task in tasks
        if _audio_file_is_valid(str(task.get("path", "")))
    }
    pending = [
        task for task in tasks
        if str(task.get("path", "")) not in succeeded_paths
    ]
    total_rounds = max(1, int(constants.TTS_RETRY_ATTEMPTS))
    request_start_lock = asyncio.Lock()
    last_request_started = 0.0

    async def pace_request_start(spacing: float) -> None:
        nonlocal last_request_started
        async with request_start_lock:
            loop = asyncio.get_running_loop()
            wait_seconds = spacing - (loop.time() - last_request_started)
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)
            last_request_started = loop.time()

    for round_index in range(total_rounds):
        if not pending:
            break

        round_number = round_index + 1
        if round_index:
            cooldown = min(
                constants.TTS_RETRY_BASE_DELAY_SECONDS * (2 ** (round_index - 1)),
                constants.TTS_RETRY_MAX_DELAY_SECONDS,
            )
            jitter = random.uniform(0.0, min(0.8, cooldown * 0.2)) if cooldown else 0.0
            _notify_progress(
                progress_callback,
                len(succeeded_paths) / total_files,
                f"语音服务暂时繁忙，{len(pending)} 个任务已放到队尾，"
                f"{cooldown + jitter:.1f} 秒后开始第 {round_number}/{total_rounds} 轮重试...",
            )
            await asyncio.sleep(cooldown + jitter)

        round_concurrency = max(1, int(concurrency)) if round_index == 0 else 1
        request_spacing = max(
            0.0,
            constants.TTS_REQUEST_SPACING_SECONDS * (1 if round_index == 0 else 2),
        )
        semaphore = asyncio.Semaphore(round_concurrency)

        async def attempt_once(task: Dict[str, str]):
            path = str(task.get("path", ""))
            text = str(task.get("text", "")).strip()[:constants.TTS_TEXT_MAX_CHARS]
            voice = str(task.get("voice", "")).strip()
            if _audio_file_is_valid(path):
                return task, True, ""
            if not path or not text or not voice:
                return task, False, "missing path, text, or voice"

            async with semaphore:
                await pace_request_start(request_spacing)
                _notify_progress(
                    progress_callback,
                    len(succeeded_paths) / total_files,
                    f"正在请求语音（第 {round_number}/{total_rounds} 轮，"
                    f"已成功 {len(succeeded_paths)}/{total_files}）...",
                )
                try:
                    communicator = edge_tts.Communicate(text, voice)
                    await _save_with_heartbeat(
                        communicator,
                        path,
                        round_number=round_number,
                        total_rounds=total_rounds,
                        completed_ratio=len(succeeded_paths) / total_files,
                        progress_callback=progress_callback,
                    )
                    if not _audio_file_is_valid(path):
                        raise RuntimeError("generated audio file is missing or too small")
                    return task, True, ""
                except Exception as exc:
                    _remove_audio_file(path)
                    return task, False, str(exc)

        failed_by_path: Dict[str, Dict[str, str]] = {}
        jobs = [attempt_once(task) for task in pending]
        for completed_job in asyncio.as_completed(jobs):
            task, success, error_message = await completed_job
            path = str(task.get("path", ""))
            if success:
                succeeded_paths.add(path)
                message = f"正在生成音频：已成功 {len(succeeded_paths)}/{total_files}"
            else:
                failed_by_path[path] = task
                logger.warning(
                    "TTS attempt %s/%s failed for %s: %s",
                    round_number,
                    total_rounds,
                    task.get("text", ""),
                    error_message,
                )
                if round_number < total_rounds:
                    message = (
                        f"一个音频暂时失败，已移到队尾；已成功 "
                        f"{len(succeeded_paths)}/{total_files}"
                    )
                else:
                    message = (
                        f"一个音频在 {total_rounds} 轮后仍失败；已成功 "
                        f"{len(succeeded_paths)}/{total_files}"
                    )
            _notify_progress(
                progress_callback,
                len(succeeded_paths) / total_files,
                message,
            )

        pending = [
            task for task in pending
            if str(task.get("path", "")) in failed_by_path
        ]

    failed_tasks = [
        task for task in tasks
        if not _audio_file_is_valid(str(task.get("path", "")))
    ]
    result = TTSBatchResult(
        total=total_files,
        succeeded=total_files - len(failed_tasks),
        failed_tasks=failed_tasks,
    )
    if result.failed:
        _notify_progress(
            progress_callback,
            1.0,
            f"语音队列结束：成功 {result.succeeded}/{result.total}，"
            f"仍有 {result.failed} 个音频失败。",
        )
    else:
        _notify_progress(
            progress_callback,
            1.0,
            f"语音全部生成完成（{result.succeeded}/{result.total}）。",
        )
    return result


def run_async_batch(
    tasks: List[Dict[str, str]],
    concurrency: int = constants.TTS_CONCURRENCY,
    progress_callback: Optional[ProgressCallback] = None
) -> TTSBatchResult:
    """Run async audio generation batch with proper event loop handling."""
    if not tasks:
        return TTSBatchResult(total=0, succeeded=0, failed_tasks=[])

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(_generate_audio_batch(tasks, concurrency, progress_callback))
    except Exception as e:
        logger.error("Async loop error: %s", e)
        failed_tasks = [
            task for task in tasks
            if not _audio_file_is_valid(str(task.get("path", "")))
        ]
        return TTSBatchResult(
            total=len(tasks),
            succeeded=len(tasks) - len(failed_tasks),
            failed_tasks=failed_tasks,
        )
    finally:
        asyncio.set_event_loop(None)
        loop.close()
