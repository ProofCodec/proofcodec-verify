"""Canonical Huffman encoding with deterministic tie-breaks.

This module provides the SINGLE SOURCE OF TRUTH for Huffman encoding
of WDL symbols. All baseline computations must use this implementation.

Frozen definitions:
- Symbol order: L < D < W (i.e., -1 < 0 < +1)
- Tie-break policy: When counts are equal, prefer symbol with lower rank
- Internal node merge: When weights equal, prefer (min_symbol_rank, node_id)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional
import heapq


# =============================================================================
# FROZEN DEFINITIONS - DO NOT MODIFY
# =============================================================================

CANONICAL_WDL_ORDER: List[int] = [-1, 0, +1]  # L < D < W

TIE_BREAK_POLICY_ID = "v18.2-huffman-tiebreak-v1"

_SYMBOL_RANK: Dict[int, int] = {
    -1: 0,  # Loss has rank 0 (lowest)
    0: 1,   # Draw has rank 1
    +1: 2,  # Win has rank 2 (highest)
}


# =============================================================================
# HUFFMAN TREE IMPLEMENTATION
# =============================================================================

@dataclass
class HuffmanNode:
    """Node in Huffman tree with tie-break metadata."""

    count: int
    symbol: Optional[int] = None
    left: Optional["HuffmanNode"] = None
    right: Optional["HuffmanNode"] = None
    min_symbol_rank: int = 0
    node_id: int = 0

    def is_leaf(self) -> bool:
        return self.symbol is not None

    def __lt__(self, other: "HuffmanNode") -> bool:
        if self.count != other.count:
            return self.count < other.count
        if self.min_symbol_rank != other.min_symbol_rank:
            return self.min_symbol_rank < other.min_symbol_rank
        return self.node_id < other.node_id


def _build_huffman_tree(counts: Dict[int, int]) -> Optional[HuffmanNode]:
    """Build Huffman tree with deterministic tie-breaking."""
    active_symbols = [(sym, cnt) for sym, cnt in counts.items() if cnt > 0]

    if not active_symbols:
        return None

    heap: List[HuffmanNode] = []
    node_id_counter = 0

    for symbol, count in active_symbols:
        rank = _SYMBOL_RANK.get(symbol, symbol)
        node = HuffmanNode(
            count=count,
            symbol=symbol,
            min_symbol_rank=rank,
            node_id=node_id_counter,
        )
        heapq.heappush(heap, node)
        node_id_counter += 1

    while len(heap) > 1:
        left = heapq.heappop(heap)
        right = heapq.heappop(heap)

        merged = HuffmanNode(
            count=left.count + right.count,
            symbol=None,
            left=left,
            right=right,
            min_symbol_rank=min(left.min_symbol_rank, right.min_symbol_rank),
            node_id=node_id_counter,
        )
        heapq.heappush(heap, merged)
        node_id_counter += 1

    return heap[0] if heap else None


def _extract_code_lengths(root: HuffmanNode) -> Dict[int, int]:
    """Extract code lengths from Huffman tree via DFS."""
    lengths: Dict[int, int] = {}

    def dfs(node: HuffmanNode, depth: int) -> None:
        if node.is_leaf():
            lengths[node.symbol] = depth
        else:
            if node.left:
                dfs(node.left, depth + 1)
            if node.right:
                dfs(node.right, depth + 1)

    dfs(root, 0)

    if len(lengths) == 1:
        for sym in lengths:
            lengths[sym] = 1

    return lengths


# =============================================================================
# PUBLIC API
# =============================================================================

@dataclass
class HuffmanResult:
    """Result of Huffman encoding computation."""

    code_lengths: Dict[int, int]
    total_bits: int
    counts: Dict[int, int]
    policy_id: str = TIE_BREAK_POLICY_ID

    def to_dict(self) -> dict:
        return {
            "code_lengths": {str(k): v for k, v in self.code_lengths.items()},
            "total_bits": self.total_bits,
            "counts": {str(k): v for k, v in self.counts.items()},
            "policy_id": self.policy_id,
        }


def canonical_huffman_code_lengths(counts: Dict[int, int]) -> Dict[int, int]:
    """Compute Huffman code lengths with deterministic tie-break.

    Args:
        counts: WDL counts as {-1: loss_count, 0: draw_count, +1: win_count}

    Returns:
        Code lengths as {symbol: length_in_bits}

    Example:
        >>> counts = {-1: 100, 0: 50, +1: 200}
        >>> lengths = canonical_huffman_code_lengths(counts)
        >>> lengths  # Most frequent (W) gets 1 bit, others get 2 bits
        {-1: 2, 0: 2, 1: 1}
    """
    root = _build_huffman_tree(counts)

    if root is None:
        return {}

    return _extract_code_lengths(root)


def compute_huffman_bits(counts: Dict[int, int]) -> int:
    """Compute total bits for Huffman-encoded sequence.

    Args:
        counts: WDL counts

    Returns:
        Total bits = sum(count[s] * code_length[s])
    """
    lengths = canonical_huffman_code_lengths(counts)

    total = 0
    for symbol, count in counts.items():
        if symbol in lengths:
            total += count * lengths[symbol]

    return total


def compute_huffman_result(counts: Dict[int, int]) -> HuffmanResult:
    """Compute full Huffman encoding result with audit info."""
    lengths = canonical_huffman_code_lengths(counts)
    total_bits = sum(counts.get(s, 0) * l for s, l in lengths.items())

    return HuffmanResult(
        code_lengths=lengths,
        total_bits=total_bits,
        counts=counts,
        policy_id=TIE_BREAK_POLICY_ID,
    )


def validate_huffman_determinism(counts: Dict[int, int], expected_lengths: Dict[int, int]) -> bool:
    """Validate that Huffman produces expected code lengths."""
    computed = canonical_huffman_code_lengths(counts)
    return computed == expected_lengths
