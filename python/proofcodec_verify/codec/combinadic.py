"""Combinadic encoding for subset indices.

Encodes a k-subset of [0, n) as a single integer rank in [0, C(n,k)).
Uses the combinatorial number system (combinadic) convention:

    rank = sum_{j=1..k} C(i_j, j)  where i_1 < i_2 < ... < i_k

This makes subset {0, 1, ..., k-1} have rank 0.

Key functions:
- rank_subset(indices, n) -> int: encode sorted indices to rank
- unrank_subset(rank, n, k) -> List[int]: decode rank to sorted indices
- binom_bitlen(n, k) -> int: compute ceil(log2(C(n,k)))
"""

from __future__ import annotations

import io
import math
from typing import List

import leb128


def binom(n: int, k: int) -> int:
    """Compute binomial coefficient C(n, k).

    Returns 0 if k < 0 or k > n, consistent with combinadic convention.
    """
    if k < 0 or k > n:
        return 0
    return math.comb(n, k)


def binom_bitlen(n: int, k: int) -> int:
    """Compute ceil(log2(C(n, k))), i.e., bits needed to store a rank.

    Returns 0 if C(n,k) <= 1 (only one possible subset).
    """
    if k <= 0 or k >= n:
        return 0

    if n <= 1000:
        c = binom(n, k)
        return c.bit_length() if c > 1 else 0

    log2_approx = (
        math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
    ) / math.log(2)

    return max(0, int(math.ceil(log2_approx - 1e-9)))


def rank_subset(indices: List[int], n: int) -> int:
    """Encode a sorted k-subset of [0, n) as a combinadic rank.

    Args:
        indices: Sorted list of distinct integers in [0, n)
        n: Universe size

    Returns:
        Integer rank in [0, C(n, k))
    """
    if not indices:
        return 0

    rank = 0
    for j, idx in enumerate(indices, start=1):
        rank += binom(idx, j)

    return rank


def unrank_subset(rank: int, n: int, k: int) -> List[int]:
    """Decode a combinadic rank to a sorted k-subset of [0, n).

    Args:
        rank: Integer in [0, C(n, k))
        n: Universe size
        k: Subset size

    Returns:
        Sorted list of k distinct integers in [0, n)
    """
    if k == 0:
        return []

    indices = [0] * k
    upper = n - 1

    for j in range(k, 0, -1):
        i = _find_largest_binom_le(rank, j, j - 1, upper)
        indices[j - 1] = i
        rank -= binom(i, j)
        upper = i - 1

    return indices


def _find_largest_binom_le(target: int, k: int, lo: int, hi: int) -> int:
    """Find largest i in [lo, hi] such that C(i, k) <= target."""
    if lo > hi:
        return lo - 1

    if hi - lo < 32:
        result = lo - 1
        for i in range(lo, hi + 1):
            if binom(i, k) <= target:
                result = i
            else:
                break
        return result

    result = lo - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c = binom(mid, k)
        if c <= target:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1

    return result


# === Varint decoding (LEB128) ===

def decode_uvarint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """Decode LEB128 varint from bytes.

    Args:
        data: Byte buffer
        offset: Starting position

    Returns:
        (value, new_offset) tuple
    """
    reader = io.BytesIO(data[offset:])
    value, bytes_read = leb128.u.decode_reader(reader)
    return value, offset + bytes_read


# === Big-endian integer decoding for ENUM_RANK ===

def decode_bigint_be(data: bytes) -> int:
    """Decode big-endian bytes to non-negative integer."""
    return int.from_bytes(data, 'big')
