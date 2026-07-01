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

import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.config import Settings, load_settings  # noqa: E402
from src.data.cache import SQLiteCache  # noqa: E402
from src.data.market import earnings_soon, regime_risk_on  # noqa: E402
from src.data.universe import UniverseResult, load_sp500_universe  # noqa: E402
from src.data.yahoo_client import YahooFinanceClient  # noqa: E402
from src.export.markdown_format import number as _fmt_number  # noqa: E402
from src.export.markdown_format import table as _fmt_table  # noqa: E402
from src.export.markdown_format import text as _fmt_text  # noqa: E402
from src.screener.advisor import (  # noqa: E402
    SCALE_2R,
    SCALE_EXTENDED,
    _isna,
    active_scale_rank,
    add_sizing,
    analysis_lookup,
    chandelier_trail,
    confirmation_add,
    core_action,
    core_rebalance,
    extended_price,
    is_core,
    open_r_multiple,
    pct_to_stop,
    portfolio_open_risk,
    r_multiple_price,
    rotation_candidates,
    satellite_action,
    suggested_add,
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
    parse_cash,
    parse_portfolio,
    parse_positions,
)
from src.screener.income import (  # noqa: E402
    IncomeEvent,
    collect_income,
    income_by_account,
    load_ledger,
    save_ledger,
)
from src.screener.portfolio import PortfolioConfig  # noqa: E402
from src.screener.scaleout import (  # noqa: E402
    load_scaleout_ledger,
    save_scaleout_ledger,
    scaleout_key,
    update_scaleout_ledger,
)
from src.screener.strategy import StrategyConfig  # noqa: E402
from src.utils.files import read_text_or_empty  # noqa: E402
from src.utils.logger import get_logger  # noqa: E402

PORTFOLIO_FILE = _REPO_ROOT / 'portfolio.txt'
POSITIONS_FILE = _REPO_ROOT / 'positions.txt'
WATCHLIST_FILE = _REPO_ROOT / 'watchlist.txt'
REPORTS_DIR = _REPO_ROOT / 'reports'
REPORT_PATH = REPORTS_DIR / 'daily_report.md'
INCOME_LEDGER_PATH = REPORTS_DIR / '.income_ledger.json'
SCALEOUT_LEDGER_PATH = REPORTS_DIR / '.scaleout_ledger.json'

HISTORY_PERIOD = '2y'
# Same-day reruns only re-pull this short tail; the 2y window stays cached.
INTRADAY_TAIL_PERIOD = '5d'
FUND_QUOTE_TYPES = {'ETF', 'MUTUALFUND'}
_LOGGER = get_logger('daily_report')

# Traffic-light status glyphs. Named because raw emoji are hard to tell apart in
# source, and the colour carries meaning (health / urgency) at each call site.
STATUS_RED = '\U0001f534'
STATUS_AMBER = '\U0001f7e1'
STATUS_GREEN = '\U0001f7e2'
STATUS_BLUE = '\U0001f535'
DASH = '\u2014'  # placeholder for a missing / not-applicable table cell


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


def _escape_dollars(text: str) -> str:
    r"""Escape ``$`` as ``\$`` so prose with money is not parsed as KaTeX math.

    Markdown renderers (GitHub, VS Code) treat a pair of ``$`` on one line as a
    math span, which mangles lines that quote two or more dollar amounts. Tables
    are left untouched (their cells render fine); only free-text sections use it.
    """
    return text.replace('$', r'\$')


def _md_table(headers: list[str], rows: list[list[str]], *, align: list[str] | None = None) -> str:
    """Render a Markdown table, right-aligning numeric columns for readability.

    Alignment is auto-detected per column (a column whose every non-placeholder
    cell looks like a number/money/percent is right-aligned) unless an explicit
    ``align`` list of ``'left'``/``'right'`` is supplied.
    """
    if not rows:
        return _fmt_table(headers, rows)
    aligns = align or _column_alignments(headers, rows)
    divider = ['---:' if a == 'right' else '---' for a in aligns]
    head = '| ' + ' | '.join(headers) + ' |'
    sep = '| ' + ' | '.join(divider) + ' |'
    body = ['| ' + ' | '.join(row) + ' |' for row in rows]
    return '\n'.join([head, sep, *body])


_NUMERIC_CELL = re.compile(r'^[-+]?\$?\d[\d,]*(\.\d+)?%?$')
_NEUTRAL_CELLS = {'', DASH, '-'}


def _column_alignments(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Right-align a column when all its meaningful cells are numeric/money/percent."""
    aligns: list[str] = []
    for col in range(len(headers)):
        cells = [row[col].strip() for row in rows if col < len(row)]
        meaningful = [c for c in cells if c not in _NEUTRAL_CELLS]
        numeric = bool(meaningful) and all(_NUMERIC_CELL.match(c) for c in meaningful)
        aligns.append('right' if numeric else 'left')
    return aligns


def _status_dot(row, action: str) -> str:
    """Traffic-light health for a holding row, present-state (trend + action)."""
    vs200 = row.get('% vs SMA200')
    if action.startswith(('Exit', 'Cut')) or (not _isna(vs200) and float(vs200) < 0):
        return STATUS_RED  # trend broken / exit
    if action.startswith(('Trim', 'Take profit', 'Review')) or 'extended' in action.lower():
        return STATUS_AMBER  # take-profit / caution
    return STATUS_GREEN  # healthy / hold / add / let-run


# --------------------------------------------------------------------------- #
# Data helpers.
# --------------------------------------------------------------------------- #
def _followed_tickers() -> list[str]:
    return [e.ticker for e in parse_portfolio(read_text_or_empty(WATCHLIST_FILE))]


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
        text = read_text_or_empty(WATCHLIST_FILE).rstrip('\n')
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


def _positive(value) -> float | None:
    """Coerce ``value`` to a positive float, or ``None`` when missing/non-positive."""
    if _isna(value):
        return None
    number = float(value)
    return number if number > 0 else None


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
    held_value = monitor['Value'].dropna()
    total_value = float(held_value.sum()) if not held_value.empty else 0.0
    pnl = monitor['Unreal P&L $'].dropna()
    cash = account_value - total_value

    metrics: list[list[str]] = [
        ['Account value', _money(account_value)],
        ['Position value', _money(total_value)],
    ]
    if not pnl.empty:
        metrics.append(['Unrealized P&L', _money(float(pnl.sum()))])
    if account_value > 0:
        metrics.append([
            'Cash', f'{_money(max(cash, 0.0))} ({_pct(max(cash, 0.0) / account_value)})'
        ])
    count = count_individual_stocks(monitor, etfs)
    cap = settings.max_individual_stocks
    flag = ' ⚠️ over cap' if count > cap else (' (near cap)' if count >= cap - 2 else '')
    metrics.append(['Individual stocks', f'{count} / {cap}{flag}'])

    alloc = allocation_summary(monitor, settings.core_allocation_min, settings.core_allocation_max)
    if alloc is not None:
        metrics.append([
            'Core allocation',
            f'{_pct(alloc.core_pct)} of {_pct(alloc.target_min)}–'
            f'{_pct(alloc.target_max)} target ({alloc.label})',
        ])

    open_risk, risk_pct = portfolio_open_risk(monitor, lookup, account_value)
    cap_pct = settings.max_portfolio_risk
    risk_value = f'{_pct(risk_pct)} of {_pct(cap_pct)} cap ({_money(open_risk)} in stops)'
    if risk_pct >= cap_pct:
        risk_value += ' — ⚠️ at cap, adds paused'
    metrics.append(['Risk budget', risk_value])

    lines: list[str] = ['## Snapshot', '']
    lines.append(_md_table(['Metric', 'Value'], metrics, align=['left', 'right']))
    return '\n'.join(lines)


def _nearest_scaleout(monitor_row, analysis_row: dict, settings: Settings):
    """Closest unreached scale-out level within the alert band, or ``None``.

    Returns ``(label, price, sell_shares, sell_dollars, gap_pct)`` for the nearer
    of the +2R and 'extended' levels when price sits within
    ``settings.scaleout_alert_pct`` below it. Levels already reached are skipped
    (those become live ``Take profit`` actions instead).
    """
    price = _positive(monitor_row.get('Price'))
    shares = _positive(monitor_row.get('Shares'))
    if price is None or shares is None:
        return None
    levels = [
        ('+2R', r_multiple_price(analysis_row.get('Entry'), analysis_row.get('Stop'), 2.0)),
        ('extended', extended_price(monitor_row.get('EMA20'), settings)),
    ]
    upcoming = [
        (lbl, float(lvl)) for lbl, lvl in levels
        if lvl is not None and not _isna(lvl) and float(lvl) > price
    ]
    if not upcoming:
        return None
    lbl, level = min(upcoming, key=lambda kv: kv[1])
    gap = (level - price) / price
    if gap > settings.scaleout_alert_pct:
        return None
    third = shares / 3.0
    return lbl, level, third, third * level, gap


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
    cash: float | None = None,
    harvested: dict[str, int] | None = None,
) -> str:
    """Plain-language buy / trim / sell plan for today, sorted by urgency."""
    earnings = earnings or set()
    harvested = harvested or {}
    show_acct = has_accounts(monitor)
    buys: list[str] = []
    trims: list[str] = []
    sells: list[str] = []
    watches: list[str] = []

    # Holdings -> sell / trim using the same per-row action.
    for _, row in monitor.iterrows():
        ticker = str(row['Ticker'])
        plan = lookup.get(ticker, {})
        if is_core(row['Sleeve']):
            continue
        sizing = add_sizing(account_value, settings, plan, float(row.get('Value') or 0.0), open_risk_pct)
        rank = harvested.get(scaleout_key(row.get('Account'), ticker), 0)
        action = satellite_action(row, plan, sizing, bool(plan.get('Actionable', False)), settings, rank)
        label = f'{ticker} ({_text(row.get("Account"))})' if show_acct and row.get('Account') else ticker
        if action.startswith(('Exit', 'Cut')):
            sells.append(f'{STATUS_RED} {label} — {action}')
            continue
        if action.startswith(('Trim', 'Take profit')):
            trims.append(f'{STATUS_AMBER} {label} — {action}')
            continue
        near = _nearest_scaleout(row, plan, settings)
        if near:
            lvl_label, level, sell_sh, sell_amt, gap = near
            watches.append(
                f'{STATUS_BLUE} {label} — approaching {lvl_label} scale-out at '
                f'{_money(level)} ({_pct(gap)} away), sell ⅓ ≈ {_money(sell_amt)} '
                f'({_num(sell_sh, 3)} sh)'
            )

    # Recommended adds -> buys (suppressed when the market regime is risk-off).
    if risk_on and recs is not None and not recs.empty:
        for _, row in recs.head(5).iterrows():
            tag = ' ⚠️ earnings soon' if str(row['Ticker']) in earnings else ''
            sizing = add_sizing(
                account_value, settings, row.to_dict(), 0.0, open_risk_pct, cash_available=cash,
            )
            sugg = suggested_add(sizing, settings)
            conf = confirmation_add(sizing, settings, row.get('Entry'), row.get('Stop'))
            if sugg and sizing:
                size_txt = f", add {_num(sugg[0], 3)} sh now ≈ {_money(sugg[1])}"
                if conf:
                    size_txt += (
                        f"; add {_num(conf[0], 3)} more at {_money(conf[1])} "
                        f"(+{_num(settings.suggested_add_trigger_r, 1)}R), stop→breakeven"
                    )
                else:
                    size_txt += f" (max {_num(sizing.shares, 3)})"
            else:
                size_txt = ''
            buys.append(
                f"{STATUS_GREEN} {row['Ticker']} — {_text(row.get('Setup'))} near {_money(row.get('Entry'))} "
                f"(R/R {_num(row.get('R/R'))}, conf {_int(row.get('Confidence'))}{tag}{size_txt})"
            )

    if not risk_on:
        buy_text = 'paused — SPY below 200-day (risk-off regime)'
    elif buys and cash is not None and cash <= 0:
        buy_text = 'no cash available — adds require freeing capital first'
    else:
        buy_text = '' if buys else 'nothing new — sit tight'

    def _block(title: str, items: list[str], inline: str = '') -> str:
        if inline:
            return f'- **{title}**: {inline}'
        if not items:
            return f'- **{title}**: none'
        return f'- **{title}**\n' + '\n'.join(f'  - {it}' for it in items)

    lines = ['## Today’s plan', '']
    if cash is not None:
        lines.append(f'_Cash available: {_money(max(cash, 0.0))}._')
        lines.append('')
    lines.append(_block('Sell / Cut', sells))
    lines.append(_block('Trim / Take profit', trims))
    lines.append(_block('Watch (scale-out)', watches))
    lines.append(_block('Buy', buys, inline=buy_text))
    return _escape_dollars('\n'.join(lines))


def _legend_section(settings: Settings) -> str:
    return (
        '<details>\n<summary>How to read this report</summary>\n\n'
        '- **Entry / Stop / Target / R/R** — a structural trade plan. For a name in a '
        'fresh setup these are the actual trigger levels; for every other holding they are '
        '*management* estimates — **Stop** is a trailing exit just below support, **Target** '
        'is the measured-move upside, and **Entry** is the current reference price.\n'
        '- **Max add (risk)** — a per-trade risk *ceiling* in fractional shares, '
        f'risk-budgeted at {_pct(settings.risk_per_trade)} of the account per trade, '
        f'capped so no single position exceeds {_pct(settings.max_position_weight)} of the '
        'account, and further capped by your available cash. It is **not a recommendation to '
        'add**: it does not account for sector/theme concentration or your single-stock cap. '
        'A dash means no room to add (already at the weight cap, no cash) or no valid level.\n'
        '- **Suggested add** — a starter tranche, '
        f'{_pct(settings.suggested_add_fraction)} of the max, to enter with now; add the '
        f'remainder once the trade is up +{_num(settings.suggested_add_trigger_r, 1)}R and move '
        'the stop to breakeven. Backtests show this staged entry roughly halves drawdown versus '
        'committing full size at once, while adding earlier or never completing the add both do '
        'worse. Bounded by the same risk, weight, and cash caps.\n'
        '- **Sleeve** — **Core** = long-term anchor (held through noise); **Satellite** = '
        'tactical position managed with the trade plan.\n'
        '- **% vs 200d** — distance above/below the 200-day average; the primary trend gauge. '
        'Negative means the long-term trend has rolled over.\n'
        '- **R now** — open gain in R-multiples ((price−entry)/(entry−stop)); +1 means up one '
        'unit of risk. **% to stop** is the cushion before the exit triggers.\n'
        '- **Action** — the suggested next step for that row, in plain language.'
        '\n\n</details>'
    )


def _holdings_section(
    monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings,
    open_risk_pct: float = 0.0, cash: float | None = None,
    harvested: dict[str, int] | None = None,
) -> str:
    """Holdings split into a scannable status table + a collapsible plan table."""
    harvested = harvested or {}
    show_acct = has_accounts(monitor)
    pos_headers = ['Ticker']
    plan_headers = ['Ticker']
    if show_acct:
        pos_headers.append('Account')
        plan_headers.append('Account')
    pos_headers += ['Sleeve', '', 'Shares', 'Price', '% vs 200d', 'Value', 'Weight', 'P&L %',
                    'Action']
    plan_headers += ['Entry', 'Stop', 'Target', 'R/R', 'R now', '% to stop', 'Max add (risk)',
                     'Suggested add']
    ordered = monitor.copy()
    ordered['_core'] = ordered['Sleeve'].map(is_core)
    ordered = ordered.sort_values(
        by=['_core', 'Weight %'], ascending=[False, False], na_position='last'
    )
    pos_rows = []
    plan_rows = []
    for _, row in ordered.iterrows():
        ticker = str(row['Ticker'])
        plan = lookup.get(ticker, {})
        core = is_core(row['Sleeve'])
        current_value = float(row['Value']) if not _isna(row.get('Value')) else 0.0
        actionable = bool(plan.get('Actionable', False))
        if core:
            add_txt = DASH
            sugg_txt = DASH
            action = core_action(row)
        else:
            sizing = add_sizing(account_value, settings, plan, current_value, open_risk_pct,
                                cash_available=cash)
            rank = harvested.get(scaleout_key(row.get('Account'), ticker), 0)
            action = satellite_action(row, plan, sizing, actionable, settings, rank)
            can_add = not action.startswith(('Trim', 'Exit', 'Cut', 'Take profit'))
            add_txt = (
                _num(sizing.shares, 3)
                if can_add and sizing and sizing.shares > 0
                else DASH
            )
            sugg = suggested_add(sizing, settings) if can_add else None
            sugg_txt = _num(sugg[0], 3) if sugg else DASH
        r_now = open_r_multiple(row.get('Price'), plan.get('Entry'), plan.get('Stop'))
        to_stop = pct_to_stop(row.get('Price'), plan.get('Stop'))
        lead = [ticker]
        if show_acct:
            lead.append(_text(row.get('Account')))
        pos_rows.append(lead + [
            'Core' if core else 'Satellite',
            _status_dot(row, action),
            _num(row.get('Shares'), 3),
            _money(row.get('Price')),
            _pct(row.get('% vs SMA200')),
            _money(row.get('Value')),
            _pct(row.get('Weight %')),
            _pct(row.get('Unreal P&L %')),
            action,
        ])
        plan_rows.append(lead + [
            _money(plan.get('Entry')),
            _money(plan.get('Stop')),
            _money(plan.get('Target')),
            _num(plan.get('R/R')),
            _num(r_now, 1) if r_now is not None else DASH,
            _pct(to_stop),
            add_txt,
            sugg_txt,
        ])
    return (
        '## Holdings\n\n'
        + _md_table(pos_headers, pos_rows)
        + '\n\n<details>\n<summary>Trade plan &amp; sizing</summary>\n\n'
        + _md_table(plan_headers, plan_rows)
        + '\n\n</details>'
    )


def _scaleout_section(
    monitor: pd.DataFrame, lookup: dict, settings: Settings,
    harvested: dict[str, int] | None = None,
) -> str:
    """Profit-taking ladder for satellite holdings: scale out ⅓ at +2R and when extended.

    Rows are ordered by proximity to the nearest *un-harvested* scale-out level
    (already-reached levels first, then closest upcoming). A reached level reads
    as act-now; a level already taken is marked so it does not re-prompt. Returns
    an empty string when no satellite holding has a usable level.
    """
    harvested = harvested or {}
    show_acct = has_accounts(monitor)

    def _gap(price: float, level: float | None) -> float | None:
        if level is None or _isna(level):
            return None
        return (float(level) - price) / price

    def _level_cell(
        price: float, shares: float, level: float | None, taken: bool, folded: bool = False
    ) -> tuple[str, str]:
        if level is None or _isna(level):
            return DASH, DASH
        if folded:  # leapfrogged by a higher-priority milestone -> won't fire separately
            return _money(level), 'folded — +2R taken'
        if taken:  # already harvested -> show price for reference, no prompt
            return _money(level), '✓ taken'
        third = shares / 3.0
        amt = f'{_num(third, 3)} sh ≈ {_money(third * float(level))}'
        if price >= float(level):  # already at/through the level -> act now
            return f'{_money(level)} ✅', f'now — {amt}'
        return _money(level), amt

    def _nearest_label(
        gap_2r: float | None, gap_ext: float | None, p2_taken: bool, ex_taken: bool
    ) -> tuple[float, str]:
        cands = [
            (g, lbl)
            for g, lbl, taken in ((gap_2r, '+2R', p2_taken), (gap_ext, 'extended', ex_taken))
            if g is not None and not taken
        ]
        if not cands:  # every available level already harvested
            return float('inf'), '✓ scaled out'
        gap, lbl = min(cands, key=lambda kv: kv[0])  # most-passed / closest upcoming
        return gap, (f'✅ {lbl} hit' if gap <= 0 else f'{_pct(gap)} to {lbl}')

    entries = []
    for _, row in monitor.iterrows():
        if is_core(row['Sleeve']):
            continue
        shares = _positive(row.get('Shares'))
        price = _positive(row.get('Price'))
        if shares is None or price is None:
            continue
        plan = lookup.get(str(row['Ticker']), {})
        plus2r = r_multiple_price(plan.get('Entry'), plan.get('Stop'), 2.0)
        ext = extended_price(row.get('EMA20'), settings)
        if plus2r is None and ext is None:
            continue
        rank = harvested.get(scaleout_key(row.get('Account'), str(row['Ticker'])), 0)
        p2_taken = rank >= SCALE_2R
        ex_taken = rank >= SCALE_EXTENDED
        # Case B: +2R harvested but the extended rung sits *above* it -> the lower-
        # ranked extended scale is suppressed (folded into the +2R trim), so flag it
        # rather than implying a separate ⅓ is still owed.
        ex_folded = (
            rank >= SCALE_2R and ext is not None and plus2r is not None
            and float(ext) > float(plus2r)
        )
        sort_gap, nearest_txt = _nearest_label(
            _gap(price, plus2r), _gap(price, ext), p2_taken, ex_taken
        )
        p2_price, p2_sell = _level_cell(price, shares, plus2r, p2_taken)
        ex_price, ex_sell = _level_cell(price, shares, ext, ex_taken, folded=ex_folded)
        cells = [str(row['Ticker'])]
        if show_acct:
            cells.append(_text(row.get('Account')))
        cells += [nearest_txt, _num(shares, 3), p2_price, p2_sell, ex_price, ex_sell]
        entries.append((sort_gap, cells))
    if not entries:
        return ''
    entries.sort(key=lambda kv: kv[0])  # nearest (or most-passed) first
    rows = [row for _, row in entries]
    headers = ['Ticker']
    if show_acct:
        headers.append('Account')
    headers += ['Nearest', 'Shares', '+2R price', 'Sell ⅓ @ +2R', 'Extended price',
                'Sell ⅓ @ ext']
    note = _escape_dollars(
        '\n\n_Swing scale-out ladder, ordered by proximity to the next level (✅ = '
        'reached, act now). Sell ⅓ of the position when price reaches **+2R** (twice your '
        'initial risk above entry) and another ⅓ once it runs **extended** '
        f'({_pct(settings.swing_extended_atr)} above the 20-day EMA). Trail the remainder; '
        'sell the final ⅓ at the **Target**. “folded — +2R taken” marks an '
        'extended rung skipped because +2R (a higher-priority milestone) was already harvested '
        'at a lower price. Levels are estimates from current entry/stop and the 20-EMA._'
    )
    return '## Scale-out ladder\n\n' + _md_table(headers, rows) + note


def _stops_section(
    monitor: pd.DataFrame, lookup: dict, settings: Settings,
    history: dict[str, pd.DataFrame] | None = None,
) -> str:
    """Stop-alert levels for satellite holdings, nearest first.

    Most fractional lots cannot carry a resting stop order, so this
    lists the price to set a **price alert** at plus the next stop action. The
    alert starts at the structural stop, steps up to your cost (breakeven) once a
    position is up more than its stop distance, then **trails** up under a
    present-state Chandelier stop (highest high minus an ATR multiple) as the
    trade runs -- always the highest protective level, never lowered. ``$ at
    risk`` is what you stand to give back from here if the alert triggers
    (shares x distance to the alert). Core sleeves are managed long-term and
    excluded. Empty when no satellite holding has a usable stop.
    """
    history = history or {}
    show_acct = has_accounts(monitor)
    entries = []
    for _, row in monitor.iterrows():
        if is_core(row['Sleeve']):
            continue
        plan = lookup.get(str(row['Ticker']), {})
        price = _positive(row.get('Price'))
        shares = _positive(row.get('Shares'))
        stop = plan.get('Stop')
        if price is None or shares is None or _isna(stop):
            continue
        stop = float(stop)
        pnl = row.get('Unreal P&L %')
        risk_pct = (price - stop) / price
        cost = price / (1 + float(pnl)) if not _isna(pnl) and float(pnl) > -1 else None
        up_one_r = not _isna(pnl) and risk_pct > 0 and float(pnl) >= risk_pct
        trail = chandelier_trail(history.get(str(row['Ticker'])), cost, settings)
        if price <= stop:
            alert, note = stop, 'Sell now — stop hit'
        else:
            # Trail up: take the highest protective level that still sits below
            # price. The Chandelier trail only ever raises the alert (it is a
            # ratcheting stop); when it sits above price it is ignored here so a
            # fixed-lookback breach never fires a false "sell now" that would
            # contradict the present-state action on a normal pullback.
            alert, note = stop, 'Alert at structural stop'
            if up_one_r and cost is not None and cost > alert and cost < price:
                alert, note = cost, 'Tighten to breakeven (cost)'
            if trail is not None and trail > alert and trail < price:
                alert, note = trail, 'Trail — Chandelier stop'
        gap = (alert - price) / price
        at_risk = shares * (price - alert) if price > alert else 0.0
        cells = [str(row['Ticker'])]
        if show_acct:
            cells.append(_text(row.get('Account')))
        cells += [_num(shares, 3), _money(price), _money(alert), _pct(gap),
                  _money(at_risk), note]
        entries.append((gap, cells))
    if not entries:
        return ''
    entries.sort(key=lambda kv: kv[0])  # closest to triggering (or already through) first
    rows = [row for _, row in entries]
    headers = ['Ticker']
    if show_acct:
        headers.append('Account')
    headers += ['Shares', 'Price', 'Alert at', '% to alert', '$ at risk', 'Next step']
    note = _escape_dollars(
        '\n\n_Set a **price alert** at each **Alert at** level (fractional shares '
        'can’t hold resting stop orders); when it fires, sell the position manually. The '
        'alert starts at the structural stop, steps up to your **cost (breakeven)** once a '
        'name is up more than its stop distance, then **trails** under a Chandelier stop '
        f'(highest high − {_num(settings.trail_atr_mult)}×ATR) as the trade runs '
        '— always raise it, never lower. **$ at risk** is what you give back from here if '
        'the alert triggers; **% to alert** is the cushion before it does (negative = price '
        'still above the alert; 0 = triggering; positive = already through it)._'
    )
    return '## Stops & alerts\n\n' + _md_table(headers, rows) + note


def _watchlist_section(
    watch_monitor: pd.DataFrame, lookup: dict, account_value: float, settings: Settings,
    open_risk_pct: float = 0.0, cash: float | None = None,
) -> str:
    """Followed (unheld) names, same plan columns as Holdings for consistency."""
    headers = ['Ticker', 'Price', 'Setup', 'Conf', 'Entry', 'Stop', 'Target',
               'R/R', 'Max add (risk)', 'Suggested add', 'Action']
    rows = []
    for _, row in watch_monitor.iterrows():
        ticker = str(row['Ticker'])
        plan = lookup.get(ticker, {})
        actionable = bool(plan.get('Actionable', False))
        sizing = add_sizing(account_value, settings, plan, 0.0, open_risk_pct, cash_available=cash)
        add_txt = _num(sizing.shares, 3) if sizing and sizing.shares > 0 else DASH
        sugg = suggested_add(sizing, settings)
        sugg_txt = _num(sugg[0], 3) if sugg else DASH
        action = 'Buy candidate — setup live' if actionable else 'Watch — no setup yet'
        rows.append([
            ticker,
            _money(row.get('Price')),
            _text(plan.get('Setup')),
            _int(plan.get('Confidence')),
            _money(plan.get('Entry')),
            _money(plan.get('Stop')),
            _money(plan.get('Target')),
            _num(plan.get('R/R')),
            add_txt,
            sugg_txt,
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
    cash: float | None = None,
    risk_on: bool = True,
) -> str:
    if recs is None or recs.empty:
        if settings.require_regime_for_adds and not risk_on:
            return (
                '## Recommended adds\n\nNo adds — **risk-off regime** (SPY below its '
                '200-day). New entries are paused: in backtests, adds taken below the '
                '200-day roughly halve expectancy, so the screen sits out until the '
                'market reclaims its trend.'
            )
        return (
            '## Recommended adds\n\nNo high-conviction adds today — sitting tight '
            f'(gates: confidence ≥ {_num(settings.rec_min_confidence, 0)}, '
            f'R/R ≥ {_num(settings.rec_min_reward_risk)}).'
        )
    current_values = current_values or {}
    headers = ['Ticker', 'Company', 'Setup', 'Type', 'Conf', 'R/R',
               'Entry', 'Stop', 'Target', 'Rank', 'Max add (risk)', 'Suggested add', 'Add $']
    rows = []
    for _, row in recs.iterrows():
        ticker = str(row['Ticker'])
        sizing = add_sizing(
            account_value, settings, row.to_dict(),
            current_value=current_values.get(ticker, 0.0), open_risk_pct=open_risk_pct,
            cash_available=cash,
        )
        sugg = suggested_add(sizing, settings)
        rows.append([
            ticker,
            _text(row.get('Company Name')),
            _text(row.get('Setup')),
            'ETF' if ticker in etfs else 'Stock',
            _int(row.get('Confidence')),
            _num(row.get('R/R')),
            _money(row.get('Entry')),
            _money(row.get('Stop')),
            _money(row.get('Target')),
            _num(row.get('Rank Score')),
            _num(sizing.shares, 3) if sizing else DASH,
            _num(sugg[0], 3) if sugg else DASH,
            _money(sugg[1]) if sugg else DASH,
        ])
    note = ''
    if cash is not None:
        note = _escape_dollars(
            f'\n\n_Add sizes are capped to your {_money(max(cash, 0.0))} cash on hand; '
            'amounts are per-name, so you cannot take every add at once. **Add $** is the '
            'starter tranche (Suggested add × price)._'
        )
    return '## Recommended adds\n\n' + _md_table(headers, rows) + note


def _company_names(analysis: pd.DataFrame | None) -> dict[str, str]:
    """Map ticker -> company name from an analysis frame, for labelling direct holdings."""
    names: dict[str, str] = {}
    if analysis is None or analysis.empty or 'Company Name' not in analysis.columns:
        return names
    for _, row in analysis.iterrows():
        ticker = str(row['Ticker'])
        label = row.get('Company Name')
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
        (str(row['Ticker']), float(row['Value']))
        for _, row in monitor.iterrows()
        if not _isna(row.get('Value'))
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
        '_True economic exposure: direct holdings combined with each fund’s top-10 '
        'holdings (Yahoo). The untracked remainder of broad funds is grouped as '
        '“Other / diversified” rather than attributed to any name._',
        '',
    ]
    headers = ['Symbol', 'Name', 'Direct', 'Via funds', 'Total', '% acct']
    rows = []
    for e in exposures[:top_n]:
        rows.append([
            e.symbol,
            _text(e.name),
            _money(e.direct_value) if e.direct_value else DASH,
            _money(e.fund_value) if e.fund_value else DASH,
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
            value = _money(float(held.sum())) if not held.empty else DASH
            pnl_txt = _money(float(pnl.sum())) if not pnl.empty else DASH
            lines.append(_escape_dollars(
                f'- {label}: {len(sub)} position(s), value {value}, P&L {pnl_txt}'
            ))
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
            [str(row['Ticker'])]
            + ([_text(row.get('Account'))] if has_acct else [])
            + [
                _pct(row.get('Trend')),
                _pct(row.get('RS')),
                _pct(row.get('Weight %')),
                _money(row.get('Value')),
                _pct(row.get('Unreal P&L %')),
            ]
            for _, row in rotation.iterrows()
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
    income: list[IncomeEvent] | None = None,
    harvested: dict[str, int] | None = None,
    history: dict[str, pd.DataFrame] | None = None,
) -> str:
    lookup = analysis_lookup(analysis)
    harvested = harvested or {}
    context = _market_context(analysis, recs)
    exposures, tail_value = exposure
    _, open_risk_pct = portfolio_open_risk(monitor, lookup, account_value)
    held_values = {
        str(row['Ticker']): float(row['Value'])
        for _, row in monitor.iterrows()
        if not _isna(row.get('Value'))
    }
    # Sum the full monitor (not the ticker-keyed dict, which collapses a ticker
    # held in two accounts) so cash matches account_value - holdings exactly.
    total_held = float(monitor['Value'].dropna().sum())
    cash = max(account_value - total_held, 0.0)
    regime_dot = STATUS_GREEN if risk_on else STATUS_RED
    sections = [
        f'# Daily Position Report\n\n{regime_dot} **{"Risk-On" if risk_on else "Risk-Off"}** '
        f'· _Generated {generated_at} · Market context: {context}_',
        _snapshot_section(monitor, lookup, etfs, account_value, settings),
        _action_plan_section(
            monitor, watch_monitor, lookup, recs, account_value, settings, risk_on, open_risk_pct,
            earnings, cash, harvested,
        ),
        _income_section(income),
        _holdings_section(monitor, lookup, account_value, settings, open_risk_pct, cash,
                          harvested),
        _scaleout_section(monitor, lookup, settings, harvested),
        _stops_section(monitor, lookup, settings, history),
        _watchlist_section(watch_monitor, lookup, account_value, settings, open_risk_pct, cash),
        _recommendations_section(
            recs, rec_etfs, account_value, settings, held_values, open_risk_pct, cash, risk_on
        ),
        _concentration_section(monitor, analysis, etfs, settings),
    ]
    exposure_section = _exposure_section(exposures, tail_value, account_value)
    if exposure_section:
        sections.append(exposure_section)
    sections.append(_legend_section(settings))
    return '\n\n---\n\n'.join(s for s in sections if s) + '\n'


def _income_section(income: list[IncomeEvent] | None) -> str:
    """Prompt to reconcile recent dividends / fund capital-gains into cash.

    Empty string when there is nothing new, so the section is dropped entirely.
    """
    if not income:
        return ''
    lines = [
        '## Income to reconcile',
        '',
        '_Distributions with ex-dates since your last report. Add each total to '
        'the matching `cash` line in positions.txt (estimates — confirm against '
        'your broker)._',
    ]
    for account, total, events in income_by_account(income):
        detail = '; '.join(
            f'{e.ticker} {e.kind.lower()} {_money(e.per_share)}/sh × {_num(e.shares, 3)} = '
            f'{_money(e.amount)} ({e.ex_date.strftime("%b %d")})'
            for e in events
        )
        lines.append(f'- **{_text(account)}** — add ≈ {_money(total)}: {detail}')
    return '\n'.join(lines)


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


def _sold_keys(positions_text: str) -> set[str]:
    """Account|ticker keys that carry at least one sell (negative-share) lot.

    Used to bootstrap the scale-out ledger on its first run: a position already
    carrying a recorded trim is treated as harvested at whatever scale level it
    currently sits, so the report does not re-prompt the same take-profit.
    """
    keys: set[str] = set()
    account = ''
    for raw in positions_text.splitlines():
        line = raw.strip()
        if line.startswith('[') and line.endswith(']'):
            account = line[1:-1].strip()
            continue
        if not line or line.startswith('#'):
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 3 or '=' in parts[0]:
            continue
        try:
            shares = float(parts[-1])
        except ValueError:
            continue
        if shares < 0:
            keys.add(scaleout_key(account, parts[0]))
    return keys


def _scaleout_state(
    monitor: pd.DataFrame, analysis: pd.DataFrame, settings: Settings, positions_text: str
) -> dict[str, int]:
    """Advance and persist the scale-out ledger; return harvested rank per key.

    Detects executed trims (share count falling while a position sits at a scale
    level) so already-harvested take-profits stop re-appearing as fresh prompts.
    """
    lookup = analysis_lookup(analysis)
    records = []
    for _, row in monitor.iterrows():
        if is_core(row['Sleeve']):
            continue
        ticker = str(row['Ticker'])
        plan = lookup.get(ticker, {})
        key = scaleout_key(row.get('Account'), ticker)
        shares = float(row.get('Shares') or 0.0)
        records.append((key, shares, active_scale_rank(row, plan, settings)))
    ledger = load_scaleout_ledger(SCALEOUT_LEDGER_PATH)
    harvested, ledger = update_scaleout_ledger(
        records, ledger, first_seen_harvested=_sold_keys(positions_text)
    )
    save_scaleout_ledger(SCALEOUT_LEDGER_PATH, ledger)
    return harvested


def _generate_report(client, engine, cache, settings: Settings, generated_at: str) -> tuple[str, str]:
    """Assemble the report markdown plus a one-line status; pure of file writes."""
    positions_text = read_text_or_empty(POSITIONS_FILE)
    merged = merge_holdings(parse_portfolio(read_text_or_empty(PORTFOLIO_FILE)), parse_positions(positions_text))
    if not merged:
        return (
            _build_unavailable(generated_at, 'no holdings in portfolio.txt/positions.txt'),
            'No holdings found; wrote placeholder report.',
        )

    held = [e.ticker for e in merged]
    watch = [t for t in _followed_tickers() if t not in set(held)]
    universe = [*held, *watch]
    # Reuse the cached 2y window and refresh only the latest bars so a same-day
    # rerun captures the current price cheaply -- without re-downloading 2 years
    # for the whole universe, which throttles and fails on Yahoo.
    history = client.fetch_history_live(
        universe, period=HISTORY_PERIOD, tail_period=INTRADAY_TAIL_PERIOD
    )
    monitor = build_monitor(merged, history, settings)
    watch_monitor = build_monitor([PositionEntry(t, sleeve=SATELLITE) for t in watch], history, settings)
    held_value = float(monitor['Value'].dropna().sum())
    explicit_cash = parse_cash(positions_text)
    if explicit_cash is not None:
        # Cash (e.g. SPAXX) is tracked directly, so account value is current
        # holdings plus that cash -- no stale cost-basis seeding to drift from.
        account_value = held_value + explicit_cash
    else:
        account_value = parse_account_value(positions_text) or held_value

    gate_config = FilterConfig(
        min_confidence=settings.rec_min_confidence,
        min_reward_risk=settings.rec_min_reward_risk,
        min_avg_volume=settings.min_avg_volume,
        require_regime=settings.require_regime_for_adds,
    )
    analysis = engine.analyze(UniverseResult(tickers=universe, companies={}), config=gate_config)
    etfs = _etf_tickers(client, universe)
    recs = _screen_recommendations(engine, cache, watch, gate_config)
    rec_etfs = _etf_tickers(client, list(recs['Ticker'])) if not recs.empty else set()
    auto_added = _auto_add_to_watchlist(recs, held, rec_etfs, settings)

    ledger = load_ledger(INCOME_LEDGER_PATH)
    income, ledger = collect_income(
        merged, history, ledger,
        today=datetime.now(UTC).date(),
        lookback_days=settings.dividend_lookback_days,
    )
    save_ledger(INCOME_LEDGER_PATH, ledger)

    harvested = _scaleout_state(monitor, analysis, settings, positions_text)

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
        income=income,
        harvested=harvested,
        history=history,
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
