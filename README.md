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
![Regime](https://img.shields.io/badge/regime-Risk--On-informational) ![Watchlist](https://img.shields.io/badge/watchlist-17-blue) ![Adds](https://img.shields.io/badge/adds-1-success)

_Last updated: 2026-09-19 21:01 UTC_

> **Parameters:** Signal model ma_dc_volume_regime · Gates conf ≥ 80 & R/R ≥ 2.5 · Min avg volume 500,000

#### Watchlist (followed names)

| Ticker | Setup | Confidence | R/R | Entry | Stop | Target | Rank Score | Beta | ATR % | Dist 200D % | Return 3M | Div Yield | Dollar ADV | Sector | Actionable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | Avoid | 0 | 2.13 | 336.13 | 318.32 | 374.05 | 0.00 | 0.68 | 2.17% | 17.39% | 12.79% | 0.31% | 16,174,437,349 | Technology | No |
| META | Avoid | 0 | 3.26 | 665.75 | 618.85 | 818.63 | 0.00 | 1.37 | 3.19% | 6.66% | 15.34% | 0.31% | 11,964,088,062 | Communication Services | No |
| TSLA | Avoid | 0 | 3.86 | 364.27 | 348.02 | 427.06 | 0.00 | 2.23 | 3.63% | -8.32% | -9.04% | 0.00% | 13,911,943,703 | Consumer Cyclical | No |
| RKLB | Avoid | 0 | 5.23 | 64.57 | 59.53 | 90.89 | 0.00 | 3.65 | 6.04% | -19.76% | -39.79% | 0.00% | 1,196,868,740 | Industrials | No |
| ORCL | Avoid | 0 | 3.91 | 147.61 | 139.09 | 180.88 | 0.00 | 2.06 | 5.18% | -11.21% | -19.90% | 1.33% | 4,763,665,216 | Technology | No |
| NVDA | Avoid | 0 | 2.86 | 222.27 | 212.67 | 249.78 | 0.00 | 1.92 | 2.89% | 12.04% | 5.50% | 0.13% | 27,885,158,112 | Technology | No |
| NFLX | Avoid | 0 | 5.90 | 71.79 | 69.50 | 85.28 | 0.00 | 0.29 | 3.39% | -16.02% | -7.22% | 0.00% | 2,697,188,670 | Communication Services | No |
| MSFT | Avoid | 0 | 3.89 | 493.78 | 483.35 | 534.41 | 0.00 | 0.96 | 2.15% | 14.41% | 30.15% | 0.73% | 14,393,914,103 | Technology | No |
| IREN | Avoid | 0 | 7.51 | 46.68 | 44.75 | 61.16 | 0.00 | 3.79 | 6.77% | 2.50% | -22.15% | 0.00% | 2,069,371,374 | Financial Services | No |
| AMZN | Avoid | 0 | 3.28 | 253.71 | 242.79 | 289.55 | 0.00 | 1.43 | 2.38% | 5.58% | 3.81% | 0.00% | 10,088,766,746 | Consumer Cyclical | No |
| GOOGL | Avoid | 0 | 5.23 | 349.54 | 343.48 | 381.24 | 0.00 | 1.35 | 2.40% | 3.57% | -5.02% | 0.24% | 9,519,521,497 | Communication Services | No |
| CRWV | Avoid | 0 | 8.64 | 81.36 | 76.82 | 120.58 | 0.00 | 3.27 | 7.12% | -11.64% | -31.02% | 0.00% | 2,306,372,795 | Technology | No |
| CRDO | Avoid | 0 | 37.73 | 175.89 | 172.26 | 312.99 | 0.00 | 3.26 | 8.13% | 0.03% | -35.29% | 0.00% | 1,143,723,666 | Technology | No |
| BABA | Avoid | 0 | 3.51 | 113.24 | 105.85 | 139.17 | 0.00 | 1.24 | 2.80% | -15.04% | 5.73% | 6.67% | 1,240,386,547 | Consumer Cyclical | No |
| ASTS | Avoid | 0 | 8.38 | 58.52 | 56.21 | 77.90 | 0.00 | 3.73 | 7.26% | -28.35% | -27.45% | 0.00% | 723,377,313 | Technology | No |
| APP | Avoid | 0 | 4.43 | 308.06 | 296.00 | 361.49 | 0.00 | 2.08 | 5.32% | -35.19% | -34.41% | 0.00% | 1,858,432,315 | Communication Services | No |
| VST | Avoid | 0 | 8.82 | 140.67 | 138.36 | 161.07 | 0.00 | 1.51 | 3.59% | -10.08% | -14.09% | 0.63% | 631,823,517 | Utilities | No |

#### Recommended adds (clear the screen gates)

| Ticker | Setup | Entry | Stop | Target | R/R | Confidence | Rank Score | Beta | ATR % | Dist 200D % | Return 3M | Div Yield | Dollar ADV | Sector |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MPC | Breakout | 423.83 | 375.92 | 561.47 | 2.87 | 97 | 96.60 | -0.12 | 2.99% | 69.10% | 74.92% | 0.95% | 1,071,349,975 | Energy |

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

