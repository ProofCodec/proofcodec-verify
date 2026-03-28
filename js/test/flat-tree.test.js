import { describe, it, expect } from 'vitest';
import { FlatTree } from '../src/flat-tree.js';

describe('FlatTree', () => {
  it('simple 3-node tree', () => {
    const model = {
      classes: [0, 1],
      n_classes: 2,
      n_features: 1,
      nodes: [
        { feature: 0, threshold: 5.0, children_left: 1, children_right: 2, value: 0 },
        { feature: -2, threshold: 0.0, children_left: -1, children_right: -1, value: 0 },
        { feature: -2, threshold: 0.0, children_left: -1, children_right: -1, value: 1 },
      ],
    };
    const tree = new FlatTree(model);
    expect(tree.predict([3])).toBe(0);  // 3 <= 5 → left
    expect(tree.predict([5])).toBe(0);  // 5 <= 5 → left
    expect(tree.predict([6])).toBe(1);  // 6 > 5 → right
    expect(tree.numLeaves).toBe(2);
    expect(tree.numNodes).toBe(3);
  });

  it('multi-feature tree', () => {
    const model = {
      classes: [0, 1],
      n_classes: 2,
      n_features: 2,
      nodes: [
        { feature: 1, threshold: 3.0, children_left: 1, children_right: 2, value: 0 },
        { feature: -2, threshold: 0.0, children_left: -1, children_right: -1, value: 1 },
        { feature: -2, threshold: 0.0, children_left: -1, children_right: -1, value: 0 },
      ],
    };
    const tree = new FlatTree(model);
    expect(tree.predict([99, 2])).toBe(1);  // feature[1]=2 <= 3
    expect(tree.predict([99, 4])).toBe(0);  // feature[1]=4 > 3
  });
});
