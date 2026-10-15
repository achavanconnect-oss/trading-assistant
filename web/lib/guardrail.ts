// Port of app/guardrails.py: every price-like number in a reply must come from a tool result
// (or from something the user typed). Anything else is flagged as unverified.

// decimals (1.0852), thousands-separated numbers (2,650.50) and integers of 3+ digits; skips percentages
const NUM = /(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d{3,})(?!\d)(?!\s*%)/g;

export function numbersIn(value: unknown, out: Set<number> = new Set()): Set<number> {
  if (typeof value === 'number' && Number.isFinite(value)) out.add(value);
  else if (Array.isArray(value)) value.forEach(v => numbersIn(v, out));
  else if (value && typeof value === 'object') Object.values(value).forEach(v => numbersIn(v, out));
  return out;
}

function parse(raw: string): number {
  return Number(raw.replace(/,/g, ''));
}

export function unverifiedNumbers(
  reply: string,
  toolOutputs: unknown[],
  userText = '',
  relTol = 1e-4,
): string[] {
  const known = new Set<number>();
  toolOutputs.forEach(o => numbersIn(o, known));
  for (const m of userText.matchAll(NUM)) known.add(parse(m[1]));

  const bad: string[] = [];
  for (const m of reply.matchAll(NUM)) {
    const v = parse(m[1]);
    const ok = [...known].some(k => Math.abs(v - k) <= relTol * Math.max(Math.abs(k), 1));
    if (!ok) bad.push(m[1]);
  }
  return bad;
}
