#!/usr/bin/env python3
import re
import sys
from pathlib import Path

BASE = Path("docs/knowledge-base-sifen")

RE_3PLUS_BLANK = re.compile(r"\n{3,}")
RE_BAD_FENCE = re.compile(r"```[ \t]*\n{3,}(?=(---\n|#))", re.M)

def main() -> int:
    if not BASE.exists():
        print(f"ERROR: no existe {BASE}")
        return 2

    md_files = sorted(BASE.rglob("*.md"))
    if not md_files:
        print(f"ERROR: no hay .md en {BASE}")
        return 2

    bad_blank = []
    bad_fence = []

    for p in md_files:
        s = p.read_text(encoding="utf-8", errors="replace")
        if RE_3PLUS_BLANK.search(s):
            bad_blank.append(p)
        if RE_BAD_FENCE.search(s):
            bad_fence.append(p)

    if not bad_blank and not bad_fence:
        print("OK ✅ KB SIFEN whitespace guardrails: sin problemas")
        return 0

    print("FAIL ❌ KB SIFEN whitespace guardrails:")
    if bad_blank:
        print(f"- Archivos con 3+ líneas en blanco seguidas: {len(bad_blank)}")
        for p in bad_blank:
            print(f"  - {p}")
    if bad_fence:
        print(f"- Archivos con transición ``` + 2+ blanks antes de ---/#: {len(bad_fence)}")
        for p in bad_fence:
            print(f"  - {p}")

    print("\nCómo arreglar (NO manual):")
    print("  find docs/knowledge-base-sifen -type f -name \"*.md\" -print0 | xargs -0 perl -0777 -i -pe 's/\\n{3,}/\\n\\n/g'")
    print("  find docs/knowledge-base-sifen -type f -name \"*.md\" -print0 | xargs -0 perl -0777 -i -pe 's/```[ \\t]*\\n{3,}(?=(---\\n|#))/```\\n\\n/gm'")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
