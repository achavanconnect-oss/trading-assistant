import { describe, expect, it, vi } from 'vitest';
import { createTools } from '@/lib/tools';

const ctx = { toolCallId: 't1', messages: [] } as never;

describe('createTools', () => {
  it('exposes exactly the four read-only tools and no order tool', () => {
    const names = Object.keys(createTools('http://backend'));
    expect(names.sort()).toEqual(['get_account_summary', 'get_candles', 'get_price', 'position_size']);
    expect(names.some(n => /order|buy|sell|close|modify/.test(n))).toBe(false);
  });

  it('posts tool arguments to the backend and returns its JSON', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ symbol: 'EURUSD', bid: 1.085 }))) as unknown as typeof fetch;
    const out = await createTools('http://backend', f).get_price.execute!({ symbol: 'EURUSD' }, ctx);
    expect(out).toEqual({ symbol: 'EURUSD', bid: 1.085 });
    const [url, init] = (f as unknown as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://backend/tools/get_price');
    expect(JSON.parse(init.body as string)).toEqual({ symbol: 'EURUSD' });
  });

  it('turns HTTP errors and network failures into {error} instead of throwing', async () => {
    const bad = vi.fn(async () => new Response('x', { status: 500 })) as unknown as typeof fetch;
    expect(await createTools('http://b', bad).get_price.execute!({ symbol: 'EURUSD' }, ctx)).toEqual({
      error: 'backend returned HTTP 500 for get_price',
    });
    const down = vi.fn(async () => { throw new Error('ECONNREFUSED'); }) as unknown as typeof fetch;
    const r = (await createTools('http://b', down).get_price.execute!({ symbol: 'EURUSD' }, ctx)) as { error: string };
    expect(r.error).toContain('backend unreachable: ECONNREFUSED');
  });
});
