import asyncio
import json
from types import SimpleNamespace as NS

import httpx

from app import agent, data, tools
from app.ollama_client import OllamaClient, to_ollama_messages, to_ollama_tools


def ndjson(*objs) -> bytes:
    return ("\n".join(json.dumps(o) for o in objs) + "\n").encode()


def transport(*turns, seen=None):
    """Fake Ollama server: replies with the next scripted NDJSON turn and records each request body."""
    turns = list(turns)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return httpx.Response(200, content=turns.pop(0))
    return httpx.MockTransport(handler)


TEXT_TURN = ndjson({"message": {"role": "assistant", "content": "Hello "}, "done": False},
                   {"message": {"role": "assistant", "content": "there."}, "done": False},
                   {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 12, "eval_count": 3})


def tool_turn(name, args):
    return ndjson({"message": {"role": "assistant", "content": "",
                               "tool_calls": [{"function": {"name": name, "arguments": args}}]}, "done": False},
                  {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 20, "eval_count": 5})


def collect(client, user="hi"):
    async def go():
        return [e async for e in agent.run_chat(client, [{"role": "user", "content": user}], data.DemoFeed())]
    return asyncio.run(go())


def test_streams_text_and_reports_usage():
    c = OllamaClient(transport=transport(TEXT_TURN))

    async def go():
        async with c.messages.stream(model="m", max_tokens=10, system="s", tools=[], messages=[{"role": "user", "content": "x"}]) as s:
            chunks = [t async for t in s.text_stream]
            return chunks, await s.get_final_message()
    chunks, final = asyncio.run(go())
    assert chunks == ["Hello ", "there."]
    assert final.content[0].type == "text" and final.content[0].text == "Hello there."
    assert (final.usage.input_tokens, final.usage.output_tokens) == (12, 3)


def test_tool_call_is_exposed_as_a_tool_use_block():
    c = OllamaClient(transport=transport(tool_turn("get_price", {"symbol": "EURUSD"})))

    async def go():
        async with c.messages.stream(model="m", max_tokens=10, system="s", tools=tools.TOOL_SPECS, messages=[{"role": "user", "content": "x"}]) as s:
            return await s.get_final_message()   # draining happens inside
    final = asyncio.run(go())
    block = final.content[0]
    assert block.type == "tool_use" and block.name == "get_price" and block.input == {"symbol": "EURUSD"} and block.id


def test_message_and_tool_conversion():
    msgs = [{"role": "user", "content": "price?"},
            {"role": "assistant", "content": [NS(type="text", text="Checking."),
                                              NS(type="tool_use", id="c1", name="get_price", input={"symbol": "EURUSD"})]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "{'bid': 1.0}"}]}]
    out = to_ollama_messages("SYS", msgs)
    assert [m["role"] for m in out] == ["system", "user", "assistant", "tool"]
    assert out[2]["tool_calls"][0]["function"] == {"name": "get_price", "arguments": {"symbol": "EURUSD"}}
    assert out[3]["tool_name"] == "get_price" and "1.0" in out[3]["content"]
    t = to_ollama_tools(tools.TOOL_SPECS)
    assert {x["function"]["name"] for x in t} == {s["name"] for s in tools.TOOL_SPECS}


def test_full_agent_loop_on_ollama_backend_runs_tool_then_grounded_answer():
    bid = data.DemoFeed().price("EURUSD")["bid"]
    answer = ndjson({"message": {"role": "assistant", "content": f"EURUSD bid is {bid}."}, "done": False},
                    {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 40, "eval_count": 9})
    seen = []
    ev = collect(OllamaClient(transport=transport(tool_turn("get_price", {"symbol": "EURUSD"}), answer, seen=seen)))
    types = [e["type"] for e in ev]
    assert types.count("tool") == 1 and "warning" not in types and types[-1] == "done"
    m = next(e for e in ev if e["type"] == "metrics")
    assert m["tokens_in"] == 60 and m["tokens_out"] == 14
    assert seen[1]["messages"][-1]["role"] == "tool"            # tool result was sent back on the second request


def test_invented_price_from_a_small_model_is_still_flagged():
    bad = ndjson({"message": {"role": "assistant", "content": "EURUSD is 1.2345."}, "done": False},
                 {"message": {"role": "assistant", "content": ""}, "done": True})
    ev = collect(OllamaClient(transport=transport(bad)))
    assert any(e["type"] == "warning" and "1.2345" in e["numbers"] for e in ev)


def test_http_error_surfaces_instead_of_hanging():
    def handler(request):
        return httpx.Response(500, content=b"model not found")
    c = OllamaClient(transport=httpx.MockTransport(handler))
    try:
        collect(c)
    except RuntimeError as e:
        assert "HTTP 500" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
