import { describe, expect, it } from 'vitest';
import { numbersIn, unverifiedNumbers } from '@/lib/guardrail';

describe('unverifiedNumbers', () => {
  const tool = [{ bid: 1.0852, ask: 1.0853 }];

  it('accepts numbers that came from a tool result', () => {
    expect(unverifiedNumbers('Bid is 1.0852.', tool)).toEqual([]);
  });

  it('flags an invented price', () => {
    expect(unverifiedNumbers('Bid is 1.0999.', tool)).toEqual(['1.0999']);
  });

  it('accepts numbers the user supplied', () => {
    expect(unverifiedNumbers('Stop at 1.0830.', [], 'stop at 1.0830')).toEqual([]);
  });

  it('handles thousands separators and ignores percentages and small integers', () => {
    expect(unverifiedNumbers('Gold is 2,650.5 with 1% risk over 20 pips', [{ bid: 2650.5 }])).toEqual([]);
  });

  it('collects numbers from nested tool output', () => {
    expect([...numbersIn({ a: [{ b: 1 }, { c: { d: 2.5 } }], s: 'x', t: true })].sort()).toEqual([1, 2.5]);
  });
});
