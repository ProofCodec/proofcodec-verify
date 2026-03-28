import { describe, it, expect } from 'vitest';
import { parseHeader, LabelCodec, PartitionMode, MAGIC } from '../src/codec.js';

describe('parseHeader', () => {
  it('parses valid 112-byte header', () => {
    const buf = new ArrayBuffer(112);
    const dv = new DataView(buf);
    const u8 = new Uint8Array(buf);

    // Magic "CEGR"
    u8[0] = 0x43; u8[1] = 0x45; u8[2] = 0x47; u8[3] = 0x52;
    dv.setUint16(4, 18, true);  // version_major
    dv.setUint16(6, 2, true);   // version_minor
    dv.setUint32(8, 0, true);   // flags
    dv.setUint32(12, 4096, true); // block_size
    dv.setUint32(16, 5, true);  // num_leaves
    dv.setUint8(20, PartitionMode.LEAF_BLOCK); // partition_mode
    dv.setUint8(21, LabelCodec.CONDITIONAL_1BIT); // label_codec
    // 22-23 reserved
    // 24-55: model_hash (zeros)
    // 56-87: syzygy_hash (zeros)
    dv.setBigUint64(88, 112n, true); // leaf_index_offset
    dv.setBigUint64(96, 1000000n, true); // total_positions
    dv.setBigUint64(104, 500n, true); // total_mismatches

    const header = parseHeader(dv);
    expect(header.versionMajor).toBe(18);
    expect(header.versionMinor).toBe(2);
    expect(header.blockSize).toBe(4096);
    expect(header.numLeaves).toBe(5);
    expect(header.labelCodec).toBe(LabelCodec.CONDITIONAL_1BIT);
    expect(header.totalPositions).toBe(1000000);
    expect(header.totalMismatches).toBe(500);
  });

  it('rejects invalid magic', () => {
    const buf = new ArrayBuffer(112);
    const u8 = new Uint8Array(buf);
    u8[0] = 0x42; u8[1] = 0x41; u8[2] = 0x41; u8[3] = 0x44; // "BAAD"

    expect(() => parseHeader(new DataView(buf))).toThrow('Invalid magic');
  });
});
