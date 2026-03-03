"""ProofCodec Verify CLI: Independent verification of proof bundles.

Usage:
    proofcodec-verify bundle <path>      Verify a proof bundle
    proofcodec-verify decode <path>      Decode and summarize a v18 residual file
    proofcodec-verify baselines W D L    Compute baselines for given WDL counts
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def cmd_bundle(args):
    """Verify a proof bundle."""
    from .proof import verify_bundle, ProofBundle, format_verification_report

    bundle_dir = Path(args.path)
    if not bundle_dir.is_dir():
        print(f"Error: {bundle_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    if not (bundle_dir / "manifest.json").exists():
        print(f"Error: No manifest.json found in {bundle_dir}", file=sys.stderr)
        sys.exit(1)

    result = verify_bundle(bundle_dir)
    bundle = ProofBundle.load(bundle_dir)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_verification_report(result, bundle.manifest))

    sys.exit(0 if result.is_valid else 1)


def cmd_decode(args):
    """Decode and summarize a v18 residual file."""
    from .codec import V18ResidualFile

    path = Path(args.path)
    if not path.exists():
        print(f"Error: {path} does not exist", file=sys.stderr)
        sys.exit(1)

    residual = V18ResidualFile.from_file(str(path))
    summary = residual.summary()

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"ProofCodec v18 Residual File: {path.name}")
        print("=" * 50)
        print(f"  Version: {summary['version']}")
        print(f"  Block size: {summary['block_size']:,}")
        print(f"  Leaves: {summary['num_leaves']}")
        print(f"  Label codec: {summary['label_codec']}")
        print(f"  Partition mode: {summary['partition_mode']}")
        print(f"  Total positions: {summary['total_positions']:,}")
        print(f"  Total mismatches: {summary['total_mismatches']:,}")
        if summary['total_positions'] > 0:
            mismatch_rate = summary['total_mismatches'] / summary['total_positions']
            print(f"  Mismatch rate: {mismatch_rate:.4%}")


def cmd_baselines(args):
    """Compute baselines for given WDL counts."""
    from .baseline import compute_all_baselines

    counts = {1: args.W, 0: args.D, -1: args.L}
    N = sum(counts.values())

    if N == 0:
        print("Error: All counts are zero", file=sys.stderr)
        sys.exit(1)

    baselines = compute_all_baselines(counts)

    if args.json:
        print(json.dumps(baselines.to_dict(), indent=2))
    else:
        print(f"ProofCodec Baseline Computation")
        print("=" * 50)
        print(f"  Positions: {N:,} (W={args.W:,}, D={args.D:,}, L={args.L:,})")
        print()
        print("  Baselines:")
        print(f"    A (2-bit fixed):   {baselines.bits_A:>14,} bits  ({baselines.A.bpp:.3f} bpp)")
        print(f"    U (uniform 3):     {baselines.bits_U:>14,.0f} bits  ({baselines.U.bpp:.3f} bpp)")
        print(f"    H (entropy):       {baselines.bits_H:>14,.0f} bits  ({baselines.H.bpp:.3f} bpp)")
        print(f"    B0 (Huffman):      {baselines.bits_B0:>14,} bits  ({baselines.B0.bpp:.3f} bpp)")
        print(f"    B1 (Huffman+hdr):  {baselines.bits_B1:>14,} bits  ({baselines.B1.bpp:.3f} bpp)")
        print()
        print(f"  Code lengths: {baselines.B0.code_lengths}")
        print(f"  Policy: {baselines.B0.policy_id}")

        if args.model_bits is not None:
            ratio = baselines.ratio_B(args.model_bits)
            print()
            print(f"  Model bits: {args.model_bits:,}")
            print(f"  ratio_B: {ratio:.6f}")
            print(f"  Beats Huffman: {'YES' if ratio < 1.0 else 'NO'}")


def main():
    parser = argparse.ArgumentParser(
        prog="proofcodec-verify",
        description="Independent verification toolkit for ProofCodec proof bundles",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # bundle
    p_bundle = subparsers.add_parser("bundle", help="Verify a proof bundle")
    p_bundle.add_argument("path", help="Path to bundle directory")
    p_bundle.add_argument("--json", action="store_true", help="Output as JSON")
    p_bundle.set_defaults(func=cmd_bundle)

    # decode
    p_decode = subparsers.add_parser("decode", help="Decode a v18 residual file")
    p_decode.add_argument("path", help="Path to residual.v18 file")
    p_decode.add_argument("--json", action="store_true", help="Output as JSON")
    p_decode.set_defaults(func=cmd_decode)

    # baselines
    p_baselines = subparsers.add_parser("baselines", help="Compute baselines for WDL counts")
    p_baselines.add_argument("W", type=int, help="Win count")
    p_baselines.add_argument("D", type=int, help="Draw count")
    p_baselines.add_argument("L", type=int, help="Loss count")
    p_baselines.add_argument("--model-bits", type=int, default=None, help="Model bits for ratio_B")
    p_baselines.add_argument("--json", action="store_true", help="Output as JSON")
    p_baselines.set_defaults(func=cmd_baselines)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
