# tools/assert_no_dup_gcamfufd.py
from pathlib import Path
from lxml import etree
import sys

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

def count_tag(xml_path: Path, local: str) -> int:
    root = etree.parse(str(xml_path)).getroot()
    return len(root.findall(f".//{{{SIFEN_NS}}}{local}"))

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: .venv/bin/python -m tools.assert_no_dup_gcamfufd <archivo.xml>")
        sys.exit(2)

    p = Path(sys.argv[1])
    if not p.exists():
        print(f"No existe: {p}")
        sys.exit(2)

    c = count_tag(p, "gCamFuFD")
    print(f"gCamFuFD count: {c}")
    if c != 1:
        print("FAIL: gCamFuFD debe ser 1")
        sys.exit(1)

    print("OK ✅")
