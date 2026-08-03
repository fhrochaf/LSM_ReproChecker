"""Re-encode .venv .pth files so Windows can decode them correctly.

Why this exists: this project's path contains a non-ASCII character
("Flavio"). uv/pip write editable-install .pth files in UTF-8, but
Python's site.py reads .pth files with encoding="locale", which on
Windows always means the system codepage (cp1252 here) regardless of
PYTHONUTF8 mode. That mis-decodes the path, os.path.exists() fails on
the mangled result, and site.py silently drops the entry from
sys.path -- so the editable install stops working.

Run this after any `uv sync` / `uv pip install -e .` that touches this
project's editable install and breaks `crewai run` again.
"""

import locale
import sys
from pathlib import Path

VENV_SITE_PACKAGES = Path(__file__).resolve().parent.parent / ".venv" / "Lib" / "site-packages"


def fix_pth_file(pth_path: Path, target_encoding: str) -> bool:
    raw = pth_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    if text.isascii():
        return False
    try:
        reencoded = text.encode(target_encoding)
    except UnicodeEncodeError as e:
        print(f"  skip {pth_path.name}: cannot represent path in {target_encoding} ({e})")
        return False
    if reencoded == raw:
        return False
    pth_path.write_bytes(reencoded)
    return True


def main() -> int:
    target_encoding = locale.getpreferredencoding(False)
    if not VENV_SITE_PACKAGES.is_dir():
        print(f"No site-packages found at {VENV_SITE_PACKAGES}")
        return 1

    fixed = 0
    for pth_path in VENV_SITE_PACKAGES.glob("*.pth"):
        if fix_pth_file(pth_path, target_encoding):
            print(f"  fixed {pth_path.name}")
            fixed += 1

    print(f"Re-encoded {fixed} .pth file(s) to {target_encoding}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
