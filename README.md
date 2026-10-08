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

_Last updated: 2026-10-08 16:39 UTC_

> **Parameters:** Signal model ma_dc_volume_regime · Gates conf ≥ 80 & R/R ≥ 2.5 · Min avg volume 500,000

#### Watchlist (followed names)

| Ticker | Setup | Confidence | R/R | Entry | Stop | Target | Rank Score | Beta | ATR % | Dist 200D % | Return 3M | Div Yield | Dollar ADV | Sector | Actionable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MSFT | Pullback | 73 | 2.58 | 511.81 | 483.27 | 585.38 | 72.70 | 0.97 | 2.06% | 22.37% | 37.84% | 0.69% | 14,069,564,734 | Technology | No |
| NVDA | Pullback | 69 | 2.26 | 229.10 | 207.56 | 277.81 | 68.90 | 1.88 | 2.33% | 16.62% | 11.64% | 0.12% | 27,808,904,295 | Technology | No |
| META | Pullback | 68 | 3.48 | 707.65 | 622.73 | 1,003.54 | 68.10 | 1.46 | 3.12% | 14.13% | 7.42% | 0.29% | 13,996,925,003 | Communication Services | No |
| AAPL | Pullback | 61 | 1.95 | 332.72 | 307.79 | 381.28 | 60.90 | 0.68 | 1.90% | 16.43% | 7.23% | 0.31% | 14,795,921,379 | Technology | No |
| GOOGL | Pullback | 58 | 3.70 | 345.91 | 325.64 | 420.91 | 57.80 | 1.34 | 2.40% | 2.82% | -2.18% | 0.24% | 9,001,892,704 | Communication Services | No |
| BABA | Avoid | 0 | 11.27 | 105.60 | 104.23 | 121.00 | 0.00 | 1.28 | 2.90% | -18.85% | -5.99% | 6.77% | 1,088,513,415 | Consumer Cyclical | No |
| AMZN | Avoid | 0 | 17.03 | 258.67 | 257.30 | 281.93 | 0.00 | 1.43 | 2.09% | 6.88% | 5.43% | 0.00% | 10,083,562,844 | Consumer Cyclical | No |
| ASTS | Avoid | 0 | 4.59 | 56.95 | 54.38 | 68.73 | 0.00 | 3.75 | 7.28% | -29.63% | -22.33% | 0.00% | 613,286,048 | Technology | No |
| APP | Avoid | 0 | 4.97 | 277.55 | 263.17 | 349.05 | 0.00 | 2.15 | 5.29% | -38.06% | -45.25% | 0.00% | 1,626,286,968 | Communication Services | No |
| IREN | Avoid | 0 | 19.40 | 36.22 | 35.46 | 50.77 | 0.00 | 3.80 | 7.30% | -20.63% | -11.97% | 0.00% | 1,498,006,376 | Financial Services | No |
| CRWV | Avoid | 0 | 13.78 | 84.18 | 82.27 | 110.50 | 0.00 | 3.22 | 5.97% | -9.10% | -5.28% | 0.00% | 2,404,500,561 | Technology | No |
| CRDO | Avoid | 0 | 6.98 | 219.74 | 206.10 | 315.07 | 0.00 | 3.28 | 6.57% | 22.82% | -14.76% | 0.00% | 1,573,545,491 | Technology | No |
| NFLX | Avoid | 0 | 3.34 | 71.19 | 66.08 | 88.25 | 0.00 | 0.32 | 2.58% | -14.81% | -2.96% | 0.00% | 2,284,902,676 | Communication Services | No |
| ORCL | Avoid | 0 | 3.20 | 142.27 | 130.06 | 181.39 | 0.00 | 2.01 | 4.28% | -12.21% | 1.16% | 1.39% | 4,138,528,470 | Technology | No |
| RKLB | Avoid | 0 | 10.47 | 69.10 | 67.40 | 86.87 | 0.00 | 3.70 | 5.83% | -15.38% | -14.73% | 0.00% | 1,324,400,719 | Industrials | No |
| TSLA | Avoid | 0 | 1.83 | 373.17 | 350.36 | 414.79 | 0.00 | 2.21 | 3.07% | -4.59% | -8.48% | 0.00% | 13,465,142,283 | Consumer Cyclical | No |
| VST | Avoid | 0 | 7.87 | 157.49 | 153.01 | 192.80 | 0.00 | 1.50 | 4.42% | 1.77% | -0.86% | 0.55% | 846,744,818 | Utilities | No |

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

