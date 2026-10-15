import { anthropic } from '@ai-sdk/anthropic';
import type { UIMessage } from 'ai';
import { createChatResponse } from '@/lib/chat';
import { createTools } from '@/lib/tools';

export async function POST(req: Request) {
  const body = (await req.json().catch(() => null)) as { messages?: UIMessage[] } | null;
  const messages = body?.messages;
  if (!Array.isArray(messages) || messages.length === 0 || messages.length > 40) {
    return Response.json({ error: 'messages must be an array of 1 to 40 items' }, { status: 400 });
  }
  return createChatResponse({
    model: anthropic(process.env.LLM_MODEL ?? 'claude-sonnet-5-5'),
    messages,
    tools: createTools(process.env.BACKEND_URL ?? 'http://127.0.0.1:8000'),
  });
}
