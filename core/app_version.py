"""Single source of truth for EDITH product and installer metadata."""
from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
try:
    APP_VERSION = _VERSION_FILE.read_text(encoding="utf-8").strip()
except OSError:
    APP_VERSION = "1.0.0"

APP_NAME = "EDITH"
PRODUCT_NAME = "Neuron Intelligence"
PUBLISHER = "Sadik Laskar"
COPYRIGHT = "Copyright (c) 2026 Sadik Laskar. All Rights Reserved."
PROJECT_URL = "https://github.com/WorkRCS/EDITH_v1"
