"""v18 Binary Codec: Read-only implementation for residual file format.

File Structure:
    [Header]
    [LeafIndexTable]
    [LeafBlobs...]

Header contains magic, version, block_size, hashes.
LeafIndexTable enables random access per leaf.
LeafBlobs are self-contained per-leaf records with RecordStreams.

NOTE: This module contains ONLY reading/deserialization functions.
The encoder is proprietary and available via the ProofCodec commercial offering.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Dict, Optional, Tuple

from .combinadic import decode_uvarint
from .residual_v18 import (
    IndexEncoding,
    RecordType,
    BlockData,
    decode_block,
    decode_empty_run,
)


# === Constants ===

MAGIC = b'CEGR'  # CEGAR residual
DEFAULT_BLOCK_SIZE = 4096


class LabelCodec(IntEnum):
    """Label encoding mode."""
    FIXED_2BIT = 0
    HUFFMAN = 1
    CONDITIONAL_1BIT = 2


class PartitionMode(IntEnum):
    """Context partitioning mode."""
    LEAF_BLOCK = 0       # v18.0: (leaf_id, block_id)
    LEAF_BLOCK_PRED = 1  # v18.1: (leaf_id, block_id, pred_label)


# === Header ===

@dataclass
class V18Header:
    """File header for v18 residual encoding.

    Layout (little-endian):
        magic: 4 bytes "CEGR"
        version_major: u16
        version_minor: u16
        flags: u32
        block_size: u32
        num_leaves: u32
        partition_mode: u8
        label_codec: u8
        reserved: 2 bytes
        model_hash: 32 bytes (SHA-256)
        syzygy_hash: 32 bytes (SHA-256)
        leaf_index_offset: u64
        total_positions: u64
        total_mismatches: u64
    """
    version_major: int = 18
    version_minor: int = 0
    flags: int = 0
    block_size: int = DEFAULT_BLOCK_SIZE
    num_leaves: int = 0
    partition_mode: PartitionMode = PartitionMode.LEAF_BLOCK
    label_codec: LabelCodec = LabelCodec.FIXED_2BIT
    model_hash: bytes = field(default_factory=lambda: b'\x00' * 32)
    syzygy_hash: bytes = field(default_factory=lambda: b'\x00' * 32)
    leaf_index_offset: int = 0
    total_positions: int = 0
    total_mismatches: int = 0

    FIXED_SIZE = 4 + 2 + 2 + 4 + 4 + 4 + 1 + 1 + 2 + 32 + 32 + 8 + 8 + 8  # 112 bytes

    @classmethod
    def from_bytes(cls, data: bytes) -> 'V18Header':
        """Deserialize header from bytes."""
        if len(data) < cls.FIXED_SIZE:
            raise ValueError(f"Header too short: {len(data)} < {cls.FIXED_SIZE}")

        (
            magic,
            version_major,
            version_minor,
            flags,
            block_size,
            num_leaves,
            partition_mode,
            label_codec,
            model_hash,
            syzygy_hash,
            leaf_index_offset,
            total_positions,
            total_mismatches,
        ) = struct.unpack('<4sHHIIIBB2x32s32sQQQ', data[:cls.FIXED_SIZE])

        if magic != MAGIC:
            raise ValueError(f"Invalid magic: {magic} != {MAGIC}")

        return cls(
            version_major=version_major,
            version_minor=version_minor,
            flags=flags,
            block_size=block_size,
            num_leaves=num_leaves,
            partition_mode=PartitionMode(partition_mode),
            label_codec=LabelCodec(label_codec),
            model_hash=model_hash,
            syzygy_hash=syzygy_hash,
            leaf_index_offset=leaf_index_offset,
            total_positions=total_positions,
            total_mismatches=total_mismatches,
        )


# === LeafIndexTable ===

@dataclass
class LeafIndexEntry:
    """Entry in leaf index table."""
    leaf_id: int
    blob_offset: int
    blob_len: int

    SIZE = 4 + 8 + 8  # 20 bytes

    @classmethod
    def from_bytes(cls, data: bytes, offset: int = 0) -> 'LeafIndexEntry':
        leaf_id, blob_offset, blob_len = struct.unpack(
            '<IQQ', data[offset:offset + cls.SIZE]
        )
        return cls(leaf_id=leaf_id, blob_offset=blob_offset, blob_len=blob_len)


def read_leaf_index_table(data: bytes, num_leaves: int, offset: int = 0) -> List[LeafIndexEntry]:
    """Deserialize leaf index table."""
    entries = []
    for i in range(num_leaves):
        entry = LeafIndexEntry.from_bytes(data, offset + i * LeafIndexEntry.SIZE)
        entries.append(entry)
    return entries


# === LeafBlob ===

@dataclass
class LeafBlobHeader:
    """Header for a single leaf blob."""
    leaf_id: int
    base_pred_label: int  # -1, 0, or 1
    n_leaf: int
    num_blocks: int
    k_leaf: int
    record_stream_len: int
    record_stream_crc32: int
    n_leaf_pred: Optional[List[int]] = None  # [n_L, n_D, n_W]

    SIZE_V180 = 4 + 1 + 4 + 4 + 4 + 8 + 4  # 29 bytes
    SIZE_V181 = SIZE_V180 + 12  # + 3 x u32 = 41 bytes

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        offset: int = 0,
        partition_mode: PartitionMode = PartitionMode.LEAF_BLOCK
    ) -> Tuple['LeafBlobHeader', int]:
        """Deserialize leaf blob header. Returns (header, new_offset)."""
        (
            leaf_id,
            pred_code,
            n_leaf,
            num_blocks,
            k_leaf,
            record_stream_len,
            record_stream_crc32,
        ) = struct.unpack('<IBIIIQ I', data[offset:offset + cls.SIZE_V180])

        base_pred_label = pred_code - 1  # 0 -> -1, 1 -> 0, 2 -> 1
        new_offset = offset + cls.SIZE_V180

        n_leaf_pred = None
        if partition_mode == PartitionMode.LEAF_BLOCK_PRED:
            n_L, n_D, n_W = struct.unpack('<III', data[new_offset:new_offset + 12])
            n_leaf_pred = [n_L, n_D, n_W]
            new_offset += 12

        return cls(
            leaf_id=leaf_id,
            base_pred_label=base_pred_label,
            n_leaf=n_leaf,
            num_blocks=num_blocks,
            k_leaf=k_leaf,
            record_stream_len=record_stream_len,
            record_stream_crc32=record_stream_crc32,
            n_leaf_pred=n_leaf_pred,
        ), new_offset


@dataclass
class LeafBlob:
    """Complete leaf blob: header + record stream."""
    header: LeafBlobHeader
    record_stream: bytes

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        offset: int = 0,
        partition_mode: PartitionMode = PartitionMode.LEAF_BLOCK,
    ) -> Tuple['LeafBlob', int]:
        """Deserialize leaf blob. Returns (blob, new_offset)."""
        header, offset = LeafBlobHeader.from_bytes(data, offset, partition_mode)
        record_stream = data[offset:offset + header.record_stream_len]
        offset += header.record_stream_len

        # Verify CRC if non-zero
        if header.record_stream_crc32 != 0:
            actual_crc = zlib.crc32(record_stream) & 0xFFFFFFFF
            if actual_crc != header.record_stream_crc32:
                raise ValueError(
                    f"CRC mismatch for leaf {header.leaf_id}: "
                    f"{actual_crc:08x} != {header.record_stream_crc32:08x}"
                )

        return cls(header=header, record_stream=record_stream), offset


# === RecordStream Decoder ===

def decode_record_stream(
    data: bytes,
    num_blocks: int,
    n_leaf: int,
    block_size: int,
    leaf_prediction: Optional[int] = None,
) -> List[Tuple[int, Optional[BlockData]]]:
    """Decode a RecordStream into list of (block_id, block_data).

    Args:
        data: Raw record stream bytes
        num_blocks: Number of blocks in this leaf
        n_leaf: Total positions in this leaf
        block_size: Block size
        leaf_prediction: Leaf's majority class for 1-bit conditional decoding

    Returns list of tuples where block_data is None for empty blocks.
    """
    offset = 0
    block_id = 0
    results = []

    while block_id < num_blocks and offset < len(data):
        rec_hdr = data[offset]
        rec_type = RecordType(rec_hdr & 0x3)

        if rec_type == RecordType.EMPTY_RUN:
            run_len, offset = decode_empty_run(data, offset)
            for _ in range(run_len):
                results.append((block_id, None))
                block_id += 1
        elif rec_type == RecordType.NON_EMPTY_BLOCK:
            if block_id < num_blocks - 1:
                n_b = block_size
            else:
                n_b = n_leaf - block_id * block_size

            block_data, _, offset = decode_block(data, n_b, offset, leaf_prediction=leaf_prediction)
            results.append((block_id, block_data))
            block_id += 1
        else:
            raise ValueError(f"Unknown record type: {rec_type}")

    return results


# === Full File Reader ===

@dataclass
class V18ResidualFile:
    """Complete v18 residual file (read-only)."""
    header: V18Header
    leaf_index: List[LeafIndexEntry]
    leaf_blobs: Dict[int, LeafBlob]  # leaf_id -> blob

    @classmethod
    def from_bytes(cls, data: bytes) -> 'V18ResidualFile':
        """Deserialize entire file from bytes."""
        header = V18Header.from_bytes(data)

        leaf_index = read_leaf_index_table(
            data,
            header.num_leaves,
            header.leaf_index_offset,
        )

        leaf_blobs = {}
        for entry in leaf_index:
            blob, _ = LeafBlob.from_bytes(
                data,
                entry.blob_offset,
                header.partition_mode,
            )
            leaf_blobs[entry.leaf_id] = blob

        return cls(
            header=header,
            leaf_index=leaf_index,
            leaf_blobs=leaf_blobs,
        )

    @classmethod
    def from_file(cls, path: str) -> 'V18ResidualFile':
        """Read and deserialize from file path."""
        with open(path, 'rb') as f:
            return cls.from_bytes(f.read())

    def build_lookup_cache(self) -> Dict[int, Dict[int, Dict[int, int]]]:
        """Build cached lookup: {leaf_id: {block_id: {idx_in_block: label}}}"""
        cache: Dict[int, Dict[int, Dict[int, int]]] = {}

        for leaf_id, blob in self.leaf_blobs.items():
            n_leaf = blob.header.n_leaf
            leaf_pred = blob.header.base_pred_label if self.header.label_codec == LabelCodec.CONDITIONAL_1BIT else None
            blocks = decode_record_stream(
                blob.record_stream,
                blob.header.num_blocks,
                n_leaf,
                self.header.block_size,
                leaf_prediction=leaf_pred,
            )

            leaf_cache: Dict[int, Dict[int, int]] = {}
            for bid, block_data in blocks:
                if block_data is not None and block_data.indices:
                    block_cache = {
                        idx: label
                        for idx, label in zip(block_data.indices, block_data.labels)
                    }
                    leaf_cache[bid] = block_cache

            cache[leaf_id] = leaf_cache

        return cache

    def lookup(self, leaf_id: int, block_id: int, idx_in_block: int) -> Optional[int]:
        """Look up correction for a specific position.

        Returns WDL label if position is a mismatch, None otherwise.
        For bulk lookups, use build_lookup_cache() instead.
        """
        if leaf_id not in self.leaf_blobs:
            return None

        blob = self.leaf_blobs[leaf_id]
        n_leaf = blob.header.n_leaf

        leaf_pred = blob.header.base_pred_label if self.header.label_codec == LabelCodec.CONDITIONAL_1BIT else None
        blocks = decode_record_stream(
            blob.record_stream,
            blob.header.num_blocks,
            n_leaf,
            self.header.block_size,
            leaf_prediction=leaf_pred,
        )

        for bid, block_data in blocks:
            if bid == block_id:
                if block_data is None:
                    return None
                try:
                    pos = block_data.indices.index(idx_in_block)
                    return block_data.labels[pos]
                except ValueError:
                    return None

        return None

    def summary(self) -> dict:
        """Return a summary of file contents."""
        total_mismatches = sum(
            blob.header.k_leaf for blob in self.leaf_blobs.values()
        )
        total_positions = sum(
            blob.header.n_leaf for blob in self.leaf_blobs.values()
        )
        return {
            "version": f"{self.header.version_major}.{self.header.version_minor}",
            "block_size": self.header.block_size,
            "num_leaves": self.header.num_leaves,
            "label_codec": self.header.label_codec.name,
            "partition_mode": self.header.partition_mode.name,
            "total_positions": total_positions,
            "total_mismatches": total_mismatches,
            "header_total_positions": self.header.total_positions,
            "header_total_mismatches": self.header.total_mismatches,
        }
