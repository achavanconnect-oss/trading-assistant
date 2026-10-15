"""Streaming tool-calling loop on the Anthropic Messages API. Yields events for the HTTP layer."""
import json, os, time
from typing import AsyncIterator
from app import tools, guardrails, data

PROVIDER = os.getenv("LLM_PROVIDER", "ollama")   # ollama (free, local; default) | anthropic (optional, needs a key)
MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b-instruct" if PROVIDER == "ollama" else "claude-sonnet-5-5")
MAX_STEPS = 6
METRICS_LOG = os.getenv("METRICS_LOG", os.path.join("logs", "metrics.jsonl"))
# Optional USD price per million tokens, set from your provider's current price list; cost is omitted if unset.
PRICE_IN = os.getenv("LLM_PRICE_IN_PER_MTOK")
PRICE_OUT = os.getenv("LLM_PRICE_OUT_PER_MTOK")
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


def _write_metrics(m: dict) -> None:
    """Append one JSON line per chat turn. Best-effort: logging must never break a reply."""
    try:
        os.makedirs(os.path.dirname(METRICS_LOG) or ".", exist_ok=True)
        with open(METRICS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(m) + "\n")
    except OSError:
        pass


async def run_chat(client, messages: list[dict], feed: data.DemoFeed, model: str = MODEL) -> AsyncIterator[dict]:
    """Event types: text (streamed chunk), tool (name, args, result), warning, metrics, done."""
    t0 = time.perf_counter()
    first_token = None
    tokens_in = tokens_out = steps = 0
    tool_secs = 0.0
    results: list[dict] = []
    reply = ""
    user_text = _user_text(messages)
    for _ in range(MAX_STEPS):
        async with client.messages.stream(model=model, max_tokens=1024, system=SYSTEM,
                                          tools=tools.TOOL_SPECS, messages=messages) as stream:
            async for chunk in stream.text_stream:
                if first_token is None:
                    first_token = time.perf_counter() - t0
                reply += chunk
                yield {"type": "text", "data": chunk}
            final = await stream.get_final_message()
        steps += 1
        usage = getattr(final, "usage", None)
        tokens_in += getattr(usage, "input_tokens", 0) or 0
        tokens_out += getattr(usage, "output_tokens", 0) or 0
        messages.append({"role": "assistant", "content": final.content})
        calls = [b for b in final.content if b.type == "tool_use"]
        if not calls:
            break
        out = []
        for c in calls:
            ts = time.perf_counter()
            bad_entry = (c.name == "position_size" and isinstance(c.input.get("entry"), (int, float))
                         and not guardrails.is_grounded(float(c.input["entry"]), results, user_text))
            if bad_entry:   # the model must not size a trade from a price it made up
                res = {"error": "entry price is not from get_price or from the user. Call get_price first, then retry."}
            else:
                res = tools.run_tool(c.name, c.input, feed)
            tool_secs += time.perf_counter() - ts
            results.append(res)
            yield {"type": "tool", "name": c.name, "args": c.input, "result": res}
            out.append({"type": "tool_result", "tool_use_id": c.id, "content": str(res)})
        messages.append({"role": "user", "content": out})
        reply += "\n"
    bad = guardrails.unverified_numbers(reply, results, user_text)
    if bad:
        yield {"type": "warning", "numbers": bad,
               "message": "These numbers were not returned by any tool and may be wrong: " + ", ".join(bad)}
    metrics = {"ts": time.time(), "model": model, "steps": steps, "tool_calls": len(results),
               "tool_errors": sum(1 for r in results if "error" in r), "tokens_in": tokens_in,
               "tokens_out": tokens_out, "latency_s": round(time.perf_counter() - t0, 3),
               "first_token_s": round(first_token, 3) if first_token is not None else None,
               "tool_s": round(tool_secs, 4), "unverified_numbers": len(bad)}
    if PRICE_IN and PRICE_OUT:
        metrics["cost_usd"] = round((tokens_in * float(PRICE_IN) + tokens_out * float(PRICE_OUT)) / 1e6, 6)
    _write_metrics(metrics)
    yield {"type": "metrics", **metrics}
    yield {"type": "done"}
