# Trading Assistant

A streaming chat assistant for a trading product: FastAPI backend, Anthropic tool calling, and a plain-JS chat UI.
Built around one rule: **the assistant must never invent a price, and it cannot place trades.**

## How it works
- `app/agent.py`: tool-calling loop on the Anthropic Messages API (`AsyncAnthropic`, streaming). Streams text chunks,
  runs tools the model requests, feeds results back, stops after 6 steps.
- `app/tools.py`: four **read-only** tools: `get_price`, `get_candles`, `get_account_summary`, `position_size`.
  There is no order tool, and a test asserts that none can be added by name (`order`, `buy`, `sell`, `close`, `modify`).
  Tool errors are returned to the model as data so it explains them instead of guessing.
- `app/guardrails.py`: after the reply, every price-like number is checked against the tool results (and numbers the
  user typed). Anything unverified is sent to the UI as a `warning` event. This is a heuristic, not a proof.
- `app/data.py`: market data behind one interface. Default is a deterministic **demo feed** (clearly labelled
  `source: demo`); set `MT5_ENABLED=1` on Windows with MetaTrader 5 installed to read live data. Read-only either way.
- `app/main.py`: `POST /chat` streams Server-Sent Events (`text`, `tool`, `warning`, `error`, `done`); `/health`; static UI.

## Run
```bash
pip install -r requirements.txt
set ANTHROPIC_API_KEY=your_key        # Windows; use export on Linux/macOS
set LLM_MODEL=claude-sonnet-5-5       # optional override
uvicorn app.main:app --reload
```
Open http://127.0.0.1:8000.

### Live data from MetaTrader 5 (Exness or any broker)
Use a **demo** account first. Log in to the MT5 terminal, then:
```bash
pip install MetaTrader5
set MT5_ENABLED=1
set MT5_SYMBOL_SUFFIX=m      # Exness standard = m, cent = c, none = leave unset
set MT5_PATH=C:\Program Files\MetaTrader 5 EXNESS\terminal64.exe   # optional
python scripts/mt5_smoke.py   # prints bid/ask + last candle per symbol; add --account to print balance
uvicorn app.main:app
```
The MT5 feed only reads prices, candles and account info. A test asserts the module never references order functions.
Note: with MT5 enabled, `get_account_summary` sends your balance and equity to the LLM provider as tool output.

## MCP server
The same four read-only tools are exposed over the Model Context Protocol, so any MCP client can use them:
```bash
python -m app.mcp_server        # stdio transport
```
Example Claude Desktop / Claude Code config:
```json
{"mcpServers": {"trading-assistant": {"command": "python", "args": ["-m", "app.mcp_server"], "cwd": "/path/to/trading-assistant"}}}
```
Tool parity with the chat agent and the absence of any order tool are enforced by tests.

## Observability
Every chat turn emits a `metrics` SSE event and appends one JSON line to `logs/metrics.jsonl`: steps, tool calls and errors,
input/output tokens, total latency, time to first token, tool time and count of unverified numbers.
Set `LLM_PRICE_IN_PER_MTOK` and `LLM_PRICE_OUT_PER_MTOK` (from your provider's price list) to also log `cost_usd`.

## Test (no API key or network needed)
```bash
pytest -q
```
The MT5 feed is tested against a stub `MetaTrader5` module (suffix mapping, errors, read-only calls). The agent loop is tested against a scripted fake client: grounded reply (no warning), invented price (warning),
runaway tool loop (capped), SSE endpoint, position-size math and input validation.

## Limitations
- Position sizing uses approximate contract sizes (EURUSD/GBPUSD 100,000; XAUUSD 100; BTCUSD 1) and USD-quoted pairs only.
  Verify with your broker.
- The number check can miss derived figures or flag harmless ones. Treat it as a safety net.
- Not financial advice.
