/**
 * v18/v20 binary codec reader — decode-only.
 *
 * Reads .v18 residual files: Header → LeafIndex → LeafBlobs → RecordStreams.
 * Port of proofcodec_verify/codec/v18_codec.py.
 *
 * Wire format (authoritative — from v18_codec.py, not CODEC_SPEC.md):
 *   Header: 112 bytes
 *   LeafIndexEntry: 20 bytes each
 *   LeafBlobHeader: 29 bytes (v18.0) or 41 bytes (v18.1)
 */

import { decodeBlock, decodeEmptyRun, RecordType } from './residual.js';
import { decodeUvarint } from './leb128.js';

export const MAGIC = new Uint8Array([0x43, 0x45, 0x47, 0x52]); // "CEGR"
export const DEFAULT_BLOCK_SIZE = 4096;

export const LabelCodec = { FIXED_2BIT: 0, HUFFMAN: 1, CONDITIONAL_1BIT: 2 };
export const PartitionMode = { LEAF_BLOCK: 0, LEAF_BLOCK_PRED: 1 };

/**
 * Parse the 112-byte V18 header.
 * @param {DataView} dv
 * @returns {Object}
 */
export function parseHeader(dv) {
  const magic = new Uint8Array(dv.buffer, dv.byteOffset, 4);
  if (magic[0] !== 0x43 || magic[1] !== 0x45 || magic[2] !== 0x47 || magic[3] !== 0x52) {
    throw new Error(`Invalid magic: ${String.fromCharCode(...magic)}`);
  }
  const versionMajor = dv.getUint16(4, true);
  return {
    versionMajor,
    versionMinor: dv.getUint16(6, true),
    flags: dv.getUint32(8, true),
    blockSize: dv.getUint32(12, true),
    numLeaves: dv.getUint32(16, true),
    partitionMode: dv.getUint8(20),
    labelCodec: dv.getUint8(21),
    nClasses: versionMajor >= 30 ? dv.getUint8(22) : 0,
    modelHash: new Uint8Array(dv.buffer, dv.byteOffset + 24, 32),
    syzygyHash: new Uint8Array(dv.buffer, dv.byteOffset + 56, 32),
    leafIndexOffset: Number(dv.getBigUint64(88, true)),
    totalPositions: Number(dv.getBigUint64(96, true)),
    totalMismatches: Number(dv.getBigUint64(104, true)),
  };
}

/**
 * Parse leaf index table.
 * @param {DataView} dv
 * @param {number} numLeaves
 * @param {number} offset
 * @returns {Array<{leafId: number, blobOffset: number, blobLen: number}>}
 */
export function parseLeafIndex(dv, numLeaves, offset) {
  const entries = [];
  for (let i = 0; i < numLeaves; i++) {
    const base = offset + i * 20;
    entries.push({
      leafId: dv.getUint32(base, true),
      blobOffset: Number(dv.getBigUint64(base + 4, true)),
      blobLen: Number(dv.getBigUint64(base + 12, true)),
    });
  }
  return entries;
}

/**
 * Parse a leaf blob header (29 bytes for v18.0).
 * @param {DataView} dv
 * @param {number} offset
 * @returns {[Object, number]} [header, newOffset]
 */
export function parseLeafBlobHeader(dv, offset) {
  const leafId = dv.getUint32(offset, true);
  const predCode = dv.getUint8(offset + 4);
  const nLeaf = dv.getUint32(offset + 5, true);
  const numBlocks = dv.getUint32(offset + 9, true);
  const kLeaf = dv.getUint32(offset + 13, true);
  const recordStreamLen = Number(dv.getBigUint64(offset + 17, true));
  const recordStreamCrc32 = dv.getUint32(offset + 25, true);
  return [{
    leafId,
    basePredLabel: predCode - 1,
    nLeaf,
    numBlocks,
    kLeaf,
    recordStreamLen,
    recordStreamCrc32,
  }, offset + 29];
}

/**
 * Decode a record stream into block data.
 * @param {Uint8Array} data
 * @param {number} numBlocks
 * @param {number} nLeaf
 * @param {number} blockSize
 * @param {number|null} leafPrediction
 * @param {number} nClasses - number of classes (0 = legacy 3-class WDL)
 * @returns {Array<[number, Object|null]>} [(blockId, blockData|null), ...]
 */
export function decodeRecordStream(data, numBlocks, nLeaf, blockSize, leafPrediction = null, nClasses = 0) {
  let offset = 0;
  let blockId = 0;
  const results = [];

  while (blockId < numBlocks && offset < data.length) {
    const recType = data[offset] & 0x3;

    if (recType === RecordType.EMPTY_RUN) {
      let runLen;
      [runLen, offset] = decodeEmptyRun(data, offset);
      for (let i = 0; i < runLen; i++) {
        results.push([blockId++, null]);
      }
    } else if (recType === RecordType.NON_EMPTY_BLOCK) {
      const nB = blockId < numBlocks - 1 ? blockSize : nLeaf - blockId * blockSize;
      let blockData, encoding;
      [blockData, encoding, offset] = decodeBlock(data, nB, offset, leafPrediction, nClasses);
      results.push([blockId++, blockData]);
    } else {
      throw new Error(`Unknown record type: ${recType}`);
    }
  }
  return results;
}

/**
 * Parse an entire v18 residual file.
 * @param {ArrayBuffer} buffer
 * @returns {Object} { header, leafIndex, leafBlobs }
 */
export function parseResidualFile(buffer) {
  const data = new Uint8Array(buffer);
  const dv = new DataView(buffer);

  const header = parseHeader(dv);
  const leafIndex = parseLeafIndex(dv, header.numLeaves, header.leafIndexOffset);

  const leafBlobs = new Map();
  for (const entry of leafIndex) {
    const [blobHeader, dataStart] = parseLeafBlobHeader(dv, entry.blobOffset);
    const recordStream = data.slice(dataStart, dataStart + blobHeader.recordStreamLen);
    leafBlobs.set(entry.leafId, { header: blobHeader, recordStream });
  }

  return { header, leafIndex, leafBlobs };
}

/**
 * Build a lookup cache from a parsed residual file.
 * @param {Object} file — from parseResidualFile
 * @returns {Map<number, Map<number, Map<number, number>>>} leafId → blockId → idxInBlock → label
 */
export function buildLookupCache(file) {
  const cache = new Map();

  for (const [leafId, blob] of file.leafBlobs) {
    const leafPred = file.header.labelCodec === LabelCodec.CONDITIONAL_1BIT
      ? blob.header.basePredLabel : null;

    const blocks = decodeRecordStream(
      blob.recordStream,
      blob.header.numBlocks,
      blob.header.nLeaf,
      file.header.blockSize,
      leafPred,
      file.header.nClasses,
    );

    const leafCache = new Map();
    for (const [bid, blockData] of blocks) {
      if (blockData && blockData.indices.length > 0) {
        const blockCache = new Map();
        for (let i = 0; i < blockData.indices.length; i++) {
          blockCache.set(blockData.indices[i], blockData.labels[i]);
        }
        leafCache.set(bid, blockCache);
      }
    }
    cache.set(leafId, leafCache);
  }
  return cache;
}
