"""MT5Feed tested against a stub MetaTrader5 module, so no terminal or account is needed."""
import pathlib, sys
from types import SimpleNamespace as NS

import pytest

from app import data


class StubMT5:
    TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 5, 15, 60, 240, 1440

    def __init__(self, symbols=("EURUSDm",)):
        self.symbols = set(symbols)
        self.calls = []

    def initialize(self, *a):
        self.calls.append(("initialize", a))
        return True

    def last_error(self):
        return (1, "stub")

    def symbol_select(self, name, enable):
        self.calls.append(("symbol_select", name))
        return name in self.symbols

    def symbol_info_tick(self, name):
        self.calls.append(("tick", name))
        return NS(bid=1.0850, ask=1.0852)

    def copy_rates_from_pos(self, name, tf, start, count):
        self.calls.append(("rates", name, tf))
        return [{"time": 1, "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1}] * count

    def account_info(self):
        return NS(balance=500.0, equity=498.0, currency="USD")

    def positions_total(self):
        return 2


@pytest.fixture
def feed(monkeypatch):
    stub = StubMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", stub)
    return data.MT5Feed(suffix="m"), stub


def test_suffix_is_applied_to_broker_symbol(feed):
    f, stub = feed
    r = f.price("EURUSD")
    assert r == {"symbol": "EURUSD", "bid": 1.0850, "ask": 1.0852, "source": "mt5"}
    assert ("tick", "EURUSDm") in stub.calls


def test_wrong_suffix_gives_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "MetaTrader5", StubMT5())
    f = data.MT5Feed(suffix="c")
    with pytest.raises(RuntimeError, match="MT5_SYMBOL_SUFFIX"):
        f.price("EURUSD")


def test_candles_and_account(feed):
    f, _ = feed
    c = f.candles("EURUSD", "H1", 3)
    assert len(c) == 3 and c[0]["close"] == 1.1
    assert f.account() == {"balance": 500.0, "equity": 498.0, "currency": "USD", "open_positions": 2, "source": "mt5"}


def test_bad_timeframe_rejected(feed):
    with pytest.raises(ValueError):
        feed[0].candles("EURUSD", "W1", 3)


def test_feed_only_uses_read_calls(feed):
    f, stub = feed
    f.price("EURUSD"); f.candles("EURUSD", "M5", 2); f.account()
    assert {c[0] for c in stub.calls} <= {"initialize", "symbol_select", "tick", "rates"}


def test_source_never_references_order_functions():
    src = pathlib.Path(data.__file__).read_text()
    for banned in ("order_send", "order_check", "positions_get", "Buy", "Sell"):
        assert banned not in src


def test_zero_tick_is_an_error_not_a_price(feed):
    f, stub = feed
    stub.symbol_info_tick = lambda name: NS(bid=0.0, ask=0.0)
    with pytest.raises(RuntimeError, match="No live quote"):
        f.price("EURUSD")
