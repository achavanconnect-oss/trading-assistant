import {
  convertToModelMessages,
  createUIMessageStreamResponse,
  isStepCount,
  streamText,
  toUIMessageStream,
  type LanguageModel,
  type ToolSet,
  type UIMessage,
} from 'ai';

export const MAX_STEPS = 6;

export const SYSTEM =
  'You are a trading assistant inside an analysis product. Rules: ' +
  '(1) Never state a price, balance or position size that did not come from a tool result in this conversation; ' +
  'call a tool, or say you do not have it. ' +
  '(2) You cannot place, modify or close trades and must say so if asked. ' +
  '(3) Not financial advice: describe, do not instruct the user to trade. ' +
  '(4) If a tool returns an error, explain it plainly; do not guess a value. ' +
  'Be concise.';

/** Streams a tool-calling reply as an AI SDK UI message stream. Model and tools are injected for testing. */
export async function createChatResponse(opts: {
  model: LanguageModel;
  messages: UIMessage[];
  tools: ToolSet;
}): Promise<Response> {
  const result = streamText({
    model: opts.model,
    system: SYSTEM,
    messages: await convertToModelMessages(opts.messages),
    tools: opts.tools,
    stopWhen: isStepCount(MAX_STEPS),
  });
  return createUIMessageStreamResponse({ stream: toUIMessageStream({ stream: result.stream }) });
}
