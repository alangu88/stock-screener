"""Dividend and fund capital-gains reconciliation for held positions.

The batched history download (``actions=True``) carries per-share ``Dividends``
and ``Capital Gains`` columns at no extra request cost. This module turns those
ex-date events into estimated cash received per ``(account, ticker)`` so the
daily report can prompt you to top up the ``cash`` directive in ``positions.txt``.

A tiny JSON *ledger* records the latest ex-date already surfaced per ticker, so
each distribution is shown exactly once even when the report is run daily. The
estimate is informational only -- actual broker cash (timing, withholding, DRIP)
is the source of truth, so nothing is credited automatically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from src.screener.holdings import DEFAULT_ACCOUNT, PositionEntry

DIVIDEND_COL = 'Dividends'
CAPGAIN_COL = 'Capital Gains'
DIVIDEND_KIND = 'Dividend'
CAPGAIN_KIND = 'Capital gain'


@dataclass(frozen=True)
class IncomeEvent:
    """One distribution credited to a held position."""

    account: str
    ticker: str
    ex_date: date
    per_share: float
    shares: float
    amount: float
    kind: str  # DIVIDEND_KIND or CAPGAIN_KIND


def load_ledger(path: Path) -> dict[str, str]:
    """Read the ``ticker -> last-seen ex-date (ISO)`` ledger; ``{}`` if missing."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def save_ledger(path: Path, ledger: dict[str, str]) -> None:
    """Persist the watermark ledger as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding='utf-8')


def collect_income(
    entries: list[PositionEntry],
    history: dict[str, pd.DataFrame],
    seen: dict[str, str],
    *,
    today: date,
    lookback_days: int,
) -> tuple[list[IncomeEvent], dict[str, str]]:
    """Return new income events plus the advanced watermark ledger.

    For a ticker with no prior watermark, only ex-dates within ``lookback_days``
    of ``today`` are surfaced (so a first run never dumps years of history), but
    the watermark still advances past every event so older ones never resurface.
    For a ticker already in the ledger, every ex-date strictly after its
    watermark is surfaced regardless of age -- robust to skipped runs.
    """
    holders = _shares_by_ticker(entries)
    ledger = dict(seen)
    events: list[IncomeEvent] = []
    cutoff = today.toordinal() - max(lookback_days, 0)

    for ticker, accounts in holders.items():
        dated = _ticker_events(history.get(ticker))
        if not dated:
            continue
        watermark = _parse_date(seen.get(ticker))
        for ex_date, per_share, kind in dated:
            if watermark is None:
                is_new = ex_date.toordinal() >= cutoff
            else:
                is_new = ex_date > watermark
            if not is_new:
                continue
            for account, shares in accounts:
                events.append(
                    IncomeEvent(
                        account=account,
                        ticker=ticker,
                        ex_date=ex_date,
                        per_share=per_share,
                        shares=shares,
                        amount=per_share * shares,
                        kind=kind,
                    )
                )
        latest = max(ex for ex, _, _ in dated)
        if watermark is None or latest > watermark:
            ledger[ticker] = latest.isoformat()

    events.sort(key=lambda e: (e.ex_date, e.account, e.ticker))
    return events, ledger


def income_by_account(events: list[IncomeEvent]) -> list[tuple[str, float, list[IncomeEvent]]]:
    """Group events into ``(account, total_amount, events)`` in first-seen order."""
    order: list[str] = []
    grouped: dict[str, list[IncomeEvent]] = {}
    for event in events:
        if event.account not in grouped:
            grouped[event.account] = []
            order.append(event.account)
        grouped[event.account].append(event)
    return [(acct, sum(e.amount for e in grouped[acct]), grouped[acct]) for acct in order]


def _shares_by_ticker(entries: list[PositionEntry]) -> dict[str, list[tuple[str, float]]]:
    """Map ticker -> list of ``(account_label, shares)`` for sized holdings."""
    holders: dict[str, list[tuple[str, float]]] = {}
    for entry in entries:
        if entry.shares is None or entry.shares <= 0:
            continue
        account = entry.account or DEFAULT_ACCOUNT
        holders.setdefault(entry.ticker, []).append((account, float(entry.shares)))
    return holders


def _ticker_events(df: pd.DataFrame | None) -> list[tuple[date, float, str]]:
    """Extract ``(ex_date, per_share, kind)`` rows from a history frame."""
    if df is None or df.empty:
        return []
    rows: list[tuple[date, float, str]] = []
    rows.extend(_column_events(df, DIVIDEND_COL, DIVIDEND_KIND))
    rows.extend(_column_events(df, CAPGAIN_COL, CAPGAIN_KIND))
    return rows


def _column_events(df: pd.DataFrame, column: str, kind: str) -> list[tuple[date, float, str]]:
    if column not in df.columns:
        return []
    series = df[column].dropna()
    series = series[series > 0]
    out: list[tuple[date, float, str]] = []
    for index, value in series.items():
        out.append((pd.Timestamp(index).date(), float(value), kind))
    return out


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
