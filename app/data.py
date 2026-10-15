"""Read-only market data. MetaTrader 5 when available and MT5_ENABLED=1, otherwise a seeded demo feed.

There is deliberately no order-placement function anywhere in this package.
"""
import os, random

DEMO_BASE = {"EURUSD": 1.0850, "GBPUSD": 1.2650, "XAUUSD": 2650.0, "BTCUSD": 67000.0}
DIGITS = {"EURUSD": 5, "GBPUSD": 5, "XAUUSD": 2, "BTCUSD": 2}
TF_SECONDS = {"M5": 300, "M15": 900, "H1": 3600, "H4": 14400, "D1": 86400}


class UnknownSymbol(ValueError):
    pass


def _check(symbol: str) -> str:
    s = symbol.upper().replace("/", "")
    if s not in DEMO_BASE:
        raise UnknownSymbol(f"Unknown symbol {symbol!r}. Supported: {', '.join(DEMO_BASE)}")
    return s


class DemoFeed:
    """Deterministic random walk so tests and demos are reproducible. Always labelled source='demo'."""
    source = "demo"

    def candles(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        s = _check(symbol)
        if timeframe not in TF_SECONDS:
            raise ValueError(f"Unknown timeframe {timeframe!r}. Supported: {', '.join(TF_SECONDS)}")
        rng = random.Random(f"{s}-{timeframe}")
        step = DEMO_BASE[s] * 0.0006
        px, out = DEMO_BASE[s], []
        t0 = 1_700_000_000
        d = DIGITS[s]
        for i in range(count):
            o = px
            c = o + rng.uniform(-1, 1) * step
            h = max(o, c) + rng.uniform(0, 0.5) * step
            l = min(o, c) - rng.uniform(0, 0.5) * step
            out.append({"time": t0 + i * TF_SECONDS[timeframe], "open": round(o, d), "high": round(h, d),
                        "low": round(l, d), "close": round(c, d)})
            px = c
        return out

    def price(self, symbol: str) -> dict:
        s = _check(symbol)
        c = self.candles(s, "M5", 50)[-1]["close"]
        d = DIGITS[s]
        return {"symbol": s, "bid": round(c, d), "ask": round(c * 1.00002, d), "source": self.source}

    def account(self) -> dict:
        return {"balance": 10000.0, "equity": 10000.0, "currency": "USD", "open_positions": 0, "source": self.source}


class MT5Feed(DemoFeed):
    """Thin read-only wrapper over the MetaTrader5 Python package. Reads only: no order functions are used."""
    source = "mt5"

    def __init__(self, suffix: str | None = None):
        import MetaTrader5 as mt5
        # Brokers append a suffix per account type (Exness: "m" on standard accounts, "c" on cent accounts)
        self.suffix = os.getenv("MT5_SYMBOL_SUFFIX", "") if suffix is None else suffix
        path = os.getenv("MT5_PATH")
        ok = mt5.initialize(path) if path else mt5.initialize()
        if not ok:
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        self.mt5 = mt5

    def _broker_symbol(self, symbol: str) -> str:
        s = _check(symbol)
        name = s + self.suffix
        if not self.mt5.symbol_select(name, True):
            raise RuntimeError(f"Symbol {name} not available on this account (check MT5_SYMBOL_SUFFIX)")
        return name

    def price(self, symbol: str) -> dict:
        s = _check(symbol)
        t = self.mt5.symbol_info_tick(self._broker_symbol(s))
        if t is None or not t.bid or not t.ask:
            # MT5 returns an empty (0.0) tick for a symbol it has only just selected, or when the market is closed
            raise RuntimeError(f"No live quote for {s} yet (bid/ask empty). Try again in a moment.")
        return {"symbol": s, "bid": t.bid, "ask": t.ask, "source": self.source}

    def candles(self, symbol: str, timeframe: str, count: int) -> list[dict]:
        s = _check(symbol)
        if timeframe not in TF_SECONDS:
            raise ValueError(f"Unknown timeframe {timeframe!r}. Supported: {', '.join(TF_SECONDS)}")
        tf = getattr(self.mt5, f"TIMEFRAME_{timeframe}")
        rates = self.mt5.copy_rates_from_pos(self._broker_symbol(s), tf, 0, count)
        if rates is None:
            raise RuntimeError(f"No rates for {s}")
        return [{"time": int(r["time"]), "open": float(r["open"]), "high": float(r["high"]),
                 "low": float(r["low"]), "close": float(r["close"])} for r in rates]

    def account(self) -> dict:
        a = self.mt5.account_info()
        return {"balance": a.balance, "equity": a.equity, "currency": a.currency,
                "open_positions": self.mt5.positions_total(), "source": self.source}


def get_feed() -> DemoFeed:
    if os.getenv("MT5_ENABLED") == "1":
        return MT5Feed()
    return DemoFeed()
