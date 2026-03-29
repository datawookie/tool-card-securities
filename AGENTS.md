# AGENTS.md — tool-card-securities

## Project overview

A single-file Python CLI tool that fetches historical price data for a security and renders a dark-themed horizontal bar chart showing percentage returns across multiple time periods. The output is a PNG file suitable for use as a card/widget (hence "tool-card").

## Repository structure

```
securities.py          # All application logic — data fetching, computation, rendering
pyproject.toml         # Project metadata and dependencies (uv / PEP 517)
.python-version        # Pins Python 3.14
chart.png              # Example output (S&P 500, generated 20/03/2026)
```

There are no tests, no sub-packages, and no configuration files beyond `pyproject.toml`.

---

## How it works

### 1. Symbol normalisation (`normalize_symbol`)

Input symbols are resolved to the format expected by the Stooq CSV API:

| Input pattern | Stooq symbol |
|---|---|
| Known alias (`S&P500`, `SPX`, `^GSPC`, …) | `^spx` (via `SPECIAL_SYMBOLS` dict) |
| Already has `^` prefix or `.` in name | lowercased as-is |
| Plain ticker (e.g. `AAPL`) | `aapl.us` |

`display_symbol` performs the inverse for the chart header — aliases become `"S&P 500"`, other tickers are uppercased.

### 2. Data fetching (`fetch_price_history`)

- Hits `https://stooq.com/q/d/l/?s={symbol}&i=d` (daily CSV endpoint).
- Sends a `Mozilla/5.0` User-Agent header to avoid blocks.
- Parses the CSV into a list of `PricePoint(day: date, close: float)` dataclasses.
- Raises `RuntimeError` on network failure or empty response.

### 3. Return calculation (`build_period_returns`)

For each of the five periods defined in `PERIOD_DELTAS`:

| Label | Look-back |
|---|---|
| 1 Day | 1 calendar day |
| 1 Week | 7 days |
| 1 Month | 1 month |
| 3 Months | 3 months |
| 1 Year | 1 year |

The reference price is found via binary search (`bisect_right`) on the sorted date list — it selects the latest trading day on or before the target date. The return is `((latest / reference) - 1) * 100`.

### 4. Chart rendering (`render_chart`)

Produces an 8×5 inch Matplotlib figure at 180 dpi saved to `chart.png` (default) or a specified path.

**Visual anatomy (bottom to top):**

- **Background** — near-black (`#0c0c0f`)
- **Scale ticks** — five reference marks (`−max`, `−max/2`, `0`, `+max/2`, `+max`) rendered as plain text below the bars
- **Track bars** — full-width dark grey (`#141418`) background for each row
- **Zero line** — thin vertical line (`#2a2a2e`) at x = 0
- **Value bars** — green (`#22c98e`) for gains, red (`#f0454a`) for losses; bar width proportional to `|return| / scale_max`
- **Period labels** — left of the track, dimmed white (`#bbbbbb`)
- **Value labels** — right of the track, coloured to match the bar, bold, with explicit `+` sign for gains
- **Header** — large bold serif ticker name (top-left) + date and last-close price (top-right, grey)

`scale_max` is `max(max absolute return across all periods, 1.0)`, so the axis always fits all bars without clipping and is never zero.

---

## Dependencies

| Package | Role |
|---|---|
| `matplotlib` | Chart rendering |
| `numpy` | `arange` for y-axis positions |
| `python-dateutil` | `relativedelta` for calendar-aware look-back periods |

All standard-library modules (`argparse`, `csv`, `io`, `bisect`, `dataclasses`, `datetime`, `urllib`) require no installation.

---

## CLI usage

```bash
# Default: S&P 500, written to ./chart.png


# Specific US stock
tool-card-securities --symbol AAPL

# Index with special handling
tool-card-securities --symbol "S&P500"
tool-card-securities --symbol SPX

# Non-US symbol (has a dot — passed through as-is)
tool-card-securities --symbol BHP.AX

# Write to a specific directory
tool-card-securities --symbol AAPL --output-dir /tmp/charts

# Custom filename
tool-card-securities --symbol AAPL --output-file aapl.png

# Both together
tool-card-securities --symbol AAPL --output-dir /tmp/charts --output-file aapl.png

# Alternative data provider
tool-card-securities --symbol AAPL --provider stooq
```

The output path is `{output-dir}/{output-file}`, both defaulting to `./chart.png`.

---

## Key design decisions

- **Single file** — all logic lives in `securities.py`; no modules, no classes beyond `PricePoint`.
- **No caching** — every invocation makes a live HTTP request to Stooq.
- **Periods ordered longest-first in the chart** — `PERIOD_DELTAS` is defined shortest-first but rendered bottom-to-top (numpy `arange` + `barh`), so the chart reads 1 Day at the bottom and 1 Year at the top.
- **Dynamic scale** — `scale_max` is derived from the actual data so bars always use the full available width.
- **Error handling** — network and parse errors surface as `RuntimeError`; `main()` catches those and `ValueError` and exits with the message via `SystemExit`.
