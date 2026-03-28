/// v18/v20 binary codec reader.
///
/// Wire format (from v18_codec.py — authoritative):
///   Header: 112 bytes
///   LeafIndexEntry: 20 bytes each
///   LeafBlobHeader: 29 bytes (v18.0)
use std::collections::HashMap;

use crate::residual::{decode_block, decode_empty_run, BlockData, RECORD_EMPTY_RUN, RECORD_NON_EMPTY_BLOCK};

pub const MAGIC: &[u8; 4] = b"CEGR";
pub const HEADER_SIZE: usize = 112;
pub const LEAF_INDEX_ENTRY_SIZE: usize = 20;
pub const LEAF_BLOB_HEADER_SIZE: usize = 29;

pub const LABEL_CODEC_FIXED_2BIT: u8 = 0;
pub const LABEL_CODEC_CONDITIONAL_1BIT: u8 = 2;

#[derive(Debug)]
pub struct V18Header {
    pub version_major: u16,
    pub version_minor: u16,
    pub block_size: u32,
    pub num_leaves: u32,
    pub partition_mode: u8,
    pub label_codec: u8,
    pub n_classes: u8,
    pub leaf_index_offset: u64,
    pub total_positions: u64,
    pub total_mismatches: u64,
}

#[derive(Debug)]
pub struct LeafBlobHeader {
    pub leaf_id: u32,
    pub base_pred_label: i8,
    pub n_leaf: u32,
    pub num_blocks: u32,
    pub k_leaf: u32,
    pub record_stream_len: u64,
    pub record_stream_crc32: u32,
}

/// Lookup cache: leaf_id → block_id → idx_in_block → label
pub type LookupCache = HashMap<u32, HashMap<u32, HashMap<u32, i8>>>;

fn read_u16_le(data: &[u8], off: usize) -> u16 {
    u16::from_le_bytes([data[off], data[off + 1]])
}

fn read_u32_le(data: &[u8], off: usize) -> u32 {
    u32::from_le_bytes([data[off], data[off + 1], data[off + 2], data[off + 3]])
}

fn read_u64_le(data: &[u8], off: usize) -> u64 {
    u64::from_le_bytes([
        data[off], data[off + 1], data[off + 2], data[off + 3],
        data[off + 4], data[off + 5], data[off + 6], data[off + 7],
    ])
}

/// Parse the 112-byte header.
pub fn parse_header(data: &[u8]) -> Result<V18Header, String> {
    if data.len() < HEADER_SIZE {
        return Err(format!("Header too short: {} < {}", data.len(), HEADER_SIZE));
    }
    if &data[0..4] != MAGIC {
        return Err(format!("Invalid magic: {:?}", &data[0..4]));
    }
    let version_major = read_u16_le(data, 4);
    Ok(V18Header {
        version_major,
        version_minor: read_u16_le(data, 6),
        block_size: read_u32_le(data, 12),
        num_leaves: read_u32_le(data, 16),
        partition_mode: data[20],
        label_codec: data[21],
        n_classes: if version_major >= 30 { data[22] } else { 0 },
        leaf_index_offset: read_u64_le(data, 88),
        total_positions: read_u64_le(data, 96),
        total_mismatches: read_u64_le(data, 104),
    })
}

/// Parse leaf index table entries.
pub fn parse_leaf_index(data: &[u8], num_leaves: u32, offset: usize) -> Vec<(u32, u64, u64)> {
    let mut entries = Vec::with_capacity(num_leaves as usize);
    for i in 0..num_leaves as usize {
        let base = offset + i * LEAF_INDEX_ENTRY_SIZE;
        let leaf_id = read_u32_le(data, base);
        let blob_offset = read_u64_le(data, base + 4);
        let blob_len = read_u64_le(data, base + 12);
        entries.push((leaf_id, blob_offset, blob_len));
    }
    entries
}

/// Parse a leaf blob header (29 bytes).
pub fn parse_leaf_blob_header(data: &[u8], offset: usize) -> (LeafBlobHeader, usize) {
    let leaf_id = read_u32_le(data, offset);
    let pred_code = data[offset + 4];
    let n_leaf = read_u32_le(data, offset + 5);
    let num_blocks = read_u32_le(data, offset + 9);
    let k_leaf = read_u32_le(data, offset + 13);
    let record_stream_len = read_u64_le(data, offset + 17);
    let record_stream_crc32 = read_u32_le(data, offset + 25);

    (
        LeafBlobHeader {
            leaf_id,
            base_pred_label: pred_code as i8 - 1,
            n_leaf,
            num_blocks,
            k_leaf,
            record_stream_len,
            record_stream_crc32,
        },
        offset + LEAF_BLOB_HEADER_SIZE,
    )
}

/// Decode a record stream into block data.
pub fn decode_record_stream(
    data: &[u8],
    num_blocks: u32,
    n_leaf: u32,
    block_size: u32,
    leaf_prediction: Option<i8>,
    n_classes: u8,
) -> Vec<(u32, Option<BlockData>)> {
    let mut offset = 0usize;
    let mut block_id = 0u32;
    let mut results = Vec::new();

    while block_id < num_blocks && offset < data.len() {
        let rec_type = data[offset] & 0x3;

        if rec_type == RECORD_EMPTY_RUN {
            let (run_len, new_off) = decode_empty_run(data, offset);
            offset = new_off;
            for _ in 0..run_len {
                results.push((block_id, None));
                block_id += 1;
            }
        } else if rec_type == RECORD_NON_EMPTY_BLOCK {
            let n_b = if block_id < num_blocks - 1 {
                block_size
            } else {
                n_leaf - block_id * block_size
            };
            let (block_data, _, new_off) = decode_block(data, n_b, offset, leaf_prediction, n_classes);
            offset = new_off;
            results.push((block_id, Some(block_data)));
            block_id += 1;
        } else {
            panic!("Unknown record type: {}", rec_type);
        }
    }
    results
}

/// Parse an entire v18 residual file and build a lookup cache.
pub fn parse_and_cache(data: &[u8]) -> Result<(V18Header, LookupCache), String> {
    let header = parse_header(data)?;
    let leaf_index = parse_leaf_index(data, header.num_leaves, header.leaf_index_offset as usize);

    let mut cache: LookupCache = HashMap::new();

    for (leaf_id, blob_offset, _blob_len) in &leaf_index {
        let (blob_header, data_start) = parse_leaf_blob_header(data, *blob_offset as usize);
        let rs_end = data_start + blob_header.record_stream_len as usize;
        let record_stream = &data[data_start..rs_end];

        let leaf_pred = if header.label_codec == LABEL_CODEC_CONDITIONAL_1BIT {
            Some(blob_header.base_pred_label)
        } else {
            None
        };

        let blocks = decode_record_stream(
            record_stream,
            blob_header.num_blocks,
            blob_header.n_leaf,
            header.block_size,
            leaf_pred,
            header.n_classes,
        );

        let mut leaf_cache: HashMap<u32, HashMap<u32, i8>> = HashMap::new();
        for (bid, block_data) in blocks {
            if let Some(bd) = block_data {
                if !bd.indices.is_empty() {
                    let mut block_cache = HashMap::new();
                    for (i, &idx) in bd.indices.iter().enumerate() {
                        block_cache.insert(idx, bd.labels[i]);
                    }
                    leaf_cache.insert(bid, block_cache);
                }
            }
        }
        cache.insert(*leaf_id, leaf_cache);
    }

    Ok((header, cache))
}
