'use client';

import { useChat } from '@ai-sdk/react';
import { useState } from 'react';
import { unverifiedNumbers } from '@/lib/guardrail';
import { messageText, toolOutputs, userText } from '@/lib/messages';

export default function Chat() {
  const [input, setInput] = useState('');
  const { messages, sendMessage, status, error } = useChat();
  const busy = status === 'submitted' || status === 'streaming';

  return (
    <main>
      <h1>Trading Assistant</h1>
      <p className="note">Read-only. Cannot place trades. Not financial advice.</p>

      <section className="log" aria-live="polite">
        {messages.map((m, idx) => {
          const isLast = idx === messages.length - 1;
          const warn =
            m.role === 'assistant' && !(isLast && busy)
              ? unverifiedNumbers(messageText(m), toolOutputs(m), userText(messages.slice(0, idx)))
              : [];
          return (
            <div key={m.id} className={`msg ${m.role}`}>
              <strong>{m.role === 'user' ? 'You' : 'Assistant'}</strong>
              {m.parts.map((part, i) => {
                if (part.type === 'text') return <p key={i}>{part.text}</p>;
                if (part.type.startsWith('tool-') && 'state' in part) {
                  const name = part.type.slice(5);
                  return (
                    <div key={i} className="tool">
                      <code>
                        {name}({JSON.stringify('input' in part ? part.input : {})})
                      </code>
                      {part.state === 'output-available' && <pre>{JSON.stringify(part.output, null, 2)}</pre>}
                      {part.state === 'output-error' && <span className="warn">tool error: {part.errorText}</span>}
                      {(part.state === 'input-streaming' || part.state === 'input-available') && <em> running...</em>}
                    </div>
                  );
                }
                return null;
              })}
              {warn.length > 0 && (
                <p className="warn" role="alert">
                  These numbers were not returned by any tool and may be wrong: {warn.join(', ')}
                </p>
              )}
            </div>
          );
        })}
        {error && <p className="warn">Error: {error.message}</p>}
      </section>

      <form
        onSubmit={e => {
          e.preventDefault();
          const text = input.trim();
          if (!text || busy) return;
          sendMessage({ text });
          setInput('');
        }}
      >
        <input
          value={input}
          onChange={e => setInput(e.currentTarget.value)}
          placeholder="e.g. Size a EURUSD trade at 1% risk with a stop 20 pips below the current price"
          aria-label="Message"
        />
        <button disabled={busy}>Send</button>
      </form>
    </main>
  );
}
