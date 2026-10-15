import { createOpenAICompatible } from '@ai-sdk/openai-compatible';
import type { LanguageModel } from 'ai';

type Env = Record<string, string | undefined>;

/**
 * Pick the language model from environment variables.
 *   LLM_PROVIDER=ollama (default): a free local model through Ollama's OpenAI-compatible API, no key needed.
 *   LLM_PROVIDER=anthropic:        Claude via @ai-sdk/anthropic (optional dependency) and ANTHROPIC_API_KEY.
 */
export async function getModel(env: Env = process.env): Promise<LanguageModel> {
  const provider = (env.LLM_PROVIDER || 'ollama').toLowerCase();

  if (provider === 'anthropic') {
    let mod: typeof import('@ai-sdk/anthropic');
    try {
      mod = await import('@ai-sdk/anthropic');
    } catch {
      throw new Error('LLM_PROVIDER=anthropic needs: npm install @ai-sdk/anthropic (and ANTHROPIC_API_KEY)');
    }
    return mod.anthropic(env.LLM_MODEL || 'claude-sonnet-5-5');
  }

  if (provider !== 'ollama') {
    throw new Error(`unknown LLM_PROVIDER "${provider}"; use "ollama" or "anthropic"`);
  }
  const ollama = createOpenAICompatible({
    name: 'ollama',
    baseURL: `${env.OLLAMA_URL || 'http://localhost:11434'}/v1`,
  });
  return ollama.chatModel(env.LLM_MODEL || 'qwen2.5:7b-instruct');
}
