# S&P 500 Stock Screener

[![CI](../../actions/workflows/ci.yml/badge.svg)](../../actions/workflows/ci.yml)
[![Daily Screen](../../actions/workflows/daily-screen.yml/badge.svg)](../../actions/workflows/daily-screen.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

A trader-style stock screener for the S&P 500, built with Python and Streamlit
on free Yahoo Finance data. Instead of listing indicator matches, it identifies
actionable trade setups, builds defined-risk structural trade plans, and ranks
them by quality adjusted for the market regime.

> **Research and educational use only. Not investment advice.** See
> [Disclaimer](#disclaimer).


## Latest Screen

> Generated on demand via the **Daily Screen** workflow or `python scripts/generate_snapshot.py`. Mechanical, research-only.

<!-- SCREENER:START -->
![Regime](https://img.shields.io/badge/regime-Risk--On-informational) ![Watchlist](https://img.shields.io/badge/watchlist-17-blue) ![Adds](https://img.shields.io/badge/adds-0-success)

_Last updated: 2026-10-27 05:58 UTC_

> **Parameters:** Signal model ma_dc_volume_regime · Gates conf ≥ 80 & R/R ≥ 2.5 · Min avg volume 500,000

#### Watchlist (followed names)

| Ticker | Setup | Confidence | R/R | Entry | Stop | Target | Rank Score | Beta | ATR % | Dist 200D % | Return 3M | Div Yield | Dollar ADV | Sector | Actionable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MSFT | Pullback | 72 | 2.18 | 525.53 | 484.41 | 615.07 | 66.88 | 1.02 | 2.12% | 21.94% | 35.40% | 0.69% | 11,306,261,300 | Technology | No |
| AAPL | Pullback | 67 | 2.31 | 340.35 | 324.20 | 377.65 | 61.88 | 0.57 | 1.87% | 16.64% | 1.13% | 0.30% | 13,947,040,467 | Technology | No |
| AMZN | Avoid | 0 | 4.95 | 249.09 | 244.84 | 270.13 | 0.00 | 1.47 | 2.59% | 2.38% | 7.90% | 0.00% | 8,687,952,193 | Consumer Cyclical | No |
| ASTS | Avoid | 0 | 7.70 | 39.45 | 35.72 | 68.20 | 0.00 | 3.82 | 10.18% | -49.79% | -30.24% | 0.00% | 507,974,069 | Technology | No |
| APP | Avoid | 0 | 9.81 | 260.74 | 252.43 | 342.22 | 0.00 | 2.22 | 4.64% | -38.47% | -37.65% | 0.00% | 1,203,349,473 | Communication Services | No |
| CRDO | Avoid | 0 | 7.32 | 151.15 | 139.03 | 239.85 | 0.00 | 3.36 | 10.21% | -16.45% | -21.39% | 0.00% | 1,247,583,585 | Technology | No |
| CRWV | Avoid | 0 | 7.69 | 55.19 | 49.73 | 97.16 | 0.00 | 3.60 | 10.92% | -39.94% | -17.99% | 0.00% | 2,088,693,093 | Technology | No |
| GOOGL | Avoid | 0 | 20.83 | 316.80 | 314.52 | 364.37 | 0.00 | 1.38 | 2.63% | -7.17% | -5.07% | 0.27% | 7,750,640,956 | Communication Services | No |
| BABA | Avoid | 0 | 13.53 | 100.25 | 98.70 | 121.19 | 0.00 | 1.13 | 3.03% | -21.38% | -12.97% | 7.27% | 1,019,041,450 | Consumer Cyclical | No |
| IREN | Avoid | 0 | 10.80 | 25.43 | 23.05 | 51.08 | 0.00 | 4.02 | 10.46% | -43.28% | -25.05% | 0.00% | 1,145,889,393 | Financial Services | No |
| META | Avoid | 0 | 16.58 | 630.56 | 621.39 | 782.58 | 0.00 | 1.52 | 4.07% | -0.30% | 6.26% | 0.33% | 13,027,501,967 | Communication Services | No |
| NFLX | Avoid | 0 | 10.48 | 63.90 | 62.31 | 80.52 | 0.00 | 0.21 | 3.41% | -22.21% | -11.73% | 0.00% | 2,301,081,229 | Communication Services | No |
| NVDA | Avoid | 0 | 4.52 | 216.00 | 208.65 | 249.19 | 0.00 | 1.93 | 2.83% | 5.98% | 9.64% | 0.13% | 24,793,232,544 | Technology | No |
| ORCL | Avoid | 0 | 6.30 | 126.06 | 121.16 | 156.90 | 0.00 | 2.22 | 5.07% | -20.33% | 5.09% | 1.59% | 3,667,503,092 | Technology | No |
| RKLB | Avoid | 0 | 5.23 | 53.82 | 48.27 | 82.85 | 0.00 | 3.88 | 7.26% | -33.09% | -15.76% | 0.00% | 1,042,269,395 | Industrials | No |
| TSLA | Avoid | 0 | 5.80 | 391.62 | 382.76 | 443.01 | 0.00 | 2.23 | 3.44% | 1.42% | 27.38% | 0.00% | 14,723,559,944 | Consumer Cyclical | No |
| VST | Avoid | 0 | 4.72 | 141.73 | 134.25 | 177.04 | 0.00 | 1.57 | 5.41% | -8.06% | -4.65% | 0.65% | 819,659,431 | Utilities | No |

#### Recommended adds (clear the screen gates)

_No candidates cleared the recommendation gates — sitting tight._

> Mechanical signals for research only — not trade recommendations.
<!-- SCREENER:END -->

## What It Does

- Universe: S&P 500 constituents only
- Market focus: NYSE, NASDAQ, AMEX (filtered via Yahoo exchange metadata)
- Data source: Yahoo Finance via `yfinance` (free)
- Behaves like a trader hunting actionable setups, not a list of indicator filters. It:
    1. Identifies a specific setup (Breakout / Pullback / Avoid)
	2. Builds a structural trade plan (Entry / Stop / Target) with real reward/risk
	3. Explains itself (reason, key factors, risks, confidence score)
	4. Ranks survivors by composite quality adjusted for the market regime
- Only high-quality candidates survive: an identified setup (never `Avoid`), an
  asymmetric reward/risk, sufficient confidence, and tradable liquidity.
- Output table columns:
	- Ticker, Company Name
	- Setup, Confidence, Rank Score
	- Entry, Stop, Target, Risk %, Reward %, R/R
	- Reason, Key Factors, Risks
	- Trend Score, RS Outperformance, Rel Volume, Market Context
	- Market Cap, PE Ratio, Revenue Growth, Price
- Features:
	- Structural setup detection grounded in trader methodologies
	- Composite ranking by setup quality, relative strength, and reward/risk
	- Market-regime adjustment (risk-on amplifies, risk-off damps)
	- Adjustable screen controls (min confidence, min reward/risk, setup types)
	- Sortable results table and CSV export
	- Chart panel with selectable period and overlays:
		- Price (candlesticks)
		- EMA 20
		- SMA 50
		- SMA 200
		- RSI (separate pane with 70/30 lines)
		- Volume
	- Structural trade-plan overlays (entry / stop / target) on the chart for
	  any name with a computable setup.

## Methodology

The screener runs a deliberately lightweight, **volume-primary** model built on
three signals rather than a large blend of indicators:

- **Moving-average trend structure** — a setup only fires in a healthy uptrend
  (price above a rising long MA, fast MA above the long MA). No trend, no trade.
- **Donchian channel levels** — the actionable level is the N-day channel: a
  clean breakout of the prior high, or a pullback holding above the long MA
  while below the channel top.
- **Volume is the decisive confirmation** — a breakout must arrive on a genuine
  volume surge *and* net accumulation (up/down volume, OBV); a pullback must be
  quiet (supply absorbed) yet still show accumulation. Volume failure demotes an
  otherwise-aligned chart to `Avoid`.
- **Regime awareness** — breakouts taken while the broad market is risk-off (SPY
  below its 200-day) were negative-EV in backtests, so the default model
  suppresses them.
- **Capital preservation and asymmetry** — stops sit below the structure that
  invalidates the thesis (with an ATR cushion) and are capped so no single trade
  risks more than a set fraction of the position. Targets project the base's
  measured move, so every surviving plan is asymmetric by construction.
- **Market context** — the broad-market regime (SPY vs its 50/200 MAs and
  long-term slope) scales the final rank.

**Why this and not the alternatives?** A pure indicator-filter screen (e.g.
RSI band + price-above-MA) finds *matches*, not *opportunities*: it ignores
structure, can't size risk, and floods you with mediocre names. A large
multi-signal blend is prone to overfitting and hides which inputs actually
carry edge. The volume-primary model keeps a small, interpretable signal set —
trend, channel, volume — that survived survivorship-adjusted, walk-forward
testing, and pairs it with defined-risk, asymmetric plans — quality over quantity.

**Architecture** mirrors the decision flow, each layer pure and testable:
`indicators` (primitives) → `features` (calculations, no decisions) → `setups`
(classification, no prices) → `trade_plan` (entry/stop/target from structure)
→ `ranking` (confidence + market-context-adjusted composite rank) → `engine`
(orchestration). All calculations are deterministic.

### Signal model (default: `ma_dc_volume_regime`)

The entry engine is selectable via `SCREENER_SIGNAL_MODEL`. The **default is the
regime-aware volume model**, a deliberately lightweight system built on three
signals — **moving-average trend structure**, **Donchian channel** levels, and
**volume as the decisive confirmation** — with one regime rule: **suppress
breakouts while SPY trades below its 200-day** (edge attribution showed those
are negative-EV). It led every risk-adjusted metric in survivorship-adjusted,
walk-forward testing on a large + mid-cap universe, with lower turnover.

| `SCREENER_SIGNAL_MODEL` | Description |
| --- | --- |
| `ma_dc_volume_regime` | **Default.** Volume-primary MA + Donchian, risk-off breakouts suppressed. |
| `ma_dc_volume` | Same, without the regime suppression (ablation). |

## How to Read the Results Table

Each row is one S&P 500 symbol with an identified, actionable setup. Rows are
sorted by **Rank Score** (highest first) by default, so the strongest
opportunities sit at the top. You can re-sort by any column from the sidebar.

### Setup and plan columns

| Column | Meaning |
| --- | --- |
| **Setup** | The classified opportunity: `Breakout` or `Pullback`. (`Avoid` candidates are filtered out.) |
| **Confidence** | 0–100 quality score blending trend, relative strength, setup family, volume/accumulation, and reward/risk. |
| **Rank Score** | Confidence scaled by the market regime (`confidence × (0.7 + 0.3 × context)`). |
| **Entry** | Structural entry — the breakout or pullback price. Not defaulted to the current price unless immediate action is justified. |
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
- **Pullback** — Established uptrend that dipped to rising support (20 EMA / 50 MA) on quiet volume while still leading SPY. Buy-the-dip continuation. (Backtesting's strongest, most statistically significant edge.)

> **Reversal** setups were removed: backtesting showed negative expectancy (a high hit rate but an inverted ~0.85 reward/risk), so counter-trend conditions are now treated as `Avoid`.

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
│   │   ├── result.py              # result schema
│   │   └── engine.py              # pipeline orchestration
│   └── utils/
│       ├── errors.py
│       ├── logger.py
│       └── numeric.py             # shared clamp helper
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

## Usage

The screener has two surfaces, both driven by the same pipeline:

**Interactive app** — `streamlit run src/app.py`. Set the screen gates in the
sidebar (min confidence, min reward/risk, setup types), run the screen over the
S&P 500 plus your watchlist, and chart any name with its structural
entry / stop / target overlaid.

**Headless snapshot** — `python scripts/generate_snapshot.py` screens the S&P
500 (plus your watchlist) and writes a Markdown block into the README between the
`SCREENER:START` / `SCREENER:END` markers. This is what the scheduled **Daily
Screen** workflow runs. `SCREENER_SNAPSHOT_SYMBOLS=30` caps the universe for a
quick run; `0` (default) screens the entire S&P 500.

### Watchlist

`watchlist.txt` (committed) is an optional list of extra tickers to screen and
chart alongside the S&P 500 — one ticker per line, `#` for comments. It carries
no positions, sizes, or cost basis; it is purely a list of candidates.

Recommendations are **suppressed in a risk-off regime** — when SPY trades below
its long (200-day) moving average — because backtests show entries taken below
the 200-day roughly halve expectancy. Set `SCREENER_REQUIRE_REGIME_FOR_ADDS=false`
to keep surfacing candidates regardless of regime.

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
| `SCREENER_FUNDAMENTALS_MAX_WORKERS` | `8` | Concurrency for per-ticker Yahoo lookups (fundamentals, earnings, fund holdings) |
| `SCREENER_FUNDAMENTALS_TTL_HOURS` | `24` | Separate (longer) cache for slow-moving fundamentals; keep high to lower `CACHE_TTL_HOURS` for fresher prices without a fundamentals re-fetch storm |
| `SCREENER_MIN_AVG_VOLUME` | `500000` | Liquidity gate |
| `SCREENER_SMA_SHORT_WINDOW` / `SCREENER_SMA_LONG_WINDOW` | `50` / `200` | Trend MAs |
| `SCREENER_EMA_WINDOW` | `20` | Fast EMA |
| `SCREENER_ATR_PERIOD` / `SCREENER_ATR_STOP_MULTIPLIER` | `14` / `2.0` | Volatility + stop cushion |
| `SCREENER_REC_MIN_CONFIDENCE` / `SCREENER_REC_MIN_REWARD_RISK` | `80` / `2.5` | Recommendation gates (min confidence, min reward:risk) |
| `SCREENER_REQUIRE_REGIME_FOR_ADDS` | `true` | Suppress recommendations while SPY is risk-off (below its 200-day) |
| `SCREENER_SIGNAL_MODEL` | `ma_dc_volume_regime` | Entry model: `ma_dc_volume_regime` (default) or `ma_dc_volume`. See [Signal model](#signal-model-default-ma_dc_volume_regime). |

See [`.env.example`](.env.example) for the complete list, including the daily
snapshot variables.

## Development

```bash
ruff check .                             # lint
mypy                                     # static type check
pytest --cov=src --cov-report=term-missing   # tests + coverage
```

CI (`.github/workflows/ci.yml`) runs the same lint, type-check, and test steps
on Python 3.11, 3.12, and 3.13 for every push and pull request.

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

