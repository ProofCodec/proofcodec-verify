/// v18/v20/v30 residual block decoding.
///
/// Three index encodings: DELTA_GAPS, ENUM_RANK, BITMAP.
/// Label codecs: FIXED_2BIT (legacy v18), CONDITIONAL_1BIT (v20), multi-class (v30).
use crate::combinadic::{decode_bigint_be, unrank_subset};
use crate::leb128::decode_uvarint;

pub const INDEX_DELTA_GAPS: u8 = 0;
pub const INDEX_ENUM_RANK: u8 = 1;
pub const INDEX_BITMAP: u8 = 2;

pub const RECORD_EMPTY_RUN: u8 = 0;
pub const RECORD_NON_EMPTY_BLOCK: u8 = 1;

/// Extract `width` bits starting at absolute bit position `bit_pos` from data,
/// handling cross-byte boundaries.
pub fn extract_bits(data: &[u8], bit_pos: u32, width: u32) -> u32 {
    let byte_idx = (bit_pos / 8) as usize;
    let bit_idx = bit_pos % 8;
    let bits_this_byte = (width).min(8 - bit_idx);
    let mut value = ((data[byte_idx] >> bit_idx) & ((1u8 << bits_this_byte) - 1)) as u32;
    if bits_this_byte < width {
        let bits_next = width - bits_this_byte;
        value |= ((data[byte_idx + 1] & ((1u8 << bits_next) - 1)) as u32) << bits_this_byte;
    }
    value
}

fn ceil_log2(n: u32) -> u32 {
    if n <= 1 { return 0; }
    32 - (n - 1).leading_zeros()
}

#[derive(Debug)]
pub struct BlockData {
    pub indices: Vec<u32>,
    pub labels: Vec<i8>,
}

/// Decode k indices from delta gaps.
pub fn decode_delta_gaps(data: &[u8], k: u32, mut offset: usize) -> (Vec<u32>, usize) {
    if k == 0 {
        return (vec![], offset);
    }
    let mut indices = Vec::with_capacity(k as usize);
    let (first, new_off) = decode_uvarint(data, offset);
    offset = new_off;
    indices.push(first as u32);

    for _ in 1..k {
        let (gap, new_off) = decode_uvarint(data, offset);
        offset = new_off;
        let prev = *indices.last().unwrap();
        indices.push(prev + 1 + gap as u32);
    }
    (indices, offset)
}

/// Decode k indices from enum rank (combinadic).
pub fn decode_enum_rank(data: &[u8], n: u32, k: u32, mut offset: usize) -> (Vec<u32>, usize) {
    if k == 0 {
        return (vec![], offset);
    }
    let (rank_len, new_off) = decode_uvarint(data, offset);
    offset = new_off;

    if rank_len == 0 {
        return ((0..k).collect(), offset);
    }

    let rank_bytes = &data[offset..offset + rank_len as usize];
    offset += rank_len as usize;

    let rank = decode_bigint_be(rank_bytes);
    let indices_u64 = unrank_subset(rank, n as u64, k as u64);
    let indices: Vec<u32> = indices_u64.into_iter().map(|x| x as u32).collect();
    (indices, offset)
}

/// Decode indices from bitmap.
pub fn decode_bitmap(data: &[u8], n: u32, offset: usize) -> (Vec<u32>, usize) {
    let num_bytes = ((n + 7) / 8) as usize;
    let mut indices = Vec::new();
    for byte_idx in 0..num_bytes {
        let byte_val = data[offset + byte_idx];
        for bit_idx in 0..8u32 {
            if byte_val & (1 << bit_idx) != 0 {
                let idx = byte_idx as u32 * 8 + bit_idx;
                if idx < n {
                    indices.push(idx);
                }
            }
        }
    }
    (indices, offset + num_bytes)
}

/// Decode k labels from packed format.
///
/// - leaf_prediction: Some(pred) for conditional decoding, None for fixed-width.
/// - n_classes: 0 = legacy 3-class WDL, >3 = multi-class (labels 0..n_classes-1).
pub fn decode_labels(
    data: &[u8],
    k: u32,
    offset: usize,
    leaf_prediction: Option<i8>,
    n_classes: u8,
) -> (Vec<i8>, usize) {
    if k == 0 {
        return (vec![], offset);
    }

    let is_legacy = n_classes == 0 || n_classes == 3;

    if let Some(pred) = leaf_prediction {
        // Conditional: exclude base prediction, variable bit width
        let all_classes: Vec<i8> = if is_legacy {
            vec![-1, 0, 1]
        } else {
            (0..n_classes as i8).collect()
        };
        let remaining: Vec<i8> = all_classes.into_iter().filter(|&c| c != pred).collect();
        let bits_per_label = ceil_log2(remaining.len() as u32).max(1);
        let total_bits = k * bits_per_label;
        let num_bytes = ((total_bits + 7) / 8) as usize;

        let mut labels = Vec::with_capacity(k as usize);
        let base_bit = (offset * 8) as u32;
        for i in 0..k {
            let code = extract_bits(data, base_bit + i * bits_per_label, bits_per_label);
            labels.push(remaining[code as usize]);
        }
        (labels, offset + num_bytes)
    } else {
        // Fixed-width
        let bits_per_label = if is_legacy {
            2u32
        } else {
            ceil_log2(n_classes as u32).max(1)
        };
        let total_bits = k * bits_per_label;
        let num_bytes = ((total_bits + 7) / 8) as usize;

        let mut labels = Vec::with_capacity(k as usize);
        let base_bit = (offset * 8) as u32;
        for i in 0..k {
            let code = extract_bits(data, base_bit + i * bits_per_label, bits_per_label);
            labels.push(if is_legacy { code as i8 - 1 } else { code as i8 });
        }
        (labels, offset + num_bytes)
    }
}

/// Decode a NON_EMPTY_BLOCK record.
pub fn decode_block(
    data: &[u8],
    n_b: u32,
    mut offset: usize,
    leaf_prediction: Option<i8>,
    n_classes: u8,
) -> (BlockData, u8, usize) {
    let rec_hdr = data[offset];
    offset += 1;

    let encoding = (rec_hdr >> 2) & 0x3;
    let (k, new_off) = decode_uvarint(data, offset);
    offset = new_off;
    let k = k as u32;

    let indices;
    match encoding {
        INDEX_DELTA_GAPS => {
            let (idx, off) = decode_delta_gaps(data, k, offset);
            indices = idx;
            offset = off;
        }
        INDEX_ENUM_RANK => {
            let (idx, off) = decode_enum_rank(data, n_b, k, offset);
            indices = idx;
            offset = off;
        }
        INDEX_BITMAP => {
            let (idx, off) = decode_bitmap(data, n_b, offset);
            indices = idx;
            offset = off;
        }
        _ => panic!("Unknown index encoding: {}", encoding),
    }

    let (labels, off) = decode_labels(data, k, offset, leaf_prediction, n_classes);
    offset = off;

    (BlockData { indices, labels }, encoding, offset)
}

/// Decode EMPTY_RUN record.
pub fn decode_empty_run(data: &[u8], offset: usize) -> (u32, usize) {
    // skip record header byte
    let (run_len, off) = decode_uvarint(data, offset + 1);
    (run_len as u32, off)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_decode_delta_gaps() {
        let data = [3u8, 3, 2];
        let (indices, _) = decode_delta_gaps(&data, 3, 0);
        assert_eq!(indices, vec![3, 7, 10]);
    }

    #[test]
    fn test_decode_bitmap() {
        let data = [0b10001001u8, 0x00];
        let (indices, offset) = decode_bitmap(&data, 16, 0);
        assert_eq!(indices, vec![0, 3, 7]);
        assert_eq!(offset, 2);
    }

    // --- Legacy 3-class (n_classes=0) ---

    #[test]
    fn test_decode_labels_2bit_legacy() {
        // [W, D, L] = codes [2, 1, 0] → byte 0x06
        let data = [0x06u8];
        let (labels, _) = decode_labels(&data, 3, 0, None, 0);
        assert_eq!(labels, vec![1, 0, -1]);
    }

    #[test]
    fn test_decode_labels_1bit_conditional_legacy() {
        // leaf_pred=1(W), remaining [-1, 0]. Pack [L, D]=[0,1] → 0x02
        let data = [0x02u8];
        let (labels, _) = decode_labels(&data, 2, 0, Some(1), 0);
        assert_eq!(labels, vec![-1, 0]);
    }

    // --- Cross-byte boundary (2-bit, 5 labels = 10 bits) ---

    #[test]
    fn test_decode_labels_2bit_cross_byte() {
        // 5 labels: [W=1, D=0, L=-1, W=1, D=0] = codes [2, 1, 0, 2, 1]
        // bits (LE): 10 01 00 10 01 (10 bits)
        // byte 0 bits[0..7]: 0,1, 1,0, 0,0, 0,1 = 0b10_00_01_10 = 0x86
        // byte 1 bits[8..9]: 1,0 = 0x01
        let data = [0x86u8, 0x01];
        let (labels, off) = decode_labels(&data, 5, 0, None, 0);
        assert_eq!(labels, vec![1, 0, -1, 1, 0]);
        assert_eq!(off, 2);
    }

    // --- extract_bits helper ---

    #[test]
    fn test_extract_bits_within_byte() {
        let data = [0b11010110u8];
        assert_eq!(extract_bits(&data, 0, 3), 0b110); // bits [0,1,2]
        assert_eq!(extract_bits(&data, 3, 2), 0b10);  // bits [3,4]
    }

    #[test]
    fn test_extract_bits_cross_byte() {
        let data = [0b11000000u8, 0b00000011];
        // bits [6,7] from byte 0 = 11, bit [0] from byte 1 = 1 → 111 = 7
        assert_eq!(extract_bits(&data, 6, 3), 0b111);
    }

    // --- Multi-class (n_classes=8, 3-bit fixed) ---

    #[test]
    fn test_decode_labels_3bit_multiclass() {
        // 4 labels: [0, 3, 5, 7] at 3 bits each = 12 bits
        // bits: 000 011 101 111 = 0b111_101_011_000 (LE)
        // byte 0: bits [0..7] = 101_011_000 → wait, let me pack correctly
        // label 0 = 000, label 3 = 011, label 5 = 101, label 7 = 111
        // bit stream: 000 011 101 111
        // byte 0 (bits 0-7): 0|11_000 from labels 0,1 + bits 0-1 of label 2 = 011_000_10 wait
        // Let me think in LE bit order:
        // bit 0-2: label[0]=0 → 000
        // bit 3-5: label[1]=3 → 011
        // bit 6-8: label[2]=5 → 101
        // bit 9-11: label[3]=7 → 111
        // byte 0 = bits[0..7]: bit6=1,bit5=0,bit4=1,bit3=0,bit2=0,bit1=0,bit0=0 → wait
        // Actually in LE: byte0[0]=bit0, byte0[1]=bit1, ...
        // byte 0: bits 0-7 → 0,0,0, 1,1,0, 1,0 = 0b01_011_000 = 0x58
        // byte 1: bits 8-11 → 1, 1,1,1 = 0b00001111 but only 4 bits matter
        // bit 8 = 1 (bit 2 of label 2), bit 9-11 = 111 (label 3)
        // byte 1: bits 8-11 → 1, 1,1,1 = 0x0F (lower 4 bits)
        let data = [0x58u8, 0x0F];
        let (labels, off) = decode_labels(&data, 4, 0, None, 8);
        assert_eq!(labels, vec![0, 3, 5, 7]);
        assert_eq!(off, 2); // ceil(12/8) = 2
    }

    #[test]
    fn test_decode_labels_conditional_8class() {
        // n_classes=8, leaf_pred=0, remaining=[1,2,3,4,5,6,7]
        // ceil(log2(7)) = 3 bits per label
        // 2 labels: [3, 5] → indices into remaining: [2, 4]
        // codes: 010 100 = 6 bits
        // byte 0: bits 0-5 → 0,1,0, 1,0,0 = 0b00_100_010 = 0x22
        let data = [0x22u8];
        let (labels, off) = decode_labels(&data, 2, 0, Some(0), 8);
        assert_eq!(labels, vec![3, 5]);
        assert_eq!(off, 1); // ceil(6/8) = 1
    }
}
