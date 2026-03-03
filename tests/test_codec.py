"""Tests for proofcodec-verify codec module.

Verifies that the decode-only extraction produces correct results
using known test vectors from the ProofCodec encoder.
"""

import json
import subprocess

import pytest
from proofcodec_verify.proof.bundle import verify_bundle, ProofBundle
from proofcodec_verify.codec.combinadic import (
    binom, binom_bitlen, rank_subset, unrank_subset,
    decode_uvarint, decode_bigint_be,
)
from proofcodec_verify.codec.residual_v18 import (
    IndexEncoding, RecordType, BlockData,
    decode_delta_gaps, decode_enum_rank, decode_bitmap,
    decode_labels_fixed, decode_block, decode_empty_run,
)


class TestCombinadic:
    def test_binom_basic(self):
        assert binom(10, 3) == 120
        assert binom(5, 0) == 1
        assert binom(5, 5) == 1
        assert binom(3, 4) == 0  # k > n
        assert binom(0, 0) == 1

    def test_binom_bitlen(self):
        assert binom_bitlen(10, 3) == 7  # ceil(log2(120)) = 7
        assert binom_bitlen(5, 0) == 0   # C(5,0) = 1, log2(1) = 0
        assert binom_bitlen(5, 5) == 0   # C(5,5) = 1

    def test_rank_unrank_roundtrip(self):
        """rank -> unrank should be identity."""
        indices = [2, 5, 7]
        n = 10
        rank = rank_subset(indices, n)
        recovered = unrank_subset(rank, n, 3)
        assert recovered == indices

    def test_rank_smallest_subset(self):
        """Subset {0, 1, ..., k-1} should have rank 0."""
        assert rank_subset([0, 1, 2], 10) == 0

    def test_rank_largest_subset(self):
        """Subset {n-k, ..., n-1} should have rank C(n,k)-1."""
        assert rank_subset([7, 8, 9], 10) == binom(10, 3) - 1

    def test_unrank_empty(self):
        assert unrank_subset(0, 10, 0) == []


class TestDeltaGaps:
    def test_decode_basic(self):
        """Manually encode [3, 7, 10] as delta gaps and decode."""
        import leb128
        # first=3, gap1=7-3-1=3, gap2=10-7-1=2
        data = leb128.u.encode(3) + leb128.u.encode(3) + leb128.u.encode(2)
        indices, offset = decode_delta_gaps(data, 3, 0)
        assert indices == [3, 7, 10]
        assert offset == len(data)

    def test_decode_empty(self):
        indices, offset = decode_delta_gaps(b'', 0, 0)
        assert indices == []
        assert offset == 0

    def test_decode_single(self):
        import leb128
        data = leb128.u.encode(42)
        indices, offset = decode_delta_gaps(data, 1, 0)
        assert indices == [42]


class TestEnumRank:
    def test_decode_basic(self):
        """Encode rank for [2,5,7] in C(10,3) and decode."""
        import leb128
        rank = rank_subset([2, 5, 7], 10)
        rank_bytes = rank.to_bytes((rank.bit_length() + 7) // 8, 'big') if rank > 0 else b'\x00'
        data = leb128.u.encode(len(rank_bytes)) + rank_bytes
        indices, offset = decode_enum_rank(data, 10, 3, 0)
        assert indices == [2, 5, 7]

    def test_decode_rank_zero(self):
        """Rank 0 special case: rank_len=0 means [0,1,...,k-1]."""
        import leb128
        data = leb128.u.encode(0)
        indices, offset = decode_enum_rank(data, 10, 3, 0)
        assert indices == [0, 1, 2]


class TestBitmap:
    def test_decode_basic(self):
        """Bitmap with bits 0, 3, 7 set in n=16."""
        bitmap = bytearray(2)  # 16 bits = 2 bytes
        bitmap[0] = 0b10001001  # bits 0, 3, 7
        bitmap[1] = 0b00000000
        indices, offset = decode_bitmap(bytes(bitmap), 16, 0)
        assert indices == [0, 3, 7]
        assert offset == 2

    def test_decode_empty(self):
        bitmap = bytes(2)
        indices, offset = decode_bitmap(bitmap, 16, 0)
        assert indices == []


class TestLabels:
    def test_decode_2bit_legacy(self):
        """Legacy 2-bit: L(-1)->code 0, D(0)->code 1, W(1)->code 2."""
        # Pack [W, D, L] codes [2, 1, 0] at 2-bit positions:
        # bits 0-1: W=2=0b10, bits 2-3: D=1=0b01, bits 4-5: L=0=0b00
        # byte = 0b00_01_10 = 0x06
        data = bytes([0x06])
        labels, offset = decode_labels_fixed(data, 3, 0, leaf_prediction=None)
        assert labels == [1, 0, -1]  # W, D, L

    def test_decode_1bit_conditional(self):
        """1-bit conditional: leaf_pred=1 (W), remaining [-1, 0]."""
        # bit 0 -> remaining[0]=-1, bit 1 -> remaining[1]=0
        # Pack [L, D] = [0, 1] = 0b10 = 0x02
        data = bytes([0x02])
        labels, offset = decode_labels_fixed(data, 2, 0, leaf_prediction=1)
        assert labels == [-1, 0]  # L, D

    def test_decode_empty(self):
        labels, offset = decode_labels_fixed(b'', 0, 0)
        assert labels == []


class TestBlockDecode:
    def test_decode_empty_run(self):
        """EMPTY_RUN record: rec_type=0, run_len varint."""
        import leb128
        rec_hdr = RecordType.EMPTY_RUN & 0x3  # 0x00
        data = bytes([rec_hdr]) + leb128.u.encode(5)
        run_len, offset = decode_empty_run(data, 0)
        assert run_len == 5


class TestBaselines:
    def test_huffman_kqvk(self):
        """Verify Huffman baseline for KQvK endgame."""
        from proofcodec_verify.baseline import compute_all_baselines
        counts = {-1: 200896, 0: 23048, 1: 144508}
        baselines = compute_all_baselines(counts)
        # KQvK has L as most frequent -> L gets 1 bit, D and W get 2 bits
        assert baselines.B0.code_lengths[-1] == 1
        assert baselines.B0.code_lengths[0] == 2
        assert baselines.B0.code_lengths[1] == 2
        # Total bits = 200896*1 + 23048*2 + 144508*2 = 536008
        assert baselines.bits_B0 == 536008

    def test_huffman_deterministic_tiebreak(self):
        """When all counts equal, W(+1) gets shortest code.

        L(-1) has lowest rank so is popped first from min-heap, merged
        earlier, ending up deeper. W(+1) survives longest and gets 1 bit.
        """
        from proofcodec_verify.baseline import compute_all_baselines
        counts = {-1: 100, 0: 100, 1: 100}
        baselines = compute_all_baselines(counts)
        assert baselines.B0.code_lengths[1] == 1   # W survives longest
        assert baselines.B0.code_lengths[-1] == 2  # L merged first (deeper)
        assert baselines.B0.code_lengths[0] == 2   # D merged with L

    def test_ratio_b(self):
        """Verify ratio_B computation."""
        from proofcodec_verify.baseline import compute_all_baselines
        counts = {-1: 200896, 0: 23048, 1: 144508}
        baselines = compute_all_baselines(counts)
        ratio = baselines.ratio_B(219)  # KQvK model_bits from BENCHMARK.csv
        assert abs(ratio - 219 / 536008) < 1e-9

    def test_all_draw_single_class(self):
        """All-draw endgame: single class gets 1-bit code."""
        from proofcodec_verify.baseline import compute_all_baselines
        counts = {-1: 0, 0: 417228, 1: 0}
        baselines = compute_all_baselines(counts)
        assert baselines.B0.code_lengths[0] == 1
        assert baselines.bits_B0 == 417228


class TestV18Codec:
    def test_header_from_bytes(self):
        """Test V18Header deserialization."""
        from proofcodec_verify.codec.v18_codec import V18Header, MAGIC, LabelCodec, PartitionMode
        import struct

        header_bytes = struct.pack(
            '<4sHHIIIBB2x32s32sQQQ',
            MAGIC, 18, 2, 0, 4096, 5,
            PartitionMode.LEAF_BLOCK, LabelCodec.CONDITIONAL_1BIT,
            b'\x00' * 32, b'\x00' * 32,
            112, 1000000, 500,
        )

        header = V18Header.from_bytes(header_bytes)
        assert header.version_major == 18
        assert header.version_minor == 2
        assert header.block_size == 4096
        assert header.num_leaves == 5
        assert header.label_codec == LabelCodec.CONDITIONAL_1BIT
        assert header.total_positions == 1000000
        assert header.total_mismatches == 500

    def test_header_invalid_magic(self):
        """Invalid magic should raise ValueError."""
        from proofcodec_verify.codec.v18_codec import V18Header
        import struct

        bad_bytes = struct.pack(
            '<4sHHIIIBB2x32s32sQQQ',
            b'BAAD', 18, 0, 0, 4096, 0,
            0, 0,
            b'\x00' * 32, b'\x00' * 32,
            0, 0, 0,
        )

        with pytest.raises(ValueError, match="Invalid magic"):
            V18Header.from_bytes(bad_bytes)


class TestBundleVerification:
    def test_verify_without_model(self, tmp_path):
        """Model-less bundle with mismatches verifies when residual present."""
        manifest = {"endgame": "test", "version": "v18", "model_hash": "abc",
                     "total_positions": 1000, "mismatches": 5}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        (tmp_path / "residual.v18").write_bytes(b"\x00")
        result = verify_bundle(tmp_path)
        assert result.model_hash_valid is True
        assert result.model_included is False
        assert result.manifest_valid is True

    def test_verify_zero_mismatch_no_residual(self, tmp_path):
        """Zero-mismatch bundle needs no residual or model."""
        manifest = {"endgame": "exact", "version": "v18",
                     "total_positions": 500, "mismatches": 0}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        result = verify_bundle(tmp_path)
        assert result.is_valid is True

    def test_flatten_v20_nested_manifest(self, tmp_path):
        """V20 nested manifest loads correctly."""
        manifest = {"version": "v18.1", "timestamp": "2026-03-01", "endgame": "KQvK",
                     "domain": {"total_positions": 368452},
                     "verification": {"mismatches": 20732, "lossless": False},
                     "compression": {"baseline_bits": 536008, "total_bits": 219,
                                     "residual_bits": 149288},
                     "hashes": {"model.json": "abc123", "residual.v18": "def456"}}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        (tmp_path / "residual.v18").write_bytes(b"\x00")
        bundle = ProofBundle.load(tmp_path)
        assert bundle.manifest.endgame == "KQvK"
        assert bundle.manifest.total_positions == 368452
        assert bundle.manifest.mismatches == 20732
        assert bundle.manifest.baseline_bits == 536008

    def test_cli_bundle_modelless(self, tmp_path):
        """CLI bundle command succeeds with model-less bundle."""
        manifest = {"endgame": "cli_test", "version": "v18",
                     "total_positions": 100, "mismatches": 0}
        (tmp_path / "manifest.json").write_text(json.dumps(manifest))
        r = subprocess.run(["uv", "run", "proofcodec-verify", "bundle", str(tmp_path), "--json"],
                           capture_output=True, text=True)
        assert r.returncode == 0
        assert json.loads(r.stdout)["is_valid"] is True


class TestLeafPredictionValidation:
    """Verify that invalid leaf_prediction values raise ValueError."""

    def test_invalid_leaf_prediction(self):
        with pytest.raises(ValueError, match="leaf_prediction must be -1, 0, or 1"):
            decode_labels_fixed(b'\x00', 1, 0, leaf_prediction=2)
