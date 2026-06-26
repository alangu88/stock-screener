from __future__ import annotations

import random
import threading
import time


class RateLimiter:
    def __init__(self, min_delay_seconds: float = 0.25) -> None:
        self.min_delay_seconds = min_delay_seconds
        self._last_call = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.time()
            elapsed = now - self._last_call
            if elapsed < self.min_delay_seconds:
                time.sleep(self.min_delay_seconds - elapsed)
            self._last_call = time.time()


def exponential_backoff_sleep(base_delay: float, attempt: int) -> None:
    delay = base_delay * (2 ** attempt)
    jitter = random.uniform(0, 0.2 * delay)
    time.sleep(delay + jitter)
