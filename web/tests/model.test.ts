import { describe, expect, it } from 'vitest';
import { getModel } from '@/lib/model';

type M = { modelId: string; provider: string };

describe('getModel', () => {
  it('defaults to a free local Ollama model with no API key', async () => {
    const m = (await getModel({})) as unknown as M;
    expect(m.modelId).toBe('qwen2.5:7b-instruct');
    expect(m.provider).toContain('ollama');
  });

  it('honours LLM_MODEL for Ollama', async () => {
    expect(((await getModel({ LLM_MODEL: 'llama3.1:8b' })) as unknown as M).modelId).toBe('llama3.1:8b');
  });

  it('uses Anthropic only when explicitly selected', async () => {
    const m = (await getModel({ LLM_PROVIDER: 'anthropic' })) as unknown as M;
    expect(m.modelId).toBe('claude-sonnet-5-5');
    expect(m.provider).toContain('anthropic');
  });

  it('rejects an unknown provider', async () => {
    await expect(getModel({ LLM_PROVIDER: 'nope' })).rejects.toThrow('unknown LLM_PROVIDER');
  });
});
