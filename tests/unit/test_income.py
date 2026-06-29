from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.screener.holdings import PositionEntry
from src.screener.income import (
    collect_income,
    income_by_account,
    load_ledger,
    save_ledger,
)

TODAY = date(2026, 6, 29)


def _frame(rows: dict[str, dict[str, float]]) -> pd.DataFrame:
    """Build a history frame with a DatetimeIndex and distribution columns."""
    idx = pd.to_datetime(list(rows))
    df = pd.DataFrame(index=idx)
    df['Close'] = 100.0
    df['Dividends'] = [rows[d].get('Dividends', 0.0) for d in rows]
    df['Capital Gains'] = [rows[d].get('Capital Gains', 0.0) for d in rows]
    return df


def test_first_run_bounds_to_lookback_window():
    entries = [PositionEntry('VTI', 300.0, 10.0, 'Taxable')]
    history = {
        'VTI': _frame({
            '2026-01-15': {'Dividends': 0.80},   # old: outside the 7-day window
            '2026-06-26': {'Dividends': 0.92},   # recent: inside the window
        })
    }
    events, ledger = collect_income(entries, history, {}, today=TODAY, lookback_days=7)

    assert [e.ex_date for e in events] == [date(2026, 6, 26)]
    assert events[0].amount == pytest.approx(9.2)
    # Watermark advances past every event so the old one never resurfaces.
    assert ledger['VTI'] == '2026-06-26'


def test_subsequent_run_shows_only_newer_than_watermark():
    entries = [PositionEntry('VTI', 300.0, 10.0, 'Taxable')]
    history = {
        'VTI': _frame({
            '2026-06-26': {'Dividends': 0.92},   # already seen
            '2026-06-29': {'Dividends': 0.10},   # new
        })
    }
    events, ledger = collect_income(
        entries, history, {'VTI': '2026-06-26'}, today=TODAY, lookback_days=7
    )

    assert [e.ex_date for e in events] == [date(2026, 6, 29)]
    assert ledger['VTI'] == '2026-06-29'


def test_watermark_run_ignores_lookback_window():
    # A gap longer than the window must still surface anything past the watermark.
    entries = [PositionEntry('XOM', 100.0, 5.0, 'Taxable')]
    history = {'XOM': _frame({'2026-06-10': {'Dividends': 0.99}})}
    events, _ = collect_income(
        entries, history, {'XOM': '2026-06-01'}, today=TODAY, lookback_days=7
    )

    assert [e.ex_date for e in events] == [date(2026, 6, 10)]


def test_same_ticker_in_two_accounts_yields_per_account_amounts():
    entries = [
        PositionEntry('VTI', 300.0, 2.0, 'Taxable'),
        PositionEntry('VTI', 320.0, 4.0, 'Roth IRA'),
    ]
    history = {'VTI': _frame({'2026-06-26': {'Dividends': 1.00}})}
    events, _ = collect_income(entries, history, {}, today=TODAY, lookback_days=7)

    by_account = {e.account: e.amount for e in events}
    assert by_account == {'Taxable': pytest.approx(2.0), 'Roth IRA': pytest.approx(4.0)}


def test_capital_gains_distribution_is_captured():
    entries = [PositionEntry('FSELX', 60.0, 10.0, 'Roth IRA')]
    history = {'FSELX': _frame({'2026-06-26': {'Capital Gains': 0.50}})}
    events, _ = collect_income(entries, history, {}, today=TODAY, lookback_days=7)

    assert len(events) == 1
    assert events[0].kind == 'Capital gain'
    assert events[0].amount == pytest.approx(5.0)


def test_unsized_and_missing_columns_produce_no_events():
    entries = [
        PositionEntry('AAA', 10.0, None, 'Taxable'),   # watch-only, no shares
        PositionEntry('BBB', 10.0, 5.0, 'Taxable'),    # no distribution columns
    ]
    history = {'BBB': pd.DataFrame({'Close': [1.0, 2.0]})}
    events, ledger = collect_income(entries, history, {}, today=TODAY, lookback_days=7)

    assert events == []
    assert ledger == {}


def test_income_by_account_groups_and_totals():
    entries = [
        PositionEntry('VTI', 300.0, 2.0, 'Taxable'),
        PositionEntry('XOM', 100.0, 3.0, 'Taxable'),
        PositionEntry('FSELX', 60.0, 4.0, 'Roth IRA'),
    ]
    history = {
        'VTI': _frame({'2026-06-26': {'Dividends': 1.00}}),
        'XOM': _frame({'2026-06-27': {'Dividends': 0.50}}),
        'FSELX': _frame({'2026-06-28': {'Capital Gains': 0.25}}),
    }
    events, _ = collect_income(entries, history, {}, today=TODAY, lookback_days=7)
    grouped = income_by_account(events)

    totals = {acct: total for acct, total, _ in grouped}
    assert totals['Taxable'] == pytest.approx(3.5)
    assert totals['Roth IRA'] == pytest.approx(1.0)


def test_ledger_round_trip_and_tolerates_missing(tmp_path):
    path = tmp_path / '.income_ledger.json'
    assert load_ledger(path) == {}

    save_ledger(path, {'VTI': '2026-06-26'})
    assert load_ledger(path) == {'VTI': '2026-06-26'}


def test_ledger_tolerates_corrupt_file(tmp_path):
    path = tmp_path / '.income_ledger.json'
    path.write_text('{ not json', encoding='utf-8')
    assert load_ledger(path) == {}
