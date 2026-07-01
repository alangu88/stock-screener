"""Equity-curve compounding and performance metrics.

All functions are pure. ``drawdown`` and ``cagr`` summarise an equity curve;
``equity_curve`` compounds a stream of closed trades under a concurrent-position
cap with conviction-scaled (optionally setup-tilted) risk.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.screener.advisor import _conviction_risk


def drawdown(curve: Sequence[float]) -> float:
    """Maximum peak-to-trough drawdown of an equity curve (<= 0.0)."""
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1.0)
    return mdd


def cagr(start: float, end: float, years: float) -> float:
    """Compound annual growth rate; 0.0 for non-positive spans or start."""
    return (end / start) ** (1 / years) - 1 if years > 0 and start > 0 else 0.0


def equity_curve(
    trades, settings, max_concurrent: int, cost: float,
    setup_mults: dict[str, float] | None = None,
) -> tuple[float, list[float]]:
    """Compound trades into an equity curve under a concurrent-position cap.

    Each trade is ``(entry_date, exit_date, r_multiple, confidence[, setup])``.
    Equity is allocated at entry and realized at exit so concurrent trades share
    capital (no fake leverage); risk per trade scales with conviction and is
    hard-capped at ``conviction_risk_max``. ``setup_mults`` optionally tilts the
    per-trade risk by setup family (e.g. larger for breakouts); the product is
    still capped. Trades without a setup field ignore the tilt.
    """
    cap = settings.conviction_risk_max
    equity = 1.0
    open_pos: list[tuple] = []  # (exit_date, alloc, r)
    events: list[tuple] = []
    for trade in trades:
        entry_date, exit_date, r_mult, conf = trade[:4]
        setup = trade[4] if len(trade) > 4 else None
        matured = [op for op in open_pos if op[0] <= entry_date]
        open_pos = [op for op in open_pos if op[0] > entry_date]
        for ex, alloc, r in sorted(matured):
            equity += alloc * (r - cost)
            events.append((ex, equity))
        if len(open_pos) >= max_concurrent:
            continue
        mult = setup_mults.get(setup, 1.0) if setup_mults else 1.0
        risk = min(_conviction_risk(settings, conf) * mult, cap)
        open_pos.append((exit_date, equity * risk, r_mult))
    for ex, alloc, r in sorted(open_pos):
        equity += alloc * (r - cost)
        events.append((ex, equity))
    events.sort(key=lambda x: x[0])
    return equity, [1.0] + [e for _, e in events]
