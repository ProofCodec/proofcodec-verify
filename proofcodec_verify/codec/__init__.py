"""ProofCodec binary codec: decode-only implementation.

This package provides read/decode functionality for the ProofCodec v18
binary residual format. It does NOT include encoding — the encoder is
proprietary and available via the ProofCodec commercial offering.

The codec format is documented in CODEC_SPEC.md (CC-BY-4.0).
"""

from .combinadic import (
    binom,
    binom_bitlen,
    rank_subset,
    unrank_subset,
    decode_uvarint,
    decode_bigint_be,
)
from .residual_v18 import (
    IndexEncoding,
    RecordType,
    BlockData,
    decode_delta_gaps,
    decode_enum_rank,
    decode_bitmap,
    decode_labels_fixed,
    decode_block,
    decode_empty_run,
)
from .v18_codec import (
    MAGIC,
    DEFAULT_BLOCK_SIZE,
    LabelCodec,
    PartitionMode,
    V18Header,
    LeafIndexEntry,
    LeafBlobHeader,
    LeafBlob,
    V18ResidualFile,
    decode_record_stream,
    read_leaf_index_table,
)

__all__ = [
    # Combinadic
    "binom", "binom_bitlen", "rank_subset", "unrank_subset",
    "decode_uvarint", "decode_bigint_be",
    # Residual v18
    "IndexEncoding", "RecordType", "BlockData",
    "decode_delta_gaps", "decode_enum_rank", "decode_bitmap",
    "decode_labels_fixed", "decode_block", "decode_empty_run",
    # v18 Codec
    "MAGIC", "DEFAULT_BLOCK_SIZE", "LabelCodec", "PartitionMode",
    "V18Header", "LeafIndexEntry", "LeafBlobHeader", "LeafBlob",
    "V18ResidualFile", "decode_record_stream", "read_leaf_index_table",
]
