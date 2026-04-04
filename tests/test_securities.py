from datetime import date, datetime, timedelta
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import securities


class FakeResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


class FakeHistoryFrame:
    def __init__(self, rows: list[tuple[object, dict[str, float]]]) -> None:
        self._rows = rows
        self.empty = not rows

    def iterrows(self):
        return iter(self._rows)


class FakeTicker:
    def __init__(self, rows: list[tuple[object, dict[str, float]]]) -> None:
        self._rows = rows

    def history(self, **kwargs) -> FakeHistoryFrame:
        return FakeHistoryFrame(self._rows)


def test_normalize_symbol_handles_aliases_and_tickers() -> None:
    assert securities.normalize_symbol("SPX") == "^spx"
    assert securities.normalize_symbol(" AAPL ") == "aapl.us"
    assert securities.normalize_symbol("BHP.AX") == "bhp.ax"


def test_display_symbol_formats_known_and_plain_symbols() -> None:
    assert securities.display_symbol("spx") == "S&P 500"
    assert securities.display_symbol(" aapl ") == "AAPL"
    assert securities.display_symbol("My Fund") == "My Fund"


def test_fetch_price_history_parses_valid_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = "\n".join(
        [
            "Date,Open,High,Low,Close,Volume",
            "2025-01-02,1,1,1,123.45,100",
            "bad-row",
            "2025-01-03,1,1,1,124.50,100",
        ]
    )

    def fake_urlopen(request, timeout: int) -> FakeResponse:
        assert request.full_url == securities.STOOQ_URL.format(symbol="aapl.us")
        assert timeout == 15
        return FakeResponse(payload)

    monkeypatch.setattr(securities, "urlopen", fake_urlopen)

    history = securities.fetch_price_history("AAPL")

    assert history == [
        securities.PricePoint(day=date(2025, 1, 2), close=123.45),
        securities.PricePoint(day=date(2025, 1, 3), close=124.50),
    ]


def test_build_period_returns_uses_latest_available_trading_day() -> None:
    history = [
        securities.PricePoint(day=date(2024, 3, 1), close=80.0),
        securities.PricePoint(day=date(2024, 12, 2), close=100.0),
        securities.PricePoint(day=date(2025, 1, 31), close=110.0),
        securities.PricePoint(day=date(2025, 2, 24), close=115.0),
        securities.PricePoint(day=date(2025, 2, 28), close=118.0),
        securities.PricePoint(day=date(2025, 3, 3), close=120.0),
    ]

    periods, latest = securities.build_period_returns(history)

    assert [label for label, _ in periods] == ["1 Day", "1 Week", "1 Month", "3 Months", "1 Year"]
    assert [change for _, change in periods] == pytest.approx(
        [1.6949152542372947, 4.347826086956519, 9.090909090909083, 20.0, 50.0]
    )
    assert latest == securities.PricePoint(day=date(2025, 3, 3), close=120.0)


def test_build_period_returns_requires_enough_history() -> None:
    history = [securities.PricePoint(day=date(2025, 3, 3), close=120.0)]

    with pytest.raises(RuntimeError, match="Not enough historical data"):
        securities.build_period_returns(history)


def test_fetch_intraday_history_yahoo_keeps_last_24_candles(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2025, 3, 1, 9, 0)
    rows = []
    for offset in range(30):
        moment = start + timedelta(hours=offset)
        rows.append(
            (
                moment,
                {
                    "Open": 100.0 + offset,
                    "High": 101.0 + offset,
                    "Low": 99.0 + offset,
                    "Close": 100.5 + offset,
                },
            )
        )

    monkeypatch.setattr(securities.yf, "Ticker", lambda symbol: FakeTicker(rows))

    candles = securities.fetch_intraday_history_yahoo("AAPL")

    assert len(candles) == 24
    assert candles[0].moment == start + timedelta(hours=6)
    assert candles[-1].close == pytest.approx(129.5)


def test_fetch_daily_candles_yahoo_keeps_last_24_days(monkeypatch: pytest.MonkeyPatch) -> None:
    start = datetime(2025, 1, 1, 0, 0)
    rows = []
    for offset in range(30):
        moment = start + timedelta(days=offset)
        rows.append(
            (
                moment,
                {
                    "Open": 200.0 + offset,
                    "High": 201.0 + offset,
                    "Low": 199.0 + offset,
                    "Close": 200.5 + offset,
                },
            )
        )

    monkeypatch.setattr(securities.yf, "Ticker", lambda symbol: FakeTicker(rows))

    candles = securities.fetch_daily_candles_yahoo("AAPL")

    assert len(candles) == 24
    assert candles[0].moment == start + timedelta(days=6)
    assert candles[-1].close == pytest.approx(229.5)


def test_render_chart_writes_image_with_intraday_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    daily_history = [
        securities.PricePoint(day=date(2024, 3, 1), close=80.0),
        securities.PricePoint(day=date(2024, 12, 2), close=100.0),
        securities.PricePoint(day=date(2025, 1, 31), close=110.0),
        securities.PricePoint(day=date(2025, 2, 24), close=115.0),
        securities.PricePoint(day=date(2025, 2, 28), close=118.0),
        securities.PricePoint(day=date(2025, 3, 3), close=120.0),
    ]
    intraday_candles = [
        securities.CandlePoint(
            moment=datetime(2025, 3, 3, 9, 0) + timedelta(hours=index),
            open=100.0 + index,
            high=101.0 + index,
            low=99.0 + index,
            close=100.5 + index,
        )
        for index in range(24)
    ]
    daily_candles = [
        securities.CandlePoint(
            moment=datetime(2025, 2, 1, 0, 0) + timedelta(days=index),
            open=90.0 + index,
            high=92.0 + index,
            low=89.0 + index,
            close=91.0 + index,
        )
        for index in range(24)
    ]

    monkeypatch.setattr(securities, "fetch_price_history_yahoo", lambda symbol: daily_history)
    monkeypatch.setattr(securities, "fetch_intraday_history_yahoo", lambda symbol: intraday_candles)
    monkeypatch.setattr(securities, "fetch_daily_candles_yahoo", lambda symbol: daily_candles)

    output_path = tmp_path / "chart.png"

    securities.render_chart("AAPL", output_path=str(output_path))

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_main_exits_with_render_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_render(symbol: str, output_path: str = "chart.png", provider: str = "yahoo") -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        securities.argparse.ArgumentParser,
        "parse_args",
        lambda self: SimpleNamespace(
            symbol="AAPL",
            provider="yahoo",
            output_dir=".",
            output_file="chart.png",
        ),
    )
    monkeypatch.setattr(securities, "render_chart", fail_render)

    with pytest.raises(SystemExit, match="boom"):
        securities.main()
