"""
Asynchronous Social & Bot Media Queue System.
Handles burst video posts, debounces multiple media uploads from users,
and processes videos sequentially or in batches without race conditions.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Any, Tuple

logger = logging.getLogger("Social.MediaQueue")

@dataclass
class QueuedVideoItem:
    video_id: str
    source_platform: str # "discord", "instagram", "x", "web"
    url_or_path: str
    user_id: str
    user_name: str
    channel_id: str
    message_context: str
    raw_attachment: Optional[Any] = None
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class UserMediaBatch:
    batch_key: str # e.g. "discord:12345" or "instagram:user99"
    items: List[QueuedVideoItem] = field(default_factory=list)
    debounce_timer: Optional[asyncio.TimerHandle] = None
    last_received: float = field(default_factory=time.time)
    is_processing: bool = False
    callback: Optional[Callable] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

class SocialMediaQueue:
    """
    Manages incoming media bursts across platforms.
    Ensures that when a user uploads multiple videos at once, they are queued
    and processed systematically with AI understanding rather than triggering
    conflicting immediate responses.
    """

    def __init__(self, debounce_seconds: float = 6.0, max_batch_size: int = 10):
        self.debounce_seconds = debounce_seconds
        self.max_batch_size = max_batch_size
        self._batches: Dict[str, UserMediaBatch] = {}
        self._global_queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._processor_func: Optional[Callable] = None
        self._running = False

    def set_processor(self, processor_func: Callable):
        """Sets the async function that processes a completed batch of media items."""
        self._processor_func = processor_func

    async def start(self):
        """Starts the background queue worker."""
        if self._running:
            return
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("[MEDIA QUEUE] SocialMediaQueue background worker started.")

    async def stop(self):
        """Stops the background queue worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    def enqueue_media(
        self,
        source_platform: str,
        channel_id: str,
        user_id: str,
        user_name: str,
        url_or_path: str,
        message_context: str = "",
        raw_attachment: Optional[Any] = None,
        custom_callback: Optional[Callable] = None
    ) -> Tuple[bool, int, str]:
        """
        Enqueues a video/media item with automatic debouncing.
        Returns: (is_new_batch, queue_position, batch_key)
        """
        batch_key = f"{source_platform}:{channel_id}:{user_id}"
        video_id = f"vid_{int(time.time()*1000)}_{len(url_or_path)}"

        item = QueuedVideoItem(
            video_id=video_id,
            source_platform=source_platform,
            url_or_path=url_or_path,
            user_id=user_id,
            user_name=user_name,
            channel_id=channel_id,
            message_context=message_context,
            raw_attachment=raw_attachment
        )

        loop = asyncio.get_event_loop()

        if batch_key not in self._batches:
            batch = UserMediaBatch(
                batch_key=batch_key,
                items=[item],
                callback=custom_callback
            )
            self._batches[batch_key] = batch
            is_new = True
        else:
            batch = self._batches[batch_key]
            batch.items.append(item)
            if custom_callback:
                batch.callback = custom_callback
            is_new = False
            # Cancel previous debounce timer
            if batch.debounce_timer:
                batch.debounce_timer.cancel()
                batch.debounce_timer = None

        batch.last_received = time.time()

        # If batch reached max limit, flush immediately
        if len(batch.items) >= self.max_batch_size:
            loop.create_task(self._flush_batch(batch_key))
        else:
            # Set debounce timer
            batch.debounce_timer = loop.call_later(
                self.debounce_seconds,
                lambda k=batch_key: asyncio.create_task(self._flush_batch(k))
            )

        logger.info(
            f"[MEDIA QUEUE] Enqueued {source_platform} video for user '{user_name}' "
            f"(Batch size: {len(batch.items)}). Debouncing {self.debounce_seconds}s..."
        )
        return is_new, len(batch.items), batch_key

    async def _flush_batch(self, batch_key: str):
        """Flushes a debounced batch into the processing queue."""
        if batch_key not in self._batches:
            return

        batch = self._batches.pop(batch_key, None)
        if not batch or not batch.items:
            return

        if batch.debounce_timer:
            batch.debounce_timer.cancel()
            batch.debounce_timer = None

        await self._global_queue.put(batch)
        logger.info(f"[MEDIA QUEUE] Batch '{batch_key}' with {len(batch.items)} videos submitted for processing.")

    async def _worker_loop(self):
        """Continuously processes batches sequentially."""
        while self._running:
            try:
                batch: UserMediaBatch = await self._global_queue.get()
                try:
                    if self._processor_func:
                        await self._processor_func(batch)
                    elif batch.callback:
                        await batch.callback(batch)
                except Exception as e:
                    logger.error(f"[MEDIA QUEUE] Error processing media batch {batch.batch_key}: {e}", exc_info=True)
                finally:
                    self._global_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MEDIA QUEUE] Worker loop exception: {e}")
                await asyncio.sleep(1.0)

    def get_pending_count(self) -> int:
        """Returns total number of media items currently queued across all active batches."""
        active_batch_items = sum(len(b.items) for b in self._batches.values())
        return active_batch_items + self._global_queue.qsize()

# Global default instance
global_media_queue = SocialMediaQueue()
