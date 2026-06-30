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


def test_scaleout_section_marks_harvested_level_taken() -> None:
    monitor = pd.DataFrame([
        # extended at 93.5 already passed; harvested -> should read 'taken', not act-now
        {'Ticker': 'AAA', 'Sleeve': 'Satellite', 'Account': 'Taxable',
         'Shares': 3.0, 'Price': 100.0, 'EMA20': 85.0},
    ])
    lookup = {'AAA': {'Entry': 95.0, 'Stop': 90.0}}
    harvested = {dr.scaleout_key('Taxable', 'AAA'): dr.SCALE_EXTENDED}
    out = dr._scaleout_section(monitor, lookup, Settings(), harvested)
    aaa_line = next(ln for ln in out.splitlines() if ln.startswith('| AAA'))
    assert '\u2713 taken' in aaa_line  # harvested extended cell marked taken
    assert 'now \u2014' not in aaa_line  # no longer prompts act-now
    assert 'to +2R' in aaa_line  # nearest now points at the un-harvested +2R


def test_scaleout_section_flags_folded_extended_when_2r_taken() -> None:
    # Case B: extended ($115) sits *above* +2R ($105); +2R already harvested (rank 2).
    # The extended rung is suppressed/folded, not a separate ⅓ still owed.
    monitor = pd.DataFrame([
        {'Ticker': 'AAA', 'Sleeve': 'Satellite', 'Account': 'Taxable',
         'Shares': 3.0, 'Price': 100.0, 'EMA20': 104.5},  # extended = 104.5 * 1.10 = 114.95
    ])
    lookup = {'AAA': {'Entry': 95.0, 'Stop': 90.0}}  # +2R = 95 + 2*5 = 105
    harvested = {dr.scaleout_key('Taxable', 'AAA'): dr.SCALE_2R}
    out = dr._scaleout_section(monitor, lookup, Settings(), harvested)
    aaa_line = next(ln for ln in out.splitlines() if ln.startswith('| AAA'))
    assert 'folded \u2014 +2R taken' in aaa_line  # extended rung flagged as suppressed
    assert '\u2713 taken' in aaa_line  # +2R cell still reads taken


def test_sold_keys_detects_negative_lots() -> None:
    text = (
        '[Taxable]\n'
        'GOOGL, 200.00, 0.5\n'
        'GOOGL, -, -0.011\n'
        '# a comment\n'
        'CASH = 35.37\n'
        '[Roth IRA]\n'
        'LRCX, -, -0.052\n'
    )
    keys = dr._sold_keys(text)
    assert keys == {'Taxable|GOOGL', 'Roth IRA|LRCX'}


def test_stops_section_breakeven_and_structural_alerts() -> None:
    monitor = pd.DataFrame([
        # Up +30% with a 25.6% stop distance and cost ($93.08) above the stop ($90)
        # -> alert tightens up to breakeven (cost).
        {'Ticker': 'AAA', 'Sleeve': 'Satellite', 'Account': 'Taxable',
         'Shares': 2.0, 'Price': 121.0, 'Unreal P&L %': 0.30},
        # Small gain, below one stop-distance of profit -> alert stays at structural stop.
        {'Ticker': 'BBB', 'Sleeve': 'Satellite', 'Account': 'Taxable',
         'Shares': 2.0, 'Price': 104.0, 'Unreal P&L %': 0.05},
        # Core holdings excluded.
        {'Ticker': 'CORE', 'Sleeve': 'Core', 'Account': 'Taxable',
         'Shares': 2.0, 'Price': 100.0, 'Unreal P&L %': 0.10},
    ])
    lookup = {
        'AAA': {'Entry': 100.0, 'Stop': 90.0},
        'BBB': {'Entry': 100.0, 'Stop': 90.0},
        'CORE': {'Entry': 50.0, 'Stop': 40.0},
    }
    out = dr._stops_section(monitor, lookup, Settings())
    assert 'CORE' not in out
    aaa_line = next(ln for ln in out.splitlines() if ln.startswith('| AAA'))
    assert 'Tighten to breakeven' in aaa_line
    assert '$93.08' in aaa_line  # cost basis = price / (1 + P&L)
    bbb_line = next(ln for ln in out.splitlines() if ln.startswith('| BBB'))
    assert 'Alert at structural stop' in bbb_line
    assert '$90.00' in bbb_line  # structural stop



