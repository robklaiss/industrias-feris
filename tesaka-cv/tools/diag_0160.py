#!/usr/bin/env python3
"""
Herramienta de diagnóstico para errores 0160.

Lee dos XML (ej: uno "exitoso" y uno "fallido") y genera reportes:
- artifacts/diag0160/xml_report.md
- artifacts/diag0160/diff_raw.txt
- artifacts/diag0160/diff_xpaths.txt
- artifacts/diag0160/firma_compare.txt
"""

import argparse
import difflib
import re
from pathlib import Path
from typing import Dict, List, Tuple

from lxml import etree

DEFAULT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "diag0160"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_xml(path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    return etree.parse(str(path), parser)


def iter_nodes(root: etree._Element) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for elem in root.iter():
        tag = etree.QName(elem).localname
        ns = etree.QName(elem).namespace
        prefix = elem.prefix or ""
        text = elem.text or ""
        has_children = len(elem) > 0
        is_empty = (not text.strip()) and not has_children
        leading_ws = bool(re.match(r"\s", text)) if text else False
        trailing_ws = bool(re.search(r"\s$", text)) if text else False
        weird_chars = []
        for ch in text:
            if ch in "\t\r\u00a0":
                weird_chars.append(repr(ch))
        xpath = root.getroottree().getpath(elem)
        results.append(
            {
                "xpath": xpath,
                "tag": tag,
                "ns": ns or "",
                "prefix": prefix,
                "text": text,
                "text_len": str(len(text)),
                "leading_ws": str(leading_ws),
                "trailing_ws": str(trailing_ws),
                "is_empty": str(is_empty),
                "weird_chars": ",".join(weird_chars),
            }
        )
    return results


def summarize(names: str, nodes: List[Dict[str, str]]) -> str:
    prefixes = sorted({n["prefix"] for n in nodes if n["prefix"]})
    ns_uris = sorted({n["ns"] for n in nodes if n["ns"]})
    empty_tags = [n for n in nodes if n["is_empty"] == "True"]
    leading = [n for n in nodes if n["leading_ws"] == "True" or n["trailing_ws"] == "True"]
    weird = [n for n in nodes if n["weird_chars"]]
    lines = [
        f"## Resumen {names}",
        f"- Prefijos usados: {prefixes or 'none'}",
        f"- Namespaces encontrados: {ns_uris or 'none'}",
        f"- Tags vacíos: {len(empty_tags)}",
        f"- Text con whitespace al inicio/fin: {len(leading)}",
        f"- Text con caracteres raros (\\t, \\r, NBSP): {len(weird)}",
    ]
    return "\n".join(lines)


def save_diff_raw(a_text: str, b_text: str, path: Path, a_label: str, b_label: str) -> None:
    diff = difflib.unified_diff(
        a_text.splitlines(),
        b_text.splitlines(),
        fromfile=a_label,
        tofile=b_label,
        lineterm="",
    )
    path.write_text("\n".join(diff), encoding="utf-8")


def save_diff_xpaths(a_nodes: List[Dict[str, str]], b_nodes: List[Dict[str, str]], path: Path) -> None:
    lines = []
    all_paths = sorted({n["xpath"] for n in a_nodes} | {n["xpath"] for n in b_nodes})
    a_map = {n["xpath"]: n for n in a_nodes}
    b_map = {n["xpath"]: n for n in b_nodes}
    for xp in all_paths:
        a_val = a_map.get(xp)
        b_val = b_map.get(xp)
        if a_val == b_val:
            continue
        lines.append(f"XPath: {xp}")
        if a_val:
            lines.append(f"  A text({a_val['text_len']}): {repr(a_val['text'])}")
            lines.append(f"  A prefix/ns: {a_val['prefix']}/{a_val['ns']}")
        else:
            lines.append("  A: missing")
        if b_val:
            lines.append(f"  B text({b_val['text_len']}): {repr(b_val['text'])}")
            lines.append(f"  B prefix/ns: {b_val['prefix']}/{b_val['ns']}")
        else:
            lines.append("  B: missing")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def extract_signature(tree: etree._ElementTree) -> Tuple[str, str]:
    root = tree.getroot()
    signed_info = root.find(".//{http://www.w3.org/2000/09/xmldsig#}SignedInfo")
    signature_value = root.find(".//{http://www.w3.org/2000/09/xmldsig#}SignatureValue")
    canon = etree.tostring(signed_info, pretty_print=True, encoding="unicode") if signed_info is not None else ""
    sig_val = signature_value.text.strip() if signature_value is not None and signature_value.text else ""
    return canon, sig_val


def write_signature_compare(a_tree: etree._ElementTree, b_tree: etree._ElementTree, path: Path) -> None:
    a_canon, a_sig = extract_signature(a_tree)
    b_canon, b_sig = extract_signature(b_tree)
    lines = [
        "=== SignedInfo A ===",
        a_canon or "(no SignedInfo)",
        "",
        "=== SignedInfo B ===",
        b_canon or "(no SignedInfo)",
        "",
        "=== SignatureValue A ===",
        a_sig or "(empty)",
        "",
        "=== SignatureValue B ===",
        b_sig or "(empty)",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de XML para error 0160")
    parser.add_argument("xml_a", type=Path, help="XML base (ej: dic 2025)")
    parser.add_argument("xml_b", type=Path, help="XML actual con 0160")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_DIR,
        help="Directorio de salida (default: artifacts/diag0160)",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    a_text = read_text(args.xml_a)
    b_text = read_text(args.xml_b)

    save_diff_raw(a_text, b_text, out_dir / "diff_raw.txt", str(args.xml_a), str(args.xml_b))

    tree_a = parse_xml(args.xml_a)
    tree_b = parse_xml(args.xml_b)
    nodes_a = iter_nodes(tree_a.getroot())
    nodes_b = iter_nodes(tree_b.getroot())

    save_diff_xpaths(nodes_a, nodes_b, out_dir / "diff_xpaths.txt")
    write_signature_compare(tree_a, tree_b, out_dir / "firma_compare.txt")

    report_lines = [
        "# Reporte XML 0160",
        summarize("A (base)", nodes_a),
        "",
        summarize("B (actual)", nodes_b),
        "",
        "### Observaciones automáticas",
        "- Revisar diff_xpaths.txt para diferencias de texto/namespaces.",
        "- Revisar firma_compare.txt para cambios en SignedInfo/SignatureValue.",
        "- Tags vacíos o whitespace pueden gatillar 0160.",
    ]
    (out_dir / "xml_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
