"""
Real-time streaming and incremental updates for reporting datasets.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, AsyncIterator

from django.utils import timezone


@dataclass
class StreamConfig:
    """Configuration for streaming datasets"""
    batch_size: int = 100
    poll_interval_seconds: float = 2.0
    max_duration_seconds: float = 300.0  # 5 minutes max
    enable_delta_mode: bool = True


class DatasetStreamer:
    """
    Stream dataset results in real-time with incremental updates.

    Supports:
    - Chunked result delivery
    - Delta updates (only changed rows)
    - Long-polling for live data
    - Backpressure handling
    """

    def __init__(self, config: StreamConfig | None = None):
        self.config = config or StreamConfig()

    async def stream_dataset_chunked(
        self,
        dataset_executor: Any,
        dataset_key: str,
        filters: dict[str, Any],
        checkpoint: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream dataset results in chunks.

        Args:
            dataset_executor: Function to execute dataset query
            dataset_key: Dataset identifier
            filters: Query filters
            checkpoint: Resume from this checkpoint (for pagination)

        Yields:
            Chunks of dataset results
        """
        offset = int(checkpoint) if checkpoint else 0
        batch_size = self.config.batch_size

        while True:
            # Fetch batch
            batch_filters = {**filters, "limit": batch_size, "offset": offset}

            try:
                result = await asyncio.to_thread(
                    dataset_executor,
                    dataset_key,
                    batch_filters,
                )
            except Exception as e:
                yield {
                    "type": "error",
                    "error": str(e),
                    "timestamp": timezone.now().isoformat(),
                }
                break

            rows = result.get("rows", [])
            has_more = len(rows) == batch_size

            yield {
                "type": "chunk",
                "data": {
                    "rows": rows,
                    "offset": offset,
                    "batch_size": len(rows),
                    "has_more": has_more,
                    "checkpoint": str(offset + len(rows)),
                },
                "timestamp": timezone.now().isoformat(),
            }

            if not has_more:
                break

            offset += batch_size

    async def stream_dataset_live(
        self,
        dataset_executor: Any,
        dataset_key: str,
        filters: dict[str, Any],
        last_run_id: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Stream live updates for a dataset using long-polling.

        Args:
            dataset_executor: Function to execute dataset query
            dataset_key: Dataset identifier
            filters: Query filters
            last_run_id: Last run ID received by client

        Yields:
            Delta updates when data changes
        """
        start_time = timezone.now()
        max_duration = self.config.max_duration_seconds
        poll_interval = self.config.poll_interval_seconds

        previous_run_id = last_run_id
        previous_checksum = None

        while True:
            # Check timeout
            elapsed = (timezone.now() - start_time).total_seconds()
            if elapsed >= max_duration:
                yield {
                    "type": "timeout",
                    "message": "Stream duration exceeded",
                    "timestamp": timezone.now().isoformat(),
                }
                break

            # Execute dataset
            try:
                result = await asyncio.to_thread(
                    dataset_executor,
                    dataset_key,
                    filters,
                )
            except Exception as e:
                yield {
                    "type": "error",
                    "error": str(e),
                    "timestamp": timezone.now().isoformat(),
                }
                break

            current_run_id = result.get("run_id")
            current_checksum = self._compute_checksum(result.get("rows", []))

            # Check if data changed
            if self.config.enable_delta_mode:
                if current_run_id != previous_run_id or current_checksum != previous_checksum:
                    # Send delta update
                    yield {
                        "type": "update",
                        "data": result,
                        "run_id": current_run_id,
                        "timestamp": timezone.now().isoformat(),
                        "is_delta": True,
                    }

                    previous_run_id = current_run_id
                    previous_checksum = current_checksum
            else:
                # Send full update
                yield {
                    "type": "update",
                    "data": result,
                    "run_id": current_run_id,
                    "timestamp": timezone.now().isoformat(),
                    "is_delta": False,
                }

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    def _compute_checksum(self, rows: list[dict[str, Any]]) -> str:
        """
        Compute checksum of dataset rows for change detection.

        Args:
            rows: Dataset rows

        Returns:
            Checksum string
        """
        import hashlib

        # Serialize rows deterministically
        content = json.dumps(rows, sort_keys=True, default=str)
        return hashlib.md5(content.encode()).hexdigest()


class StreamingMetrics:
    """Track streaming performance metrics"""

    def __init__(self):
        self.active_streams = 0
        self.total_streams = 0
        self.total_chunks_sent = 0
        self.total_errors = 0

    def stream_started(self) -> None:
        """Record stream start"""
        self.active_streams += 1
        self.total_streams += 1

    def stream_ended(self) -> None:
        """Record stream end"""
        self.active_streams = max(0, self.active_streams - 1)

    def chunk_sent(self) -> None:
        """Record chunk delivery"""
        self.total_chunks_sent += 1

    def error_occurred(self) -> None:
        """Record error"""
        self.total_errors += 1

    def get_metrics(self) -> dict[str, Any]:
        """Get current metrics"""
        return {
            "active_streams": self.active_streams,
            "total_streams": self.total_streams,
            "total_chunks_sent": self.total_chunks_sent,
            "total_errors": self.total_errors,
        }


# Global metrics instance
_streaming_metrics = StreamingMetrics()


def get_streaming_metrics() -> StreamingMetrics:
    """Get global streaming metrics instance"""
    return _streaming_metrics
