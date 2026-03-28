/**
 * Flat decision tree inference — decode-only.
 *
 * Loads a model_flat.json and provides predict(features) → label.
 */

export class FlatTree {
  /**
   * @param {Object} modelJson — model_flat.json contents
   */
  constructor(modelJson) {
    this.nodes = modelJson.nodes;
    this.classes = modelJson.classes || [];
    this.nClasses = modelJson.n_classes || this.classes.length;
    this.nFeatures = modelJson.n_features || 0;
  }

  /**
   * Predict label for a feature vector.
   * @param {number[]} features
   * @returns {number} predicted label
   */
  predict(features) {
    let idx = 0;
    while (true) {
      const node = this.nodes[idx];
      if (node.feature < 0) return node.value;
      if (features[node.feature] <= node.threshold) {
        idx = node.children_left;
      } else {
        idx = node.children_right;
      }
    }
  }

  get numLeaves() {
    return this.nodes.filter(n => n.feature < 0).length;
  }

  get numNodes() {
    return this.nodes.length;
  }
}
