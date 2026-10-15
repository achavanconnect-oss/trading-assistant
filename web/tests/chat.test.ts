import { simulateReadableStream, type UIMessage } from 'ai';
import { MockLanguageModelV4 } from 'ai/test';
import { describe, expect, it, vi } from 'vitest';
import { createChatResponse, SYSTEM } from '@/lib/chat';
import { createTools } from '@/lib/tools';

const usage = {
  inputTokens: { total: 10, noCache: 10, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 5, text: 5, reasoning: undefined },
};
const finish = (unified: 'stop' | 'tool-calls') => ({
  type: 'finish' as const, finishReason: { unified, raw: undefined }, usage,
});

function scriptedModel() {
  return new MockLanguageModelV4({
    doStream: [
      {
        stream: simulateReadableStream({
          chunks: [
            { type: 'tool-call', toolCallId: 'call-1', toolName: 'get_price', input: '{"symbol":"EURUSD"}' },
            finish('tool-calls'),
          ],
        }),
      },
      {
        stream: simulateReadableStream({
          chunks: [
            { type: 'text-start', id: 'text-1' },
            { type: 'text-delta', id: 'text-1', delta: 'EURUSD bid is 1.0852.' },
            { type: 'text-end', id: 'text-1' },
            finish('stop'),
          ],
        }),
      },
    ],
  });
}

const userMsg = (text: string): UIMessage => ({ id: 'u1', role: 'user', parts: [{ type: 'text', text }] });

describe('createChatResponse', () => {
  it('streams a tool call, runs the backend tool, then streams the grounded answer', async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ symbol: 'EURUSD', bid: 1.0852, ask: 1.0853 }))) as unknown as typeof fetch;
    const model = scriptedModel();
    const res = await createChatResponse({
      model,
      messages: [userMsg('Price of EURUSD?')],
      tools: createTools('http://backend', f),
    });
    expect(res.headers.get('content-type')).toContain('text/event-stream');
    const body = await res.text();
    expect(body).toContain('tool-input-available');
    expect(body).toContain('tool-output-available');
    expect(body).toContain('1.0852');
    expect(body).toContain('EURUSD bid is');
    expect((f as unknown as ReturnType<typeof vi.fn>).mock.calls).toHaveLength(1);
    expect(model.doStreamCalls).toHaveLength(2);
  });

  it('sends the safety system prompt and only read-only tools to the model', async () => {
    const model = scriptedModel();
    await (await createChatResponse({ model, messages: [userMsg('hi')], tools: createTools('http://b', vi.fn(async () => new Response('{}')) as unknown as typeof fetch) })).text();
    const call = model.doStreamCalls[0];
    expect(JSON.stringify(call.prompt)).toContain(SYSTEM.slice(0, 40));
    expect((call.tools ?? []).map(t => t.name).sort()).toEqual(['get_account_summary', 'get_candles', 'get_price', 'position_size']);
  });
});
