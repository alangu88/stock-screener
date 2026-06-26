from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import Settings
from src.screener.holdings import (
    DEFAULT_ACCOUNT,
    SATELLITE,
    PositionEntry,
    account_groups,
    allocation_summary,
    build_monitor,
    concentration_summary,
    count_individual_stocks,
    export_manifest,
    has_accounts,
    merge_holdings,
    parse_account_value,
    parse_portfolio,
    parse_positions,
)

SETTINGS = Settings()


def _history(prices: list[float]) -> pd.DataFrame:
    index = pd.date_range('2022-01-01', periods=len(prices), freq='B')
    return pd.DataFrame({'Close': prices, 'Volume': [1_000_000] * len(prices)}, index=index)


def test_parse_positions_ticker_only():
    entries = parse_positions('AAPL\nMSFT\n')
    assert entries == [PositionEntry('AAPL'), PositionEntry('MSFT')]


def test_parse_positions_with_price_and_shares():
    entries = parse_positions('NVDA, 95.20, 100')
    assert entries == [PositionEntry('NVDA', 95.20, 100.0)]


def test_parse_positions_handles_whitespace_and_dollar_sign():
    entries = parse_positions('brk.b  $410.50  1000')
    assert entries == [PositionEntry('BRK-B', 410.50, 1000.0)]


def test_parse_positions_skips_comments_blank_and_duplicates():
    entries = parse_positions('# header\nAAPL\n\nAAPL, 10\n  # note\nMSFT')
    assert [e.ticker for e in entries] == ['AAPL', 'MSFT']
    # First occurrence wins (no entry price).
    assert entries[0].entry_price is None


def test_parse_positions_bad_numbers_become_none():
    entries = parse_positions('AAPL, n/a, junk')
    assert entries == [PositionEntry('AAPL', None, None)]


def test_parse_positions_assigns_account_sections():
    text = '[Taxable]\nAAPL\nMSFT, 410.50\n\n[Roth IRA]\nNVDA, 95.20, 100'
    entries = parse_positions(text)
    assert entries == [
        PositionEntry('AAPL', None, None, 'Taxable'),
        PositionEntry('MSFT', 410.50, None, 'Taxable'),
        PositionEntry('NVDA', 95.20, 100.0, 'Roth IRA'),
    ]


def test_parse_positions_same_ticker_allowed_across_accounts():
    entries = parse_positions('[Taxable]\nAAPL, 100\n[Roth IRA]\nAAPL, 120')
    assert [(e.ticker, e.account, e.entry_price) for e in entries] == [
        ('AAPL', 'Taxable', 100.0),
        ('AAPL', 'Roth IRA', 120.0),
    ]


def test_parse_positions_dupe_within_account_keeps_first():
    entries = parse_positions('[Taxable]\nAAPL, 100\nAAPL, 200')
    assert entries == [PositionEntry('AAPL', 100.0, None, 'Taxable')]


def test_parse_positions_merges_lots_into_average_cost():
    entries = parse_positions('[Taxable]\nAAPL, 150, 10\nAAPL, 170, 20')
    assert len(entries) == 1
    aapl = entries[0]
    assert aapl.shares == 30.0
    # Weighted average: (150*10 + 170*20) / 30 = 163.333...
    assert round(aapl.entry_price, 4) == 163.3333


def test_parse_positions_lots_stay_separate_across_accounts():
    entries = parse_positions('[Taxable]\nAAPL, 150, 10\n[Roth IRA]\nAAPL, 170, 20')
    assert [(e.account, e.shares, e.entry_price) for e in entries] == [
        ('Taxable', 10.0, 150.0),
        ('Roth IRA', 20.0, 170.0),
    ]



def test_parse_positions_entries_before_header_have_no_account():
    entries = parse_positions('AAPL\n[Taxable]\nMSFT')
    assert entries[0].account is None
    assert entries[1].account == 'Taxable'



def test_build_monitor_uptrend_and_levels():
    rising = list(np.linspace(100, 300, 260))
    monitor = build_monitor([PositionEntry('UP')], {'UP': _history(rising)}, SETTINGS)
    row = monitor.iloc[0]
    assert row['Ticker'] == 'UP'
    assert row['Price'] > row['EMA20'] > row['SMA50'] > row['SMA200']
    assert row['Trend'] == 'Uptrend (stacked)'
    assert row['Signal'] == 'Bullish (above 50 & 200)'
    assert row['% vs SMA200'] > 0


def test_build_monitor_pnl_value_and_weight():
    flat = [100.0] * 260
    entries = [PositionEntry('A', entry_price=50.0, shares=10.0)]
    monitor = build_monitor(entries, {'A': _history(flat)}, SETTINGS)
    row = monitor.iloc[0]
    assert row['Unreal P&L %'] == 1.0  # 100 vs 50 entry
    assert row['Value'] == 1000.0
    assert row['Unreal P&L $'] == 500.0
    assert row['Weight %'] == 1.0  # only holding


def test_build_monitor_weight_split_across_holdings():
    flat = [100.0] * 260
    entries = [
        PositionEntry('A', entry_price=100.0, shares=30.0),
        PositionEntry('B', entry_price=100.0, shares=10.0),
    ]
    history = {'A': _history(flat), 'B': _history(flat)}
    monitor = build_monitor(entries, history, SETTINGS).set_index('Ticker')
    assert monitor.loc['A', 'Weight %'] == 0.75
    assert monitor.loc['B', 'Weight %'] == 0.25


def test_build_monitor_insufficient_history():
    monitor = build_monitor([PositionEntry('SHORT')], {'SHORT': _history([100.0] * 30)}, SETTINGS)
    row = monitor.iloc[0]
    assert row['SMA200'] is None
    assert row['Trend'] == 'Insufficient history'


def test_build_monitor_missing_data_lists_ticker_with_no_data_signal():
    monitor = build_monitor([PositionEntry('GONE')], {}, SETTINGS)
    row = monitor.iloc[0]
    assert row['Ticker'] == 'GONE'
    assert row['Signal'] == 'No data'
    assert row['Price'] is None


def _portfolio_monitor(weights: dict[str, float]) -> pd.DataFrame:
    """Build a monitor frame with flat prices so Value == shares (== weight*total)."""
    flat = [100.0] * 260
    entries = [PositionEntry(t, entry_price=100.0, shares=w) for t, w in weights.items()]
    history = {t: _history(flat) for t in weights}
    return build_monitor(entries, history, SETTINGS)


def test_concentration_summary_none_without_sized_positions():
    monitor = build_monitor([PositionEntry('AAPL')], {'AAPL': _history([100.0] * 260)}, SETTINGS)
    assert concentration_summary(monitor) is None


def test_concentration_summary_equal_weight_is_diversified():
    monitor = _portfolio_monitor({'A': 10, 'B': 10, 'C': 10, 'D': 10, 'E': 10, 'F': 10, 'G': 10})
    stats = concentration_summary(monitor)
    assert stats is not None
    assert stats.positions == 7
    assert stats.largest_weight == 1 / 7
    assert round(stats.effective_positions, 6) == 7.0
    assert stats.label == 'Diversified'


def test_concentration_summary_single_position_is_concentrated():
    monitor = _portfolio_monitor({'BIG': 100})
    stats = concentration_summary(monitor)
    assert stats is not None
    assert stats.largest_ticker == 'BIG'
    assert stats.largest_weight == 1.0
    assert stats.hhi == 1.0
    assert stats.effective_positions == 1.0
    assert stats.label == 'Concentrated'


def test_concentration_summary_top_n_and_largest():
    monitor = _portfolio_monitor({'A': 50, 'B': 30, 'C': 10, 'D': 10})
    stats = concentration_summary(monitor)
    assert stats is not None
    assert stats.largest_ticker == 'A'
    assert stats.largest_weight == 0.5
    # Only 4 positions, so top-5 weight rolls up the whole book.
    assert round(stats.top_n_weight, 6) == 1.0
    # HHI = 0.5^2 + 0.3^2 + 0.1^2 + 0.1^2 = 0.36
    assert round(stats.hhi, 6) == 0.36
    assert stats.label == 'Concentrated'


def test_build_monitor_carries_account_column():
    flat = [100.0] * 260
    entries = [
        PositionEntry('A', 100.0, 10.0, 'Taxable'),
        PositionEntry('B', 100.0, 10.0, 'Roth IRA'),
    ]
    history = {'A': _history(flat), 'B': _history(flat)}
    monitor = build_monitor(entries, history, SETTINGS).set_index('Ticker')
    assert monitor.loc['A', 'Account'] == 'Taxable'
    assert monitor.loc['B', 'Account'] == 'Roth IRA'


def test_has_accounts_detects_sections():
    flat = [100.0] * 260
    tagged = build_monitor([PositionEntry('A', account='Taxable')], {'A': _history(flat)}, SETTINGS)
    untagged = build_monitor([PositionEntry('A')], {'A': _history(flat)}, SETTINGS)
    assert has_accounts(tagged) is True
    assert has_accounts(untagged) is False


def test_account_groups_split_and_order():
    flat = [100.0] * 260
    entries = [
        PositionEntry('A', 100.0, 10.0, 'Taxable'),
        PositionEntry('B', 100.0, 10.0, 'Roth IRA'),
        PositionEntry('C', 100.0, 10.0, 'Taxable'),
        PositionEntry('D'),  # no account -> default bucket
    ]
    history = {t: _history(flat) for t in ('A', 'B', 'C', 'D')}
    monitor = build_monitor(entries, history, SETTINGS)
    groups = account_groups(monitor)
    assert [label for label, _ in groups] == ['Taxable', 'Roth IRA', DEFAULT_ACCOUNT]
    taxable = dict(groups)['Taxable']
    assert list(taxable['Ticker']) == ['A', 'C']


def test_parse_portfolio_sleeve_tags_and_default():
    text = '[Taxable]\nVTI, core\nFSELX, satellite\nNVDA\n'
    entries = parse_portfolio(text)
    by_ticker = {e.ticker: e for e in entries}
    assert by_ticker['VTI'].sleeve == 'core'
    assert by_ticker['VTI'].account == 'Taxable'
    assert by_ticker['FSELX'].sleeve == 'satellite'
    assert by_ticker['NVDA'].sleeve == SATELLITE  # default
    assert all(e.shares is None and e.entry_price is None for e in entries)


def test_parse_portfolio_sleeve_token_before_ticker_and_case_insensitive():
    entries = parse_portfolio('Core VTI\nSATELLITE fselx\n')
    by_ticker = {e.ticker: e for e in entries}
    assert by_ticker['VTI'].sleeve == 'core'
    assert by_ticker['FSELX'].sleeve == 'satellite'


def test_parse_portfolio_dedupes_per_account_keeps_first():
    entries = parse_portfolio('[Taxable]\nVTI, core\nVTI, satellite\n[Roth IRA]\nVTI, core\n')
    taxable = [e for e in entries if e.account == 'Taxable']
    assert len(taxable) == 1
    assert taxable[0].sleeve == 'core'
    # Same ticker under a different account is kept.
    assert any(e.account == 'Roth IRA' and e.ticker == 'VTI' for e in entries)


def test_parse_account_value_directive_forms():
    assert parse_account_value('account_value = 100000') == 100000.0
    assert parse_account_value('ACCOUNT_VALUE: $95,000') == 95000.0
    assert parse_account_value('VTI, 240, 10') is None
    assert parse_account_value('# account_value = 5') is None


def test_parse_positions_skips_account_value_directive():
    entries = parse_positions('account_value = 100000\nAAPL, 150, 10\n')
    assert [e.ticker for e in entries] == ['AAPL']


def test_parse_account_value_sums_plus_separated_terms():
    assert parse_account_value('account_value = 2310.60 + 5269.23') == 7579.83
    assert parse_account_value('account_value = $1,000 + 2,000 + 500') == 3500.0


def test_account_value_line_never_becomes_a_ticker():
    # Even a malformed value must be treated as the directive, not a ticker.
    entries = parse_positions('account_value = 10 +\nAAPL\n')
    tickers = [e.ticker for e in entries]
    assert 'ACCOUNT_VALUE' not in tickers
    assert tickers == ['AAPL']


def test_merge_holdings_joins_sleeve_and_sizes():
    portfolio = [
        PositionEntry('VTI', account='Taxable', sleeve='core'),
        PositionEntry('FSELX', account='Taxable', sleeve='satellite'),
    ]
    positions = [
        PositionEntry('VTI', entry_price=240.0, shares=10.0, account='Taxable'),
    ]
    merged = merge_holdings(portfolio, positions)
    by_ticker = {e.ticker: e for e in merged}
    assert by_ticker['VTI'].sleeve == 'core'
    assert by_ticker['VTI'].shares == 10.0
    assert by_ticker['VTI'].entry_price == 240.0
    # In portfolio but no size -> sleeve kept, sizes None.
    assert by_ticker['FSELX'].sleeve == 'satellite'
    assert by_ticker['FSELX'].shares is None


def test_merge_holdings_appends_position_only_with_default_sleeve():
    portfolio = [PositionEntry('VTI', account='Taxable', sleeve='core')]
    positions = [
        PositionEntry('VTI', entry_price=240.0, shares=10.0, account='Taxable'),
        PositionEntry('NVDA', entry_price=95.0, shares=5.0, account='Taxable'),
    ]
    merged = merge_holdings(portfolio, positions)
    assert [e.ticker for e in merged] == ['VTI', 'NVDA']  # portfolio order first
    nvda = merged[1]
    assert nvda.sleeve == SATELLITE
    assert nvda.shares == 5.0


def test_export_manifest_round_trips_without_sizes():
    entries = [
        PositionEntry('VTI', entry_price=240.0, shares=10.0, account='Taxable', sleeve='core'),
        PositionEntry('FSELX', entry_price=30.5, shares=200.0, account='Taxable', sleeve='satellite'),
        PositionEntry('NVDA', entry_price=95.0, shares=5.0, account='Roth IRA', sleeve='satellite'),
    ]
    text = export_manifest(entries)
    # No private sizing should leak into the committed manifest.
    assert '240' not in text
    assert '200' not in text
    assert '[Taxable]' in text and '[Roth IRA]' in text
    # Re-parsing yields the same tickers, accounts, and sleeves.
    reparsed = {(e.account, e.ticker): e.sleeve for e in parse_portfolio(text)}
    assert reparsed[('Taxable', 'VTI')] == 'core'
    assert reparsed[('Taxable', 'FSELX')] == 'satellite'
    assert reparsed[('Roth IRA', 'NVDA')] == 'satellite'


def _sleeved_monitor(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Build a monitor from (ticker, sleeve, shares) at a flat $100 price."""
    flat = [100.0] * 260
    entries = [
        PositionEntry(t, entry_price=100.0, shares=sh, sleeve=sleeve)
        for t, sleeve, sh in rows
    ]
    history = {t: _history(flat) for t, _, _ in rows}
    return build_monitor(entries, history, SETTINGS)


def test_build_monitor_carries_sleeve_column():
    monitor = _sleeved_monitor([('VTI', 'core', 10.0), ('NVDA', 'satellite', 5.0)])
    by_ticker = monitor.set_index('Ticker')
    assert by_ticker.loc['VTI', 'Sleeve'] == 'core'
    assert by_ticker.loc['NVDA', 'Sleeve'] == 'satellite'


def test_allocation_summary_on_target():
    # Core $6,500 of $10,000 = 65%, inside the 60-70% band.
    monitor = _sleeved_monitor([('VTI', 'core', 65.0), ('NVDA', 'satellite', 35.0)])
    stats = allocation_summary(monitor, 0.60, 0.70)
    assert stats is not None
    assert round(stats.core_pct, 4) == 0.65
    assert round(stats.satellite_pct, 4) == 0.35
    assert stats.within_band is True
    assert stats.label == 'On target'


def test_allocation_summary_core_light_and_heavy():
    light = allocation_summary(_sleeved_monitor([('VTI', 'core', 40.0), ('NVDA', 'satellite', 60.0)]), 0.60, 0.70)
    assert light is not None and light.label == 'Core light' and light.within_band is False
    heavy = allocation_summary(_sleeved_monitor([('VTI', 'core', 90.0), ('NVDA', 'satellite', 10.0)]), 0.60, 0.70)
    assert heavy is not None and heavy.label == 'Core heavy' and heavy.within_band is False


def test_allocation_summary_none_without_sized_positions():
    flat = [100.0] * 260
    monitor = build_monitor([PositionEntry('VTI', sleeve='core')], {'VTI': _history(flat)}, SETTINGS)
    assert allocation_summary(monitor, 0.60, 0.70) is None


def test_count_individual_stocks_excludes_core_and_etfs():
    monitor = _sleeved_monitor([
        ('VTI', 'core', 10.0),       # core -> excluded
        ('FSELX', 'satellite', 5.0),  # satellite ETF -> excluded via etf set
        ('NVDA', 'satellite', 5.0),   # individual stock -> counts
        ('AAPL', 'satellite', 5.0),   # individual stock -> counts
    ])
    assert count_individual_stocks(monitor, etf_tickers={'FSELX', 'VTI'}) == 2




