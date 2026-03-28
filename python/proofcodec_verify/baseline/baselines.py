"""Unified baseline computation for independent verification.

Baseline definitions (frozen):
- A (Packed2): 2 bits per position, fixed-length encoding
- U (Uniform3): log2(3) bits per position, theoretical uniform 3-class
- H (EntropyEmp): -Sigma p*log2(p) bits, empirical Shannon entropy
- B0 (HuffmanGlobal): Canonical Huffman, no overhead — PRIMARY CLAIM BASELINE
- B1 (HuffmanGlobal+Header): B0 + header overhead

The headline metric ratio_B is ALWAYS computed as:
    ratio_B = bits_payload / bits_B0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
import math

from .huffman_canonical import (
    TIE_BREAK_POLICY_ID,
    compute_huffman_bits,
    compute_huffman_result,
)


# =============================================================================
# CONSTANTS
# =============================================================================

B1_HEADER_BYTES = 20
B1_HEADER_BITS = B1_HEADER_BYTES * 8


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class BaselineA:
    """Baseline A: Packed 2-bit encoding (fixed-length)."""
    N: int
    total_bits: int
    bpp: float = 2.0

    @classmethod
    def compute(cls, N: int) -> "BaselineA":
        return cls(N=N, total_bits=2 * N, bpp=2.0)


@dataclass
class BaselineU:
    """Baseline U: Uniform 3-class encoding (theoretical)."""
    N: int
    total_bits: float
    bpp: float = field(init=False)

    def __post_init__(self):
        self.bpp = math.log2(3)

    @classmethod
    def compute(cls, N: int) -> "BaselineU":
        return cls(N=N, total_bits=N * math.log2(3))


@dataclass
class BaselineH:
    """Baseline H: Empirical Shannon entropy (theoretical lower bound)."""
    N: int
    total_bits: float
    bpp: float
    entropy_per_symbol: float

    @classmethod
    def compute(cls, counts: Dict[int, int]) -> "BaselineH":
        N = sum(counts.values())
        if N == 0:
            return cls(N=0, total_bits=0.0, bpp=0.0, entropy_per_symbol=0.0)

        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / N
                entropy -= p * math.log2(p)

        return cls(
            N=N,
            total_bits=N * entropy,
            bpp=entropy,
            entropy_per_symbol=entropy,
        )


@dataclass
class BaselineB0:
    """Baseline B0: Global Huffman encoding (no overhead).

    This is the PRIMARY CLAIM BASELINE for ratio_B computation.
    """
    N: int
    total_bits: int
    bpp: float
    code_lengths: Dict[int, int]
    counts: Dict[int, int]
    policy_id: str = TIE_BREAK_POLICY_ID

    @classmethod
    def compute(cls, counts: Dict[int, int]) -> "BaselineB0":
        N = sum(counts.values())
        if N == 0:
            return cls(N=0, total_bits=0, bpp=0.0, code_lengths={}, counts=counts)

        result = compute_huffman_result(counts)
        return cls(
            N=N,
            total_bits=result.total_bits,
            bpp=result.total_bits / N,
            code_lengths=result.code_lengths,
            counts=counts,
            policy_id=result.policy_id,
        )

    def to_dict(self) -> dict:
        return {
            "N": self.N,
            "total_bits": self.total_bits,
            "bpp": self.bpp,
            "code_lengths": {str(k): v for k, v in self.code_lengths.items()},
            "counts": {str(k): v for k, v in self.counts.items()},
            "policy_id": self.policy_id,
        }


@dataclass
class BaselineB1:
    """Baseline B1: Global Huffman with header overhead."""
    N: int
    total_bits: int
    bpp: float
    payload_bits: int
    header_bits: int = B1_HEADER_BITS

    @classmethod
    def compute(cls, counts: Dict[int, int]) -> "BaselineB1":
        N = sum(counts.values())
        if N == 0:
            return cls(N=0, total_bits=0, bpp=0.0, payload_bits=0)

        payload = compute_huffman_bits(counts)
        total = payload + B1_HEADER_BITS

        return cls(
            N=N,
            total_bits=total,
            bpp=total / N,
            payload_bits=payload,
            header_bits=B1_HEADER_BITS,
        )


# =============================================================================
# UNIFIED BASELINE RESULT
# =============================================================================

@dataclass
class AllBaselines:
    """All baseline computations in one structure."""
    A: BaselineA
    U: BaselineU
    H: BaselineH
    B0: BaselineB0
    B1: BaselineB1

    @property
    def bits_A(self) -> int:
        return self.A.total_bits

    @property
    def bits_U(self) -> float:
        return self.U.total_bits

    @property
    def bits_H(self) -> float:
        return self.H.total_bits

    @property
    def bits_B0(self) -> int:
        """Primary baseline for ratio_B computation."""
        return self.B0.total_bits

    @property
    def bits_B1(self) -> int:
        return self.B1.total_bits

    def ratio_B(self, model_bits: int) -> float:
        """Compute ratio_B = model_bits / bits_B0."""
        if self.bits_B0 == 0:
            return float("inf")
        return model_bits / self.bits_B0

    def to_dict(self) -> dict:
        return {
            "policy_id": TIE_BREAK_POLICY_ID,
            "wdl_counts": {
                "W": self.B0.counts.get(1, 0),
                "D": self.B0.counts.get(0, 0),
                "L": self.B0.counts.get(-1, 0),
            },
            "code_lengths": {
                "W": self.B0.code_lengths.get(1),
                "D": self.B0.code_lengths.get(0),
                "L": self.B0.code_lengths.get(-1),
            },
            "bits_A": self.bits_A,
            "bits_U": self.bits_U,
            "bits_H": self.bits_H,
            "bits_B0": self.bits_B0,
            "bits_B1": self.bits_B1,
        }


# =============================================================================
# PUBLIC API
# =============================================================================

def compute_all_baselines(counts: Dict[int, int]) -> AllBaselines:
    """Compute all baselines from WDL counts.

    Args:
        counts: WDL counts as {-1: loss, 0: draw, +1: win}

    Returns:
        AllBaselines with A, U, H, B0, B1
    """
    N = sum(counts.values())

    return AllBaselines(
        A=BaselineA.compute(N),
        U=BaselineU.compute(N),
        H=BaselineH.compute(counts),
        B0=BaselineB0.compute(counts),
        B1=BaselineB1.compute(counts),
    )


def compute_ratio_B(model_bits: int, counts: Dict[int, int]) -> float:
    """Compute ratio_B = model_bits / bits_B0.

    Args:
        model_bits: Total model bits (payload only)
        counts: WDL counts

    Returns:
        Compression ratio vs Huffman baseline (< 1.0 means beats Huffman)
    """
    bits_B0 = compute_huffman_bits(counts)
    if bits_B0 == 0:
        return float("inf")
    return model_bits / bits_B0
