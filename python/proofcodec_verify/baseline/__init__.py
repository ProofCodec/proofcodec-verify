"""ProofCodec baseline computation for independent verification.

Provides canonical Huffman baseline computation with deterministic
tie-breaks, enabling anyone to independently verify compression claims.
"""

from .huffman_canonical import (
    CANONICAL_WDL_ORDER,
    TIE_BREAK_POLICY_ID,
    HuffmanResult,
    canonical_huffman_code_lengths,
    compute_huffman_bits,
    compute_huffman_result,
    validate_huffman_determinism,
)
from .baselines import (
    BaselineA,
    BaselineU,
    BaselineH,
    BaselineB0,
    BaselineB1,
    AllBaselines,
    compute_all_baselines,
    compute_ratio_B,
)

__all__ = [
    # Huffman
    "CANONICAL_WDL_ORDER", "TIE_BREAK_POLICY_ID",
    "HuffmanResult", "canonical_huffman_code_lengths",
    "compute_huffman_bits", "compute_huffman_result",
    "validate_huffman_determinism",
    # Baselines
    "BaselineA", "BaselineU", "BaselineH", "BaselineB0", "BaselineB1",
    "AllBaselines", "compute_all_baselines", "compute_ratio_B",
]
