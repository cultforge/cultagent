"""Extract preview logos into web static/img."""
from __future__ import annotations

import base64
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "preview"
OUT = ROOT / "src" / "cultagent" / "web" / "static" / "img"
OUT.mkdir(parents=True, exist_ok=True)


def extract_png(svg_path: Path, out_name: str) -> None:
    text = svg_path.read_text(encoding="utf-8", errors="ignore")
    patterns = [
        r'data:img/png;base64,([A-Za-z0-9+/=]+)',
        r'data:image/png;base64,([A-Za-z0-9+/=]+)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            data = base64.b64decode(m.group(1))
            (OUT / out_name).write_bytes(data)
            print(f"wrote {out_name} ({len(data)} bytes)")
            return
    print(f"no png in {svg_path.name}")


def main() -> None:
    extract_png(PREVIEW / "logo-disc.svg", "logo-disc.png")
    extract_png(PREVIEW / "logo-abstract.svg", "logo-abstract.png")
    shutil.copy(PREVIEW / "logo-thin.svg", OUT / "logo-thin.svg")
    # Prefer a lighter splash asset: copy disc if abstract is huge
    for name in ("logo-disc.png", "logo-abstract.png"):
        p = OUT / name
        if p.exists():
            print(name, "size", p.stat().st_size)
    print("done", OUT)


if __name__ == "__main__":
    main()
