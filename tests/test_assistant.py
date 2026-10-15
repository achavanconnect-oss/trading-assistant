import asyncio, json
from types import SimpleNamespace as NS
import pytest
from fastapi.testclient import TestClient

from app import agent, data, guardrails, tools
from app.main import app, get_client, get_feed


# ---------- fake Anthropic client: scripted turns, no network ----------
class FakeStream:
    def __init__(self, turn):
        self.turn = turn

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def text_stream(self):
        async def gen():
            for b in self.turn:
                if b.type == "text":
                    for piece in b.text.split(" "):
                        yield piece + " "
        return gen()

    async def get_final_message(self):
        return NS(content=self.turn)


class FakeClient:
    def __init__(self, turns):
        self.turns = list(turns)
        self.messages = self

    def stream(self, **kw):
        return FakeStream(self.turns.pop(0))


def text(t):
    return NS(type="text", text=t)


def call(name, args, id="tu_1"):
    return NS(type="tool_use", id=id, name=name, input=args)


def collect(client, user="What is EURUSD?"):
    async def go():
        return [e async for e in agent.run_chat(client, [{"role": "user", "content": user}], data.DemoFeed())]
    return asyncio.run(go())


# ---------- tools ----------
def test_no_tool_can_place_orders():
    names = {t["name"] for t in tools.TOOL_SPECS}
    assert names == {"get_price", "get_candles", "get_account_summary", "position_size"}
    assert not any(k in n for n in names for k in ("order", "buy", "sell", "close", "modify"))


def test_position_size_math():
    r = tools.position_size("EURUSD", 10000, 1, 1.0850, 1.0830)  # risk $100, 20 pip stop
    assert r["risk_amount"] == 100.0
    assert r["lots"] == 0.5


@pytest.mark.parametrize("kw", [dict(risk_pct=0), dict(risk_pct=9), dict(balance=-1), dict(stop=1.0850)])
def test_position_size_rejects_bad_input(kw):
    args = dict(symbol="EURUSD", balance=10000, risk_pct=1, entry=1.0850, stop=1.0830) | kw
    with pytest.raises(ValueError):
        tools.position_size(**args)


def test_unknown_symbol_returns_error_not_guess():
    assert "error" in tools.run_tool("get_price", {"symbol": "FOOBAR"}, data.DemoFeed())


# ---------- guardrail ----------
def test_guardrail_flags_invented_number_and_accepts_tool_number():
    res = [{"bid": 1.0852, "ask": 1.0853}]
    assert guardrails.unverified_numbers("Bid is 1.0852.", res) == []
    assert guardrails.unverified_numbers("Bid is 1.0999.", res) == ["1.0999"]


def test_guardrail_accepts_numbers_the_user_supplied():
    assert guardrails.unverified_numbers("Stop at 1.0830.", [], user_text="stop at 1.0830") == []


# ---------- streaming agent loop ----------
def test_tool_call_then_grounded_reply_has_no_warning():
    bid = data.DemoFeed().price("EURUSD")["bid"]
    client = FakeClient([[text("Checking."), call("get_price", {"symbol": "EURUSD"})],
                         [text(f"EURUSD bid is {bid}.")]])
    ev = collect(client)
    types = [e["type"] for e in ev]
    assert types.count("tool") == 1 and "warning" not in types and types[-1] == "done"
    assert any(e["type"] == "text" for e in ev)


def test_invented_price_triggers_warning():
    client = FakeClient([[text("EURUSD is trading at 1.2345 right now.")]])
    ev = collect(client)
    w = [e for e in ev if e["type"] == "warning"]
    assert w and "1.2345" in w[0]["numbers"]


def test_loop_stops_after_max_steps():
    turns = [[call("get_price", {"symbol": "EURUSD"}, id=f"tu_{i}")] for i in range(agent.MAX_STEPS + 3)]
    ev = collect(FakeClient(turns))
    assert [e["type"] for e in ev].count("tool") == agent.MAX_STEPS


# ---------- HTTP streaming endpoint ----------
def test_chat_endpoint_streams_sse():
    bid = data.DemoFeed().price("EURUSD")["bid"]
    client = FakeClient([[call("get_price", {"symbol": "EURUSD"})], [text(f"Bid {bid}.")]])
    app.dependency_overrides[get_client] = lambda: client
    app.dependency_overrides[get_feed] = lambda: data.DemoFeed()
    try:
        r = TestClient(app).post("/chat", json={"messages": [{"role": "user", "content": "price?"}]})
    finally:
        app.dependency_overrides.clear()
    assert r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(l[6:]) for l in r.text.split("\n\n") if l.startswith("data: ")]
    assert events[-1]["type"] == "done" and any(e["type"] == "tool" for e in events)


def test_chat_rejects_empty_messages():
    assert TestClient(app).post("/chat", json={"messages": []}).status_code == 422


# ---------- metrics / observability ----------
def test_metrics_event_and_log_line(tmp_path, monkeypatch):
    log = tmp_path / "m.jsonl"
    monkeypatch.setattr(agent, "METRICS_LOG", str(log))
    monkeypatch.setattr(agent, "PRICE_IN", "3")
    monkeypatch.setattr(agent, "PRICE_OUT", "15")
    t1 = [call("get_price", {"symbol": "EURUSD"})]
    t2 = [text("Done.")]
    client = FakeClient([t1, t2])
    # attach usage to each scripted final message
    orig = FakeStream.get_final_message

    async def with_usage(self):
        m = await orig(self)
        m.usage = NS(input_tokens=100, output_tokens=20)
        return m
    monkeypatch.setattr(FakeStream, "get_final_message", with_usage)
    ev = collect(client)
    m = next(e for e in ev if e["type"] == "metrics")
    assert m["steps"] == 2 and m["tool_calls"] == 1 and m["tokens_in"] == 200 and m["tokens_out"] == 40
    assert m["cost_usd"] == round((200 * 3 + 40 * 15) / 1e6, 6)
    assert json.loads(log.read_text().splitlines()[-1])["steps"] == 2


def test_metrics_without_usage_does_not_break(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "METRICS_LOG", str(tmp_path / "m.jsonl"))
    monkeypatch.setattr(agent, "PRICE_IN", None)
    ev = collect(FakeClient([[text("Hello there.")]]))
    m = next(e for e in ev if e["type"] == "metrics")
    assert m["tokens_in"] == 0 and "cost_usd" not in m
