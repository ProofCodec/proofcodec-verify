import { describe, it, expect } from 'vitest';
import { binom, binomBitlen, rankSubset, unrankSubset, decodeBigintBe } from '../src/combinadic.js';

describe('binom', () => {
  it('basic values', () => {
    expect(binom(10, 3)).toBe(120n);
    expect(binom(5, 0)).toBe(1n);
    expect(binom(5, 5)).toBe(1n);
    expect(binom(3, 4)).toBe(0n); // k > n
    expect(binom(0, 0)).toBe(1n);
  });
});

describe('binomBitlen', () => {
  it('basic values', () => {
    expect(binomBitlen(10, 3)).toBe(7); // ceil(log2(120)) = 7
    expect(binomBitlen(5, 0)).toBe(0);
    expect(binomBitlen(5, 5)).toBe(0);
  });
});

describe('rankSubset / unrankSubset', () => {
  it('roundtrip [2, 5, 7] in C(10, 3)', () => {
    const indices = [2, 5, 7];
    const rank = rankSubset(indices, 10);
    const recovered = unrankSubset(rank, 10, 3);
    expect(recovered).toEqual(indices);
  });

  it('smallest subset has rank 0', () => {
    expect(rankSubset([0, 1, 2], 10)).toBe(0n);
  });

  it('largest subset has rank C(n,k)-1', () => {
    expect(rankSubset([7, 8, 9], 10)).toBe(binom(10, 3) - 1n);
  });

  it('unrank empty', () => {
    expect(unrankSubset(0n, 10, 0)).toEqual([]);
  });
});

describe('decodeBigintBe', () => {
  it('decodes big-endian bytes', () => {
    expect(decodeBigintBe(new Uint8Array([0x01, 0x00]))).toBe(256n);
    expect(decodeBigintBe(new Uint8Array([0xff]))).toBe(255n);
    expect(decodeBigintBe(new Uint8Array([]))).toBe(0n);
  });
});
