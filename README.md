# S&P 500 Stock Screener

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Daily Screen](../../actions/workflows/daily-screen.yml/badge.svg)](../../actions/workflows/daily-screen.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A trader-style stock screener for the S&P 500, built with Python and Streamlit
on free Yahoo Finance data. Instead of listing indicator matches, it identifies
actionable trade setups, builds defined-risk trade plans, ranks them by quality,
and organizes survivors into a Core / Satellite portfolio.

> **Research and educational use only. Not investment advice.** See
> [Disclaimer](#disclaimer).


## Latest Screen

> Generated on demand via the **Daily Screen** workflow or `python scripts/generate_snapshot.py`. Mechanical, research-only.

<!-- SCREENER:START -->
![Regime](https://img.shields.io/badge/regime-Risk--On-informational) ![Watchlist](https://img.shields.io/badge/watchlist-21-blue) ![Adds](https://img.shields.io/badge/adds-14-success)

_Last updated: 2026-06-29 13:33 UTC_

> **Parameters:** Risk/trade 1% · Core band 60%–70% · Add gates conf ≥ 70 & R/R ≥ 2.5 · Max 10 single-stock names · Max position 10%

#### Watchlist (your holdings + followed names)

| Ticker | Setup | Confidence | R/R | Entry | Stop | Target | Rank Score | Actionable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TSM | Pullback | 81 | 2.38 | 442.39 | 389.30 | 568.52 | 81.10 | Yes |
| COHR | Pullback | 78 | 4.16 | 369.00 | 326.80 | 544.52 | 78.00 | Yes |
| FSELX | Pullback | 72 | 3.85 | 66.58 | 61.01 | 88.06 | 72.10 | No |
| VTI | Pullback | 62 | 2.73 | 365.27 | 355.08 | 393.12 | 62.00 | Yes |
| VXUS | Pullback | 60 | 3.96 | 84.53 | 81.88 | 95.02 | 59.60 | Yes |
| AVGO | Avoid | 0 | 8.78 | 374.05 | 359.11 | 505.23 | 0.00 | No |
| AMZN | Avoid | 0 | 7.32 | 237.59 | 230.86 | 286.79 | 0.00 | No |
| AMD | Avoid | 0 | 4.44 | 532.80 | 494.60 | 702.43 | 0.00 | No |
| AAPL | Avoid | 0 | 3.31 | 284.96 | 271.77 | 328.61 | 0.00 | No |
| META | Avoid | 0 | 3.54 | 564.63 | 535.55 | 667.45 | 0.00 | No |
| GOOGL | Avoid | 0 | 4.00 | 346.85 | 327.24 | 425.25 | 0.00 | No |
| LLY | Avoid | 0 | 1.75 | 1,233.64 | 1,085.60 | 1,492.77 | 0.00 | No |
| LRCX | Avoid | 0 | 4.41 | 388.64 | 355.53 | 534.68 | 0.00 | No |
| NFLX | Avoid | 0 | 4.85 | 74.51 | 70.26 | 95.13 | 0.00 | No |
| MU | Avoid | 0 | 4.58 | 1,099.95 | 968.40 | 1,702.74 | 0.00 | No |
| MSFT | Avoid | 0 | 3.88 | 376.22 | 346.01 | 493.34 | 0.00 | No |
| NOW | Avoid | 0 | 14.62 | 101.73 | 98.32 | 151.54 | 0.00 | No |
| SNDK | Avoid | 0 | 5.97 | 1,995.50 | 1,815.05 | 3,072.56 | 0.00 | No |
| PLTR | Avoid | 0 | 4.82 | 116.67 | 104.77 | 174.00 | 0.00 | No |
| NVDA | Avoid | 0 | 8.22 | 194.47 | 189.48 | 235.53 | 0.00 | No |
| XOM | Avoid | 0 | 11.26 | 136.99 | 134.44 | 165.72 | 0.00 | No |

#### Recommended adds (clear the gates)

| Ticker | Setup | Sleeve | Entry | Stop | Target | R/R | Confidence | Rank Score | Position Size % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MRVL | Pullback | Core | 271.11 | 238.58 | 496.91 | 6.94 | 85 | 85.00 | 4.05% |
| FLEX | Pullback | Core | 148.38 | 130.57 | 212.42 | 3.60 | 83 | 83.20 | 3.96% |
| DELL | Pullback | Core | 390.36 | 343.52 | 711.67 | 6.86 | 79 | 78.60 | 3.74% |
| COHR | Pullback | Core | 369.55 | 326.80 | 544.52 | 4.09 | 78 | 78.00 | 3.85% |
| ELV | Pullback | Core | 393.40 | 378.73 | 472.72 | 5.41 | 77 | 77.10 | 10.00% |
| EXPD | Pullback | Core | 161.53 | 152.91 | 183.28 | 2.52 | 77 | 76.60 | 8.20% |
| EBAY | Pullback | Core | 109.31 | 104.12 | 133.74 | 4.71 | 76 | 76.00 | 9.15% |
| NUE | Pullback | Core | 240.10 | 217.60 | 322.31 | 3.65 | 76 | 76.00 | 4.63% |
| INTC | Pullback | Core | 126.63 | 111.43 | 184.57 | 3.81 | 76 | 75.60 | 3.60% |
| STLD | Pullback | Core | 246.84 | 217.22 | 358.45 | 3.77 | 74 | 73.50 | 3.50% |
| ODFL | Pullback | Core | 218.99 | 193.38 | 308.62 | 3.50 | 73 | 73.00 | 3.57% |
| JBL | Pullback | Core | 358.52 | 317.40 | 535.94 | 4.32 | 72 | 72.10 | 3.59% |
| ADM | Pullback | Core | 77.71 | 71.07 | 99.12 | 3.23 | 72 | 71.80 | 4.80% |
| CDNS | Pullback | Core | 381.33 | 335.57 | 501.82 | 2.63 | 71 | 70.60 | 3.36% |

> Mechanical signals for research only — not trade recommendations.
<!-- SCREENER:END -->

## What It Does

- Universe: S&P 500 constituents only
- Market focus: NYSE, NASDAQ, AMEX (filtered via Yahoo exchange metadata)
- Data source: Yahoo Finance via `yfinance` (free)
- Behaves like a trader hunting actionable setups, not a list of indicator filters. It:
    1. Identifies a specific setup (Breakout / Volatility Contraction / Pullback / Avoid)
	2. Builds a structural trade plan (Entry / Stop / Target) with real reward/risk
	3. Explains itself (reason, key factors, risks, confidence score)
	4. Ranks survivors by composite quality adjusted for the market regime
	5. Splits survivors into a Core / Satellite portfolio with risk-based position sizes
- Only high-quality candidates survive: an identified setup (never `Avoid`), an
  asymmetric reward/risk, sufficient confidence, and tradable liquidity.
- Output table columns:
	- Ticker, Company Name
	- Setup, Sleeve, Confidence, Core Score, Rank Score
	- Position Size %
	- Entry, Stop, Target, Risk %, Risk Contribution %, Reward %, R/R
	- Reason, Key Factors, Risks
	- Trend Score, RS Outperformance, Rel Volume, Market Context
	- Market Cap, PE Ratio, Revenue Growth, Price
- Features:
	- Structural setup detection grounded in trader methodologies
	- Composite ranking by setup quality, relative strength, and reward/risk
	- Market-regime adjustment (risk-on amplifies, risk-off damps)
	- Core / Satellite portfolio construction with risk-parity position sizing
	- Adjustable screen controls (min confidence, min reward/risk, setup types)
	- Adjustable portfolio controls (core allocation, core threshold, max weight)
	- Sortable table, pagination, CSV export
	- Chart panel with selectable period and overlays:
		- Price (candlesticks)
		- EMA 20
		- SMA 50
		- SMA 200
		- RSI (separate pane with 70/30 lines)
		- Volume
	- Positions monitor: track your own holdings (any symbol, including ETFs)
	  against the 20 / 50 / 200 moving averages, with trend and
	  golden/death-cross flags. Add an entry price and share count to also see
	  unrealized P&L, position value, and portfolio weight — group holdings by
	  account (e.g. taxable vs. Roth IRA) for a per-account value and
	  concentration/risk breakdown, and repeat a ticker per lot to get a
	  share-weighted average cost basis. Your positions persist in a private,
	  git-ignored `positions.txt` (copy `positions.example.txt` to start) that
	  the app auto-loads on launch.

## Methodology

The screener encodes principles that recur across leadership-momentum and
trend-following traders (O'Neil, Minervini, Weinstein, Wyckoff, Darvas, the
Turtles) rather than arbitrary indicator thresholds:

- **Trade with the primary trend** — a trend-template score (price vs stacked
  50/150/200 MAs, rising long-term MA, position within the 52-week range)
  gates every long setup (Weinstein Stage 2, Minervini trend template).
- **Demand relative-strength leadership** — blended multi-horizon
  outperformance vs SPY, plus an RS-line-at-new-highs check (O'Neil RS,
  Minervini RS line).
- **Prefer supply drying up** — volatility contraction (short/long ATR) and
  quiet pullbacks to rising support (Minervini VCP, Wyckoff accumulation,
  Darvas boxes).
- **Confirmation over prediction** — breakouts require volume expansion;
  contractions are anticipatory and trigger only on a buy-stop through the
  pivot.
- **Capital preservation and asymmetry** — stops sit below the structure that
  invalidates the thesis (with an ATR cushion) and are capped so no single
  trade risks more than a set fraction of the position. Targets project the
  base's measured move, so every surviving plan is asymmetric by construction.
- **Market context** — the broad-market regime (SPY vs its 50/200 MAs and
  long-term slope) scales the final rank.

**Why this and not the alternatives?** A pure indicator-filter screen (e.g.
RSI band + price-above-MA) finds *matches*, not *opportunities*: it ignores
structure, can't size risk, and floods you with mediocre names. A
mean-reversion design fights the trend and depends on precise timing. The
chosen confirmation-based leadership-momentum framework instead favors a small
number of high-quality, defined-risk setups — quality over quantity.

**Architecture** mirrors the decision flow, each layer pure and testable:
`indicators` (primitives) → `features` (calculations, no decisions) → `setups`
(classification, no prices) → `trade_plan` (entry/stop/target from structure)
→ `ranking` (confidence + market-context-adjusted composite rank) → `portfolio`
(Core/Satellite sleeves + risk-based sizing) → `engine` (orchestration). All
calculations are deterministic.

## How to Read the Results Table

Each row is one S&P 500 symbol with an identified, actionable setup. Rows are
sorted by **Rank Score** (highest first) by default, so the strongest
opportunities sit at the top. You can re-sort by any column from the sidebar.

### Setup and plan columns

| Column | Meaning |
| --- | --- |
| **Setup** | The classified opportunity: `Breakout`, `Volatility Contraction`, or `Pullback`. (`Avoid` candidates are filtered out.) |
| **Confidence** | 0–100 quality score blending trend, relative strength, setup family, volume/accumulation, contraction, and reward/risk. |
| **Rank Score** | Confidence scaled by the market regime (`confidence × (0.7 + 0.3 × context)`). |
| **Entry** | Structural entry — the breakout/pullback price, or a buy-stop at the pivot for a contraction. Not defaulted to the current price unless immediate action is justified. |
| **Stop** | Protective stop below the invalidating structure (with an ATR cushion), capped so risk never exceeds the configured maximum. |
| **Target** | Profit objective from the base's measured move. |
| **Risk %** | `(Entry − Stop) / Entry`. |
| **Reward %** | `(Target − Entry) / Entry`. |
| **R/R** | Reward ÷ Risk. Survivors are **≥ 2** by default. |

### Explainability columns

- **Reason**: one-line rationale for the classification.
- **Key Factors**: the supporting evidence (trend, RS, volume, structure).
- **Risks**: what could invalidate the setup.

### Setup types

- **Breakout** — Price cleared a base pivot in a leading uptrend, confirmed by volume expansion. Momentum continuation.
- **Volatility Contraction** — Supply is drying up (short/long ATR contracting) while price coils just below a pivot. Anticipatory; triggers on a buy-stop through the pivot.
- **Pullback** — Established uptrend that dipped to rising support (20 EMA / 50 MA) on quiet volume while still leading SPY. Buy-the-dip continuation. (Backtesting's strongest, most statistically significant edge.)

> **Reversal** setups were removed: backtesting showed negative expectancy (a high hit rate but an inverted ~0.85 reward/risk), so counter-trend conditions are now treated as `Avoid`.

### Portfolio columns (Core / Satellite)

After screening, survivors are organized into a classic **core-satellite**
portfolio so the table reads as an allocation plan, not just a watchlist:

- **Sleeve** — `Core` (durable trend-continuation leaders: pullbacks /
  contractions in larger, trending names — backtesting's strongest edge) or
  `Satellite` (higher-octane tactical plays, mostly breakouts / smaller names).
- **Core Score** — 0–1 *core-ness* blend of setup family (40%), confidence
  (20%), market-cap/liquidity on a log scale (20%), and trend persistence
  (20%). At or above the threshold (default 0.60) a name joins the Core sleeve.
- **Position Size %** — suggested weight as a share of the whole book. Capital
  is split by the **core allocation** (default 70% Core / 30% Satellite), then
  within each sleeve positions are sized by **risk parity** — equal risk budget
  per name (inverse of the entry-to-stop distance), tilted by confidence — and
  capped per name (default 10%). If a sleeve has too few names to deploy its
  allocation under the cap, the remainder is implicitly held as cash.
- **Risk Contribution %** — capital actually at risk in that name
  (`Position Size % × Risk %`); summed per sleeve it is the *portfolio heat*.

A per-sleeve summary panel above the table rolls up positions, allocation,
portfolio heat, and average quality for Core, Satellite, and the total book.
All portfolio controls live in the sidebar and the columns are included in the
CSV export.

### Context columns

- **Trend Score**: fraction of trend-template conditions met (1.0 = textbook uptrend).
- **RS Outperformance**: blended multi-horizon return vs SPY (positive = leading).
- **Rel Volume**: latest volume vs its average (× the norm).
- **Market Context**: broad-market regime (`Risk-On` / `Neutral` / `Risk-Off`).
- **Market Cap / PE Ratio / Revenue Growth**: fundamentals (blank when Yahoo omits them).
- **Price**: latest close.

> These are mechanical signals for research only — not trade recommendations.
Always confirm with your own analysis.

## Project Structure

```
stock-screener/
├── .github/
│   └── workflows/
│       ├── ci.yml                 # tests + lint on push/PR
│       └── daily-screen.yml       # scheduled README snapshot
├── scripts/
│   └── generate_snapshot.py       # headless screen -> README injection
├── src/
│   ├── app.py                     # Streamlit UI
│   ├── config.py                  # Settings + env loading
│   ├── analysis/
│   │   ├── indicators.py          # SMA/EMA/RSI/ATR/OBV primitives
│   │   ├── relative_strength.py   # RS vs benchmark
│   │   └── features.py            # MarketFeatures (pure calculations)
│   ├── data/
│   │   ├── cache.py               # SQLite TTL cache
│   │   ├── rate_limiter.py        # request throttling + backoff
│   │   ├── universe.py            # S&P 500 constituents
│   │   └── yahoo_client.py        # yfinance fetch + retries
│   ├── export/
│   │   ├── markdown_format.py     # shared Markdown primitives
│   │   └── markdown_export.py     # snapshot/README rendering
│   ├── screener/
│   │   ├── strategy.py            # central StrategyConfig thresholds
│   │   ├── setups.py              # setup classification
│   │   ├── trade_plan.py          # entry/stop/target from structure
│   │   ├── ranking.py             # confidence + composite rank
│   │   ├── portfolio.py           # Core/Satellite + risk-parity sizing
│   │   ├── holdings.py            # positions parsing + MA/P&L monitor
│   │   ├── result.py              # result schema
│   │   └── engine.py              # pipeline orchestration
│   └── utils/
│       ├── errors.py
│       ├── logger.py
│       └── numeric.py             # shared clamp/is_nan helpers
├── tests/
│   ├── integration/
│   └── unit/
├── pyproject.toml
├── requirements.txt               # runtime dependencies
└── requirements-dev.txt           # + testing and linting
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run src/app.py
```

For development (tests + linting), install the dev extras instead:

```bash
pip install -r requirements-dev.txt
```

## Position Management & Daily Report

The app doubles as a personal position-management tool built around a
privacy-preserving two-file model:

| File | Committed? | Contents |
| --- | --- | --- |
| `portfolio.txt` | Yes | Composition only — `[Account]` sections with `TICKER, core|satellite` lines. No sizes. |
| `positions.txt` | **No** (git-ignored) | Private sizes — `[Account]` sections with `TICKER, cost_basis, shares` lines, plus a `cash = NNNN` directive per account (or a single `account_value = NNNNN`). Copy `positions.example.txt` to start. |
| `watchlist.txt` | Yes | Tickers you follow but do not hold. |
| `reports/daily_report.md` | **No** (git-ignored) | Latest generated report (overwritten each run). |

The app **merges** the two files at runtime: sleeve and membership come from the
committed `portfolio.txt`, while share counts and cost basis stay in the private
`positions.txt`, so your real sizes never get committed. The **Publish
composition** button regenerates `portfolio.txt` from your current holdings
(tickers + sleeve only). Add a `cash = NNNN` line per `[Account]` for free cash
(e.g. SPAXX); the totals are summed and your **account value = current holdings +
cash**, which keeps buy sizing capped to what you can actually spend. As an
alternative, set a single `account_value` total directly; it supports
`+`-separated sums, e.g. `account_value = 2310.60 + 5269.23`, and cash is then
inferred as account value minus holdings.

The daily report (`scripts/daily_report.py`) adds an **Income to reconcile**
digest: dividends and fund capital-gains distributions are read from the
(already batched) price history at no extra request cost, multiplied by your
held shares, and grouped per account so you can top up the right `cash` line.
A git-ignored watermark (`reports/.income_ledger.json`) surfaces each ex-date
exactly once; `SCREENER_DIVIDEND_LOOKBACK_DAYS` (default 7) bounds the first run.
Estimates are informational — your broker's cash remains the source of truth, so
nothing is credited automatically.

Position sizing uses **1% account risk per trade** (`SCREENER_RISK_PER_TRADE`),
capped by the per-name weight limit. Every add shows a risk-based **Max add**
(the ceiling) alongside a **Suggested add** starter tranche — by default half
the max (`SCREENER_SUGGESTED_ADD_FRACTION`, `0 < f <= 1`) — entered now, with the
remainder added once the trade is up **+1R** (`SCREENER_SUGGESTED_ADD_TRIGGER_R`)
and the stop moved to breakeven. Backtesting (`scripts/backtest_scalein.py`)
found this staged entry roughly halves drawdown versus committing full size at
once, while adding earlier (+0.5R) or never completing the add both underperform.
Core allocation targets **60–70%**
(`SCREENER_CORE_ALLOCATION_MIN` / `_MAX`), and the app flags when you exceed the
**individual-stock cap** (`SCREENER_MAX_INDIVIDUAL_STOCKS`, ETFs excluded).
Recommended Adds uses tight gates by default (confidence ≥ 85, R/R ≥ 2.5).

### Daily report

Generate a local Markdown snapshot (positions status, add sizes, recommended
adds, allocation, risk, and concentration) without launching the app:

```bash
python scripts/daily_report.py
```

It writes a single file, `reports/daily_report.md`, **overwritten on every run**
(no history is kept). Network failures are caught and turned into an
"unavailable" notice rather than crashing.

To run it automatically each day, schedule it with **Windows Task Scheduler**
(Create Basic Task → Daily → Start a program):

- Program/script: `C:\path\to\stock-screener\.venv\Scripts\python.exe`
- Arguments: `scripts\daily_report.py`
- Start in: `C:\path\to\stock-screener`

On macOS/Linux, use a `cron` entry such as
`0 7 * * * cd /path/to/stock-screener && .venv/bin/python scripts/daily_report.py`.

## Configuration

All settings have sensible defaults and can be overridden with `SCREENER_*`
environment variables exported in your shell (the app reads the process
environment directly). Use [`.env.example`](.env.example) as a reference for the
available variables. The most commonly adjusted values:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SCREENER_CACHE_DIR` | `.cache` | SQLite cache location |
| `SCREENER_CACHE_TTL_HOURS` | `24` | Cache freshness window |
| `SCREENER_MAX_RETRIES` | `4` | Yahoo request retry attempts |
| `SCREENER_REQUEST_DELAY_SECONDS` | `0.25` | Throttle between requests |
| `SCREENER_FUNDAMENTALS_MAX_WORKERS` | `8` | Fundamentals fetch concurrency |
| `SCREENER_FUNDAMENTALS_TTL_HOURS` | `24` | Separate (longer) cache for slow-moving fundamentals; keep high to lower `CACHE_TTL_HOURS` for fresher prices without a fundamentals re-fetch storm |
| `SCREENER_MIN_AVG_VOLUME` | `500000` | Liquidity gate |
| `SCREENER_SMA_SHORT_WINDOW` / `SCREENER_SMA_LONG_WINDOW` | `50` / `200` | Trend MAs |
| `SCREENER_EMA_WINDOW` | `20` | Fast EMA |
| `SCREENER_ATR_PERIOD` / `SCREENER_ATR_STOP_MULTIPLIER` | `14` / `2.0` | Volatility + stop cushion |
| `SCREENER_CORE_ALLOCATION` | `0.70` | Core sleeve share of capital |
| `SCREENER_CORE_SCORE_THRESHOLD` | `0.60` | Core vs Satellite cutoff |
| `SCREENER_MAX_POSITION_WEIGHT` | `0.10` | Per-name position cap |
| `SCREENER_WATCHLIST_AUTO_CONFIDENCE` | `80` | Recommended adds at/above this confidence auto-join `watchlist.txt` |

See [`.env.example`](.env.example) for the complete list, including the daily
snapshot variables.

## Development

```bash
ruff check .     # lint
pytest           # run the test suite
```

## Error Handling and Rate Limits

- Exponential backoff retry in Yahoo requests
- Per-request delay throttling
- Cache-first reads to reduce API pressure
- Partial-failure tolerance (bad symbols are skipped)

## Performance Notes

- Caches both historical prices and fundamentals in SQLite (`.cache/screener_cache.sqlite3`)
- Daily cache TTL by default
- Manual cache reset via the app button
- Warm-cache runs are much faster than first runs

## Roadmap

Possible future enhancements:

- Strict fundamentals mode (exclude symbols missing PE or revenue growth).
- Supplemental free data sources (e.g. SEC EDGAR insider activity).

## Disclaimer

This project is for research and educational purposes only. It produces
mechanical signals, **not** investment advice or trade recommendations. Market
data may be delayed or incomplete, and past performance does not guarantee
future results. Always do your own analysis. Use at your own risk.

## License

Released under the [MIT License](LICENSE).

