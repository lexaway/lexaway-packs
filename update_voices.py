"""Inject the voice catalog from voices.py into manifest.json.

Idempotent. Run this whenever voices.py changes (and once before each release,
which release.sh wires in for you).

Usage:
    uv run python update_voices.py
"""

import json
from pathlib import Path

from voices import VOICES


def inject_voices(manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text())
    manifest["voices"] = VOICES
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    total = sum(len(v) for v in VOICES.values())
    print(f"  Wrote {total} voices across {len(VOICES)} languages → {manifest_path}")


if __name__ == "__main__":
    inject_voices(Path("manifest.json"))
