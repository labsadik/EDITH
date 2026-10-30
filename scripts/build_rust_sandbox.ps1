$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "Rust/Cargo is required. Install stable Rust with rustup and reopen PowerShell."
}
cargo check --manifest-path sandbox-rs/Cargo.toml
if ($LASTEXITCODE -ne 0) { throw "cargo check failed" }
cargo build --release --manifest-path sandbox-rs/Cargo.toml
if ($LASTEXITCODE -ne 0) { throw "cargo build failed" }
& (Join-Path $Root "sandbox-rs/target/release/edith-sandbox.exe") --version
if ($LASTEXITCODE -ne 0) { throw "Rust sandbox self-check failed" }
