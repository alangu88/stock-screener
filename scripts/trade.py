"""CLI: fast buy/sell entry into positions.txt.

Appends a lot line to the right ``[Account]`` block so the report's share count
and average cost update on the next run -- no manual recomputation. Buys carry a
price (cost-basis weighting); sells are unpriced negative lots, so the average
cost basis is preserved while shares net down.

Examples
--------
    python scripts/trade.py buy AAPL 10 175.20 --account Taxable
    python scripts/trade.py sell AAPL 5 --account Taxable
    python scripts/trade.py buy NVDA 100 95.20            # default account
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.screener.holdings import parse_positions  # noqa: E402

POSITIONS_PATH = _REPO_ROOT / 'positions.txt'


def _header(account: str | None) -> str:
    return f'[{account}]' if account else ''


def _append_lot(text: str, account: str | None, line: str) -> str:
    lines = text.splitlines()
    want = _header(account).lower()
    if not want:  # no account: just append at end
        return text.rstrip('\n') + f'\n{line}\n'
    # Find the account header; insert the lot at the end of its block.
    insert_at = None
    for i, raw in enumerate(lines):
        if raw.strip().lower() == want:
            insert_at = len(lines)
            for j in range(i + 1, len(lines)):
                if lines[j].strip().startswith('['):
                    insert_at = j
                    break
            break
    if insert_at is None:  # account does not exist yet -> add a new section
        return text.rstrip('\n') + f'\n\n{_header(account)}\n{line}\n'
    while insert_at > 0 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, line)
    return '\n'.join(lines) + '\n'


def main() -> int:
    p = argparse.ArgumentParser(description='Record a buy/sell into positions.txt.')
    p.add_argument('side', choices=['buy', 'sell'])
    p.add_argument('ticker')
    p.add_argument('shares', type=float)
    p.add_argument('price', type=float, nargs='?', help='Required for a buy.')
    p.add_argument('--account', default=None, help='Account section (e.g. Taxable).')
    p.add_argument('--dry-run', action='store_true', help='Print, do not write.')
    args = p.parse_args()

    ticker = args.ticker.upper()
    if args.shares <= 0:
        print('Shares must be positive.')
        return 1
    if args.side == 'buy':
        if args.price is None:
            print('A buy needs a price: trade.py buy TICKER SHARES PRICE')
            return 1
        line = f'{ticker}, {args.price:g}, {args.shares:g}'
    else:  # sell: unpriced negative lot keeps the average cost basis intact
        line = f'{ticker}, -, {-args.shares:g}'

    text = POSITIONS_PATH.read_text(encoding='utf-8') if POSITIONS_PATH.exists() else ''
    updated = _append_lot(text, args.account, line)
    if args.dry_run:
        print(f'+ {line}   ({args.account or "no account"})')
    else:
        POSITIONS_PATH.write_text(updated, encoding='utf-8')

    pos = next(
        (e for e in parse_positions(updated)
         if e.ticker == ticker and (args.account is None or e.account == args.account)),
        None,
    )
    if pos:
        cost = f'{pos.entry_price:.2f}' if pos.entry_price else '\u2014'
        print(f'{ticker}: {pos.shares:g} sh @ avg {cost} ({args.account or "no account"})')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
