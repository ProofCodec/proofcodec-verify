import { describe, it, expect } from 'vitest';
import { decodeDeltaGaps, decodeEnumRank, decodeBitmap, decodeLabelsFixed, decodeEmptyRun, extractBits } from '../src/residual.js';
import { rankSubset } from '../src/combinadic.js';

// Helper: encode unsigned LEB128
function leb128Encode(value) {
  const bytes = [];
  do {
    let byte = value & 0x7f;
    value >>>= 7;
    if (value > 0) byte |= 0x80;
    bytes.push(byte);
  } while (value > 0);
  return new Uint8Array(bytes);
}

describe('decodeDeltaGaps', () => {
  it('decodes [3, 7, 10]', () => {
    // first=3, gap1=7-3-1=3, gap2=10-7-1=2
    const data = new Uint8Array([...leb128Encode(3), ...leb128Encode(3), ...leb128Encode(2)]);
    const [indices, offset] = decodeDeltaGaps(data, 3);
    expect(indices).toEqual([3, 7, 10]);
    expect(offset).toBe(data.length);
  });

  it('decodes empty', () => {
    const [indices, offset] = decodeDeltaGaps(new Uint8Array(), 0);
    expect(indices).toEqual([]);
    expect(offset).toBe(0);
  });

  it('decodes single', () => {
    const data = leb128Encode(42);
    const [indices] = decodeDeltaGaps(data, 1);
    expect(indices).toEqual([42]);
  });
});

describe('decodeEnumRank', () => {
  it('decodes [2, 5, 7] from rank', () => {
    const rank = Number(rankSubset([2, 5, 7], 10));
    const rankBytes = rank > 0 ? [rank] : [0]; // small enough for 1 byte
    const data = new Uint8Array([...leb128Encode(rankBytes.length), ...rankBytes]);
    const [indices] = decodeEnumRank(data, 10, 3);
    expect(indices).toEqual([2, 5, 7]);
  });

  it('rank_len=0 means [0,1,...,k-1]', () => {
    const data = leb128Encode(0);
    const [indices] = decodeEnumRank(data, 10, 3);
    expect(indices).toEqual([0, 1, 2]);
  });
});

describe('decodeBitmap', () => {
  it('decodes bits 0, 3, 7 in n=16', () => {
    const bitmap = new Uint8Array([0b10001001, 0b00000000]);
    const [indices, offset] = decodeBitmap(bitmap, 16);
    expect(indices).toEqual([0, 3, 7]);
    expect(offset).toBe(2);
  });

  it('decodes empty bitmap', () => {
    const [indices] = decodeBitmap(new Uint8Array(2), 16);
    expect(indices).toEqual([]);
  });
});

describe('decodeLabelsFixed', () => {
  it('2-bit legacy: [W, D, L]', () => {
    // codes [2, 1, 0] packed at 2-bit positions: byte = 0b00_01_10 = 0x06
    const [labels] = decodeLabelsFixed(new Uint8Array([0x06]), 3, 0, null);
    expect(labels).toEqual([1, 0, -1]); // W, D, L
  });

  it('1-bit conditional: leaf_pred=1, remaining [-1, 0]', () => {
    // bit 0 → remaining[0]=-1, bit 1 → remaining[1]=0
    // Pack [L, D] = [0, 1] = 0b10 = 0x02
    const [labels] = decodeLabelsFixed(new Uint8Array([0x02]), 2, 0, 1);
    expect(labels).toEqual([-1, 0]); // L, D
  });

  it('empty', () => {
    const [labels] = decodeLabelsFixed(new Uint8Array(), 0);
    expect(labels).toEqual([]);
  });
});

describe('extractBits', () => {
  it('within single byte', () => {
    const data = new Uint8Array([0b11010110]);
    expect(extractBits(data, 0, 3)).toBe(0b110); // bits [0,1,2]
    expect(extractBits(data, 3, 2)).toBe(0b10);  // bits [3,4]
  });

  it('cross-byte boundary', () => {
    const data = new Uint8Array([0b11000000, 0b00000011]);
    // bits [6,7] from byte 0 = 11, bit [0] from byte 1 = 1 → 111 = 7
    expect(extractBits(data, 6, 3)).toBe(7);
  });
});

describe('decodeLabelsFixed — multi-class', () => {
  it('3-bit fixed (8 classes): [0, 3, 5, 7]', () => {
    // label 0=000, label 3=011, label 5=101, label 7=111
    // bit stream: 000 011 101 111 (12 bits)
    // byte 0 (bits 0-7): 0,0,0, 0,1,1, 1,0 = 0x58
    // byte 1 (bits 8-11): 1, 1,1,1 = 0x0F
    const [labels, off] = decodeLabelsFixed(new Uint8Array([0x58, 0x0F]), 4, 0, null, 8);
    expect(labels).toEqual([0, 3, 5, 7]);
    expect(off).toBe(2);
  });

  it('conditional 8-class: leaf_pred=0, labels [3, 5]', () => {
    // remaining=[1,2,3,4,5,6,7], ceil(log2(7))=3 bits
    // label 3 → index 2 in remaining → code 010
    // label 5 → index 4 in remaining → code 100
    // bits: 010 100 (6 bits) → byte 0x22
    const [labels, off] = decodeLabelsFixed(new Uint8Array([0x22]), 2, 0, 0, 8);
    expect(labels).toEqual([3, 5]);
    expect(off).toBe(1);
  });

  it('2-bit legacy cross-byte: 5 labels', () => {
    // [W=1, D=0, L=-1, W=1, D=0] = codes [2, 1, 0, 2, 1]
    // bits (LE): 10 01 00 10 01 (10 bits)
    // byte 0 bits[0..7]: 0,1,1,0,0,0,0,1 = 0x86, byte 1: 0x01
    const [labels, off] = decodeLabelsFixed(new Uint8Array([0x86, 0x01]), 5, 0, null, 0);
    expect(labels).toEqual([1, 0, -1, 1, 0]);
    expect(off).toBe(2);
  });

  it('backwards compat: legacy 3-class with nClasses=0', () => {
    const [labels] = decodeLabelsFixed(new Uint8Array([0x06]), 3, 0, null, 0);
    expect(labels).toEqual([1, 0, -1]);
  });
});

describe('decodeEmptyRun', () => {
  it('decodes run length', () => {
    const data = new Uint8Array([0x00, ...leb128Encode(5)]);
    const [runLen] = decodeEmptyRun(data);
    expect(runLen).toBe(5);
  });
});
