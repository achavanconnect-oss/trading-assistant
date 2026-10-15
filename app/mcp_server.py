"""Model Context Protocol server exposing the same read-only trading tools to any MCP client
(Claude Desktop, Claude Code, other agents).

Run over stdio:   python -m app.mcp_server
Uses the demo feed unless MT5_ENABLED=1 (see README). There is no order tool, here or anywhere.
"""
from mcp.server.mcpserver import MCPServer

from app import data, tools

mcp = MCPServer("trading-assistant", instructions=(
    "Read-only market tools. Prices must come from get_price; never invent a price. "
    "These tools cannot place, modify or close trades."))

_feed = None


def feed() -> data.DemoFeed:
    global _feed
    if _feed is None:
        _feed = data.get_feed()
    return _feed


@mcp.tool()
def get_price(symbol: str) -> dict:
    """Current bid/ask for EURUSD, GBPUSD, XAUUSD or BTCUSD."""
    return tools.run_tool("get_price", {"symbol": symbol}, feed())


@mcp.tool()
def get_candles(symbol: str, timeframe: str, count: int = 20) -> dict:
    """Recent OHLC candles (max 50). timeframe is one of M5, M15, H1, H4, D1."""
    return tools.run_tool("get_candles", {"symbol": symbol, "timeframe": timeframe, "count": count}, feed())


@mcp.tool()
def get_account_summary() -> dict:
    """Balance, equity and open position count. With MT5 enabled this is your real account data."""
    return tools.run_tool("get_account_summary", {}, feed())


@mcp.tool()
def position_size(symbol: str, balance: float, risk_pct: float, stop_pips: float | None = None,
                  entry: float | None = None, stop: float | None = None) -> dict:
    """Lot size so that hitting the stop loses risk_pct (max 5) of balance. Pass stop_pips, or entry and stop. Calculation only."""
    args = {"symbol": symbol, "balance": balance, "risk_pct": risk_pct, "stop_pips": stop_pips, "entry": entry, "stop": stop}
    return tools.run_tool("position_size", {k: v for k, v in args.items() if v is not None}, feed())


if __name__ == "__main__":
    mcp.run()
