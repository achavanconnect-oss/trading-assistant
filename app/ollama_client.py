"""Local-model backend with the small slice of the Anthropic async client that app/agent.py uses.

    client.messages.stream(model=, max_tokens=, system=, tools=, messages=)  -> async context manager with
        .text_stream (async iterator of text chunks) and await .get_final_message() -> .content blocks, .usage

so `agent.run_chat` works unchanged on a free local model served by Ollama (it needs a tool-capable model,
e.g. qwen2.5:7b-instruct). Small models follow tool-use rules less reliably than Claude: the number guardrail
still checks every reply.
"""
import json
from types import SimpleNamespace as NS
from typing import AsyncIterator

import httpx


def to_ollama_tools(specs: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}} for t in specs]


def _get(block, key, default=None):
    return block.get(key, default) if isinstance(block, dict) else getattr(block, key, default)


def to_ollama_messages(system: str, messages: list[dict]) -> list[dict]:
    """Convert Anthropic-style messages (text, tool_use and tool_result blocks) to Ollama chat messages."""
    out = [{"role": "system", "content": system}]
    names: dict[str, str] = {}
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
        elif m["role"] == "assistant":
            text = "".join(_get(b, "text", "") for b in content if _get(b, "type") == "text")
            calls = []
            for b in content:
                if _get(b, "type") == "tool_use":
                    names[_get(b, "id")] = _get(b, "name")
                    calls.append({"function": {"name": _get(b, "name"), "arguments": _get(b, "input") or {}}})
            msg = {"role": "assistant", "content": text}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:  # user turn made of tool_result blocks
            for b in content:
                if _get(b, "type") == "tool_result":
                    out.append({"role": "tool", "tool_name": names.get(_get(b, "tool_use_id"), ""),
                                "content": str(_get(b, "content", ""))})
    return out


class _Stream:
    def __init__(self, client: "OllamaClient", model, system, tools, messages, **_):
        self.client, self.model = client, model
        self.body = {"model": model, "stream": True, "options": {"temperature": 0},
                     "messages": to_ollama_messages(system, messages), "tools": to_ollama_tools(tools or [])}
        self._text = ""
        self._calls: list[dict] = []
        self._usage = NS(input_tokens=0, output_tokens=0)
        self._done = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def _chunks(self) -> AsyncIterator[str]:
        async with httpx.AsyncClient(base_url=self.client.base_url, transport=self.client.transport, timeout=None) as c:
            async with c.stream("POST", "/api/chat", json=self.body) as r:
                if r.status_code != 200:
                    raise RuntimeError(f"Ollama returned HTTP {r.status_code}: {(await r.aread())[:200]!r}")
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    msg = d.get("message") or {}
                    if msg.get("content"):
                        self._text += msg["content"]
                        yield msg["content"]
                    for tc in msg.get("tool_calls") or []:
                        self._calls.append(tc["function"])
                    if d.get("done"):
                        self._usage = NS(input_tokens=d.get("prompt_eval_count", 0), output_tokens=d.get("eval_count", 0))
        self._done = True

    @property
    def text_stream(self) -> AsyncIterator[str]:
        return self._chunks()

    async def get_final_message(self):
        if not self._done:
            async for _ in self._chunks():
                pass
        blocks = []
        if self._text:
            blocks.append(NS(type="text", text=self._text))
        for i, fn in enumerate(self._calls):
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            blocks.append(NS(type="tool_use", id=f"call_{len(self.body['messages'])}_{i}", name=fn["name"], input=args))
        return NS(content=blocks, usage=self._usage)


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434", transport: httpx.AsyncBaseTransport | None = None):
        self.base_url, self.transport = base_url, transport
        self.messages = self

    def stream(self, **kw) -> _Stream:
        return _Stream(self, **kw)
