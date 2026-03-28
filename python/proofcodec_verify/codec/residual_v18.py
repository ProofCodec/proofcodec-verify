"""v18 Residual Decoding: Conditional, enumerative residual decoding.

Decode-only implementation for three index encoding strategies:
1. DELTA_GAPS: first_index + gap varints (best for tiny k)
2. ENUM_RANK: combinadic rank (best for moderate k)
3. BITMAP: n-bit mask (fallback for high k)

NOTE: This module contains ONLY decoding functions. The encoder is
proprietary and available via the ProofCodec commercial offering.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import math
from typing import List, Tuple, Optional

from .combinadic import (
    unrank_subset,
    decode_uvarint,
    decode_bigint_be,
)


class IndexEncoding(IntEnum):
    """Index encoding type for NON_EMPTY_BLOCK records."""
    DELTA_GAPS = 0
    ENUM_RANK = 1
    BITMAP = 2
    RESERVED = 3


class RecordType(IntEnum):
    """Record type in RecordStream."""
    EMPTY_RUN = 0
    NON_EMPTY_BLOCK = 1
    RESERVED_2 = 2
    RESERVED_3 = 3


@dataclass
class BlockData:
    """Data for a single block within a leaf."""
    indices: List[int]  # Mismatch indices within block [0, n_b)
    labels: List[int]   # WDL labels (-1=L, 0=D, 1=W) for each mismatch

    @property
    def k(self) -> int:
        """Number of mismatches."""
        return len(self.indices)

    def validate(self, n_b: int) -> None:
        """Validate block data consistency."""
        assert len(self.indices) == len(self.labels), "indices and labels must match"
        assert self.indices == sorted(self.indices), "indices must be sorted"
        assert len(set(self.indices)) == len(self.indices), "indices must be unique"
        if self.indices:
            assert 0 <= self.indices[0], "indices must be non-negative"
            assert self.indices[-1] < n_b, f"indices must be < n_b={n_b}"


# === Index Decoders ===

def decode_delta_gaps(data: bytes, k: int, offset: int = 0) -> Tuple[List[int], int]:
    """Decode k indices from delta gaps format.

    Returns (indices, new_offset).
    """
    if k == 0:
        return [], offset

    indices = []
    first, offset = decode_uvarint(data, offset)
    indices.append(first)

    for _ in range(k - 1):
        gap, offset = decode_uvarint(data, offset)
        indices.append(indices[-1] + 1 + gap)

    return indices, offset


def decode_enum_rank(data: bytes, n: int, k: int, offset: int = 0) -> Tuple[List[int], int]:
    """Decode k indices from enum rank format.

    Returns (indices, new_offset).
    """
    if k == 0:
        return [], offset

    rank_len, offset = decode_uvarint(data, offset)
    if rank_len == 0:
        return list(range(k)), offset

    rank_bytes = data[offset:offset + rank_len]
    offset += rank_len

    rank = decode_bigint_be(rank_bytes)
    indices = unrank_subset(rank, n, k)

    return indices, offset


def decode_bitmap(data: bytes, n: int, offset: int = 0) -> Tuple[List[int], int]:
    """Decode indices from bitmap format.

    Returns (indices, new_offset).
    """
    num_bytes = (n + 7) // 8
    bitmap = data[offset:offset + num_bytes]
    offset += num_bytes

    indices = []
    for byte_idx, byte_val in enumerate(bitmap):
        for bit_idx in range(8):
            if byte_val & (1 << bit_idx):
                idx = byte_idx * 8 + bit_idx
                if idx < n:
                    indices.append(idx)

    return indices, offset


# === Label Decoding ===

def _extract_bits(data: bytes, bit_pos: int, width: int) -> int:
    """Extract `width` bits from data starting at absolute bit position, handling cross-byte boundaries."""
    byte_idx = bit_pos // 8
    bit_idx = bit_pos % 8
    bits_this_byte = min(width, 8 - bit_idx)
    value = (data[byte_idx] >> bit_idx) & ((1 << bits_this_byte) - 1)
    if bits_this_byte < width:
        bits_next = width - bits_this_byte
        value |= (data[byte_idx + 1] & ((1 << bits_next) - 1)) << bits_this_byte
    return value


def decode_labels_fixed(
    data: bytes, k: int, offset: int = 0,
    leaf_prediction: Optional[int] = None, n_classes: int = 0,
) -> Tuple[List[int], int]:
    """Decode k labels from packed format.

    Args:
        data: Raw bytes
        k: Number of labels
        offset: Current read offset
        leaf_prediction: Base prediction for conditional decoding (None = fixed-width)
        n_classes: Number of classes (0 = legacy 3-class WDL)

    Returns (labels, new_offset).
    """
    if k == 0:
        return [], offset

    is_legacy = n_classes == 0 or n_classes == 3
    all_classes = [-1, 0, 1] if is_legacy else list(range(n_classes))

    if leaf_prediction is not None:
        # Conditional decoding: exclude base prediction, variable bit width
        remaining = sorted(c for c in all_classes if c != leaf_prediction)
        bits_per_label = max(1, math.ceil(math.log2(len(remaining)))) if len(remaining) > 1 else 1
        total_bits = k * bits_per_label
        num_bytes = (total_bits + 7) // 8

        labels = []
        base_bit = offset * 8
        for i in range(k):
            code = _extract_bits(data, base_bit + i * bits_per_label, bits_per_label)
            labels.append(remaining[code])

        return labels, offset + num_bytes
    else:
        # Fixed-width decoding
        bits_per_label = 2 if is_legacy else max(1, math.ceil(math.log2(len(all_classes))))
        total_bits = k * bits_per_label
        num_bytes = (total_bits + 7) // 8

        labels = []
        base_bit = offset * 8
        for i in range(k):
            code = _extract_bits(data, base_bit + i * bits_per_label, bits_per_label)
            labels.append(code - 1 if is_legacy else code)

        return labels, offset + num_bytes


# === Block Decoding ===

def decode_block(
    data: bytes,
    n_b: int,
    offset: int = 0,
    leaf_prediction: Optional[int] = None,
    n_classes: int = 0,
) -> Tuple[BlockData, IndexEncoding, int]:
    """Decode a NON_EMPTY_BLOCK record to BlockData.

    Args:
        data: Raw bytes
        n_b: Block size
        offset: Current read offset
        leaf_prediction: Leaf's majority class for conditional decoding
        n_classes: Number of classes (0 = legacy 3-class WDL)

    Returns:
        (BlockData, encoding_used, new_offset)
    """
    rec_hdr = data[offset]
    offset += 1

    rec_type = RecordType(rec_hdr & 0x3)
    assert rec_type == RecordType.NON_EMPTY_BLOCK

    encoding = IndexEncoding((rec_hdr >> 2) & 0x3)

    k, offset = decode_uvarint(data, offset)

    if encoding == IndexEncoding.DELTA_GAPS:
        indices, offset = decode_delta_gaps(data, k, offset)
    elif encoding == IndexEncoding.ENUM_RANK:
        indices, offset = decode_enum_rank(data, n_b, k, offset)
    else:  # BITMAP
        indices, offset = decode_bitmap(data, n_b, offset)

    labels, offset = decode_labels_fixed(data, k, offset, leaf_prediction=leaf_prediction, n_classes=n_classes)

    return BlockData(indices=indices, labels=labels), encoding, offset


# === Empty Run Decoding ===

def decode_empty_run(data: bytes, offset: int = 0) -> Tuple[int, int]:
    """Decode EMPTY_RUN record.

    Returns (run_len, new_offset).
    """
    rec_hdr = data[offset]
    offset += 1

    rec_type = RecordType(rec_hdr & 0x3)
    assert rec_type == RecordType.EMPTY_RUN

    run_len, offset = decode_uvarint(data, offset)
    return run_len, offset
