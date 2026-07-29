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
![Regime](https://img.shields.io/badge/regime-Risk--On-informational) ![Watchlist](https://img.shields.io/badge/watchlist-11-blue) ![Adds](https://img.shields.io/badge/adds-0-success)

_Last updated: 2026-07-29 15:08 UTC_

> **Parameters:** Signal model ma_dc_volume_regime · Gates conf ≥ 80 & R/R ≥ 2.5 · Min avg volume 500,000

#### Watchlist (followed names)

| Ticker | Setup | Confidence | R/R | Entry | Stop | Target | Rank Score | Beta | ATR % | Dist 200D % | Return 3M | Div Yield | Dollar ADV | Sector | Actionable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AAPL | Avoid | 0 | 3.07 | 340.21 | 317.40 | 410.13 | 0.00 | 0.85 | 2.29% | 22.72% | 25.67% | 0.31% | 18,843,971,609 | Technology | No |
| AMZN | Avoid | 0 | 11.80 | 228.28 | 225.53 | 260.81 | 0.00 | 1.44 | 2.93% | -2.72% | -12.10% | 0.00% | 10,983,659,938 | Consumer Cyclical | No |
| BABA | Avoid | 0 | 30.90 | 114.76 | 113.79 | 144.63 | 0.00 | 1.27 | 3.08% | -18.89% | -12.30% | 6.29% | 1,376,903,143 | Consumer Cyclical | No |
| CRWV | Avoid | 0 | 32.10 | 63.10 | 61.26 | 122.15 | 0.00 | 2.95 | 10.69% | -33.93% | -40.20% | 0.00% | 1,757,239,934 | Technology | No |
| GOOGL | Avoid | 0 | 4.81 | 335.10 | 322.41 | 396.20 | 0.00 | 1.40 | 3.36% | 3.04% | -4.20% | 0.25% | 11,169,740,001 | Communication Services | No |
| META | Avoid | 0 | 15.32 | 590.36 | 580.84 | 736.26 | 0.00 | 1.50 | 3.76% | -7.20% | -12.06% | 0.35% | 10,544,287,847 | Communication Services | No |
| MSFT | Avoid | 0 | 2.70 | 395.52 | 374.52 | 452.30 | 0.00 | 0.76 | 2.91% | -8.90% | -7.86% | 0.91% | 15,484,523,939 | Technology | No |
| NFLX | Avoid | 0 | 2.15 | 72.29 | 64.45 | 89.14 | 0.00 | 0.31 | 3.47% | -21.24% | -21.65% | 0.00% | 3,231,329,144 | Communication Services | No |
| NVDA | Avoid | 0 | 6.75 | 192.70 | 189.06 | 217.29 | 0.00 | 1.87 | 3.87% | -0.16% | -9.60% | 0.02% | 29,016,265,584 | Technology | No |
| ORCL | Avoid | 0 | 15.11 | 117.99 | 112.64 | 198.81 | 0.00 | 1.85 | 6.31% | -36.17% | -28.90% | 1.67% | 3,752,135,721 | Technology | No |
| TSLA | Avoid | 0 | 20.99 | 302.71 | 296.41 | 434.88 | 0.00 | 2.24 | 5.65% | -26.66% | -19.50% | 0.00% | 13,527,080,001 | Consumer Cyclical | No |

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

