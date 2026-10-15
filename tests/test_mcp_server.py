import asyncio, json

from app import tools
from app.mcp_server import mcp


def test_mcp_exposes_same_read_only_tools_as_the_chat_agent():
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert names == {t["name"] for t in tools.TOOL_SPECS}
    assert not any(k in n for n in names for k in ("order", "buy", "sell", "close", "modify"))


def test_mcp_get_price_returns_json_text():
    r = asyncio.run(mcp.call_tool("get_price", {"symbol": "EURUSD"}))
    body = json.loads(r.content[0].text)
    assert body["symbol"] == "EURUSD" and body["bid"] > 0 and body["source"] == "demo"


def test_mcp_position_size_matches_direct_call():
    args = dict(symbol="EURUSD", balance=10000, risk_pct=1, entry=1.0850, stop=1.0830)
    r = asyncio.run(mcp.call_tool("position_size", args))
    assert json.loads(r.content[0].text) == tools.position_size(**args)


def test_mcp_errors_come_back_as_data():
    r = asyncio.run(mcp.call_tool("get_price", {"symbol": "NOPE"}))
    assert "error" in json.loads(r.content[0].text)
