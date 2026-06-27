from __future__ import annotations

import time

from src.data import rate_limiter
from src.data.rate_limiter import RateLimiter, exponential_backoff_sleep


def test_wait_enforces_minimum_delay() -> None:
    limiter = RateLimiter(min_delay_seconds=0.05)
    start = time.monotonic()
    limiter.wait()  # first call returns immediately
    limiter.wait()  # second call must wait out the min delay
    elapsed = time.monotonic() - start
    assert elapsed >= 0.05


def test_wait_does_not_sleep_when_enough_time_passed() -> None:
    limiter = RateLimiter(min_delay_seconds=0.0)
    start = time.monotonic()
    limiter.wait()
    limiter.wait()
    assert time.monotonic() - start < 0.05


def test_exponential_backoff_grows_with_attempt(monkeypatch) -> None:
    captured: list[float] = []
    monkeypatch.setattr(rate_limiter.time, 'sleep', captured.append)
    monkeypatch.setattr(rate_limiter.random, 'uniform', lambda _a, _b: 0.0)

    exponential_backoff_sleep(base_delay=1.0, attempt=0)
    exponential_backoff_sleep(base_delay=1.0, attempt=1)
    exponential_backoff_sleep(base_delay=1.0, attempt=2)

    assert captured == [1.0, 2.0, 4.0]


def test_exponential_backoff_adds_jitter(monkeypatch) -> None:
    captured: list[float] = []
    monkeypatch.setattr(rate_limiter.time, 'sleep', captured.append)
    monkeypatch.setattr(rate_limiter.random, 'uniform', lambda _a, b: b)

    exponential_backoff_sleep(base_delay=1.0, attempt=1)
    # delay = 2.0, jitter ceiling = 0.2 * 2.0 = 0.4 -> 2.4
    assert captured == [2.4]
