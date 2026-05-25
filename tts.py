# TTS audio generation (edge_tts, async batch).

import asyncio
import logging
import os
import random
from typing import Dict, List, Optional

import edge_tts

import constants
from errors import ProgressCallback

logger = logging.getLogger(__name__)


async def _generate_audio_batch(
    tasks: List[Dict[str, str]],
    concurrency: int = constants.TTS_CONCURRENCY,
    progress_callback: Optional[ProgressCallback] = None
) -> None:
    """Generate audio files concurrently with retry logic."""
    semaphore = asyncio.Semaphore(concurrency)
    total_files = len(tasks)
    completed_files = 0

    async def worker(task: Dict[str, str]) -> None:
        nonlocal completed_files
        success = False
        try:
            async with semaphore:
                await asyncio.sleep(random.uniform(0.1, 0.8))

                error_msg = ""

                for attempt in range(constants.TTS_RETRY_ATTEMPTS):
                    try:
                        if not os.path.exists(task['path']):
                            text = str(task['text']).strip()[:constants.TTS_TEXT_MAX_CHARS]
                            comm = edge_tts.Communicate(text, task['voice'])
                            await asyncio.wait_for(
                                comm.save(task['path']),
                                timeout=constants.TTS_TASK_TIMEOUT_SECONDS,
                            )

                            if os.path.exists(task['path']) and os.path.getsize(task['path']) > constants.MIN_AUDIO_FILE_SIZE:
                                success = True
                                break
                            else:
                                if os.path.exists(task['path']):
                                    os.remove(task['path'])
                                raise Exception("File size too small")
                        else:
                            success = True
                            break
                    except Exception as e:
                        error_msg = str(e)
                        if os.path.exists(task['path']):
                            try:
                                os.remove(task['path'])
                            except OSError:
                                pass
                        await asyncio.sleep(1.0 * (attempt + 1))

                if not success:
                    logger.error("TTS failed for: %s | Error: %s", task['text'], error_msg)
        except Exception as e:
            logger.error("TTS worker failed for: %s | Error: %s", task.get('text', ''), e)
        finally:
            completed_files += 1
            if progress_callback:
                progress_callback(
                    completed_files / total_files,
                    f"正在生成音频 ({completed_files}/{total_files})"
                )

    jobs = [worker(task) for task in tasks]
    await asyncio.gather(*jobs, return_exceptions=True)


def run_async_batch(
    tasks: List[Dict[str, str]],
    concurrency: int = constants.TTS_CONCURRENCY,
    progress_callback: Optional[ProgressCallback] = None
) -> None:
    """Run async audio generation batch with proper event loop handling."""
    if not tasks:
        return

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_generate_audio_batch(tasks, concurrency, progress_callback))
    except Exception as e:
        logger.error("Async loop error: %s", e)
    finally:
        asyncio.set_event_loop(None)
        loop.close()
