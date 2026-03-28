#!/bin/bash
set -e
cd "$(dirname "$0")"

rustup target add wasm32-unknown-unknown 2>/dev/null || true
cargo build --target wasm32-unknown-unknown --release

WASM_FILE="target/wasm32-unknown-unknown/release/proofcodec_verify_wasm.wasm"
if [ -f "$WASM_FILE" ]; then
    cp "$WASM_FILE" ../proofcodec_verify.wasm
    SIZE=$(wc -c < ../proofcodec_verify.wasm)
    echo "Built: proofcodec_verify.wasm ($SIZE bytes)"
else
    echo "ERROR: WASM file not found at $WASM_FILE"
    exit 1
fi
