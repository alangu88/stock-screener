from __future__ import annotations

import pandas as pd
import pytest

import scripts.daily_report as dr
from src.config import Settings


def _recs(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_auto_add_high_confidence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    wl = tmp_path / 'watchlist.txt'
    wl.write_text('# header\nAAPL\n', encoding='utf-8')
    monkeypatch.setattr(dr, 'WATCHLIST_FILE', wl)

    recs = _recs([
        {'Ticker': 'NVDA', 'Confidence': 92.0},
        {'Ticker': 'AAPL', 'Confidence': 95.0},   # already watched
        {'Ticker': 'MSFT', 'Confidence': 60.0},   # below threshold
        {'Ticker': 'TSLA', 'Confidence': 81.0},
    ])
    added = dr._auto_add_to_watchlist(recs, held=['GOOGL'], exclude=set(), settings=Settings())

    assert added == ['NVDA', 'TSLA']
    assert wl.read_text(encoding='utf-8').endswith('AAPL\nNVDA\nTSLA\n')


def test_auto_add_skips_held_and_funds(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    wl = tmp_path / 'watchlist.txt'
    wl.write_text('AAPL\n', encoding='utf-8')
    monkeypatch.setattr(dr, 'WATCHLIST_FILE', wl)

    recs = _recs([
        {'Ticker': 'GOOGL', 'Confidence': 90.0},  # held
        {'Ticker': 'VTI', 'Confidence': 90.0},    # fund (excluded)
    ])
    added = dr._auto_add_to_watchlist(recs, held=['GOOGL'], exclude={'VTI'}, settings=Settings())

    assert added == []
    assert wl.read_text(encoding='utf-8') == 'AAPL\n'


def test_auto_add_ignores_nan_confidence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    wl = tmp_path / 'watchlist.txt'
    wl.write_text('AAPL\n', encoding='utf-8')
    monkeypatch.setattr(dr, 'WATCHLIST_FILE', wl)

    recs = _recs([{'Ticker': 'NVDA', 'Confidence': float('nan')}])
    assert dr._auto_add_to_watchlist(recs, held=[], exclude=set(), settings=Settings()) == []


def test_auto_add_empty_recs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    wl = tmp_path / 'watchlist.txt'
    wl.write_text('AAPL\n', encoding='utf-8')
    monkeypatch.setattr(dr, 'WATCHLIST_FILE', wl)

    assert dr._auto_add_to_watchlist(pd.DataFrame(), [], set(), Settings()) == []
    assert wl.read_text(encoding='utf-8') == 'AAPL\n'
