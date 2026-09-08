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

_Last updated: 2026-09-08 22:38 UTC_

> **Parameters:** Signal model ma_dc_volume_regime · Gates conf ≥ 80 & R/R ≥ 2.5 · Min avg volume 500,000

#### Watchlist (followed names)

| Ticker | Setup | Confidence | R/R | Entry | Stop | Target | Rank Score | Beta | ATR % | Dist 200D % | Return 3M | Div Yield | Dollar ADV | Sector | Actionable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | Pullback | 62 | 4.15 | 315.80 | 298.12 | 389.14 | 61.50 | 0.68 | 2.37% | 11.30% | 4.87% | 0.33% | 15,378,076,077 | Technology | Yes |
| AMZN | Avoid | 0 | 14.69 | 256.97 | 252.81 | 318.01 | 0.00 | 1.41 | 2.52% | 7.39% | 4.79% | 0.00% | 10,843,690,578 | Consumer Cyclical | No |
| APP | Avoid | 0 | 8.56 | 312.01 | 295.62 | 452.30 | 0.00 | 2.14 | 5.45% | -35.66% | -44.65% | 0.00% | 1,882,063,399 | Communication Services | No |
| ASTS | Avoid | 0 | 2.81 | 66.12 | 58.19 | 88.40 | 0.00 | 3.71 | 6.92% | -18.82% | -28.18% | 0.00% | 901,182,949 | Technology | No |
| BABA | Avoid | 0 | 5.93 | 112.66 | 108.80 | 135.56 | 0.00 | 1.28 | 3.10% | -16.68% | -6.17% | 6.40% | 1,375,977,741 | Consumer Cyclical | No |
| CRDO | Avoid | 0 | 10.76 | 167.75 | 156.09 | 293.24 | 0.00 | 3.26 | 11.11% | -4.41% | -24.53% | 0.00% | 1,073,384,579 | Technology | No |
| CRWV | Avoid | 0 | 5.74 | 99.83 | 89.90 | 156.77 | 0.00 | 3.32 | 6.78% | 8.99% | -2.48% | 0.00% | 2,737,263,594 | Technology | No |
| GOOGL | Avoid | 0 | 14.47 | 338.36 | 334.21 | 398.40 | 0.00 | 1.36 | 2.36% | 0.64% | -6.87% | 0.25% | 9,176,589,282 | Communication Services | No |
| IREN | Avoid | 0 | 9.40 | 46.93 | 44.76 | 67.29 | 0.00 | 3.84 | 7.56% | 2.80% | -20.71% | 0.00% | 2,127,145,897 | Financial Services | No |
| META | Avoid | 0 | 4.63 | 613.48 | 591.82 | 713.79 | 0.00 | 1.41 | 3.22% | -1.43% | 4.80% | 0.34% | 11,052,514,553 | Communication Services | No |
| MSFT | Avoid | 0 | 10.27 | 493.95 | 481.38 | 622.99 | 0.00 | 0.96 | 2.36% | 14.59% | 19.97% | 0.73% | 15,863,702,840 | Technology | No |
| NFLX | Avoid | 0 | 9.01 | 76.77 | 75.32 | 89.82 | 0.00 | 0.27 | 3.11% | -11.45% | -7.10% | 0.00% | 2,957,790,225 | Communication Services | No |
| NVDA | Avoid | 0 | 2.73 | 225.73 | 209.36 | 270.48 | 0.00 | 1.92 | 3.32% | 14.64% | 8.19% | 0.12% | 29,372,055,373 | Technology | No |
| ORCL | Avoid | 0 | 2.88 | 162.52 | 143.02 | 218.72 | 0.00 | 2.06 | 4.39% | -3.55% | -23.27% | 1.26% | 5,160,104,813 | Technology | No |
| RKLB | Avoid | 0 | 5.28 | 65.87 | 60.45 | 94.50 | 0.00 | 3.66 | 6.07% | -17.24% | -42.04% | 0.00% | 1,267,405,806 | Industrials | No |
| TSLA | Avoid | 0 | 6.07 | 368.16 | 353.89 | 454.82 | 0.00 | 2.27 | 4.16% | -7.82% | -9.97% | 0.00% | 14,803,582,233 | Consumer Cyclical | No |
| VST | Avoid | 0 | 6.12 | 151.72 | 148.04 | 174.21 | 0.00 | 1.49 | 3.60% | -3.76% | 3.28% | 0.61% | 662,435,251 | Utilities | No |

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

