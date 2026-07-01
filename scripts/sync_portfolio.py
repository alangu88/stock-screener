"""Re-publish the committed portfolio composition from your private positions.

``portfolio.txt`` (tickers + sleeve, no sizes) is the only holdings file that
gets committed, so it is the sole source the snapshot CI job can see. This
script merges your committed sleeves with the private ``positions.txt`` and
rewrites ``portfolio.txt`` so every held ticker is published -- which is what
makes your positions mirror into the snapshot watchlist on GitHub Actions.

Existing sleeve choices in ``portfolio.txt`` win; tickers held only in
``positions.txt`` are appended as ``satellite``. The file's leading comment
header is preserved. No share counts, cost basis, or account value are ever
written, so the output stays safe to commit.

Run from the repo root:
    python scripts/sync_portfolio.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.screener.holdings import (  # noqa: E402
    export_manifest,
    merge_holdings,
    parse_portfolio,
    parse_positions,
)
from src.utils.files import read_text_or_empty  # noqa: E402

PORTFOLIO_PATH = _REPO_ROOT / 'portfolio.txt'
POSITIONS_PATH = _REPO_ROOT / 'positions.txt'


def _leading_header(text: str) -> str:
    """Return the leading comment/blank block, up to the first content line.

    Content is the first line that is neither blank nor a ``#`` comment (i.e. an
    ``[Account]`` header or a ticker). Preserving this block keeps the file's
    hand-written documentation across re-publishes.
    """
    header: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith('#'):
            break
        header.append(raw.rstrip())
    return '\n'.join(header).rstrip('\n')


def main() -> int:
    positions_text = read_text_or_empty(POSITIONS_PATH)
    if not positions_text.strip():
        print(f'No positions found at {POSITIONS_PATH.name}; nothing to sync.', file=sys.stderr)
        return 1

    portfolio_text = read_text_or_empty(PORTFOLIO_PATH)
    merged = merge_holdings(
        parse_portfolio(portfolio_text),
        parse_positions(positions_text),
    )

    # export_manifest emits its own 2-line header; swap in the file's richer
    # hand-written header when one exists.
    manifest = export_manifest(merged)
    body = '\n'.join(manifest.split('\n')[2:])
    header = _leading_header(portfolio_text)
    updated = (header + '\n' + body) if header else manifest
    if not updated.endswith('\n'):
        updated += '\n'

    if updated == portfolio_text:
        print(f'{PORTFOLIO_PATH.name} already up to date ({len(merged)} holdings).')
        return 0

    PORTFOLIO_PATH.write_text(updated, encoding='utf-8')
    print(f'Published {len(merged)} holdings to {PORTFOLIO_PATH.name}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
