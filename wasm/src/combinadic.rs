/// Binomial coefficient C(n, k) using u128 for large values.
pub fn binom(n: u64, k: u64) -> u128 {
    if k > n {
        return 0;
    }
    if k == 0 || k == n {
        return 1;
    }
    let k = k.min(n - k) as u128;
    let n = n as u128;
    let mut result: u128 = 1;
    for i in 0..k {
        result = result * (n - i) / (i + 1);
    }
    result
}

/// Decode a combinadic rank to a sorted k-subset of [0, n).
pub fn unrank_subset(mut rank: u128, n: u64, k: u64) -> Vec<u64> {
    if k == 0 {
        return vec![];
    }
    let mut indices = vec![0u64; k as usize];
    let mut upper = n - 1;

    for j in (1..=k).rev() {
        let i = find_largest_binom_le(rank, j, if j > 0 { j - 1 } else { 0 }, upper);
        indices[(j - 1) as usize] = i;
        rank -= binom(i, j);
        upper = if i > 0 { i - 1 } else { 0 };
    }
    indices
}

fn find_largest_binom_le(target: u128, k: u64, lo: u64, hi: u64) -> u64 {
    if lo > hi {
        return lo.wrapping_sub(1);
    }
    let mut result = lo.wrapping_sub(1);
    let mut lo = lo;
    let mut hi = hi;
    while lo <= hi {
        let mid = lo + (hi - lo) / 2;
        if binom(mid, k) <= target {
            result = mid;
            if mid == u64::MAX {
                break;
            }
            lo = mid + 1;
        } else {
            if mid == 0 {
                break;
            }
            hi = mid - 1;
        }
    }
    result
}

/// Decode big-endian bytes to u128.
pub fn decode_bigint_be(data: &[u8]) -> u128 {
    let mut value: u128 = 0;
    for &byte in data {
        value = (value << 8) | byte as u128;
    }
    value
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_binom() {
        assert_eq!(binom(10, 3), 120);
        assert_eq!(binom(5, 0), 1);
        assert_eq!(binom(5, 5), 1);
        assert_eq!(binom(3, 4), 0);
    }

    #[test]
    fn test_unrank_roundtrip() {
        // rank of [2,5,7] in C(10,3)
        let rank = binom(2, 1) + binom(5, 2) + binom(7, 3);
        let indices = unrank_subset(rank, 10, 3);
        assert_eq!(indices, vec![2, 5, 7]);
    }

    #[test]
    fn test_unrank_smallest() {
        let indices = unrank_subset(0, 10, 3);
        assert_eq!(indices, vec![0, 1, 2]);
    }

    #[test]
    fn test_unrank_empty() {
        assert_eq!(unrank_subset(0, 10, 0), Vec::<u64>::new());
    }
}
