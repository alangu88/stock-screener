"""Risk-based position sizing for add recommendations.

Translates a fixed *risk-per-trade* budget (a fraction of account value) into a
concrete number of shares to add, then caps that by a maximum position weight so
no single name dominates the book.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PositionSizing:
    """A suggested add: how many shares, the dollar cost, and the risk taken.

    Attributes:
        shares: Whole shares to add (never negative).
        dollars: Dollar cost of the add (``shares * entry``).
        risk_dollars: Dollars at risk on the add if stopped out
            (``shares * (entry - stop)``).
        weight: Resulting position weight after the add
            (``(current_value + dollars) / account_value``).
        capped_by: What limited the size -- ``'risk'`` when the risk budget is
            the binding constraint, ``'weight'`` when the max-position-weight cap
            reduced the count further.
    """

    shares: int
    dollars: float
    risk_dollars: float
    weight: float
    capped_by: str


def suggest_add_size(
    account_value: float,
    risk_pct: float,
    entry: float,
    stop: float,
    *,
    current_value: float = 0.0,
    max_position_weight: float = 0.10,
) -> PositionSizing | None:
    """Suggest how many shares to add given a risk budget and weight cap.

    The base size risks ``account_value * risk_pct`` across the per-share risk
    ``entry - stop``. The result is then capped so the position's total value
    (``current_value`` plus the add) stays within ``max_position_weight`` of the
    account.

    Returns ``None`` when the inputs cannot produce a valid trade
    (``entry <= stop`` or ``account_value <= 0``).
    """
    if account_value <= 0 or entry <= stop:
        return None

    per_share_risk = entry - stop
    risk_budget = account_value * risk_pct
    risk_shares = math.floor(risk_budget / per_share_risk)

    max_position_dollars = max_position_weight * account_value
    remaining_room = max_position_dollars - current_value
    weight_shares = math.floor(remaining_room / entry) if remaining_room > 0 else 0

    if weight_shares < risk_shares:
        shares = max(weight_shares, 0)
        capped_by = 'weight'
    else:
        shares = max(risk_shares, 0)
        capped_by = 'risk'

    dollars = shares * entry
    risk_dollars = shares * per_share_risk
    weight = (current_value + dollars) / account_value
    return PositionSizing(
        shares=shares,
        dollars=dollars,
        risk_dollars=risk_dollars,
        weight=weight,
        capped_by=capped_by,
    )
