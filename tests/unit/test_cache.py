import time
from pathlib import Path

from src.data.cache import SQLiteCache


def test_cache_set_get(tmp_path: Path):
    cache = SQLiteCache(tmp_path)
    cache.set('k1', {'a': 1}, ttl_seconds=30)
    assert cache.get('k1') == {'a': 1}


def test_cache_expiration(tmp_path: Path):
    cache = SQLiteCache(tmp_path)
    cache.set('soon', {'x': 2}, ttl_seconds=1)
    time.sleep(1.2)
    assert cache.get('soon') is None


def test_cache_clear(tmp_path: Path):
    cache = SQLiteCache(tmp_path)
    cache.set('k2', 123, ttl_seconds=30)
    cache.clear()
    assert cache.get('k2') is None


def test_cache_close_allows_reuse(tmp_path: Path):
    cache = SQLiteCache(tmp_path)
    cache.set('k3', 'v', ttl_seconds=30)
    cache.close()
    # close() is idempotent and the cache reconnects transparently afterwards.
    cache.close()
    assert cache.get('k3') == 'v'

