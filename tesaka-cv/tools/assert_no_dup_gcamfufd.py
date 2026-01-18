#!/usr/bin/env python3
import sys
from lxml import etree

def count_gcamfufd(xml_path: str) -> int:
    root = etree.parse(xml_path).getroot()
    return len(root.xpath('//*[local-name()="gCamFuFD"]'))

def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Uso: python tools/assert_no_dup_gcamfufd.py <archivo.xml>", file=sys.stderr)
        return 2
    path = argv[1]
    n = count_gcamfufd(path)
    print(f"gCamFuFD count: {n} ({path})")
    return 0 if n == 1 else 1

if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
