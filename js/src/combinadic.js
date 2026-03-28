/**
 * Combinadic encoding/decoding for subset indices.
 *
 * Uses BigInt for large values (n > 60) where JS Number loses precision.
 */

/**
 * Compute binomial coefficient C(n, k).
 * Returns 0n if k < 0 or k > n.
 * @param {number} n
 * @param {number} k
 * @returns {bigint}
 */
export function binom(n, k) {
  if (k < 0 || k > n) return 0n;
  if (k === 0 || k === n) return 1n;
  if (k > n - k) k = n - k;
  let result = 1n;
  for (let i = 0; i < k; i++) {
    result = result * BigInt(n - i) / BigInt(i + 1);
  }
  return result;
}

/**
 * Compute ceil(log2(C(n, k))), bits needed to store a rank.
 * @param {number} n
 * @param {number} k
 * @returns {number}
 */
export function binomBitlen(n, k) {
  if (k <= 0 || k >= n) return 0;
  const c = binom(n, k);
  if (c <= 1n) return 0;
  return c.toString(2).length;
}

/**
 * Encode a sorted k-subset of [0, n) as a combinadic rank.
 * @param {number[]} indices — sorted
 * @param {number} n
 * @returns {bigint}
 */
export function rankSubset(indices, n) {
  let rank = 0n;
  for (let j = 0; j < indices.length; j++) {
    rank += binom(indices[j], j + 1);
  }
  return rank;
}

/**
 * Decode a combinadic rank to a sorted k-subset of [0, n).
 * @param {bigint} rank
 * @param {number} n
 * @param {number} k
 * @returns {number[]}
 */
export function unrankSubset(rank, n, k) {
  if (k === 0) return [];
  const indices = new Array(k);
  let upper = n - 1;

  for (let j = k; j >= 1; j--) {
    const i = findLargestBinomLe(rank, j, j - 1, upper);
    indices[j - 1] = i;
    rank -= binom(i, j);
    upper = i - 1;
  }
  return indices;
}

function findLargestBinomLe(target, k, lo, hi) {
  if (lo > hi) return lo - 1;
  let result = lo - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (binom(mid, k) <= target) {
      result = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return result;
}

/**
 * Decode big-endian bytes to a non-negative BigInt.
 * @param {Uint8Array} data
 * @returns {bigint}
 */
export function decodeBigintBe(data) {
  let value = 0n;
  for (const byte of data) {
    value = (value << 8n) | BigInt(byte);
  }
  return value;
}
