"""Tools the assistant may call. All are read-only; none can place, modify or close an order."""
from app import data

# Approximate USD value of a 1.0 price move for 1 standard lot (documented in the README)
CONTRACT_SIZE = {"EURUSD": 100_000, "GBPUSD": 100_000, "XAUUSD": 100, "BTCUSD": 1}
# Price value of one "pip" per symbol (a convention: gold is quoted differently by different brokers)
PIP_SIZE = {"EURUSD": 0.0001, "GBPUSD": 0.0001, "XAUUSD": 0.1, "BTCUSD": 1.0}

TOOL_SPECS = [
    {"name": "get_price", "description": "Current bid/ask for a symbol. The only valid source of live prices.",
     "input_schema": {"type": "object", "properties": {"symbol": {"type": "string"}}, "required": ["symbol"]}},
    {"name": "get_candles",
     "description": "Recent OHLC candles (max 50) for a symbol and timeframe (M5, M15, H1, H4, D1).",
     "input_schema": {"type": "object",
                      "properties": {"symbol": {"type": "string"}, "timeframe": {"type": "string"},
                                     "count": {"type": "integer", "minimum": 1, "maximum": 50}},
                      "required": ["symbol", "timeframe"]}},
    {"name": "get_account_summary", "description": "Balance, equity and number of open positions.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "position_size",
     "description": ("Lot size so that hitting the stop loses risk_pct of balance (max 5). Calculation only; does not place a trade. "
                     "When the user gives the stop as a distance, pass stop_pips and do NOT compute a stop price yourself. "
                     "Otherwise pass entry and stop prices."),
     "input_schema": {"type": "object",
                      "properties": {"symbol": {"type": "string"}, "balance": {"type": "number"},
                                     "risk_pct": {"type": "number"}, "stop_pips": {"type": "number"},
                                     "entry": {"type": "number"}, "stop": {"type": "number"}},
                      "required": ["symbol", "balance", "risk_pct"]}},
]


def position_size(symbol: str, balance: float, risk_pct: float, entry: float | None = None,
                  stop: float | None = None, stop_pips: float | None = None) -> dict:
    s = data._check(symbol)
    if not 0 < risk_pct <= 5:
        raise ValueError("risk_pct must be greater than 0 and at most 5")
    if balance <= 0:
        raise ValueError("balance must be positive")
    if stop_pips is not None:
        if stop_pips <= 0:
            raise ValueError("stop_pips must be positive")
        dist = stop_pips * PIP_SIZE[s]
    elif entry is not None and stop is not None:
        dist = abs(entry - stop)
        if dist == 0:
            raise ValueError("entry and stop must differ")
    else:
        raise ValueError("give either stop_pips, or both entry and stop")
    risk_amount = balance * risk_pct / 100
    lots = risk_amount / (dist * CONTRACT_SIZE[s])
    return {"symbol": s, "risk_amount": round(risk_amount, 2), "stop_distance": round(dist, 5),
            "stop_pips": round(dist / PIP_SIZE[s], 2), "lots": round(lots, 2),
            "note": f"Calculation only. 1 pip = {PIP_SIZE[s]} here; verify pip and contract size with your broker."}


def run_tool(name: str, args: dict, feed: data.DemoFeed) -> dict:
    """Execute a tool; errors come back as {'error': ...} so the model can explain them, never invent a result."""
    try:
        if name == "get_price":
            return feed.price(args["symbol"])
        if name == "get_candles":
            n = min(int(args.get("count", 20)), 50)
            return {"symbol": data._check(args["symbol"]), "timeframe": args["timeframe"], "source": feed.source,
                    "candles": feed.candles(args["symbol"], args["timeframe"], n)}
        if name == "get_account_summary":
            return feed.account()
        if name == "position_size":
            return position_size(args["symbol"], args["balance"], args["risk_pct"], args.get("entry"),
                             args.get("stop"), args.get("stop_pips"))
        return {"error": f"unknown tool {name}"}
    except Exception as e:  # noqa: BLE001 - surfaced to the model as data
        return {"error": str(e)}
