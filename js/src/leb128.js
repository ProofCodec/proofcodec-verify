/**
 * LEB128 unsigned varint decoding.
 */

/**
 * Decode an unsigned LEB128 varint from a Uint8Array.
 * @param {Uint8Array} data
 * @param {number} offset
 * @returns {[number, number]} [value, newOffset]
 */
export function decodeUvarint(data, offset = 0) {
  let value = 0;
  let shift = 0;
  while (offset < data.length) {
    const byte = data[offset++];
    value |= (byte & 0x7f) << shift;
    if ((byte & 0x80) === 0) break;
    shift += 7;
  }
  return [value, offset];
}
