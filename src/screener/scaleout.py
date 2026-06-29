"""Persisted scale-out ledger: remembers which profit-taking levels you have
already harvested so the daily report stops re-recommending the same trim.

State is a JSON map ``"<account>|<ticker>" -> {"shares": float, "rank": int}``
where ``rank`` is the highest scale level already taken (see the ``SCALE_*``
ranks in :mod:`src.screener.advisor`). A trim is detected when a position's
share count falls between runs while it sits at/over a scale level; the harvested
rank then rises to that level and is held until a higher-ranked level triggers.
Rebuilding the position (share count rises) re-arms it from scratch.

The ledger lives alongside the report (gitignored), like the income ledger, and
is private per-user state.
"""

from __future__ import annotations

import json
from pathlib import Path

# Tolerance for share-count comparisons (fractional shares are common).
_SHARE_EPS = 1e-9


def scaleout_key(account: str | None, ticker: str) -> str:
    """Stable ledger key for an account-scoped position."""
    return f'{account or ""}|{ticker.upper()}'


def load_scaleout_ledger(path: Path) -> dict[str, dict]:
    """Read the ledger, returning an empty map when missing or unreadable."""
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_scaleout_ledger(path: Path, ledger: dict[str, dict]) -> None:
    """Persist the ledger as pretty JSON, creating parent folders as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding='utf-8')


def update_scaleout_ledger(
    records: list[tuple[str, float, int]],
    ledger: dict[str, dict],
    first_seen_harvested: set[str] | None = None,
) -> tuple[dict[str, int], dict[str, dict]]:
    """Advance the ledger one run; return ``(harvested_map, new_ledger)``.

    ``records`` is an iterable of ``(key, shares, active_rank)`` for each managed
    (satellite) position this run, where ``active_rank`` is the highest scale
    level currently satisfied (0 when none).

    Detection rules per key:

    * **First sight** -- harvested at ``active_rank`` when the key is in
      ``first_seen_harvested`` (bootstrap from an already-recorded trim) and the
      position currently sits at a scale level; otherwise 0.
    * **Trim** -- when shares fall versus the prior run while sitting at a scale
      level higher than the stored rank, the harvested rank rises to it.
    * **Rebuild** -- when shares rise versus the prior run, the rank resets to 0
      so the fresh position is managed from scratch.

    ``new_ledger`` carries only keys seen this run, so positions fully closed
    drop out automatically.
    """
    boot = first_seen_harvested or set()
    harvested_map: dict[str, int] = {}
    new_ledger: dict[str, dict] = {}
    for key, shares, active_rank in records:
        prev = ledger.get(key)
        if prev is None:
            rank = active_rank if (key in boot and active_rank > 0) else 0
        else:
            rank = int(prev.get('rank', 0))
            prev_shares = float(prev.get('shares', shares))
            if shares > prev_shares + _SHARE_EPS:
                rank = 0  # position rebuilt -> manage fresh
            elif shares < prev_shares - _SHARE_EPS and active_rank > rank:
                rank = active_rank  # a trim at a higher level -> harvested
        harvested_map[key] = rank
        new_ledger[key] = {'shares': shares, 'rank': rank}
    return harvested_map, new_ledger
