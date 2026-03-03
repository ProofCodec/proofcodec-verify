# Codec Specification

**Version**: v20 (extends v18.2-freeze)
**Date**: March 2026

---

## Frozen Parameters

### Block Size
- `DEFAULT_BLOCK_SIZE = 4096` positions per block
- Leaf-local blocking: block_id = position_in_leaf // block_size

### Baseline Definitions

**Baseline A**: Fixed 2-bit encoding
- W(+1) → 00, D(0) → 01, L(-1) → 10
- Bits = total_positions × 2

**Baseline B**: Global Huffman encoding
- Single codebook for entire domain
- **Deterministic tie-break**: L(-1) < D(0) < W(+1) when frequencies equal
- Code lengths: most frequent → 1 bit, others → 2 bits

### MDL Encoding Selection

Three encodings for index sets within blocks:

| Encoding | Tag | Best For | Bits |
|----------|-----|----------|------|
| DELTA_GAPS | 0 | Sparse (k ≪ n) | first + Σ gaps (varint) |
| ENUM_RANK | 1 | Moderate k | ⌈log₂(C(n,k))⌉ |
| BITMAP | 2 | Dense (k → n) | n bits |

Selection: minimum description length wins per block.

### Context Partitioning

- **partition_mode**: LEAF_BLOCK
- Each decision tree leaf forms a context
- Blocks are local to each leaf (not global)

### Label Codec

- **v18.2**: `label_codec: FIXED_2BIT` — 2 bits per correction label
- **v20**: `label_codec: conditional_1bit` — 1 bit per correction label (binary: correct class known from leaf majority, correction selects from remaining 2 classes)

### v20 Extensions

**Best-of-N Tree Selection** (v20):
- `n_random_seeds: 10` — train 10 trees per (depth, leaf_size) candidate
- Select tree with minimum `total_bits = tree_bits + residual_bits`
- Deterministic per seed (seeds 42, 43, ..., 51)

**Iterative Residual Boosting** (v20):
- Second-stage tree trained on mismatch positions from first tree
- `max_depth_t2: 8`, `min_samples_leaf_t2: 50`
- Combined encoding: T1 tree + T2 tree + joint residual

**Feature Set** (v20):
- `feature_set: v20_endgame` — 49 features (17 chess-specific + v2 base)
- v18.2 used `v1` — 8 coarse features

---

## File Format

```
Header (32 bytes):
  magic: "CEGR" (4 bytes)
  version_major: u16
  version_minor: u16
  flags: u32
  block_size: u32
  num_leaves: u32
  partition_mode: u8
  label_codec: u8
  reserved: u16
  total_positions: u64
  total_mismatches: u32
  model_hash: u32

LeafIndex (8 bytes × num_leaves):
  leaf_id: u32
  offset: u32

LeafBlobs (variable):
  For each leaf:
    LeafBlobHeader (24 bytes)
    RecordStream (variable)
```

---

## Reproducibility Guarantees

1. **Enumeration order**: Strictly ascending by canonical index
2. **Huffman tie-break**: L < D < W
3. **MDL selection**: Deterministic (minimum bits, tie-break by encoding tag)
4. **Random seed**: Fixed (default 42) for tree training

---

## Reference Implementation

- `proofcodec_verify/baseline/baselines.py` - Baseline A, B computation
- `proofcodec_verify/codec/v18_codec.py` - Binary format
- `proofcodec_verify/codec/residual_v18.py` - MDL encoding selection
