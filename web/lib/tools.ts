import { tool } from 'ai';
import { z } from 'zod';

type Fetch = typeof fetch;

/** Call one read-only tool on the FastAPI backend. Failures come back as {error} so the model explains them. */
async function callBackend(base: string, name: string, args: unknown, f: Fetch): Promise<unknown> {
  try {
    const res = await f(`${base}/tools/${name}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(args),
    });
    if (!res.ok) return { error: `backend returned HTTP ${res.status} for ${name}` };
    return await res.json();
  } catch (e) {
    return { error: `backend unreachable: ${e instanceof Error ? e.message : String(e)}` };
  }
}

/** The same four read-only tools as the Python agent. There is deliberately no order tool. */
export function createTools(base: string, f: Fetch = fetch) {
  return {
    get_price: tool({
      description: 'Current bid/ask for a symbol. The only valid source of live prices.',
      inputSchema: z.object({ symbol: z.string() }),
      execute: args => callBackend(base, 'get_price', args, f),
    }),
    get_candles: tool({
      description: 'Recent OHLC candles (max 50) for a symbol and timeframe (M5, M15, H1, H4, D1).',
      inputSchema: z.object({
        symbol: z.string(),
        timeframe: z.string(),
        count: z.number().int().min(1).max(50).optional(),
      }),
      execute: args => callBackend(base, 'get_candles', args, f),
    }),
    get_account_summary: tool({
      description: 'Balance, equity and number of open positions.',
      inputSchema: z.object({}),
      execute: args => callBackend(base, 'get_account_summary', args, f),
    }),
    position_size: tool({
      description:
        'Lot size so that hitting the stop loses risk_pct of balance (max 5). Calculation only; does not place a trade.',
      inputSchema: z.object({
        symbol: z.string(),
        balance: z.number(),
        risk_pct: z.number(),
        entry: z.number(),
        stop: z.number(),
      }),
      execute: args => callBackend(base, 'position_size', args, f),
    }),
  };
}
