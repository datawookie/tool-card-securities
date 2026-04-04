import argparse
import csv
import io
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import matplotlib.pyplot as plt
import numpy as np
import yfinance as yf
from dateutil.relativedelta import relativedelta
from matplotlib.patches import Rectangle

PERIOD_DELTAS = [
    ("1 Day", relativedelta(days=1)),
    ("1 Week", relativedelta(weeks=1)),
    ("1 Month", relativedelta(months=1)),
    ("3 Months", relativedelta(months=3)),
    ("1 Year", relativedelta(years=1)),
]
STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"
SPECIAL_SYMBOLS = {
    "S&P500": "^spx",
    "S&P 500": "^spx",
    "SP500": "^spx",
    "SPX": "^spx",
    "^SPX": "^spx",
    "GSPC": "^spx",
    "^GSPC": "^spx",
}
YAHOO_SPECIAL_SYMBOLS = {
    "S&P500": "^GSPC",
    "S&P 500": "^GSPC",
    "SP500": "^GSPC",
    "SPX": "^GSPC",
    "^SPX": "^GSPC",
    "GSPC": "^GSPC",
    "^GSPC": "^GSPC",
}

COLOR_POS = "#22c98e"
COLOR_NEG = "#f0454a"
BG = "#0c0c0f"
TRACK = "#141418"
GRID_LINE = "#2a2a2e"
TEXT_MAIN = "#f0f0f0"
TEXT_DIM = "#bbbbbb"
TEXT_HINT = "#444444"
ROW_STEP = 0.84
INTRADAY_HOURS = 24
DAILY_CANDLES = 24


@dataclass(frozen=True)
class PricePoint:
    day: date
    close: float


@dataclass(frozen=True)
class CandlePoint:
    moment: datetime
    open: float
    high: float
    low: float
    close: float


def normalize_symbol(symbol: str) -> str:
    stripped = symbol.strip()
    if not stripped:
        raise ValueError("Symbol must not be empty.")

    key = stripped.upper()
    if key in SPECIAL_SYMBOLS:
        return SPECIAL_SYMBOLS[key]

    if stripped.startswith("^") or "." in stripped:
        return stripped.lower()

    return f"{stripped.lower()}.us"


def display_symbol(symbol: str) -> str:
    stripped = symbol.strip()
    if stripped.upper() in SPECIAL_SYMBOLS:
        return "S&P 500"
    if stripped and all(ch.isalnum() or ch in ".^-" for ch in stripped):
        return stripped.upper()
    return stripped


def fetch_price_history(symbol: str) -> list[PricePoint]:
    resolved_symbol = normalize_symbol(symbol)
    url = STOOQ_URL.format(symbol=quote(resolved_symbol, safe=""))
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch price history for {symbol}: {exc.reason}") from exc

    rows = list(csv.DictReader(io.StringIO(payload)))
    history = []
    for row in rows:
        try:
            point = PricePoint(
                day=datetime.strptime(row["Date"], "%Y-%m-%d").date(),
                close=float(row["Close"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        history.append(point)

    if not history:
        raise RuntimeError(f"No price history found for symbol {symbol!r}.")

    return history


def fetch_daily_candles_stooq(symbol: str, days: int = DAILY_CANDLES) -> list[CandlePoint]:
    resolved_symbol = normalize_symbol(symbol)
    url = STOOQ_URL.format(symbol=quote(resolved_symbol, safe=""))
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})

    try:
        with urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch daily candle history for {symbol}: {exc.reason}") from exc

    candles = []
    for row in csv.DictReader(io.StringIO(payload)):
        try:
            day = datetime.strptime(row["Date"], "%Y-%m-%d").date()
            open_price = float(row["Open"])
            high_price = float(row["High"])
            low_price = float(row["Low"])
            close_price = float(row["Close"])
        except (KeyError, TypeError, ValueError):
            continue

        candles.append(
            CandlePoint(
                moment=datetime.combine(day, time.min),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
            )
        )

    if not candles:
        raise RuntimeError(f"No daily candle history found for symbol {symbol!r}.")

    return candles[-days:]


def normalize_symbol_yahoo(symbol: str) -> str:
    stripped = symbol.strip()
    if not stripped:
        raise ValueError("Symbol must not be empty.")
    key = stripped.upper()
    if key in YAHOO_SPECIAL_SYMBOLS:
        return YAHOO_SPECIAL_SYMBOLS[key]
    return stripped


def fetch_price_history_yahoo(symbol: str) -> list[PricePoint]:
    resolved = normalize_symbol_yahoo(symbol)
    df = yf.Ticker(resolved).history(period="2y")
    if df.empty:
        raise RuntimeError(f"No price history found for symbol {symbol!r}.")
    return [PricePoint(day=ts.date(), close=float(row["Close"])) for ts, row in df.iterrows()]


def fetch_daily_candles_yahoo(symbol: str, days: int = DAILY_CANDLES) -> list[CandlePoint]:
    resolved = normalize_symbol_yahoo(symbol)
    df = yf.Ticker(resolved).history(period="6mo", interval="1d")
    if df.empty:
        raise RuntimeError(f"No daily candle history found for symbol {symbol!r}.")

    candles = []
    for ts, row in df.iterrows():
        try:
            moment = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if moment.tzinfo is not None:
                moment = moment.replace(tzinfo=None)
            open_price = float(row["Open"])
            high_price = float(row["High"])
            low_price = float(row["Low"])
            close_price = float(row["Close"])
        except (KeyError, TypeError, ValueError):
            continue

        if not np.isfinite([open_price, high_price, low_price, close_price]).all():
            continue

        candles.append(
            CandlePoint(
                moment=moment,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
            )
        )

    if not candles:
        raise RuntimeError(f"No daily candle history found for symbol {symbol!r}.")

    return candles[-days:]


def fetch_intraday_history_yahoo(symbol: str, hours: int = INTRADAY_HOURS) -> list[CandlePoint]:
    resolved = normalize_symbol_yahoo(symbol)
    df = yf.Ticker(resolved).history(period="5d", interval="1h")
    if df.empty:
        raise RuntimeError(f"No intraday price history found for symbol {symbol!r}.")

    candles = []
    for ts, row in df.iterrows():
        try:
            moment = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
            if moment.tzinfo is not None:
                moment = moment.replace(tzinfo=None)
            open_price = float(row["Open"])
            high_price = float(row["High"])
            low_price = float(row["Low"])
            close_price = float(row["Close"])
        except (KeyError, TypeError, ValueError):
            continue

        if not np.isfinite([open_price, high_price, low_price, close_price]).all():
            continue

        candles.append(
            CandlePoint(
                moment=moment,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
            )
        )

    if not candles:
        raise RuntimeError(f"No intraday price history found for symbol {symbol!r}.")

    return candles[-hours:]


def build_period_returns(history: list[PricePoint]) -> tuple[list[tuple[str, float]], PricePoint]:
    latest = history[-1]
    dates = [point.day for point in history]
    closes = [point.close for point in history]

    periods = []
    for label, delta in PERIOD_DELTAS:
        target_day = latest.day - delta
        index = bisect_right(dates, target_day) - 1
        if index < 0:
            continue

        reference_close = closes[index]
        if reference_close == 0:
            continue

        change = ((latest.close / reference_close) - 1) * 100
        periods.append((label, change))

    if not periods:
        raise RuntimeError(f"Not enough historical data to calculate returns for {latest.day:%d/%m/%Y}.")

    return periods, latest


def format_price(price: float) -> str:
    return f"{price:,.2f}"


def format_header_price(price: float) -> str:
    return f"{price:.2f}"


def render_candlestick_strip(ax: plt.Axes, candles: list[CandlePoint], label: str) -> None:
    ax.set_facecolor(BG)

    lows = [candle.low for candle in candles]
    highs = [candle.high for candle in candles]
    price_floor = min(lows)
    price_ceiling = max(highs)
    price_range = max(price_ceiling - price_floor, price_ceiling * 0.01, 1.0)
    padding = price_range * 0.12
    body_width = 0.58
    min_body = price_range * 0.01

    for index, candle in enumerate(candles):
        color = COLOR_POS if candle.close >= candle.open else COLOR_NEG
        ax.vlines(index, candle.low, candle.high, color=color, linewidth=1.2, zorder=2)

        body_bottom = min(candle.open, candle.close)
        body_height = abs(candle.close - candle.open)
        if body_height < min_body:
            ax.hlines(
                (candle.open + candle.close) / 2,
                index - body_width / 2,
                index + body_width / 2,
                color=color,
                linewidth=2.2,
                zorder=3,
            )
            continue

        ax.add_patch(
            Rectangle(
                (index - body_width / 2, body_bottom),
                body_width,
                body_height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.8,
                zorder=3,
            )
        )

    ax.set_xlim(-0.8, len(candles) - 0.2)
    ax.set_ylim(price_floor - padding, price_ceiling + padding)
    ax.set_xticks([])
    ax.set_yticks([])

    ax.spines["top"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.text(
        0.0,
        1.02,
        label,
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        color=TEXT_HINT,
        fontsize=9,
        fontweight="bold",
        fontfamily="sans-serif",
        clip_on=False,
    )


def render_chart(symbol: str, output_path: str = "chart.png", provider: str = "yahoo") -> None:
    if provider == "yahoo":
        history = fetch_price_history_yahoo(symbol)
        daily_candles = fetch_daily_candles_yahoo(symbol)
    else:
        history = fetch_price_history(symbol)
        daily_candles = fetch_daily_candles_stooq(symbol)
    # Hourly candles come from Yahoo because the Stooq path in this tool is daily-only.
    intraday_candles = fetch_intraday_history_yahoo(symbol)
    periods, latest = build_period_returns(history)

    values = [period[1] for period in periods]
    scale_max = max(max(abs(value) for value in values), 1.0)

    fig = plt.figure(figsize=(8, 7.15))
    grid = fig.add_gridspec(3, 1, height_ratios=[3.1, 1.08, 1.08], hspace=0.05)
    ax = fig.add_subplot(grid[0])
    intraday_ax = fig.add_subplot(grid[1])
    daily_ax = fig.add_subplot(grid[2])
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    intraday_ax.set_facecolor(BG)
    daily_ax.set_facecolor(BG)

    y_positions = np.arange(len(periods)) * ROW_STEP
    bar_height = 0.56

    # Draw track (background bar) for each row.
    for y in y_positions:
        ax.barh(y, scale_max * 2, left=-scale_max, height=bar_height,
                color=TRACK, zorder=1)

    # Draw center zero line.
    ax.axvline(0, color=GRID_LINE, linewidth=1.2, zorder=2)

    # Draw value bars.
    for i, (_, val) in enumerate(periods):
        color = COLOR_POS if val >= 0 else COLOR_NEG
        left = 0 if val >= 0 else val
        ax.barh(y_positions[i], abs(val), left=left, height=bar_height,
                color=color, alpha=0.85, zorder=3)

    # Period labels (left side).
    for i, (label, _) in enumerate(periods):
        ax.text(-scale_max - 0.6, y_positions[i], label,
                ha="right", va="center",
                color=TEXT_DIM, fontsize=11, fontfamily="sans-serif")

    # Value labels (right side).
    for i, (_, val) in enumerate(periods):
        color = COLOR_POS if val >= 0 else COLOR_NEG
        sign = "+" if val >= 0 else ""
        ax.text(scale_max + 0.6, y_positions[i], f"{sign}{val:.2f}%",
                ha="left", va="center",
                color=color, fontsize=11, fontweight="bold", fontfamily="sans-serif")

    # Scale ticks at bottom.
    for x_tick in [-scale_max, -scale_max / 2, 0, scale_max / 2, scale_max]:
        sign = "+" if x_tick > 0 else ""
        label = "0" if x_tick == 0 else f"{sign}{x_tick:.0f}%"
        ax.text(x_tick, -0.50, label,
                ha="center", va="top",
                color=TEXT_HINT, fontsize=8, fontfamily="sans-serif")

    # Header.
    fig.text(0.13, 0.902, display_symbol(symbol),
             color=TEXT_MAIN, fontsize=34, fontweight="bold", fontfamily="serif",
             va="center")
    fig.text(0.93, 0.908, latest.day.strftime("%d/%m/%Y"),
             color="#555555", fontsize=14, fontfamily="sans-serif",
             ha="right", va="bottom")
    fig.text(0.93, 0.872, f"Last close {format_header_price(latest.close)}",
             color="#555555", fontsize=14, fontfamily="sans-serif",
             ha="right", va="bottom")

    # Clean up axes.
    ax.set_xlim(-scale_max - 5, scale_max + 5)
    ax.set_ylim(-0.8, y_positions[-1] + 0.45)
    ax.axis("off")

    render_candlestick_strip(intraday_ax, intraday_candles, "Hourly")
    render_candlestick_strip(daily_ax, daily_candles, "Daily")

    fig.subplots_adjust(left=0.12, right=0.92, top=0.845, bottom=0.095)
    fig.savefig(output_path, dpi=180, bbox_inches="tight", pad_inches=0.16, facecolor=BG)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a security performance chart.")
    parser.add_argument(
        "--symbol",
        default="S&P 500",
        help="Ticker or label shown in the chart header. Plain tickers are treated as US symbols.",
    )
    parser.add_argument(
        "--provider",
        choices=["yahoo", "stooq"],
        default="yahoo",
        help="Data provider (default: yahoo).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory to write the chart into (default: current directory).",
    )
    parser.add_argument(
        "--output-file",
        default="chart.png",
        help="Filename for the chart (default: chart.png).",
    )
    args = parser.parse_args()

    output_path = str(Path(args.output_dir) / args.output_file)

    try:
        render_chart(args.symbol, output_path=output_path, provider=args.provider)
    except (RuntimeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
