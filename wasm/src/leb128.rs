/// Decode an unsigned LEB128 varint from a byte slice.
/// Returns (value, bytes_consumed).
pub fn decode_uvarint(data: &[u8], offset: usize) -> (u64, usize) {
    let mut value: u64 = 0;
    let mut shift = 0u32;
    let mut pos = offset;
    while pos < data.len() {
        let byte = data[pos];
        pos += 1;
        value |= ((byte & 0x7f) as u64) << shift;
        if byte & 0x80 == 0 {
            break;
        }
        shift += 7;
    }
    (value, pos)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_single_byte() {
        let (val, off) = decode_uvarint(&[42], 0);
        assert_eq!(val, 42);
        assert_eq!(off, 1);
    }

    #[test]
    fn test_multi_byte() {
        // 300 = 0b100101100 → LEB128: [0xAC, 0x02]
        let (val, off) = decode_uvarint(&[0xAC, 0x02], 0);
        assert_eq!(val, 300);
        assert_eq!(off, 2);
    }

    #[test]
    fn test_with_offset() {
        let (val, off) = decode_uvarint(&[0xFF, 42], 1);
        assert_eq!(val, 42);
        assert_eq!(off, 2);
    }
}
