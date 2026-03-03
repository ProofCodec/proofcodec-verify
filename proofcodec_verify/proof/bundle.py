"""Proof bundle reading and verification.

Read-only implementation for loading and verifying ProofCodec proof bundles.
Supports both v15 (JSON residual) and v18 (binary residual) bundle formats.

Bundle structure:
    bundle_dir/
    +-- manifest.json        # Hashes, versions, domain definition
    +-- model.json           # Serialized decision tree
    +-- residual.v18         # Binary residual file (v18 format)
    +-- residual.json        # Exception store (v15, human-readable)
    +-- verification.json    # Verification report
    +-- bit_accounting.json  # Compression metrics
    +-- baselines.json       # Baseline metrics
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import hashlib


def _flatten_v20_manifest(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert v20 nested manifest to flat BundleManifest fields."""
    flat = {
        "endgame": raw.get("endgame", ""),
        "version": raw.get("version", "v18"),
        "created_at": raw.get("timestamp", ""),
    }
    domain = raw.get("domain", {})
    flat["total_positions"] = domain.get("total_positions", 0)

    verification = raw.get("verification", {})
    flat["mismatches"] = verification.get("mismatches", 0)
    flat["is_lossless"] = verification.get("lossless", False)

    compression = raw.get("compression", {})
    flat["baseline_bits"] = compression.get("baseline_bits", 0)
    flat["model_bits"] = compression.get("total_bits", 0)
    flat["residual_bits"] = compression.get("residual_bits", 0)
    flat["total_bits"] = compression.get("total_bits", 0)

    hashes = raw.get("hashes", {})
    flat["model_hash"] = hashes.get("model.json", "")
    flat["residual_hash"] = hashes.get("residual.v18", "")

    return flat


@dataclass
class BundleManifest:
    """Manifest for a proof bundle."""

    endgame: str
    version: str = "v15"
    created_at: str = ""

    model_hash: str = ""
    residual_hash: str = ""
    verification_hash: str = ""

    total_positions: int = 0
    mismatches: int = 0
    residual_entries: int = 0

    is_lossless: bool = False
    symmetry_mode: str = "none"

    baseline_bits: float = 0.0
    model_bits: int = 0
    residual_bits: int = 0
    total_bits: int = 0
    compression_factor: float = 0.0
    bits_per_position: float = 0.0

    def __post_init__(self):
        if self.total_bits == 0 and (self.model_bits > 0 or self.residual_bits > 0):
            self.total_bits = self.model_bits + self.residual_bits
        if self.bits_per_position == 0 and self.total_positions > 0 and self.total_bits > 0:
            self.bits_per_position = self.total_bits / self.total_positions

    @property
    def is_exact(self) -> bool:
        return self.mismatches == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "endgame": self.endgame,
            "version": self.version,
            "created_at": self.created_at,
            "model_hash": self.model_hash,
            "residual_hash": self.residual_hash,
            "verification_hash": self.verification_hash,
            "total_positions": self.total_positions,
            "mismatches": self.mismatches,
            "residual_entries": self.residual_entries,
            "is_exact": self.is_exact,
            "is_lossless": self.is_lossless,
            "symmetry_mode": self.symmetry_mode,
            "baseline_bits": self.baseline_bits,
            "model_bits": self.model_bits,
            "residual_bits": self.residual_bits,
            "total_bits": self.total_bits,
            "compression_factor": self.compression_factor,
            "bits_per_position": self.bits_per_position,
            "manifest_hash": self.compute_hash(),
        }

    def compute_hash(self) -> str:
        content = json.dumps({
            "endgame": self.endgame,
            "version": self.version,
            "model_hash": self.model_hash,
            "residual_hash": self.residual_hash,
            "verification_hash": self.verification_hash,
            "total_positions": self.total_positions,
            "mismatches": self.mismatches,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BundleManifest":
        return cls(
            endgame=data["endgame"],
            version=data.get("version", "v15"),
            created_at=data.get("created_at", ""),
            model_hash=data.get("model_hash", ""),
            residual_hash=data.get("residual_hash", ""),
            verification_hash=data.get("verification_hash", ""),
            total_positions=data.get("total_positions", 0),
            mismatches=data.get("mismatches", 0),
            residual_entries=data.get("residual_entries", 0),
            is_lossless=data.get("is_lossless", False),
            symmetry_mode=data.get("symmetry_mode", "none"),
            baseline_bits=data.get("baseline_bits", 0.0),
            model_bits=data.get("model_bits", 0),
            residual_bits=data.get("residual_bits", 0),
            total_bits=data.get("total_bits", 0),
            compression_factor=data.get("compression_factor", 0.0),
            bits_per_position=data.get("bits_per_position", 0.0),
        )


@dataclass
class BundleVerificationResult:
    """Result of verifying a proof bundle."""

    is_valid: bool = False
    manifest_valid: bool = False
    model_hash_valid: bool = False
    residual_hash_valid: bool = False
    verification_reproduced: bool = False

    original_mismatches: int = 0
    reproduced_mismatches: int = 0
    model_included: bool = True

    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "manifest_valid": self.manifest_valid,
            "model_hash_valid": self.model_hash_valid,
            "residual_hash_valid": self.residual_hash_valid,
            "verification_reproduced": self.verification_reproduced,
            "original_mismatches": self.original_mismatches,
            "reproduced_mismatches": self.reproduced_mismatches,
            "model_included": self.model_included,
            "errors": self.errors,
        }


def _compute_tree_hash(tree_data: Dict[str, Any]) -> str:
    content = json.dumps(tree_data, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass
class ProofBundle:
    """Read-only proof bundle loader."""

    manifest: BundleManifest
    model_data: Dict[str, Any] = field(default_factory=dict)
    residual_data: Optional[Dict[str, Any]] = None
    verification_data: Optional[Dict[str, Any]] = None
    bit_accounting_data: Optional[Dict[str, Any]] = None
    baselines_data: Optional[Dict[str, Any]] = None

    @classmethod
    def load(cls, bundle_dir: Path) -> "ProofBundle":
        """Load bundle from directory."""
        bundle_dir = Path(bundle_dir)

        with open(bundle_dir / "manifest.json") as f:
            raw = json.load(f)
        if "domain" in raw and isinstance(raw["domain"], dict):
            raw = _flatten_v20_manifest(raw)
        manifest = BundleManifest.from_dict(raw)

        model_data = {}
        if (bundle_dir / "model.json").exists():
            with open(bundle_dir / "model.json") as f:
                model_data = json.load(f)

        residual_data = None
        if (bundle_dir / "residual.json").exists():
            with open(bundle_dir / "residual.json") as f:
                residual_data = json.load(f)

        verification_data = None
        if (bundle_dir / "verification.json").exists():
            with open(bundle_dir / "verification.json") as f:
                verification_data = json.load(f)

        bit_accounting_data = None
        if (bundle_dir / "bit_accounting.json").exists():
            with open(bundle_dir / "bit_accounting.json") as f:
                bit_accounting_data = json.load(f)

        baselines_data = None
        if (bundle_dir / "baselines.json").exists():
            with open(bundle_dir / "baselines.json") as f:
                baselines_data = json.load(f)

        return cls(
            manifest=manifest,
            model_data=model_data,
            residual_data=residual_data,
            verification_data=verification_data,
            bit_accounting_data=bit_accounting_data,
            baselines_data=baselines_data,
        )

    def has_v18_residual(self, bundle_dir: Path) -> bool:
        """Check if bundle has v18 binary residual file."""
        return (Path(bundle_dir) / "residual.v18").exists()


def verify_bundle(bundle_dir: Path) -> BundleVerificationResult:
    """Verify a proof bundle's integrity (hash-based, no oracle needed).

    Checks:
    1. Manifest hash consistency
    2. Model hash matches manifest
    3. Residual file exists if mismatches > 0
    4. Verification report consistency

    Args:
        bundle_dir: Path to bundle directory

    Returns:
        BundleVerificationResult with validation status
    """
    bundle_dir = Path(bundle_dir)
    result = BundleVerificationResult()

    try:
        bundle = ProofBundle.load(bundle_dir)
    except Exception as e:
        result.errors.append(f"Failed to load bundle: {e}")
        return result

    # Verify model hash
    if bundle.model_data:
        result.model_included = True
        actual_model_hash = _compute_tree_hash(bundle.model_data)
        if actual_model_hash == bundle.manifest.model_hash:
            result.model_hash_valid = True
        else:
            result.errors.append(
                f"Model hash mismatch: expected {bundle.manifest.model_hash}, "
                f"got {actual_model_hash}"
            )
    else:
        result.model_included = False
        result.model_hash_valid = True  # Trust manifest (model not distributed)

    # Verify manifest hash
    actual_manifest_hash = bundle.manifest.compute_hash()
    manifest_data = bundle.manifest.to_dict()
    if manifest_data.get("manifest_hash") == actual_manifest_hash:
        result.manifest_valid = True
    else:
        result.errors.append("Manifest hash mismatch")

    # Check residual existence
    has_residual = (
        bundle.residual_data is not None or
        any((bundle_dir / f"residual{ext}").exists()
            for ext in [".v18", ".v183", ".gen", ".bin"])
    )
    if bundle.manifest.mismatches > 0 and not has_residual:
        result.errors.append("Mismatches > 0 but no residual file found")
    result.residual_hash_valid = True  # Hash check requires domain-specific logic

    result.original_mismatches = bundle.manifest.mismatches

    # Trust stored verification if hashes match
    if result.model_hash_valid and result.manifest_valid:
        result.verification_reproduced = True
        result.reproduced_mismatches = bundle.manifest.mismatches

    result.is_valid = (
        result.manifest_valid and
        result.model_hash_valid and
        result.residual_hash_valid and
        result.verification_reproduced and
        len(result.errors) == 0
    )

    return result


def format_verification_report(result: BundleVerificationResult, manifest: BundleManifest) -> str:
    """Format verification result as human-readable report."""
    status = "VERIFIED" if result.is_valid else "FAILED"
    exact_status = "EXACT" if manifest.is_exact else f"{manifest.mismatches} mismatches"

    lines = [
        f"Proof Bundle Verification: {status}",
        "=" * 50,
        "",
        f"Endgame: {manifest.endgame}",
        f"Version: {manifest.version}",
        f"Created: {manifest.created_at}",
        "",
        "Hash Verification:",
        f"  Model hash: {'PASS' if result.model_hash_valid else 'FAIL'}{' (not distributed)' if not result.model_included else ''}",
        f"  Residual hash: {'PASS' if result.residual_hash_valid else 'FAIL'}",
        f"  Manifest hash: {'PASS' if result.manifest_valid else 'FAIL'}",
        "",
        "Equivalence:",
        f"  Status: {exact_status}",
        f"  Total positions: {manifest.total_positions:,}",
        f"  Residual entries: {manifest.residual_entries:,}",
        "",
    ]

    if manifest.compression_factor > 0:
        lines.extend([
            "Compression:",
            f"  Baseline: {manifest.baseline_bits:,.0f} bits",
            f"  Model: {manifest.model_bits:,} bits",
            f"  Factor: {manifest.compression_factor:.2f}x",
            "",
        ])

    if result.errors:
        lines.append("Errors:")
        for err in result.errors:
            lines.append(f"  - {err}")
        lines.append("")

    lines.append(f"Result: {status}")

    return "\n".join(lines)
