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
from src.data.market import earnings_soon, market_is_open, regime_risk_on  # noqa: E402
from src.data.universe import UniverseResult, load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.export.markdown_format import number as _fmt_number  # noqa: E402
from src.export.markdown_format import table as _fmt_table  # noqa: E402
from src.export.markdown_format import text as _fmt_text  # noqa: E402
from src.screener.advisor import (  # noqa: E402
    _isna,
    add_sizing,
    analysis_lookup,
    core_action,
    core_rebalance,
    is_core,
    open_r_multiple,
    pct_to_stop,
    portfolio_open_risk,
    rotation_candidates,
    satellite_action,
)
from src.screener.engine import FilterConfig, ScreenerEngine  # noqa: E402
from src.screener.exposure import look_through_exposure  # noqa: E402
from src.screener.holdings import (  # noqa: E402
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
from src.screener.strategy import StrategyConfig  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

PORTFOLIO_FILE = _REPO_ROOT / 'portfolio.txt'
POSITIONS_FILE = _REPO_ROOT / 'positions.txt'
WATCHLIST_FILE = _REPO_ROOT / 'watchlist.txt'
REPORTS_DIR = _REPO_ROOT / 'reports'
REPORT_PATH = REPORTS_DIR / 'daily_report.md'

HISTORY_PERIOD = '2y'
FUND_QUOTE_TYPES = {'ETF', 'MUTUALFUND'}
_LOGGER = get_logger('daily_report')


# --------------------------------------------------------------------------- #
# Formatting helpers (pure, no Streamlit).
# --------------------------------------------------------------------------- #
def _money(value) -> str:
    return _fmt_number(value, ',.2f', prefix='$')


def _pct(value) -> str:
    return _fmt_number(value, '.2f', scale=100, suffix='%')


def _num(value, digits: int = 2) -> str:
    return _fmt_number(value, f'.{digits}f')


def _int(value) -> str:
    return _fmt_number(value, '.0f')


def _text(value) -> str:
    return _fmt_text(value)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    return _fmt_table(headers, rows)


# --------------------------------------------------------------------------- #
# Data helpers.
# --------------------------------------------------------------------------- #
def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8') if path.exists() else ''


def _followed_tickers() -> list[str]:
    return [e.ticker for e in parse_portfolio(_read(WATCHLIST_FILE))]


def _auto_add_to_watchlist(
    recs: pd.DataFrame, held: list[str], exclude: set[str], settings: Settings
) -> list[str]:
    """Persist high-confidence recommended adds to ``watchlist.txt``.

    Names at or above ``watchlist_auto_confidence`` that are not already held,
    watched, or funds get appended so they carry forward to future runs.
    Returns the tickers added (empty when there is nothing new).
    """
    if recs.empty:
        return []
    skip = {t.upper() for t in _followed_tickers()}
    skip |= {t.upper() for t in held} | {t.upper() for t in exclude}
    added: list[str] = []
    for _, row in recs.iterrows():
        ticker = str(row['Ticker']).upper()
        conf = row.get('Confidence')
        if ticker in skip or _isna(conf) or float(conf) < settings.watchlist_auto_confidence:
            continue
        added.append(ticker)
        skip.add(ticker)
    if added:
        text = _read(WATCHLIST_FILE).rstrip('\n')
        WATCHLIST_FILE.write_text(text + '\n' + '\n'.join(added) + '\n', encoding='utf-8')
    return added


def _etf_tickers(client: YahooFinanceClient, tickers: list[str]) -> set[str]:
    if not tickers:
        return set()
    fundamentals = client.fetch_fundamentals(tickers)
    return {
        t for t, f in fundamentals.items()
        if (f.quote_type or '').upper() in FUND_QUOTE_TYPES
    }


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

    open_risk, risk_pct = portfolio_open_risk(monitor, lookup, account_value)
    lines.append(f'- Open risk (satellite stops): {_money(open_risk)} ({_pct(risk_pct)} of account)')
    headroom = max(settings.max_portfolio_risk - risk_pct, 0.0)
    lines.append(
        f'- Risk headroom: {_pct(headroom)} of {_pct(settings.max_portfolio_risk)} cap'
        + ('  — ⚠️ at cap, adds paused' if headroom <= 0 else '')
    )
    cash = account_value - total_value
    if account_value > 0:
        lines.append(f'- Cash: {_money(max(cash, 0.0))} ({_pct(max(cash, 0.0) / account_value)})')

    count = count_individual_stocks(monitor, etfs)
    cap = settings.max_individual_stocks
    flag = ' \u26a0\ufe0f over cap' if count > cap else (' (approaching cap)' if count >= cap - 2 else '')
    lines.append(f'- Individual stocks: {count} / {cap}{flag}')
    return '\n'.join(lines)


def _action_plan_section(
    monitor: pd.DataFrame,
    watch_monitor: pd.DataFrame,
    lookup: dict,
    recs: pd.DataFrame,
    account_value: float,
    settings: Settings,
    risk_on: bool = True,
    open_risk_pct: float = 0.0,
    earnings: set[str] | None = None,
) -> str:
    """Plain-language buy / trim / sell plan for today, sorted by urgency."""
    earnings = earnings or set()
    buys: list[str] = []
    trims: list[str] = []
    sells: list[str] = []

    # Holdings -> sell / trim using the same per-row action.
    for _, r in monitor.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        if is_core(r['Sleeve']):
            continue
        sizing = add_sizing(account_value, settings, a, float(r.get('Value') or 0.0), open_risk_pct)
        action = satellite_action(r, a, sizing, bool(a.get('Actionable', False)), settings)
        if action.startswith(('Exit', 'Cut')):
            sells.append(f'\U0001f534 {ticker} \u2014 {action}')
        elif action.startswith(('Trim', 'Take profit')):
            trims.append(f'\U0001f7e1 {ticker} \u2014 {action}')

    # Recommended adds -> buys (suppressed when the market regime is risk-off).
    if risk_on and recs is not None and not recs.empty:
        for _, r in recs.head(5).iterrows():
            tag = ' \u26a0\ufe0f earnings soon' if str(r['Ticker']) in earnings else ''
            buys.append(
                f"\U0001f7e2 {r['Ticker']} \u2014 {_text(r.get('Setup'))} near {_money(r.get('Entry'))} "
                f"(R/R {_num(r.get('R/R'))}, conf {_int(r.get('Confidence'))}){tag}"
            )

    if not risk_on:
        buy_text = 'paused \u2014 SPY below 200-day (risk-off regime)'
    else:
        buy_text = '; '.join(buys) if buys else 'nothing new \u2014 sit tight'
    lines = ['## Today\u2019s plan', '']
    lines.append('- **Sell/Cut**: ' + ('; '.join(sells) if sells else 'none'))
    lines.append('- **Trim/Take profit**: ' + ('; '.join(trims) if trims else 'none'))
    lines.append('- **Buy**: ' + buy_text)
    return '\n'.join(lines)


def _legend_section(settings: Settings) -> str:
    return (
        '## How to read this report\n\n'
        '- **Entry / Stop / Target / R/R** \u2014 a structural trade plan. For a name in a '
        'fresh setup these are the actual trigger levels; for every other holding they are '
        '*management* estimates \u2014 **Stop** is a trailing exit just below support, **Target** '
        'is the measured-move upside, and **Entry** is the current reference price.\n'
        '- **Max add (risk)** — a per-trade risk *ceiling* in fractional shares, '
        f'risk-budgeted at {_pct(settings.risk_per_trade)} of the account per trade and '
        f'capped so no single position exceeds {_pct(settings.max_position_weight)} of the '
        'account. It is **not a recommendation to add**: it does not account for '
        'sector/theme concentration or your single-stock cap. A dash means no room to add '
        '(already at the weight cap) or no valid level.\n'
        '- **Sleeve** \u2014 **Core** = long-term anchor (held through noise); **Satellite** = '
        'tactical position managed with the trade plan.\n'
        '- **% vs 200d** \u2014 distance above/below the 200-day average; the primary trend gauge. '
        'Negative means the long-term trend has rolled over.\n'
        '- **R now** \u2014 open gain in R-multiples ((price\u2212entry)/(entry\u2212stop)); +1 means up one '
        'unit of risk. **% to stop** is the cushion before the exit triggers.\n'
        '- **Action** \u2014 the suggested next step for that row, in plain language.'
    )


def _holdings_section(
    monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings,
    open_risk_pct: float = 0.0,
) -> str:
    """One consistent table for every holding (core first, then by weight)."""
    show_acct = has_accounts(monitor)
    headers = ['Ticker']
    if show_acct:
        headers.append('Account')
    headers += ['Sleeve', 'Shares', 'Price', '% vs 200d', 'Value', 'Weight', 'P&L %',
                'Entry', 'Stop', 'Target', 'R/R', 'R now', '% to stop', 'Max add (risk)', 'Action']
    ordered = monitor.copy()
    ordered['_core'] = ordered['Sleeve'].map(is_core)
    ordered = ordered.sort_values(
        by=['_core', 'Weight %'], ascending=[False, False], na_position='last'
    )
    rows = []
    for _, r in ordered.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        core = is_core(r['Sleeve'])
        current_value = float(r['Value']) if not _isna(r.get('Value')) else 0.0
        actionable = bool(a.get('Actionable', False))
        if core:
            add_txt = '\u2014'
            action = core_action(r)
        else:
            sizing = add_sizing(account_value, settings, a, current_value, open_risk_pct)
            action = satellite_action(r, a, sizing, actionable, settings)
            can_add = not action.startswith(('Trim', 'Exit', 'Cut', 'Take profit'))
            add_txt = (
                _num(sizing.shares, 3)
                if can_add and sizing and sizing.shares > 0
                else '\u2014'
            )
        r_now = open_r_multiple(r.get('Price'), a.get('Entry'), a.get('Stop'))
        to_stop = pct_to_stop(r.get('Price'), a.get('Stop'))
        row = [ticker]
        if show_acct:
            row.append(_text(r.get('Account')))
        row += [
            'Core' if core else 'Satellite',
            _num(r.get('Shares'), 3),
            _money(r.get('Price')),
            _pct(r.get('% vs SMA200')),
            _money(r.get('Value')),
            _pct(r.get('Weight %')),
            _pct(r.get('Unreal P&L %')),
            _money(a.get('Entry')),
            _money(a.get('Stop')),
            _money(a.get('Target')),
            _num(a.get('R/R')),
            _num(r_now, 1) if r_now is not None else '\u2014',
            _pct(to_stop),
            add_txt,
            action,
        ]
        rows.append(row)
    return '## Holdings\n\n' + _md_table(headers, rows)


def _watchlist_section(
    watch_monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings,
    open_risk_pct: float = 0.0,
) -> str:
    """Followed (unheld) names, same plan columns as Holdings for consistency."""
    headers = ['Ticker', 'Price', 'Setup', 'Conf', 'Entry', 'Stop', 'Target',
               'R/R', 'Max add (risk)', 'Action']
    rows = []
    for _, r in watch_monitor.iterrows():
        ticker = str(r['Ticker'])
        a = lookup.get(ticker, {})
        actionable = bool(a.get('Actionable', False))
        sizing = add_sizing(account_value, settings, a, 0.0, open_risk_pct)
        add_txt = _num(sizing.shares, 3) if sizing and sizing.shares > 0 else '\u2014'
        action = 'Buy candidate \u2014 setup live' if actionable else 'Watch \u2014 no setup yet'
        rows.append([
            ticker,
            _money(r.get('Price')),
            _text(a.get('Setup')),
            _int(a.get('Confidence')),
            _money(a.get('Entry')),
            _money(a.get('Stop')),
            _money(a.get('Target')),
            _num(a.get('R/R')),
            add_txt,
            action,
        ])
    return '## Watchlist\n\n' + _md_table(headers, rows)


def _recommendations_section(
    recs: pd.DataFrame,
    etfs: set,
    account_value: float,
    settings: Settings,
    current_values: dict[str, float] | None = None,
    open_risk_pct: float = 0.0,
) -> str:
    if recs is None or recs.empty:
        return (
            '## Recommended adds\n\nNo high-conviction adds today — sitting tight '
            f'(gates: confidence ≥ {_num(settings.rec_min_confidence, 0)}, '
            f'R/R ≥ {_num(settings.rec_min_reward_risk)}).'
        )
    current_values = current_values or {}
    headers = ['Ticker', 'Company', 'Setup', 'Type', 'Conf', 'R/R',
               'Entry', 'Stop', 'Target', 'Rank', 'Max add (risk)', 'Add $']
    rows = []
    for _, r in recs.iterrows():
        ticker = str(r['Ticker'])
        sizing = add_sizing(
            account_value, settings, r.to_dict(),
            current_value=current_values.get(ticker, 0.0), open_risk_pct=open_risk_pct,
        )
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
            _num(sizing.shares, 3) if sizing else '\u2014',
            _money(sizing.dollars) if sizing else '\u2014',
        ])
    return '## Recommended adds\n\n' + _md_table(headers, rows)


def _company_names(analysis: pd.DataFrame | None) -> dict[str, str]:
    """Map ticker -> company name from an analysis frame, for labelling direct holdings."""
    names: dict[str, str] = {}
    if analysis is None or analysis.empty or 'Company Name' not in analysis.columns:
        return names
    for _, r in analysis.iterrows():
        ticker = str(r['Ticker'])
        label = r.get('Company Name')
        if label and not _isna(label):
            names[ticker] = str(label)
    return names


def _build_exposure(
    client: YahooFinanceClient,
    monitor: pd.DataFrame,
    etfs: set,
    account_value: float,
    analysis: pd.DataFrame | None = None,
) -> tuple[list, float]:
    """Look-through exposure: direct holdings + fund top-holdings."""
    empty: tuple[list, float] = ([], 0.0)
    if monitor is None or monitor.empty or account_value <= 0:
        return empty
    held_tickers = [str(t) for t in monitor['Ticker']]
    fund_tickers = {t for t in held_tickers if t in etfs}
    fund_holdings = client.fetch_fund_holdings(sorted(fund_tickers))
    holdings = [
        (str(r['Ticker']), float(r['Value']))
        for _, r in monitor.iterrows()
        if not _isna(r.get('Value'))
    ]
    name_lookup = _company_names(analysis)
    exposures, tail_value = look_through_exposure(
        holdings, fund_holdings, fund_tickers, account_value, name_lookup
    )
    if not exposures:
        return empty
    return exposures, tail_value


def _exposure_section(
    exposures: list, tail_value: float, account_value: float, top_n: int = 15
) -> str:
    if not exposures:
        return ''
    lines = [
        '## Look-through exposure',
        '',
        '_True economic exposure: direct holdings combined with each fund\u2019s top-10 '
        'holdings (Yahoo). The untracked remainder of broad funds is grouped as '
        '\u201cOther / diversified\u201d rather than attributed to any name._',
        '',
    ]
    headers = ['Symbol', 'Name', 'Direct', 'Via funds', 'Total', '% acct']
    rows = []
    for e in exposures[:top_n]:
        rows.append([
            e.symbol,
            _text(e.name),
            _money(e.direct_value) if e.direct_value else '\u2014',
            _money(e.fund_value) if e.fund_value else '\u2014',
            _money(e.total_value),
            _pct(e.weight),
        ])
    lines.append(_md_table(headers, rows))
    if tail_value > 0:
        lines.append('')
        lines.append(
            f'- Other / diversified (fund tail): {_money(tail_value)} '
            f'({_pct(tail_value / account_value if account_value > 0 else 0)})'
        )
    return '\n'.join(lines)


def _concentration_section(
    monitor: pd.DataFrame, analysis: pd.DataFrame, etfs: set, settings: Settings
) -> str:
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
    alloc = allocation_summary(monitor, settings.core_allocation_min, settings.core_allocation_max)
    if alloc is not None and not alloc.within_band:
        _, rebalance_note = core_rebalance(alloc)
        if rebalance_note:
            lines.append(f'- Rebalance: {rebalance_note}')
    if has_accounts(monitor):
        lines.append('')
        lines.append('### By account')
        for label, sub in account_groups(monitor):
            held = sub['Value'].dropna()
            pnl = sub['Unreal P&L $'].dropna()
            value = _money(float(held.sum())) if not held.empty else '\u2014'
            pnl_txt = _money(float(pnl.sum())) if not pnl.empty else '\u2014'
            lines.append(f'- {label}: {len(sub)} position(s), value {value}, P&L {pnl_txt}')
    rotation = rotation_candidates(monitor, analysis, etfs)
    if not rotation.empty:
        lines.append('')
        lines.append('### Rotation candidates (weakest first)')
        has_acct = 'Account' in rotation.columns
        headers = (
            ['Ticker']
            + (['Account'] if has_acct else [])
            + ['Trend', 'RS', 'Weight %', 'Value', 'Unreal P&L %']
        )
        rows = [
            [str(r['Ticker'])]
            + ([_text(r.get('Account'))] if has_acct else [])
            + [
                _pct(r.get('Trend')),
                _pct(r.get('RS')),
                _pct(r.get('Weight %')),
                _money(r.get('Value')),
                _pct(r.get('Unreal P&L %')),
            ]
            for _, r in rotation.iterrows()
        ]
        lines.append(_md_table(headers, rows))
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
    exposure: tuple[list, float] = ([], 0.0),
    risk_on: bool = True,
    earnings: set[str] | None = None,
) -> str:
    lookup = analysis_lookup(analysis)
    context = _market_context(analysis, recs)
    exposures, tail_value = exposure
    _, open_risk_pct = portfolio_open_risk(monitor, lookup, account_value)
    held_values = {
        str(r['Ticker']): float(r['Value'])
        for _, r in monitor.iterrows()
        if not _isna(r.get('Value'))
    }
    sections = [
        f'# Daily Position Report\n\n_Generated {generated_at}. Market context: {context}. '
        f'Regime: {"Risk-On" if risk_on else "Risk-Off"}._',
        _legend_section(settings),
        _snapshot_section(monitor, lookup, etfs, account_value, settings),
        _action_plan_section(
            monitor, watch_monitor, lookup, recs, account_value, settings, risk_on, open_risk_pct,
            earnings,
        ),
        _holdings_section(monitor, lookup, account_value, settings, open_risk_pct),
        _watchlist_section(watch_monitor, lookup, account_value, settings, open_risk_pct),
        _recommendations_section(recs, rec_etfs, account_value, settings, held_values, open_risk_pct),
        _concentration_section(monitor, analysis, etfs, settings),
    ]
    exposure_section = _exposure_section(exposures, tail_value, account_value)
    if exposure_section:
        sections.append(exposure_section)
    return '\n\n'.join(sections) + '\n'


def _build_unavailable(generated_at: str, reason: str) -> str:
    return (
        '# Daily Position Report\n\n'
        f'_Generated {generated_at}._\n\n'
        f'Report unavailable: market data could not be retrieved ({reason}). '
        'Try again later.\n'
    )


def _screen_recommendations(engine, cache, watch: list[str], gate_config: FilterConfig):
    """Rank S&P 500 + watchlist adds, best first; empty frame if none qualify."""
    universe_full = load_sp500_universe(cache)
    tickers = list(dict.fromkeys([*universe_full.tickers, *watch]))
    universe = UniverseResult(tickers=tickers, companies=dict(universe_full.companies))
    recs = engine.screen(universe, config=gate_config)
    if not recs.empty:
        recs = recs.sort_values('Rank Score', ascending=False).reset_index(drop=True)
    return recs


def _generate_report(client, engine, cache, settings: Settings, generated_at: str) -> tuple[str, str]:
    """Assemble the report markdown plus a one-line status; pure of file writes."""
    positions_text = _read(POSITIONS_FILE)
    merged = merge_holdings(parse_portfolio(_read(PORTFOLIO_FILE)), parse_positions(positions_text))
    if not merged:
        return (
            _build_unavailable(generated_at, 'no holdings in portfolio.txt/positions.txt'),
            'No holdings found; wrote placeholder report.',
        )

    held = [e.ticker for e in merged]
    watch = [t for t in _followed_tickers() if t not in set(held)]
    universe = [*held, *watch]
    # Keep the portfolio + watchlist live intraday; the broad S&P universe used
    # for recommendations stays on the normal cache to avoid Yahoo throttling.
    refresh = universe if market_is_open() else None
    history = client.fetch_history(universe, period=HISTORY_PERIOD, refresh_tickers=refresh)
    monitor = build_monitor(merged, history, settings)
    watch_monitor = build_monitor([PositionEntry(t, sleeve=SATELLITE) for t in watch], history, settings)
    account_value = parse_account_value(positions_text) or float(monitor['Value'].dropna().sum())

    gate_config = FilterConfig(
        min_confidence=settings.rec_min_confidence,
        min_reward_risk=settings.rec_min_reward_risk,
        min_avg_volume=settings.min_avg_volume,
    )
    analysis = engine.analyze(UniverseResult(tickers=universe, companies={}), config=gate_config)
    etfs = _etf_tickers(client, universe)
    recs = _screen_recommendations(engine, cache, watch, gate_config)
    rec_etfs = _etf_tickers(client, list(recs['Ticker'])) if not recs.empty else set()
    auto_added = _auto_add_to_watchlist(recs, held, rec_etfs, settings)

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
        exposure=_build_exposure(client, monitor, etfs, account_value, analysis),
        risk_on=regime_risk_on(client, settings),
        earnings=earnings_soon(client, held, settings.earnings_blackout_days),
    )
    status = (f'{len(monitor)} holding(s), {len(watch_monitor)} watch, '
              f'{len(recs)} recommendation(s).')
    if auto_added:
        status += f' Auto-added to watchlist: {", ".join(auto_added)}.'
    return report, status


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
        report, status = _generate_report(client, engine, cache, settings, generated_at)
        REPORT_PATH.write_text(report, encoding='utf-8')
        print(f'Wrote {REPORT_PATH.relative_to(_REPO_ROOT)}: {status}')
        return 0
    except Exception as exc:  # network / data feed problems must not crash the run
        REPORT_PATH.write_text(_build_unavailable(generated_at, type(exc).__name__), encoding='utf-8')
        _LOGGER.exception('Report generation failed: %s', type(exc).__name__)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
