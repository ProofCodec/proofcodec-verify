//! ProofCodec residual decoder — WASM build (decode-only).
//!
//! Scoped to residual decoding only. Tree inference stays in JS (flat-tree.js).
//! This crate handles the performance-critical part: parsing .v18 binary files
//! and looking up corrections by (leaf_id, block_id, idx_in_block).
//!
//! Exports:
//!   alloc(size) -> ptr             — allocate in WASM linear memory
//!   load_residual(ptr, len) -> i32 — parse .v18 file, returns 0=ok, -1=error
//!   get_num_leaves() -> u32
//!   get_total_positions() -> u64
//!   lookup(leaf_id, block_id, idx) -> i32  — returns label or -128 if no correction

mod codec;
mod combinadic;
mod leb128;
mod residual;

use std::sync::Mutex;

use codec::{LookupCache, V18Header};

static STATE: Mutex<Option<LoadedState>> = Mutex::new(None);

struct LoadedState {
    header: V18Header,
    cache: LookupCache,
}

/// Allocate bytes in WASM linear memory.
/// JS writes data here, then calls load_residual with the returned pointer.
#[no_mangle]
pub extern "C" fn alloc(size: u32) -> *mut u8 {
    let mut buf = Vec::with_capacity(size as usize);
    buf.resize(size as usize, 0u8);
    let ptr = buf.as_mut_ptr();
    std::mem::forget(buf);
    ptr
}

/// Parse a .v18 residual file from WASM memory.
/// Returns 0 on success, -1 on error.
#[no_mangle]
pub extern "C" fn load_residual(ptr: *const u8, len: u32) -> i32 {
    let data = unsafe { std::slice::from_raw_parts(ptr, len as usize) };
    match codec::parse_and_cache(data) {
        Ok((header, cache)) => {
            let mut state = STATE.lock().unwrap();
            *state = Some(LoadedState { header, cache });
            0
        }
        Err(_) => -1,
    }
}

/// Return number of leaves in the loaded file.
#[no_mangle]
pub extern "C" fn get_num_leaves() -> u32 {
    let state = STATE.lock().unwrap();
    match state.as_ref() {
        Some(s) => s.header.num_leaves,
        None => 0,
    }
}

/// Return total positions from the loaded file header.
#[no_mangle]
pub extern "C" fn get_total_positions() -> u64 {
    let state = STATE.lock().unwrap();
    match state.as_ref() {
        Some(s) => s.header.total_positions,
        None => 0,
    }
}

/// Look up a correction for a specific position.
/// Returns the WDL label (-1, 0, or 1) if position is a mismatch,
/// or -128 if no correction exists.
#[no_mangle]
pub extern "C" fn lookup(leaf_id: u32, block_id: u32, idx_in_block: u32) -> i32 {
    let state = STATE.lock().unwrap();
    let Some(s) = state.as_ref() else {
        return -128;
    };
    let Some(leaf_cache) = s.cache.get(&leaf_id) else {
        return -128;
    };
    let Some(block_cache) = leaf_cache.get(&block_id) else {
        return -128;
    };
    match block_cache.get(&idx_in_block) {
        Some(&label) => label as i32,
        None => -128,
    }
}
