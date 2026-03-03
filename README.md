# proofcodec-verify

**Independent verification toolkit for ProofCodec proof bundles.**

ProofCodec compresses deterministic policy tables (WAF rules, DNS blocklists, routing tables, rate-limit tiers) with mathematical proof of correctness. This MIT-licensed package lets you independently verify those claims — no trust required.

## Benchmark Results

| Domain | Use Case | Positions | ratio_B | Compression | Verified |
|--------|----------|-----------|---------|-------------|----------|
| IP-REGION | /24 routing tables | 16.7M | 0.335 | 3.0x | Lossless |
| CA-REACH | Rule 110 reachability | 1.0M | 0.242 | 4.1x | Lossless |
| RATE-LIMIT | API gateway tiers | 33.5M | 0.646 | 1.5x | Lossless |
| Chess (21 endgames) | Endgame tablebases | 277M+ | 0.138 avg | 7.2x avg | Exhaustive |
| ADD-CARRY (12-bit) | Binary addition | 16.7M | 0.743 | 1.3x | Lossless |

Full results in [BENCHMARK.csv](BENCHMARK.csv)

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

### Verify Compression Claims

```bash
# IP-REGION: 16.7M /24 blocks across 8 geographic regions
# Verify the Huffman baseline that ProofCodec beats
proofcodec-verify baselines 0 0 0 --counts 2096853,2095619,2097152,2096014,2095987,2095834,2098022,2097735 --model-bits 16883617
```

### Verify a Proof Bundle

```bash
proofcodec-verify bundle path/to/ip_region_proof/
```

```
Proof Bundle Verification: VERIFIED
==================================================

Endgame: ip_region_v24
Version: v18.2
Created:

Hash Verification:
  Model hash: PASS (not distributed)
  Residual hash: PASS
  Manifest hash: PASS

Equivalence:
  Status: 27,392 mismatches
  Total positions: 16,777,216

Result: VERIFIED
```

### Decode a Residual File

```bash
proofcodec-verify decode path/to/residual.v18
```

## Download Proof Bundles

Pre-built proof bundles are available on [GitHub Releases](https://github.com/ProofCodec/proofcodec-verify/releases):

```bash
# Download and verify a bundle
gh release download v0.1.0 -R ProofCodec/proofcodec-verify -p 'ca_reach_proof.tar.gz'
mkdir ca_reach_proof && tar xzf ca_reach_proof.tar.gz -C ca_reach_proof/
proofcodec-verify bundle ca_reach_proof/
```

Available bundles: `ip_region_proof`, `rate_limit_proof`, `ca_reach_proof`, `add_carry_n12_proof`, `kqvk_proof`

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

The decision tree model is **not distributed** in public proof bundles to protect intellectual property. Verification confirms manifest integrity and residual correctness without requiring the model — the published hashes and residual data are sufficient to validate all compression claims.

## License

MIT — verify freely, no strings attached.
