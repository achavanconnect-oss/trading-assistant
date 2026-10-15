import json, os
from fastapi import FastAPI, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from app import agent, auth, cache as cache_mod, data, db as db_mod, tools

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "..", "static")
app = FastAPI(title="Trading Assistant")

MAX_LOGIN_FAILS = 5
LOGIN_WINDOW_S = 60


class ChatIn(BaseModel):
    messages: list[dict] = Field(min_length=1, max_length=40)


class RegisterIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)
    password: str = Field(min_length=auth.MIN_PASSWORD_LEN, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=200)


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


# ---- shared singletons, created on first use ----
_state: dict = {}


def get_db():
    if "db" not in _state:
        dsn = os.getenv("DATABASE_URL")
        _state["db"] = db_mod.PgDB(dsn) if dsn else db_mod.MemoryDB()
    return _state["db"]


def get_cache():
    if "cache" not in _state:
        _state["cache"] = cache_mod.make_cache()
    return _state["cache"]


def get_feed():
    key = os.getenv("MT5_ENABLED") == "1"
    if _state.get("feed_key") != key:
        _state["feed"], _state["feed_key"] = data.get_feed(), key
    return cache_mod.CachedFeed(_state["feed"], get_cache())


def current_user(authorization: str | None = Header(default=None)) -> dict | None:
    """None when AUTH_REQUIRED is off (open local demo); otherwise a valid bearer token is required."""
    if not auth.auth_required():
        return None
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        claims = auth.decode_token(authorization[7:].strip())
    except auth.AuthError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return {"id": int(claims["sub"]), "email": claims["email"]}


# ---- accounts ----
@app.post("/auth/register", status_code=201)
def register(body: RegisterIn, db=Depends(get_db)):
    email = body.email.lower()
    try:
        uid = db.create_user(email, auth.hash_password(body.password))
    except db_mod.DuplicateUser:
        raise HTTPException(status_code=409, detail="email already registered")
    return {"id": uid, "email": email}


@app.post("/auth/login")
def login(body: LoginIn, db=Depends(get_db), cache=Depends(get_cache)):
    email = body.email.lower()
    key = f"login_fail:{email}"
    if (cache.get(key) or 0) >= MAX_LOGIN_FAILS:
        raise HTTPException(status_code=429, detail="too many failed attempts; try again in a minute")
    user = db.get_user(email)
    ok = auth.verify_password(body.password, user["pw_hash"] if user else auth._DUMMY_HASH) and user is not None
    if not ok:
        cache.incr(key, LOGIN_WINDOW_S)
        raise HTTPException(status_code=401, detail="invalid email or password")
    cache.delete(key)
    try:
        token = auth.create_token(user["id"], email)
    except auth.AuthError:
        raise HTTPException(status_code=503, detail="server has no JWT_SECRET configured")
    return {"access_token": token, "token_type": "bearer", "expires_in": auth.TOKEN_TTL_S}


@app.get("/history")
def history(user=Depends(current_user), db=Depends(get_db)):
    if user is None:
        raise HTTPException(status_code=400, detail="history needs AUTH_REQUIRED=1 (it is stored per user)")
    return {"messages": db.history(user["id"])}


# ---- chat and tools ----
@app.post("/chat")
async def chat(body: ChatIn, client=Depends(get_client), feed=Depends(get_feed),
               user=Depends(current_user), db=Depends(get_db)):
    last = body.messages[-1]
    if user and last.get("role") == "user" and isinstance(last.get("content"), str):
        db.add_message(user["id"], "user", last["content"])

    async def sse():
        reply = ""
        try:
            async for ev in agent.run_chat(client, body.messages, feed):
                if ev["type"] == "text":
                    reply += ev["data"]
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        if user and reply:
            db.add_message(user["id"], "assistant", reply)
    return StreamingResponse(sse(), media_type="text/event-stream")


@app.post("/tools/{name}")
def call_tool(name: str, args: dict | None = None, feed=Depends(get_feed), user=Depends(current_user)):
    """Run one read-only tool by name. Used by the Next.js front end; unknown names are rejected."""
    if name not in {t["name"] for t in tools.TOOL_SPECS}:
        raise HTTPException(status_code=404, detail=f"unknown tool {name!r}")
    return tools.run_tool(name, args or {}, feed)


@app.get("/health")
def health():
    return {"ok": True, "provider": agent.PROVIDER, "model": agent.MODEL,
            "feed": "mt5" if os.getenv("MT5_ENABLED") == "1" else "demo", "auth_required": auth.auth_required()}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC, "index.html"))
