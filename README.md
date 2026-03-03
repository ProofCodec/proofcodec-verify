# proofcodec-verify

**Independent verification toolkit for ProofCodec proof bundles.**

ProofCodec compresses deterministic policy tables (WAF rules, DNS blocklists, routing tables, rate-limit tiers) with mathematical proof of correctness. This MIT-licensed package lets you independently verify those claims — no trust required.

## What This Package Does

- **Decode** ProofCodec v18 binary residual files
- **Verify** proof bundle integrity (hash checks, manifest validation)
- **Compute baselines** (Huffman, entropy, fixed-width) to validate compression ratios
- **Inspect** bundle contents without needing the proprietary encoder

## What This Package Does NOT Do

This package contains **no encoding logic**. The ProofCodec encoder is proprietary and available via commercial license. This separation is intentional: you can verify every claim we make without needing to trust our software.

## Install

```bash
pip install proofcodec-verify
```

For chess endgame verification (optional):
```bash
pip install proofcodec-verify[chess]
```

## Quick Start

### Verify a Proof Bundle

```bash
proofcodec-verify bundle path/to/kqvk_proof/
```

```
Proof Bundle Verification: VERIFIED
==================================================

Endgame: KQvK
Version: v15
Created: 2026-02-15T12:00:00Z

Hash Verification:
  Model hash: PASS
  Residual hash: PASS
  Manifest hash: PASS

Equivalence:
  Status: EXACT
  Total positions: 368,452
  Residual entries: 0

Result: VERIFIED
```

### Decode a Residual File

```bash
proofcodec-verify decode results/v20/KQvKR/residual.v18
```

### Verify Compression Claims

```bash
# KQvK: 200,896 losses, 23,048 draws, 144,508 wins
proofcodec-verify baselines 144508 23048 200896 --model-bits 219
```

```
ProofCodec Baseline Computation
==================================================
  Positions: 368,452 (W=144,508, D=23,048, L=200,896)

  Baselines:
    A (2-bit fixed):          736,904 bits  (2.000 bpp)
    B0 (Huffman):             536,008 bits  (1.455 bpp)

  Model bits: 219
  ratio_B: 0.000409
  Beats Huffman: YES
```

## Python API

```python
from proofcodec_verify import (
    V18ResidualFile,
    compute_all_baselines,
    verify_bundle,
    ProofBundle,
    format_verification_report,
)

# Decode residual file
residual = V18ResidualFile.from_file("residual.v18")
print(residual.summary())

# Build lookup cache for O(1) position queries
cache = residual.build_lookup_cache()

# Compute baselines
baselines = compute_all_baselines({-1: 200896, 0: 23048, 1: 144508})
print(f"Huffman baseline: {baselines.bits_B0:,} bits")
print(f"ratio_B with 219 model bits: {baselines.ratio_B(219):.6f}")

# Verify bundle
result = verify_bundle("path/to/bundle")
bundle = ProofBundle.load("path/to/bundle")
print(format_verification_report(result, bundle.manifest))
```

## Codec Format

The v18 binary residual format uses:
- **3 index encodings** per block (MDL-selected): DELTA_GAPS, ENUM_RANK, BITMAP
- **Conditional 1-bit labels**: corrections need only 1 bit (2 remaining classes)
- **Leaf-local blocking**: each decision tree leaf is a separate context
- **CRC32 integrity**: per-leaf record stream verification

Full specification: [CODEC_SPEC.md](CODEC_SPEC.md) (CC-BY-4.0)

## How Verification Works

ProofCodec proof bundles are **self-verifying**:

1. The **decision tree** predicts Win/Draw/Loss for every position
2. The **residual file** corrects every mismatch between tree and ground truth
3. The **manifest** contains SHA-256 hashes of both artifacts
4. `proofcodec-verify` checks hashes, decodes the residual, and validates metrics

This means you can verify compression claims **without access to the encoder, the training data, or any proprietary software**.

## License

MIT — verify freely, no strings attached.
