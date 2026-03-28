"""Decode-only flat decision tree inference.

Loads a model_flat.json file and provides predict(features) → label.
This is the read-only counterpart to the proprietary tree trainer.
"""

from __future__ import annotations

import json
from typing import List, Optional


class FlatTree:
    """Flat decision tree for inference only.

    Node array format (from model_flat.json):
        nodes[i].feature       — split feature index (< 0 for leaf)
        nodes[i].threshold     — split threshold
        nodes[i].children_left — left child index
        nodes[i].children_right— right child index
        nodes[i].value         — leaf prediction label
    """

    def __init__(self, model_json: dict):
        self.nodes = model_json["nodes"]
        self.classes = model_json.get("classes", [])
        self.n_classes = model_json.get("n_classes", len(self.classes))
        self.n_features = model_json.get("n_features", 0)

    @classmethod
    def from_file(cls, path: str) -> 'FlatTree':
        """Load from a model_flat.json file."""
        with open(path) as f:
            return cls(json.load(f))

    def predict(self, features: List[int]) -> int:
        """Predict label for a feature vector.

        Args:
            features: List of integer feature values, length >= n_features

        Returns:
            Predicted label (integer)
        """
        node_idx = 0
        while True:
            node = self.nodes[node_idx]
            if node["feature"] < 0:
                return node["value"]
            if features[node["feature"]] <= node["threshold"]:
                node_idx = node["children_left"]
            else:
                node_idx = node["children_right"]

    @property
    def num_leaves(self) -> int:
        """Count leaf nodes."""
        return sum(1 for n in self.nodes if n["feature"] < 0)

    @property
    def num_nodes(self) -> int:
        """Total nodes in tree."""
        return len(self.nodes)
