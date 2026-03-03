"""ProofCodec Verify: Independent verification toolkit for ProofCodec proof bundles.

This package provides decode-only and verification functionality for the
ProofCodec proof-carrying compression format. It contains NO encoding logic.

MIT Licensed — verify ProofCodec claims independently.

Quick start:
    # Verify a proof bundle
    from proofcodec_verify.proof import verify_bundle, ProofBundle, format_verification_report
    result = verify_bundle("path/to/bundle")
    print(format_verification_report(result, ProofBundle.load("path/to/bundle").manifest))

    # Decode a v18 residual file
    from proofcodec_verify.codec import V18ResidualFile
    residual = V18ResidualFile.from_file("residual.v18")
    print(residual.summary())

    # Compute baselines to verify compression claims
    from proofcodec_verify.baseline import compute_all_baselines
    baselines = compute_all_baselines({-1: 200896, 0: 23048, 1: 144508})
    print(f"Huffman baseline: {baselines.bits_B0:,} bits")
"""

__version__ = "0.1.0"

from .codec import V18ResidualFile, V18Header, BlockData
from .baseline import compute_all_baselines, compute_ratio_B, AllBaselines
from .proof import verify_bundle, ProofBundle, BundleManifest, format_verification_report

__all__ = [
    "__version__",
    # Codec
    "V18ResidualFile", "V18Header", "BlockData",
    # Baselines
    "compute_all_baselines", "compute_ratio_B", "AllBaselines",
    # Proof
    "verify_bundle", "ProofBundle", "BundleManifest", "format_verification_report",
]
