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


def test_nearest_scaleout_flags_approaching_plus2r() -> None:
    # entry 100, stop 90 -> +2R at 120; price 118 is 1.7% below, within the 3% band
    row = {'Price': 118.0, 'Shares': 3.0, 'EMA20': 90.0}
    analysis = {'Entry': 100.0, 'Stop': 90.0}
    near = dr._nearest_scaleout(row, analysis, Settings())
    assert near is not None
    label, level, sell_sh, sell_amt, gap = near
    assert label == '+2R'
    assert level == pytest.approx(120.0)
    assert sell_sh == pytest.approx(1.0)
    assert sell_amt == pytest.approx(120.0)
    assert gap == pytest.approx((120.0 - 118.0) / 118.0)


def test_nearest_scaleout_none_when_outside_band() -> None:
    # +2R at 120, price 100 is 20% away -> beyond the alert band
    row = {'Price': 100.0, 'Shares': 3.0, 'EMA20': 80.0}
    analysis = {'Entry': 100.0, 'Stop': 90.0}
    assert dr._nearest_scaleout(row, analysis, Settings()) is None


def test_nearest_scaleout_picks_closer_level() -> None:
    # +2R at 120 (price 118, 1.7% away); extended at 90*1.1=99 already passed.
    # EMA20 110 -> extended 121, slightly farther than +2R, so +2R is chosen.
    row = {'Price': 118.0, 'Shares': 3.0, 'EMA20': 110.0}
    analysis = {'Entry': 100.0, 'Stop': 90.0}
    near = dr._nearest_scaleout(row, analysis, Settings())
    assert near is not None
    assert near[0] == '+2R'


def test_scaleout_section_orders_by_proximity_and_marks_reached() -> None:
    monitor = pd.DataFrame([
        # +2R at 105 (5% away); extended at 93.5 already passed -> nearest -6.5%
        {'Ticker': 'AAA', 'Sleeve': 'Satellite', 'Shares': 3.0, 'Price': 100.0, 'EMA20': 85.0},
        # +2R at 102 (2% away); extended far -> nearest +2%
        {'Ticker': 'BBB', 'Sleeve': 'Satellite', 'Shares': 3.0, 'Price': 100.0, 'EMA20': 99.0},
        # +2R at 105 (5% away); extended at 110 -> nearest +5%
        {'Ticker': 'CCC', 'Sleeve': 'Satellite', 'Shares': 3.0, 'Price': 100.0, 'EMA20': 100.0},
        {'Ticker': 'CORE', 'Sleeve': 'Core', 'Shares': 3.0, 'Price': 100.0, 'EMA20': 50.0},
    ])
    lookup = {
        'AAA': {'Entry': 95.0, 'Stop': 90.0},
        'BBB': {'Entry': 90.0, 'Stop': 84.0},
        'CCC': {'Entry': 95.0, 'Stop': 90.0},
        'CORE': {'Entry': 50.0, 'Stop': 40.0},
    }
    out = dr._scaleout_section(monitor, lookup, Settings())
    assert 'CORE' not in out  # core holdings excluded
    assert out.index('AAA') < out.index('BBB') < out.index('CCC')  # nearest first
    aaa_line = next(ln for ln in out.splitlines() if ln.startswith('| AAA'))
    assert '\u2705 extended hit' in aaa_line  # reached level flagged on the nearest cell
    assert 'now \u2014' in aaa_line  # reached sell cell marked act-now
    bbb_line = next(ln for ln in out.splitlines() if ln.startswith('| BBB'))
    assert 'to +2R' in bbb_line
