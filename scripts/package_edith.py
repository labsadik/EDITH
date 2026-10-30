"""Build an onedir EDITH application bundle for the current operating system."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
WINDOWS = os.name == "nt"
BINARY = "edith-sandbox.exe" if WINDOWS else "edith-sandbox"
SANDBOX = ROOT / "sandbox-rs" / "target" / "release" / BINARY

if not SANDBOX.is_file():
    raise SystemExit(
        f"Missing native sandbox binary: {SANDBOX}. "
        "Build it first with cargo build --release --manifest-path sandbox-rs/Cargo.toml"
    )

dist = ROOT / "dist"
if dist.exists():
    shutil.rmtree(dist)
dist.mkdir(parents=True, exist_ok=True)

sep = os.pathsep
data = [
    ("VERSION", "."),
    ("core/prompt.txt", "core"),
    ("assets/hud_reference.mp4", "assets"),
    ("config/mcp_servers.json", "config"),
    ("agents/manifest.json", "agents"),
    ("plugins", "plugins"),
]
for source, _destination in data:
    if not (ROOT / source).exists():
        raise SystemExit(f"Required EDITH resource is missing: {source}")

args = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm", "--clean", "--onedir", "--windowed",
    "--name", "EDITH",
    "--distpath", str(dist),
    "--workpath", str(ROOT / "build" / "pyinstaller"),
    "--specpath", str(ROOT / "build"),
]
if WINDOWS:
    args += [
        "--icon", str(ROOT / "config" / "assistant.ico"),
        "--version-file", str(ROOT / "installer" / "windows" / "version_info.txt"),
    ]
elif sys.platform == "darwin":
    from PIL import Image
    icon_file = ROOT / "build" / "edith.icns"
    icon_file.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(ROOT / "config" / "assistant.ico") as source_icon:
        source_icon.convert("RGBA").save(
            icon_file, format="ICNS",
            sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512)],
        )
    args += ["--icon", str(icon_file)]
for source, destination in data:
    args += ["--add-data", f"{ROOT / source}{sep}{destination}"]
args += ["--add-binary", f"{SANDBOX}{sep}sandbox-rs/target/release"]

# Keep importlib/plugin-discovered modules and Qt WebEngine runtime inside the
# distributable. Per-user credentials are deliberately never bundled.
for package in (
    "google.genai", "langchain_core", "langchain_text_splitters",
    "langgraph", "lancedb", "paho.mqtt", "actions", "agents", "core",
    "dashboard", "memory", "plugins", "edith", "tools",
):
    args += ["--collect-all", package]
args += [
    # SDK tests are not runtime dependencies; avoid bundling pytest-only modules.
    "--exclude-module", "google.genai.tests",
    "--hidden-import", "google.genai.types",
    "--hidden-import", "PyQt6.QtCore",
    "--hidden-import", "PyQt6.QtGui",
    "--hidden-import", "PyQt6.QtWidgets",
    "--hidden-import", "PyQt6.QtMultimedia",
    "--hidden-import", "PyQt6.QtNetwork",
    "--hidden-import", "PyQt6.QtSvg",
    "--hidden-import", "PyQt6.QtWebEngineCore",
    "--hidden-import", "PyQt6.QtWebEngineWidgets",
    "--hidden-import", "sounddevice",
    "--hidden-import", "keyring",
    str(ROOT / "main.py"),
]
subprocess.run(args, cwd=ROOT, check=True)

if sys.platform == "darwin":
    output = dist / "EDITH.app"
else:
    output = dist / "EDITH"
if not output.exists():
    raise SystemExit("PyInstaller did not produce the EDITH application bundle")
print(f"Built {output} (version {VERSION})")
