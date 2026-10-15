"""Streaming tool-calling loop on the Anthropic Messages API. Yields events for the HTTP layer."""
import os
from typing import AsyncIterator
from app import tools, guardrails, data

MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
MAX_STEPS = 6
SYSTEM = (
    "You are a trading assistant inside an analysis product. Rules: "
    "(1) Never state a price, balance or position size that did not come from a tool result in this conversation; "
    "call a tool, or say you do not have it. "
    "(2) You cannot place, modify or close trades and must say so if asked. "
    "(3) Not financial advice: describe, do not instruct the user to trade. "
    "(4) If a tool returns an error, explain it plainly; do not guess a value. "
    "Be concise."
)


def _user_text(messages: list[dict]) -> str:
    return " ".join(m["content"] for m in messages if m.get("role") == "user" and isinstance(m.get("content"), str))


async def run_chat(client, messages: list[dict], feed: data.DemoFeed, model: str = MODEL) -> AsyncIterator[dict]:
    """Event types: text (streamed chunk), tool (name, args, result), warning, done."""
    results: list[dict] = []
    reply = ""
    user_text = _user_text(messages)
    for _ in range(MAX_STEPS):
        async with client.messages.stream(model=model, max_tokens=1024, system=SYSTEM,
                                          tools=tools.TOOL_SPECS, messages=messages) as stream:
            async for chunk in stream.text_stream:
                reply += chunk
                yield {"type": "text", "data": chunk}
            final = await stream.get_final_message()
        messages.append({"role": "assistant", "content": final.content})
        calls = [b for b in final.content if b.type == "tool_use"]
        if not calls:
            break
        out = []
        for c in calls:
            res = tools.run_tool(c.name, c.input, feed)
            results.append(res)
            yield {"type": "tool", "name": c.name, "args": c.input, "result": res}
            out.append({"type": "tool_result", "tool_use_id": c.id, "content": str(res)})
        messages.append({"role": "user", "content": out})
        reply += "\n"
    bad = guardrails.unverified_numbers(reply, results, user_text)
    if bad:
        yield {"type": "warning", "numbers": bad,
               "message": "These numbers were not returned by any tool and may be wrong: " + ", ".join(bad)}
    yield {"type": "done"}
