"""Decision helpers shared by the Streamlit app and the daily report.

Pure functions (no Streamlit, no I/O) that turn holdings plus per-ticker
analysis into add sizing, action hints, the diversification-cap state, and
recommendation rows. Centralized here so both ``src/app.py`` and
``scripts/daily_report.py`` reuse identical logic and it can be unit-tested
without a UI.
"""

from __future__ import annotations

import pandas as pd

from src.analysis.indicators import atr
from src.config import Settings
from src.screener.holdings import CORE, AllocationStats, count_individual_stocks
from src.screener.sizing import SHARE_PRECISION, PositionSizing, suggest_add_size


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


def portfolio_open_risk(monitor: pd.DataFrame, lookup: dict, account_value: float) -> tuple[float, float]:
    """Aggregate satellite open risk (dollars above stops) and fraction of account.

    Core sleeves are excluded; rows below their stop contribute nothing. Returns
    ``(0.0, 0.0)`` when there is no account value to measure against.
    """
    if monitor is None or 'Sleeve' not in monitor.columns or account_value <= 0:
        return 0.0, 0.0
    total = 0.0
    for _, r in monitor.iterrows():
        if is_core(r['Sleeve']):
            continue
        shares, price = r.get('Shares'), r.get('Price')
        stop = lookup.get(str(r['Ticker']), {}).get('Stop')
        if not _isna(shares) and not _isna(price) and not _isna(stop) and float(price) > float(stop):
            total += float(shares) * (float(price) - float(stop))
    return total, total / account_value


def _conviction_risk(settings: Settings, confidence) -> float:
    """Scale risk from base toward the 2% cap as confidence climbs to 100.

    At the recommendation gate the base ``risk_per_trade`` applies; the highest
    convictions earn up to ``conviction_risk_max`` (hard cap). Missing or low
    confidence falls back to the base risk.
    """
    base = settings.risk_per_trade
    cap = settings.conviction_risk_max
    if _isna(confidence):
        return base
    gate = settings.rec_min_confidence
    span = max(100.0 - gate, 1.0)
    frac = max(0.0, min(1.0, (float(confidence) - gate) / span))
    return min(cap, base + frac * (cap - base))


def _setup_risk(settings: Settings, confidence, setup) -> float:
    """Conviction risk tilted by setup family, still hard-capped at the max.

    Breakouts realized markedly higher expectancy than pullbacks in walk-forward
    tests, so risk is weighted toward them (``breakout_risk_mult``) and away from
    pullbacks (``pullback_risk_mult``); other families keep the conviction risk.
    """
    risk = _conviction_risk(settings, confidence)
    label = str(setup).lower() if setup is not None else ''
    if label.startswith('breakout'):
        risk *= settings.breakout_risk_mult
    elif label.startswith('pullback'):
        risk *= settings.pullback_risk_mult
    return min(risk, settings.conviction_risk_max)


def add_sizing(
    account_value: float, settings: Settings, row: dict, current_value: float,
    open_risk_pct: float = 0.0, cash_available: float | None = None,
) -> PositionSizing | None:
    """Risk-based add size for a plan row, or ``None`` when it cannot be sized.

    ``open_risk_pct`` is the portfolio's aggregate open risk (stop distance) as a
    fraction of the account. The per-trade risk is trimmed to whatever headroom
    remains under ``max_portfolio_risk``; with no headroom left the add is denied.
    ``cash_available``, when given, further caps the add to the cash on hand.
    """
    entry = row.get('Entry')
    stop = row.get('Stop')
    if account_value <= 0 or _isna(entry) or _isna(stop):
        return None
    risk = _setup_risk(settings, row.get('Confidence'), row.get('Setup'))
    headroom = settings.max_portfolio_risk - max(open_risk_pct, 0.0)
    if headroom <= 0:
        return None
    risk = min(risk, headroom)
    return suggest_add_size(
        account_value,
        risk,
        float(entry),
        float(stop),
        current_value=float(current_value),
        max_position_weight=settings.max_position_weight,
        cash_available=cash_available,
    )


def suggested_add(sizing: PositionSizing | None, settings: Settings) -> tuple[float, float] | None:
    """Starter-tranche size to *actually* enter with, as ``(shares, dollars)``.

    The ``Max add (risk)`` is a ceiling; this scales it by
    ``settings.suggested_add_fraction`` so a first entry is staged (e.g. half now,
    the rest on confirmation). Returns ``None`` when there is nothing to add.
    """
    if sizing is None or sizing.shares <= 0:
        return None
    shares = round(sizing.shares * settings.suggested_add_fraction, SHARE_PRECISION)
    if shares <= 0:
        return None
    per_share = sizing.dollars / sizing.shares
    return shares, shares * per_share


def confirmation_add(
    sizing: PositionSizing | None, settings: Settings, entry, stop,
) -> tuple[float, float] | None:
    """The second tranche to complete the position once the trade confirms.

    Backtesting (``scripts/backtest_scalein.py``) found that staging an entry --
    a starter now, the remainder added only after the trade is up
    ``suggested_add_trigger_r`` (default +1R) with the stop moved to breakeven --
    roughly halves drawdown versus committing full size at once, while adding too
    early (+0.5R) or never completing the add both underperform.

    Returns ``(remaining_shares, confirm_price)`` -- the shares still to add to
    reach the risk-based max and the price that confirms them -- or ``None`` when
    there is no staged remainder (no sizing, or the starter already is the max).
    """
    starter = suggested_add(sizing, settings)
    if starter is None or sizing is None or _isna(entry) or _isna(stop):
        return None
    entry_f, stop_f = float(entry), float(stop)
    if entry_f <= stop_f:
        return None
    remaining = round(max(sizing.shares - starter[0], 0.0), SHARE_PRECISION)
    if remaining <= 0:
        return None
    confirm_price = entry_f + settings.suggested_add_trigger_r * (entry_f - stop_f)
    return remaining, confirm_price


def satellite_action(
    monitor_row, analysis_row: dict, sizing, actionable: bool, settings: Settings | None = None,
    harvested_rank: int = 0,
) -> str:
    """Descriptive next-step hint for a satellite holding (priority-ordered).

    When ``settings.swing_mode`` is on, use explicit swing verbs (Cut / Take
    profit / Trail). Otherwise fall back to the long-only Hold/Trim hints.
    ``harvested_rank`` only applies to the swing path (see
    :func:`swing_satellite_action`).
    """
    if settings is not None and settings.swing_mode:
        return swing_satellite_action(
            monitor_row, analysis_row, sizing, actionable, settings, harvested_rank
        )
    price = monitor_row.get('Price')
    stop = analysis_row.get('Stop')
    vs_sma200 = monitor_row.get('% vs SMA200')
    vs_ema20 = monitor_row.get('% vs EMA20')
    if not _isna(price) and not _isna(stop) and float(price) < float(stop):
        return 'Exit \u2014 price below stop' + _trim_hint(monitor_row, 1.0)
    if not _isna(vs_sma200) and float(vs_sma200) < 0:
        return 'Trim \u2014 below 200-day trend' + _trim_hint(monitor_row, 1 / 3)
    if actionable and sizing is not None and sizing.shares > 0:
        entry = analysis_row.get('Entry')
        return f'Add near ${float(entry):,.2f}' if not _isna(entry) else 'Add to position'
    if not _isna(vs_ema20) and float(vs_ema20) > 0.10:
        return 'Hold \u2014 extended, await pullback'
    return 'Hold \u2014 trend intact'


# Scale-out level ranks (higher = higher-priority profit-taking trigger). Used to
# remember which scale a position has already harvested so the report does not
# keep re-recommending the same trim.
SCALE_EXTENDED = 1
SCALE_2R = 2
SCALE_TARGET = 3


def active_scale_rank(monitor_row, analysis_row: dict, settings: Settings) -> int:
    """Highest scale-out level a satellite currently satisfies (0 when none).

    Mirrors the scale branches of :func:`swing_satellite_action`: at/over target
    (3), up +2R (2), or extended above the 20-EMA while in profit (1).
    """
    price = monitor_row.get('Price')
    if _isna(price):
        return 0
    target = analysis_row.get('Target')
    if not _isna(target) and float(price) >= float(target):
        return SCALE_TARGET
    r_mult = open_r_multiple(price, analysis_row.get('Entry'), analysis_row.get('Stop'))
    if r_mult is not None and r_mult >= 2.0:
        return SCALE_2R
    pnl = monitor_row.get('Unreal P&L %')
    vs_ema20 = monitor_row.get('% vs EMA20')
    in_profit = not _isna(pnl) and float(pnl) > 0
    if in_profit and not _isna(vs_ema20) and float(vs_ema20) > settings.swing_extended_atr:
        return SCALE_EXTENDED
    return 0


def swing_satellite_action(
    monitor_row, analysis_row: dict, sizing, actionable: bool, settings: Settings,
    harvested_rank: int = 0,
) -> str:
    """Explicit swing-trading verbs for a satellite holding (priority-ordered).

    Mirrors the best-backtested exit ladder: cut below stop, take profit at
    target, scale 1/3 at +2R, trail to breakeven once +1R, cut broken trend.

    ``harvested_rank`` suppresses scale-outs already executed: a scale at rank
    ``<=`` ``harvested_rank`` is replaced by a 'Trail -- 1/3 taken' hint instead
    of re-advising the same trim. Higher-ranked levels still fire, and hard exits
    (stop hit, broken trend) are never suppressed.
    """
    price = monitor_row.get('Price')
    stop = analysis_row.get('Stop')
    target = analysis_row.get('Target')
    entry = analysis_row.get('Entry')
    vs_sma200 = monitor_row.get('% vs SMA200')
    vs_ema20 = monitor_row.get('% vs EMA20')
    pnl = monitor_row.get('Unreal P&L %')
    in_profit = not _isna(pnl) and float(pnl) > 0
    r_mult = open_r_multiple(price, entry, stop)
    harvested = False
    if not _isna(price) and not _isna(stop) and float(price) < float(stop):
        return 'Cut \u2014 stop hit' + _trim_hint(monitor_row, 1.0)
    if not _isna(price) and not _isna(target) and float(price) >= float(target):
        if SCALE_TARGET > harvested_rank:
            return 'Take profit \u2014 sell \u2153 at target' + _trim_hint(monitor_row, 1 / 3)
        harvested = True
    if not _isna(vs_sma200) and float(vs_sma200) < 0:
        return 'Cut \u2014 trend broken below 200-day' + _trim_hint(monitor_row, 1.0)
    if r_mult is not None and r_mult >= 2.0:
        if SCALE_2R > harvested_rank:
            return 'Take profit \u2014 +2R, scale out \u2153' + _trim_hint(monitor_row, 1 / 3)
        harvested = True
    if in_profit and not _isna(vs_ema20) and float(vs_ema20) > settings.swing_extended_atr:
        if SCALE_EXTENDED > harvested_rank:
            return 'Take profit \u2014 extended, scale out \u2153' + _trim_hint(monitor_row, 1 / 3)
        harvested = True
    if actionable and sizing is not None and sizing.shares > 0:
        entry = analysis_row.get('Entry')
        return f'Add near ${float(entry):,.2f}' if not _isna(entry) else 'Add to position'
    if harvested:
        return 'Trail \u2014 \u2153 taken, let rest run'
    if r_mult is not None and r_mult >= 1.0:
        return 'Trail \u2014 stop to breakeven'
    if in_profit:
        return 'Trail \u2014 let it run'
    return 'Hold \u2014 trend intact'


def _trim_hint(monitor_row, frac: float) -> str:
    """Append a concrete sell size: ' (sell N sh \u2248 $V)' for fraction ``frac``."""
    shares = monitor_row.get('Shares')
    value = monitor_row.get('Value')
    if _isna(shares) or float(shares) <= 0:
        return ''
    sell_sh = float(shares) * frac
    sh_txt = f'{sell_sh:,.0f}' if sell_sh >= 1 else f'{sell_sh:,.3f}'
    if not _isna(value) and float(value) > 0:
        return f' (sell {sh_txt} sh \u2248 ${float(value) * frac:,.0f})'
    return f' (sell {sh_txt} sh)'



def open_r_multiple(price, entry, stop) -> float | None:
    """Open gain in R-multiples: (price - entry) / (entry - stop), or None."""
    if _isna(price) or _isna(entry) or _isna(stop):
        return None
    risk = float(entry) - float(stop)
    if risk <= 0:
        return None
    return (float(price) - float(entry)) / risk



def pct_to_stop(price, stop) -> float | None:
    """Downside cushion: pct above stop (negative once price is below stop)."""
    if _isna(price) or _isna(stop) or float(price) <= 0:
        return None
    return (float(price) - float(stop)) / float(price)


def pct_to_target(price, target) -> float | None:
    """Upside remaining: pct gap up to target (negative once at/over target)."""
    if _isna(price) or _isna(target) or float(price) <= 0:
        return None
    return (float(target) - float(price)) / float(price)


def r_multiple_price(entry, stop, r) -> float | None:
    """Price at which an open trade is up ``r`` R-multiples ((entry-stop) units)."""
    if _isna(entry) or _isna(stop):
        return None
    risk = float(entry) - float(stop)
    if risk <= 0:
        return None
    return float(entry) + float(r) * risk


def extended_price(ema20, settings: Settings) -> float | None:
    """Price at which a holding becomes 'extended' above its 20-EMA (scale-out level)."""
    if _isna(ema20) or float(ema20) <= 0:
        return None
    return float(ema20) * (1 + settings.swing_extended_atr)


def chandelier_trail(df: pd.DataFrame | None, cost_basis, settings: Settings) -> float | None:
    """Present-state Chandelier trailing stop, breakeven-locked at cost.

    ``trail = highest_high(last trail_lookback_bars) - trail_atr_mult * ATR``.
    Once price is up at least one trail-width (``trail_breakeven_r`` * width)
    above the cost basis, the trail is floored at cost so a clear winner cannot
    round-trip into a loss.

    This is a pure function of *recent price action* plus your cost basis -- no
    entry date and no entry-setup label -- so it respects a present-state,
    risk-anchored management style. Returns ``None`` when there is too little
    history or no usable ATR.
    """
    if df is None or df.empty or 'Close' not in df.columns:
        return None
    close = df['Close'].dropna()
    if len(close) < settings.atr_period + 1:
        return None
    high = df['High'].reindex(close.index).fillna(close) if 'High' in df.columns else close
    low = df['Low'].reindex(close.index).fillna(close) if 'Low' in df.columns else close
    atr_series = atr(high, low, close, settings.atr_period).dropna()
    if atr_series.empty:
        return None
    atr_val = float(atr_series.iloc[-1])
    if atr_val <= 0:
        return None
    width = settings.trail_atr_mult * atr_val
    high_water = float(high.tail(settings.trail_lookback_bars).max())
    trail = high_water - width
    price = float(close.iloc[-1])
    if not _isna(cost_basis) and float(cost_basis) > 0 and \
            price >= float(cost_basis) + settings.trail_breakeven_r * width:
        trail = max(trail, float(cost_basis))
    return trail


def core_action(monitor_row) -> str:
    """Descriptive next-step hint for a core (long-term anchor) holding."""
    vs_sma200 = monitor_row.get('% vs SMA200')
    if not _isna(vs_sma200) and float(vs_sma200) < 0:
        return 'Review \u2014 core below 200-day'
    return 'Hold \u2014 core anchor'


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
    recs: pd.DataFrame,
    account_value: float,
    settings: Settings,
    etfs: set,
    current_values: dict[str, float] | None = None,
    open_risk_pct: float = 0.0,
    cash_available: float | None = None,
) -> pd.DataFrame:
    """Build the Recommended Adds display rows (numeric; formatting is caller's job).

    ``current_values`` maps ticker -> existing position value so adds to names
    already held are sized against the weight cap on top of what is owned; names
    absent from the map are sized as fresh positions. ``cash_available``, when
    given, caps each add to the cash on hand.
    """
    current_values = current_values or {}
    rows = []
    for _, r in recs.iterrows():
        ticker = str(r['Ticker'])
        sizing = add_sizing(
            account_value, settings, r.to_dict(),
            current_value=current_values.get(ticker, 0.0), open_risk_pct=open_risk_pct,
            cash_available=cash_available,
        )
        sugg = suggested_add(sizing, settings)
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
            'Suggested': sugg[0] if sugg else None,
        })
    return pd.DataFrame(rows)


def rotation_candidates(
    monitor: pd.DataFrame, analysis: pd.DataFrame, etfs: set
) -> pd.DataFrame:
    """Rank held single-stock satellites weakest-first as rotation/trim ideas.

    Excludes Core holdings and funds. Weakest is defined as furthest below the
    200-day trend, then lowest relative-strength outperformance, then smallest
    position value (cheapest to exit). Returns an empty frame when there are no
    individual satellites to rank.
    """
    if monitor is None or 'Sleeve' not in monitor.columns:
        return pd.DataFrame()
    lookup = analysis_lookup(analysis)
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

