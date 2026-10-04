#!/usr/bin/env python3
"""Fail the build when a generated internal HTML link has no target."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
HREF = re.compile(r'<a\b[^>]*\bhref="([^"]+)"', re.I)


def resolve(page: Path, href: str) -> Path:
    # Query-строка и якорь — это часть адреса страницы, а не отдельный файл.
    # catalog/?type=tv открывает catalog/index.html, а не несуществующий путь с «?».
    clean = href.split("?", 1)[0].split("#", 1)[0]
    path = (page.parent / clean).resolve()
    if clean.endswith("/") or not clean:
        return path / "index.html"
    if path.is_dir():
        return path / "index.html"
    return path


def main():
    errors = []
    pages = sorted(DOCS.rglob("*.html"))
    for page in pages:
        for href in HREF.findall(page.read_text(encoding="utf-8")):
            if href.startswith(("#", "http:", "https:", "mailto:", "javascript:")):
                continue
            if not resolve(page, href).exists():
                errors.append(f"{page.relative_to(DOCS)} -> {href}")
    if errors:
        print("Broken internal links:")
        print("\n".join(errors[:100]))
        return 1
    print(f"Internal links passed: {len(pages)} pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
