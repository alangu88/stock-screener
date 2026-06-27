"""Trade-plan generation.

Derives entry, stop, and target from structure -- pivots, base lows, measured
moves -- rather than from the current price or a fixed percentage. Entries are
only set at the current price when immediate action is justified by the setup
(a confirmed breakout or a tag of support); otherwise they sit at the level
that would actually trigger the trade (e.g. a buy-stop above a coil).

Stops are placed below the structure that invalidates the thesis, with an ATR
cushion to avoid noise, and are capped so a single trade never risks more than
``max_risk_pct`` of position value (capital preservation). Targets project the
base's measured move, keeping every plan asymmetric by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.analysis.features import MarketFeatures
from src.screener.setups import BREAKOUT, CONTRACTION, PULLBACK, Setup
from src.screener.strategy import StrategyConfig


@dataclass(frozen=True)
class TradePlan:
    entry: float | None
    stop: float | None
    target: float | None
    risk_pct: float | None
    reward_pct: float | None
    reward_risk: float | None
    immediate_entry: bool


NO_PLAN = TradePlan(None, None, None, None, None, None, False)


def build_trade_plan(features: MarketFeatures, setup: Setup, config: StrategyConfig) -> TradePlan:
    builder = _BUILDERS.get(setup.setup_type)
    if builder is None:
        return NO_PLAN
    entry, structure_low, target, immediate = builder(features, config)
    stop = _stop_from_structure(entry, structure_low, features.atr, config)
    return _finalize(entry, stop, target, immediate)


def management_plan(features: MarketFeatures, config: StrategyConfig) -> TradePlan:
    """Always-valid trend-management levels for a name with no entry setup.

    Unlike :func:`build_trade_plan` (which intentionally yields ``NO_PLAN`` for
    ``Avoid`` names), this returns usable management levels for *any* held or
    watched position so the report can show a stop/target for every row:

    * ``entry`` -- the current price, used as the reference / add level.
    * ``stop`` -- a trailing stop just below the nearest structural support
      beneath price (moving average, base low, or contraction low), cushioned by
      ATR and capped so risk never exceeds ``max_risk_pct``. When price sits
      below all support (a broken downtrend) the cap itself sets the stop.
    * ``target`` -- the base's measured move projected from price.

    The levels are always asymmetric (``stop < entry < target``), so this never
    returns ``NO_PLAN``. ``immediate_entry`` is ``False``: these are management
    estimates, not a triggered entry signal.
    """
    price = features.price
    if price <= 0:
        return NO_PLAN

    supports = [s for s in (features.ma_fast, features.ma_long, features.base_low,
                            features.pivot_low) if s and s < price]
    risk_floor = price * (1 - config.max_risk_pct)
    if supports:
        stop = max(supports) - config.stop_buffer_atr * features.atr
        stop = max(stop, risk_floor)
    else:
        stop = risk_floor
    if stop >= price:  # support too close after the cushion -> fall back to the cap
        stop = risk_floor

    target = price + _measured_move(features)
    if target <= price:
        target = price + config.min_reward_risk * (price - stop)

    risk_pct = (price - stop) / price
    reward_pct = (target - price) / price
    reward_risk = reward_pct / risk_pct if risk_pct > 0 else None
    return TradePlan(
        entry=price,
        stop=stop,
        target=target,
        risk_pct=risk_pct,
        reward_pct=reward_pct,
        reward_risk=reward_risk,
        immediate_entry=False,
    )


def _breakout_levels(f: MarketFeatures, config: StrategyConfig):
    entry = f.price  # confirmed breakout -> immediate entry is justified
    target = entry + _measured_move(f)
    return entry, f.pivot_low, target, True


def _contraction_levels(f: MarketFeatures, config: StrategyConfig):
    entry = f.pivot  # buy-stop above the coil; do not chase the current price
    target = entry + _measured_move(f)
    return entry, f.pivot_low, target, False


def _pullback_levels(f: MarketFeatures, config: StrategyConfig):
    entry = f.price  # tagging rising support
    target = max(f.pivot, f.base_high) + _measured_move(f)
    return entry, f.base_low, target, True


_BUILDERS = {
    BREAKOUT: _breakout_levels,
    CONTRACTION: _contraction_levels,
    PULLBACK: _pullback_levels,
}


def _measured_move(f: MarketFeatures) -> float:
    """Base height projected upward (Darvas/O'Neil measured move)."""
    return max(f.base_high - f.base_low, f.atr)


def _stop_from_structure(entry: float, structure_low: float, atr: float, config: StrategyConfig) -> float:
    """Stop just below invalidating structure, capped at ``max_risk_pct`` risk."""
    structure_stop = structure_low - config.stop_buffer_atr * atr
    risk_floor = entry * (1 - config.max_risk_pct)
    return max(structure_stop, risk_floor)


def _finalize(entry: float, stop: float, target: float, immediate: bool) -> TradePlan:
    if entry <= 0 or stop >= entry or target <= entry:
        return NO_PLAN
    risk_pct = (entry - stop) / entry
    reward_pct = (target - entry) / entry
    reward_risk = reward_pct / risk_pct if risk_pct > 0 else None
    return TradePlan(
        entry=entry,
        stop=stop,
        target=target,
        risk_pct=risk_pct,
        reward_pct=reward_pct,
        reward_risk=reward_risk,
        immediate_entry=immediate,
    )
