"""Pure, deterministic single-trade exit simulator.

Given an entry (price, initial stop, target) and the forward price path, this
simulates how a configurable stop strategy would have managed the trade and
returns the realized result in **R-multiples** (multiples of the initial risk
per share, ``entry - initial_stop``). R is the natural unit for comparing
expectancy across names of different price and volatility.

No network, no global state, no look-ahead: the trailing stop for each bar is
derived from information available *before* that bar (the prior high-water mark
and a prior-bar ATR supplied by the caller).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class StopParams:
    """Configuration for one exit strategy variant.

    All fields are optional levers so a single simulator covers every variant:

    * ``chandelier_atr_mult`` -- trail a stop at ``high_water - mult * ATR``;
      ratchets up only (never loosens). ``None`` disables trailing.
    * ``breakeven_r`` -- once the trade's favorable excursion reaches this many
      R, raise the stop to the entry price. ``None`` disables it.
    * ``time_stop_bars`` -- exit if, by this many bars held, the trade has not
      reached ``min_progress_r`` of favorable excursion. ``None`` disables it.
    * ``partial_r`` / ``partial_frac`` -- book ``partial_frac`` of the position
      at ``partial_r`` R, then manage the remainder. ``None`` disables it.
    * ``target_exit`` -- when ``True`` the (remaining) position is closed at the
      structural target; when ``False`` the trade rides the trailing stop with
      no upside cap (the "let winners run" case).
    """

    name: str
    chandelier_atr_mult: float | None = None
    breakeven_r: float | None = None
    time_stop_bars: int | None = None
    min_progress_r: float = 0.5
    partial_r: float | None = None
    partial_frac: float = 0.0
    target_exit: bool = True


@dataclass(frozen=True)
class TradeResult:
    """Outcome of one simulated trade, in initial-risk (R) units."""

    r_multiple: float
    bars_held: int
    exit_reason: str  # 'stop' | 'target' | 'time' | 'eod'
    mae_r: float  # max adverse excursion (<= 0)
    mfe_r: float  # max favorable excursion (>= 0)


def simulate_trade(
    entry: float,
    initial_stop: float,
    target: float,
    high: Sequence[float],
    low: Sequence[float],
    close: Sequence[float],
    atr_prev: Sequence[float],
    params: StopParams,
) -> TradeResult | None:
    """Simulate a single long trade forward from the bar after entry.

    ``high``/``low``/``close`` are the forward bars (entry bar excluded), all the
    same length. ``atr_prev[i]`` is the ATR to use for the trailing stop at bar
    ``i`` -- it must be known before bar ``i`` (the caller passes a prior-bar
    ATR), so no intrabar look-ahead occurs.

    Returns ``None`` for a degenerate setup (``initial_stop >= entry`` or no
    forward bars).
    """
    risk = entry - initial_stop
    if risk <= 0 or len(high) == 0:
        return None

    n = len(high)
    stop = initial_stop
    high_water = entry
    remaining = 1.0
    realized_r = 0.0
    mae_r = 0.0
    mfe_r = 0.0
    partial_done = False

    def r_at(price: float) -> float:
        return (price - entry) / risk

    for i in range(n):
        # 1) Raise the stop using only pre-bar information (high_water/atr_prev).
        if params.chandelier_atr_mult is not None:
            candidate = high_water - params.chandelier_atr_mult * float(atr_prev[i])
            stop = max(stop, candidate)
        if params.breakeven_r is not None and mfe_r >= params.breakeven_r:
            stop = max(stop, entry)

        bar_high = float(high[i])
        bar_low = float(low[i])
        bar_close = float(close[i])

        # 2) Stop check first (pessimistic: assume the low is hit before the high).
        if bar_low <= stop:
            realized_r += remaining * r_at(stop)
            return TradeResult(realized_r, i + 1, 'stop', min(mae_r, r_at(bar_low)), mfe_r)

        # 3) Optional partial profit at a fixed R.
        if (
            params.partial_r is not None
            and not partial_done
            and params.partial_frac > 0.0
            and bar_high >= entry + params.partial_r * risk
        ):
            realized_r += params.partial_frac * params.partial_r
            remaining -= params.partial_frac
            partial_done = True

        # 4) Structural target closes the remainder (only when target_exit).
        if params.target_exit and remaining > 0 and bar_high >= target:
            realized_r += remaining * r_at(target)
            return TradeResult(realized_r, i + 1, 'target', mae_r, max(mfe_r, r_at(target)))

        # 5) Update excursions with this bar.
        high_water = max(high_water, bar_high)
        mfe_r = max(mfe_r, r_at(bar_high))
        mae_r = min(mae_r, r_at(bar_low))

        # 6) Time stop: dead money is recycled.
        if (
            params.time_stop_bars is not None
            and i + 1 >= params.time_stop_bars
            and mfe_r < params.min_progress_r
        ):
            realized_r += remaining * r_at(bar_close)
            return TradeResult(realized_r, i + 1, 'time', mae_r, mfe_r)

    # Ran out of data: mark to the last close.
    realized_r += remaining * r_at(float(close[-1]))
    return TradeResult(realized_r, n, 'eod', mae_r, mfe_r)
