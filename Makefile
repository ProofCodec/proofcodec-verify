.PHONY: test-python test-js test-wasm test-all

test-python:
	uv run pytest python/tests/ -v

test-js:
	cd js && npm ci && npx vitest run

test-wasm:
	cd wasm && cargo test
	cd wasm && bash build.sh

test-all: test-python test-js test-wasm
