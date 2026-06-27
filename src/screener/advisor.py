"""Decision helpers shared by the Streamlit app and the daily report.

Pure functions (no Streamlit, no I/O) that turn holdings plus per-ticker
analysis into add sizing, action hints, the diversification-cap state, and
recommendation rows. Centralized here so both ``src/app.py`` and
``scripts/daily_report.py`` reuse identical logic and it can be unit-tested
without a UI.
"""

from __future__ import annotations

import pandas as pd

from src.config import Settings
from src.screener.holdings import CORE, AllocationStats, count_individual_stocks
from src.screener.sizing import PositionSizing, suggest_add_size


def _isna(value) -> bool:
    try:
        return value is None or bool(pd.isna(value))
    except (TypeError, ValueError):
        return value is None


def is_core(sleeve) -> bool:
    """Whether a sleeve tag is the Core sleeve (case-insensitive)."""
    return str(sleeve).lower() == CORE


def analysis_lookup(analysis: pd.DataFrame) -> dict[str, dict]:
    """Map ticker -> analysis row dict for quick per-ticker lookups."""
    if analysis is None or analysis.empty:
        return {}
    return {str(row['Ticker']): row.to_dict() for _, row in analysis.iterrows()}


def add_sizing(
    account_value: float, settings: Settings, row: dict, current_value: float
) -> PositionSizing | None:
    """Risk-based add size for a plan row, or ``None`` when it cannot be sized."""
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


def satellite_action(monitor_row, analysis_row: dict, sizing, actionable: bool) -> str:
    """One-word action hint for a satellite holding (priority-ordered)."""
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
        return f'Add near ${float(entry):,.2f}' if not _isna(entry) else 'Add'
    if not _isna(vs_ema20) and float(vs_ema20) > 0.10:
        return 'Extended'
    return 'Hold'


def individual_cap_state(monitor: pd.DataFrame, etfs: set, settings: Settings) -> tuple[bool, str]:
    """Whether the held individual-stock count is at/over the diversification cap."""
    if monitor is None or 'Sleeve' not in monitor.columns:
        return False, ''
    count = count_individual_stocks(monitor, etfs)
    cap = settings.max_individual_stocks
    if count >= cap:
        return True, (
            f'At max individual holdings ({count}/{cap}) \u2014 consider rotating rather '
            'than adding. Single-stock picks are de-emphasized below; fund picks still shown.'
        )
    return False, ''


def recommendation_rows(
    recs: pd.DataFrame, account_value: float, settings: Settings, etfs: set
) -> pd.DataFrame:
    """Build the Recommended Adds display rows (numeric; formatting is caller's job)."""
    rows = []
    for _, r in recs.iterrows():
        ticker = str(r['Ticker'])
        sizing = add_sizing(account_value, settings, r.to_dict(), current_value=0.0)
        rows.append({
            'Ticker': ticker,
            'Company': r.get('Company Name'),
            'Setup': r.get('Setup'),
            'Type': 'ETF' if ticker in etfs else 'Stock',
            'Confidence': r.get('Confidence'),
            'R/R': r.get('R/R'),
            'Entry': r.get('Entry'),
            'Stop': r.get('Stop'),
            'Target': r.get('Target'),
            'Rank Score': r.get('Rank Score'),
            'Add Shares': sizing.shares if sizing else None,
            'Add $': sizing.dollars if sizing else None,
        })
    return pd.DataFrame(rows)


def rotation_candidates(
    monitor: pd.DataFrame, analysis: pd.DataFrame | dict, etfs: set
) -> pd.DataFrame:
    """Rank held single-stock satellites weakest-first as rotation/trim ideas.

    Excludes Core holdings and funds. Weakest is defined as furthest below the
    200-day trend, then lowest relative-strength outperformance, then smallest
    position value (cheapest to exit). Returns an empty frame when there are no
    individual satellites to rank.
    """
    if monitor is None or 'Sleeve' not in monitor.columns:
        return pd.DataFrame()
    lookup = analysis if isinstance(analysis, dict) else analysis_lookup(analysis)
    etf_up = {str(t).upper() for t in etfs}
    rows = []
    for _, r in monitor.iterrows():
        if is_core(r['Sleeve']):
            continue
        ticker = str(r['Ticker'])
        if ticker.upper() in etf_up:
            continue
        a = lookup.get(ticker, {})
        rows.append({
            'Ticker': ticker,
            'Account': r.get('Account'),
            'Trend': r.get('% vs SMA200'),
            'RS': a.get('RS Outperformance'),
            'Weight %': r.get('Weight %'),
            'Value': r.get('Value'),
            'Unreal P&L %': r.get('Unreal P&L %'),
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if 'Account' in df.columns and df['Account'].dropna().empty:
        df = df.drop(columns=['Account'])
    df = df.sort_values(
        by=['Trend', 'RS', 'Value'],
        ascending=[True, True, True],
        na_position='first',
    )
    return df.reset_index(drop=True)


def core_rebalance(alloc: AllocationStats | None) -> tuple[float, str]:
    """Dollars to move into (positive) or out of (negative) Core to hit the band.

    Assumes a within-portfolio shift (total value held fixed): to reach the
    floor, ``target_min * total - core`` dollars move into Core; if Core is over
    the ceiling, the excess above ``target_max * total`` is the trim amount.
    Returns ``(0.0, message)`` when already inside the band or unsized.
    """
    if alloc is None or alloc.total_value <= 0:
        return 0.0, ''
    if alloc.core_pct < alloc.target_min:
        needed = alloc.target_min * alloc.total_value - alloc.core_value
        return needed, (
            f'Core is {alloc.core_pct:.0%} (floor {alloc.target_min:.0%}) \u2014 move '
            f'~${needed:,.0f} from satellites into core (e.g. VTI / VXUS) to re-enter the band.'
        )
    if alloc.core_pct > alloc.target_max:
        excess = alloc.core_value - alloc.target_max * alloc.total_value
        return -excess, (
            f'Core is {alloc.core_pct:.0%} (ceiling {alloc.target_max:.0%}) \u2014 trim '
            f'~${excess:,.0f} from core into satellites to re-enter the band.'
        )
    return 0.0, f'Core allocation {alloc.core_pct:.0%} is within the target band.'

