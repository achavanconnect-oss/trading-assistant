import json, os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app import agent, data, tools

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "static")
app = FastAPI(title="Trading Assistant")


class ChatIn(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=40)


def get_client():
    if agent.PROVIDER == "ollama":
        from app.ollama_client import OllamaClient
        return OllamaClient(os.getenv("OLLAMA_URL", "http://localhost:11434"))
    if agent.PROVIDER != "anthropic":
        raise RuntimeError(f"unknown LLM_PROVIDER {agent.PROVIDER!r}; use 'ollama' or 'anthropic'")
    try:
        from anthropic import AsyncAnthropic
    except ImportError as e:
        raise RuntimeError("LLM_PROVIDER=anthropic needs: pip install anthropic (and ANTHROPIC_API_KEY)") from e
    return AsyncAnthropic()  # reads ANTHROPIC_API_KEY from the environment


def get_feed():
    return data.get_feed()


@app.post("/chat")
async def chat(body: ChatIn, client=Depends(get_client), feed=Depends(get_feed)):
    async def sse():
        try:
            async for ev in agent.run_chat(client, body.messages, feed):
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
    return StreamingResponse(sse(), media_type="text/event-stream")


@app.post("/tools/{name}")
def call_tool(name: str, args: dict | None = None, feed=Depends(get_feed)):
    """Run one read-only tool by name. Used by the Next.js front end; unknown names are rejected."""
    if name not in {t["name"] for t in tools.TOOL_SPECS}:
        raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
    return tools.run_tool(name, args or {}, feed)


@app.get("/health")
def health():
    return {"ok": True, "provider": agent.PROVIDER, "model": agent.MODEL, "feed": "mt5" if os.getenv("MT5_ENABLED") == "1" else "demo"}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
