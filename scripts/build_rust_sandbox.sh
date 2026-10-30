#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if ! command -v cargo >/dev/null 2>&1; then
  echo "Rust/Cargo is required. Install stable Rust with rustup." >&2
  exit 1
fi
cargo fmt --manifest-path sandbox-rs/Cargo.toml --all -- --check
cargo check --manifest-path sandbox-rs/Cargo.toml
cargo build --release --manifest-path sandbox-rs/Cargo.toml
"$ROOT/sandbox-rs/target/release/edith-sandbox" --version
