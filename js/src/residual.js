/**
 * v18/v20 residual block decoding.
 *
 * Decode-only implementation for three index encoding strategies:
 * 1. DELTA_GAPS (tag 0): first + gap varints
 * 2. ENUM_RANK (tag 1): combinadic rank
 * 3. BITMAP   (tag 2): n-bit mask
 *
 * Label codecs:
 * - FIXED_2BIT: 2 bits per label (legacy v18)
 * - CONDITIONAL_1BIT: 1 bit per label (v20)
 */

import { decodeUvarint } from './leb128.js';
import { unrankSubset, decodeBigintBe } from './combinadic.js';

export const IndexEncoding = { DELTA_GAPS: 0, ENUM_RANK: 1, BITMAP: 2 };
export const RecordType = { EMPTY_RUN: 0, NON_EMPTY_BLOCK: 1 };

/**
 * Extract `width` bits starting at bit position `bitPos` from data,
 * handling cross-byte boundaries.
 * @param {Uint8Array} data
 * @param {number} bitPos - absolute bit position
 * @param {number} width - number of bits to read (1-8)
 * @returns {number}
 */
export function extractBits(data, bitPos, width) {
  const byteIdx = bitPos >> 3;
  const bitIdx = bitPos & 7;
  const bitsThisByte = Math.min(width, 8 - bitIdx);
  let value = (data[byteIdx] >> bitIdx) & ((1 << bitsThisByte) - 1);
  if (bitsThisByte < width) {
    const bitsNext = width - bitsThisByte;
    value |= (data[byteIdx + 1] & ((1 << bitsNext) - 1)) << bitsThisByte;
  }
  return value;
}

/**
 * Decode k indices from delta gaps format.
 * @param {Uint8Array} data
 * @param {number} k
 * @param {number} offset
 * @returns {[number[], number]}
 */
export function decodeDeltaGaps(data, k, offset = 0) {
  if (k === 0) return [[], offset];
  const indices = [];
  let [first, off] = decodeUvarint(data, offset);
  indices.push(first);
  for (let i = 1; i < k; i++) {
    let gap;
    [gap, off] = decodeUvarint(data, off);
    indices.push(indices[i - 1] + 1 + gap);
  }
  return [indices, off];
}

/**
 * Decode k indices from enum rank format.
 * @param {Uint8Array} data
 * @param {number} n — block size
 * @param {number} k
 * @param {number} offset
 * @returns {[number[], number]}
 */
export function decodeEnumRank(data, n, k, offset = 0) {
  if (k === 0) return [[], offset];
  let [rankLen, off] = decodeUvarint(data, offset);
  if (rankLen === 0) {
    return [Array.from({ length: k }, (_, i) => i), off];
  }
  const rankBytes = data.slice(off, off + rankLen);
  off += rankLen;
  const rank = decodeBigintBe(rankBytes);
  const indices = unrankSubset(rank, n, k);
  return [indices, off];
}

/**
 * Decode indices from bitmap format.
 * @param {Uint8Array} data
 * @param {number} n
 * @param {number} offset
 * @returns {[number[], number]}
 */
export function decodeBitmap(data, n, offset = 0) {
  const numBytes = (n + 7) >> 3;
  const indices = [];
  for (let byteIdx = 0; byteIdx < numBytes; byteIdx++) {
    const byte = data[offset + byteIdx];
    for (let bitIdx = 0; bitIdx < 8; bitIdx++) {
      if (byte & (1 << bitIdx)) {
        const idx = byteIdx * 8 + bitIdx;
        if (idx < n) indices.push(idx);
      }
    }
  }
  return [indices, offset + numBytes];
}

/**
 * Decode k labels from packed format.
 *
 * When leafPrediction is provided, uses conditional decoding:
 *   - Filters out the base prediction from the class list
 *   - Uses ceil(log2(remaining)) bits per label
 * When null, uses fixed-width decoding:
 *   - Legacy (nClasses <= 3): 2 bits per label, code-1 mapping
 *   - Multi-class (nClasses > 3): ceil(log2(nClasses)) bits per label, identity mapping
 *
 * @param {Uint8Array} data
 * @param {number} k
 * @param {number} offset
 * @param {number|null} leafPrediction
 * @param {number} nClasses - number of classes (0 = legacy 3-class WDL)
 * @returns {[number[], number]}
 */
export function decodeLabelsFixed(data, k, offset = 0, leafPrediction = null, nClasses = 0) {
  if (k === 0) return [[], offset];

  // Resolve class list
  const isLegacy = nClasses === 0 || nClasses === 3;
  const allClasses = isLegacy
    ? [-1, 0, 1]
    : Array.from({ length: nClasses }, (_, i) => i);

  if (leafPrediction !== null) {
    // Conditional decoding: exclude base prediction, variable bit width
    const remaining = allClasses.filter(c => c !== leafPrediction).sort((a, b) => a - b);
    const bitsPerLabel = Math.max(1, Math.ceil(Math.log2(remaining.length)));
    const totalBits = k * bitsPerLabel;
    const numBytes = (totalBits + 7) >> 3;
    const labels = [];
    for (let i = 0; i < k; i++) {
      const code = extractBits(data, offset * 8 + i * bitsPerLabel, bitsPerLabel);
      labels.push(remaining[code]);
    }
    return [labels, offset + numBytes];
  } else {
    // Fixed-width decoding
    const bitsPerLabel = isLegacy ? 2 : Math.max(1, Math.ceil(Math.log2(allClasses.length)));
    const totalBits = k * bitsPerLabel;
    const numBytes = (totalBits + 7) >> 3;
    const labels = [];
    for (let i = 0; i < k; i++) {
      const code = extractBits(data, offset * 8 + i * bitsPerLabel, bitsPerLabel);
      labels.push(isLegacy ? code - 1 : code);
    }
    return [labels, offset + numBytes];
  }
}

/**
 * Decode a NON_EMPTY_BLOCK record.
 * @param {Uint8Array} data
 * @param {number} nB — block size
 * @param {number} offset
 * @param {number|null} leafPrediction
 * @param {number} nClasses - number of classes (0 = legacy 3-class WDL)
 * @returns {[{indices: number[], labels: number[]}, number, number]} [blockData, encoding, newOffset]
 */
export function decodeBlock(data, nB, offset = 0, leafPrediction = null, nClasses = 0) {
  const recHdr = data[offset++];
  const encoding = (recHdr >> 2) & 0x3;

  let [k, off] = decodeUvarint(data, offset);
  let indices;

  if (encoding === IndexEncoding.DELTA_GAPS) {
    [indices, off] = decodeDeltaGaps(data, k, off);
  } else if (encoding === IndexEncoding.ENUM_RANK) {
    [indices, off] = decodeEnumRank(data, nB, k, off);
  } else {
    [indices, off] = decodeBitmap(data, nB, off);
  }

  let labels;
  [labels, off] = decodeLabelsFixed(data, k, off, leafPrediction, nClasses);

  return [{ indices, labels }, encoding, off];
}

/**
 * Decode EMPTY_RUN record.
 * @param {Uint8Array} data
 * @param {number} offset
 * @returns {[number, number]} [runLen, newOffset]
 */
export function decodeEmptyRun(data, offset = 0) {
  offset++; // skip record header byte
  let [runLen, off] = decodeUvarint(data, offset);
  return [runLen, off];
}
