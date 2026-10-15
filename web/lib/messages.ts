import type { UIMessage } from 'ai';

type Part = UIMessage['parts'][number];

export function messageText(m: UIMessage): string {
  return m.parts.map(p => (p.type === 'text' ? p.text : '')).join('');
}

/** Outputs of completed tool calls in a message (tool parts are named `tool-<name>`). */
export function toolOutputs(m: UIMessage): unknown[] {
  return m.parts
    .filter((p: Part) => p.type.startsWith('tool-') && 'state' in p && p.state === 'output-available')
    .map((p: Part) => ('output' in p ? p.output : undefined));
}

export function userText(messages: UIMessage[]): string {
  return messages.filter(m => m.role === 'user').map(messageText).join(' ');
}
