"""Generate a local daily position-management report.

Headless companion to the Streamlit app (no Streamlit import) so it can be run
on a schedule (e.g. Windows Task Scheduler). It merges your committed
composition (``portfolio.txt``) with your private sizes (``positions.txt``),
refreshes market data, and writes a single Markdown snapshot to
``reports/daily_report.md`` -- overwritten on every run, so only the latest
report is kept.

Run from the repo root:
    python scripts/daily_report.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.config import Settings, load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.universe import UniverseResult, load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.screener.engine import FilterConfig, ScreenerEngine  # noqa: E402
from src.screener.holdings import (  # noqa: E402
    CORE,
    SATELLITE,
    PositionEntry,
    account_groups,
    allocation_summary,
    build_monitor,
    concentration_summary,
    count_individual_stocks,
    has_accounts,
    merge_holdings,
    parse_account_value,
    parse_portfolio,
    parse_positions,
)
from src.screener.portfolio import PortfolioConfig  # noqa: E402
from src.screener.sizing import suggest_add_size  # noqa: E402
from src.screener.strategy import StrategyConfig  # noqa: E402

PORTFOLIO_FILE = _REPO_ROOT / 'portfolio.txt'
POSITIONS_FILE = _REPO_ROOT / 'positions.txt'
WATCHLIST_FILE = _REPO_ROOT / 'watchlist.txt'
REPORTS_DIR = _REPO_ROOT / 'reports'
REPORT_PATH = REPORTS_DIR / 'daily_report.md'

HISTORY_PERIOD = '2y'
FUND_QUOTE_TYPES = {'ETF', 'MUTUALFUND'}


# --------------------------------------------------------------------------- #
# Formatting helpers (pure, no Streamlit).
# --------------------------------------------------------------------------- #
def _isna(value) -> bool:
    try:
        return value is None or pd.isna(value)
    except (TypeError, ValueError):
        return value is None


def _money(value) -> str:
    return '\u2014' if _isna(value) else f'${float(value):,.2f}'


def _pct(value) -> str:
    return '\u2014' if _isna(value) else f'{float(value) * 100:.2f}%'


def _num(value, digits: int = 2) -> str:
    return '\u2014' if _isna(value) else f'{float(value):.{digits}f}'


def _int(value) -> str:
    return '\u2014' if _isna(value) else f'{int(round(float(value)))}'


def _text(value) -> str:
    return '\u2014' if value is None or value == '' else str(value)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '_None._'
    head = '| ' + ' | '.join(headers) + ' |'
    sep = '| ' + ' | '.join(['---'] * len(headers)) + ' |'
    body = ['| ' + ' | '.join(row) + ' |' for row in rows]
    return '\n'.join([head, sep, *body])


# --------------------------------------------------------------------------- #
# Data helpers.
# --------------------------------------------------------------------------- #
def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def _watchlist_tickers() -> list[str]:
    return [e.ticker for e in parse_portfolio(_read(WATCHLIST_FILE))]


def _etf_tickers(client: YahooFinanceClient, tickers: list[str]) -> set[str]:
    if not tickers:
        return set()
    fundamentals = client.fetch_fundamentals(tickers)
    return {
        t for t, f in fundamentals.items()
        if (f.quote_type or '').upper() in FUND_QUOTE_TYPES
    }


def _analysis_lookup(analysis: pd.DataFrame) -> dict[str, dict]:
    if analysis is None or analysis.empty:
        return {}
    return {str(row['Ticker']): row.to_dict() for _, row in analysis.iterrows()}


def _is_core(sleeve) -> bool:
    return str(sleeve).lower() == CORE


def _add_sizing(account_value: float, settings: Settings, row: dict, current_value: float):
    entry = row.get('Entry')
    stop = row.get('Stop')
    if account_value <= 0 or _isna(entry) or _isna(stop):
        return None
    return suggest_add_size(
        account_value,
        settings.risk_per_trade,
        float(entry),
        float(stop),
        current_value=float(current_value),
        max_position_weight=settings.max_position_weight,
    )


def _satellite_action(monitor_row, analysis_row: dict, sizing, actionable: bool) -> str:
    price = monitor_row.get('Price')
    stop = analysis_row.get('Stop')
    vs_sma200 = monitor_row.get('% vs SMA200')
    vs_ema20 = monitor_row.get('% vs EMA20')
    if not _isna(price) and not _isna(stop) and float(price) < float(stop):
        return 'Stop breached'
    if not _isna(vs_sma200) and float(vs_sma200) < 0:
        return 'Trend broke'
    if actionable and sizing is not None and sizing.shares > 0:
        entry = analysis_row.get('Entry')
        return f'Add near {_money(entry)}' if not _isna(entry) else 'Add'
    if not _isna(vs_ema20) and float(vs_ema20) > 0.10:
        return 'Extended'
    return 'Hold'


def _market_context(*frames: pd.DataFrame) -> str:
    for frame in frames:
        if frame is not None and not frame.empty and 'Market Context' in frame.columns:
            value = frame['Market Context'].iloc[0]
            if value:
                return str(value)
    return 'Unknown'


# --------------------------------------------------------------------------- #
# Report sections.
# --------------------------------------------------------------------------- #
def _snapshot_section(
    monitor: pd.DataFrame,
    lookup: dict,
    etfs: set,
    account_value: float,
    settings: Settings,
) -> str:
    lines: list[str] = ['## Snapshot', '']
    held_value = monitor['Value'].dropna()
    total_value = float(held_value.sum()) if not held_value.empty else 0.0
    pnl = monitor['Unreal P&L $'].dropna()
    lines.append(f'- Account value: {_money(account_value)}')
    lines.append(f'- Position value: {_money(total_value)}')
    if not pnl.empty:
        lines.append(f'- Unrealized P&L: {_money(float(pnl.sum()))}')

    alloc = allocation_summary(monitor, settings.core_allocation_min, settings.core_allocation_max)
    if alloc is not None:
        lines.append(
            f'- Core allocation: {_pct(alloc.core_pct)} (target '
            f'{_pct(alloc.target_min)}\u2013{_pct(alloc.target_max)}) \u2014 {alloc.label}'
        )
        lines.append(f'- Satellite allocation: {_pct(alloc.satellite_pct)}')

    open_risk = 0.0
    for _, r in monitor.iterrows():
        if _is_core(r['Sleeve']):
            continue
        shares, price = r.get('Shares'), r.get('Price')
        stop = lookup.get(str(r['Ticker']), {}).get('Stop')
        if not _isna(shares) and not _isna(price) and not _isna(stop) and float(price) > float(stop):
            open_risk += float(shares) * (float(price) - float(stop))
    risk_pct = open_risk / account_value if account_value > 0 else None
    lines.append(f'- Open risk (satellite stops): {_money(open_risk)} ({_pct(risk_pct)} of account)')

    count = count_individual_stocks(monitor, etfs)
    cap = settings.max_individual_stocks
    flag = ' \u26a0\ufe0f over cap' if count > cap else (' (approaching cap)' if count >= cap - 2 else '')
    lines.append(f'- Individual stocks: {count} / {cap}{flag}')
    return '\n'.join(lines)


def _core_section(monitor: pd.DataFrame) -> str:
    core = monitor[monitor['Sleeve'].map(_is_core)]
    show_acct = has_accounts(monitor)
    headers = ['Ticker']
    if show_acct:
        headers.append('Account')
    headers += ['Price', '% vs SMA50', '% vs SMA200', 'Trend', 'Signal', 'Value', 'Weight', 'P&L %']
    rows = []
    for _, r in core.iterrows():
        row = [str(r['Ticker'])]
        if show_acct:
            row.append(_text(r.get('Account')))
        row += [
            _money(r.get('Price')),
            _pct(r.get('% vs SMA50')),
            _pct(r.get('% vs SMA200')),
            _text(r.get('Trend')),
            _text(r.get('Signal')),
            _money(r.get('Value')),
            _pct(r.get('Weight %')),
            _pct(r.get('Unreal P&L %')),
        ]
        rows.append(row)
    return '## Core holdings\n\n' + _md_table(headers, rows)


def _satellite_section(
    monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings
) -> str:
    sat = monitor[~monitor['Sleeve'].map(_is_core)]
    show_acct = has_accounts(monitor)
    headers = ['Ticker']
    if show_acct:
        headers.append('Account')
    headers += ['Price', 'Entry', 'Stop', 'Target', 'R/R', 'Value', 'Weight',
                'P&L %', 'Add Shares', 'Add $', 'Action']
    rows = []
    for _, r in sat.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        current_value = float(r['Value']) if not _isna(r.get('Value')) else 0.0
        actionable = bool(a.get('Actionable', False))
        sizing = _add_sizing(account_value, settings, a, current_value)
        row = [ticker]
        if show_acct:
            row.append(_text(r.get('Account')))
        row += [
            _money(r.get('Price')),
            _money(a.get('Entry')),
            _money(a.get('Stop')),
            _money(a.get('Target')),
            _num(a.get('R/R')),
            _money(r.get('Value')),
            _pct(r.get('Weight %')),
            _pct(r.get('Unreal P&L %')),
            _int(sizing.shares) if sizing else '\u2014',
            _money(sizing.dollars) if sizing else '\u2014',
            _satellite_action(r, a, sizing, actionable),
        ]
        rows.append(row)
    return '## Satellite holdings\n\n' + _md_table(headers, rows)


def _watchlist_section(
    watch_monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings
) -> str:
    headers = ['Ticker', 'Price', 'Entry', 'Stop', 'Target', 'R/R',
               'Confidence', 'Add Shares', 'Add $', 'Hint']
    rows = []
    for _, r in watch_monitor.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        actionable = bool(a.get('Actionable', False))
        sizing = _add_sizing(account_value, settings, a, current_value=0.0)
        rows.append([
            ticker,
            _money(r.get('Price')),
            _money(a.get('Entry')),
            _money(a.get('Stop')),
            _money(a.get('Target')),
            _num(a.get('R/R')),
            _int(a.get('Confidence')),
            _int(sizing.shares) if sizing else '\u2014',
            _money(sizing.dollars) if sizing else '\u2014',
            'Actionable' if actionable else 'Watch',
        ])
    return '## Watchlist\n\n' + _md_table(headers, rows)


def _recommendations_section(
    recs: pd.DataFrame, etfs: set, account_value: float, settings: Settings
) -> str:
    if recs is None or recs.empty:
        return (
            '## Recommended adds\n\nNo high-conviction adds today \u2014 sitting tight '
            f'(gates: confidence \u2265 {_num(settings.rec_min_confidence, 0)}, '
            f'R/R \u2265 {_num(settings.rec_min_reward_risk)}).'
        )
    headers = ['Ticker', 'Company', 'Setup', 'Type', 'Confidence', 'R/R',
               'Entry', 'Stop', 'Target', 'Rank', 'Add Shares', 'Add $']
    rows = []
    for _, r in recs.iterrows():
        ticker = str(r['Ticker'])
        sizing = _add_sizing(account_value, settings, r.to_dict(), current_value=0.0)
        rows.append([
            ticker,
            _text(r.get('Company Name')),
            _text(r.get('Setup')),
            'ETF' if ticker in etfs else 'Stock',
            _int(r.get('Confidence')),
            _num(r.get('R/R')),
            _money(r.get('Entry')),
            _money(r.get('Stop')),
            _money(r.get('Target')),
            _num(r.get('Rank Score')),
            _int(sizing.shares) if sizing else '\u2014',
            _money(sizing.dollars) if sizing else '\u2014',
        ])
    return '## Recommended adds\n\n' + _md_table(headers, rows)


def _concentration_section(monitor: pd.DataFrame) -> str:
    lines = ['## Risk & concentration', '']
    stats = concentration_summary(monitor)
    if stats is not None:
        lines.append(f'- Positions: {stats.positions}')
        lines.append(
            f'- Largest: {stats.largest_ticker} at {_pct(stats.largest_weight)}'
        )
        lines.append(
            f'- Top {min(stats.positions, 5)} weight: {_pct(stats.top_n_weight)}'
        )
        lines.append(f'- Effective holdings: {stats.effective_positions:.1f}')
        lines.append(f'- Diversification: {stats.label} (HHI {stats.hhi:.2f})')
    if has_accounts(monitor):
        lines.append('')
        lines.append('### By account')
        for label, sub in account_groups(monitor):
            held = sub['Value'].dropna()
            pnl = sub['Unreal P&L $'].dropna()
            value = _money(float(held.sum())) if not held.empty else '\u2014'
            pnl_txt = _money(float(pnl.sum())) if not pnl.empty else '\u2014'
            lines.append(f'- {label}: {len(sub)} position(s), value {value}, P&L {pnl_txt}')
    return '\n'.join(lines)


def _build_report(
    *,
    generated_at: str,
    monitor: pd.DataFrame,
    watch_monitor: pd.DataFrame,
    analysis: pd.DataFrame,
    recs: pd.DataFrame,
    etfs: set,
    rec_etfs: set,
    account_value: float,
    settings: Settings,
) -> str:
    lookup = _analysis_lookup(analysis)
    context = _market_context(analysis, recs)
    sections = [
        f'# Daily Position Report\n\n_Generated {generated_at}. Market context: {context}._',
        _snapshot_section(monitor, lookup, etfs, account_value, settings),
        _core_section(monitor),
        _satellite_section(monitor, lookup, account_value, settings),
        _watchlist_section(watch_monitor, lookup, account_value, settings),
        _recommendations_section(recs, rec_etfs, account_value, settings),
        _concentration_section(monitor),
    ]
    return '\n\n'.join(sections) + '\n'


def _build_unavailable(generated_at: str, reason: str) -> str:
    return (
        '# Daily Position Report\n\n'
        f'_Generated {generated_at}._\n\n'
        f'Report unavailable: market data could not be retrieved ({reason}). '
        'Try again later.\n'
    )


def main() -> int:
    settings = load_settings()
    generated_at = datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')
    cache = SQLiteCache(settings.cache_dir)
    client = YahooFinanceClient(settings=settings, cache=cache)
    engine = ScreenerEngine(
        client=client,
        strategy=StrategyConfig.from_settings(settings),
        portfolio=PortfolioConfig.from_settings(settings),
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        portfolio_entries = parse_portfolio(_read(PORTFOLIO_FILE))
        positions_text = _read(POSITIONS_FILE)
        position_entries = parse_positions(positions_text)
        merged = merge_holdings(portfolio_entries, position_entries)
        if not merged:
            report = _build_unavailable(generated_at, 'no holdings in portfolio.txt/positions.txt')
            REPORT_PATH.write_text(report, encoding='utf-8')
            print('No holdings found; wrote placeholder report.')
            return 0

        held = [e.ticker for e in merged]
        held_set = set(held)
        watch = [t for t in _watchlist_tickers() if t not in held_set]
        account_value = parse_account_value(positions_text) or 0.0

        history = client.fetch_history([*held, *watch], period=HISTORY_PERIOD)
        monitor = build_monitor(merged, history, settings)
        watch_entries = [PositionEntry(t, sleeve=SATELLITE) for t in watch]
        watch_monitor = build_monitor(watch_entries, history, settings)

        if account_value <= 0:
            account_value = float(monitor['Value'].dropna().sum())

        held_universe = UniverseResult(tickers=[*held, *watch], companies={})
        analysis = engine.analyze(held_universe, config=FilterConfig())
        etfs = _etf_tickers(client, [*held, *watch])

        rec_universe_full = load_sp500_universe(cache)
        rec_tickers = list(dict.fromkeys([*rec_universe_full.tickers, *watch]))
        rec_universe = UniverseResult(
            tickers=rec_tickers, companies=dict(rec_universe_full.companies)
        )
        rec_config = FilterConfig(
            min_confidence=settings.rec_min_confidence,
            min_reward_risk=settings.rec_min_reward_risk,
            min_avg_volume=settings.min_avg_volume,
        )
        recs = engine.screen(rec_universe, config=rec_config)
        if not recs.empty:
            recs = recs[~recs['Ticker'].isin(held_set)]
            recs = recs.sort_values('Rank Score', ascending=False).reset_index(drop=True)
        rec_etfs = _etf_tickers(client, list(recs['Ticker'])) if not recs.empty else set()

        report = _build_report(
            generated_at=generated_at,
            monitor=monitor,
            watch_monitor=watch_monitor,
            analysis=analysis,
            recs=recs,
            etfs=etfs,
            rec_etfs=rec_etfs,
            account_value=account_value,
            settings=settings,
        )
        REPORT_PATH.write_text(report, encoding='utf-8')
        print(
            f'Wrote {REPORT_PATH.relative_to(_REPO_ROOT)}: '
            f'{len(monitor)} holding(s), {len(watch_monitor)} watch, {len(recs)} recommendation(s).'
        )
        return 0
    except Exception as exc:  # network / data feed problems must not crash the run
        report = _build_unavailable(generated_at, type(exc).__name__)
        REPORT_PATH.write_text(report, encoding='utf-8')
        print(f'Report unavailable: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
