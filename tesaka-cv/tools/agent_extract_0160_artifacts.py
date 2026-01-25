#!/usr/bin/env python3
"""Inspect artifacts for 0160 debugging without dumping huge XML blocks."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

from lxml import etree


TARGET_CHILDREN = [
    "dPorcDescTotal",
    "dDescTotal",
    "dTotDesc",
    "dTotOpe",
    "dTotIVA",
    "dTotGralOp",
    "dTotGrav",
    "dTotExe",
    "dSub5",
    "dSub10",
    "dSubExe",
    "dSubExo",
]

MAX_LIST_FILES = 30
MAX_LIST_LOGS = 10
MAX_SNIPPET_CHARS = 200
LOG_DID_PATTERN = re.compile(r"dId\s*=\s*([A-Za-z0-9_-]+)")
SKIP_DIR_NAMES = {".git", ".venv", "__pycache__", "node_modules"}
ARTIFACT_SEARCH_MAX_DEPTH = 3


@dataclass
class ArtifactPaths:
    transmitted_xml: Path
    consulta_response_xml: Path
    discovery_notes: list[str] = field(default_factory=list)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extracta información resumida de artifacts del último intento 0160"
    )
    parser.add_argument(
        "artifacts_dir",
        help="Directorio raíz donde viven los artifacts (ej: /path/to/SIFEN_ARTIFACTS)",
    )
    return parser.parse_args(argv)


def find_newest_file(directory: Path, pattern: str) -> Path | None:
    candidates = list(directory.glob(pattern))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def resolve_paths(artifacts_dir: Path) -> ArtifactPaths:
    tesaka_root = Path(__file__).resolve().parent.parent
    repo_root = tesaka_root.parent

    discovery_notes: list[str] = []
    transmitted = find_newest_file(artifacts_dir, "DE_TAL_CUAL_TRANSMITIDO*.xml")
    if transmitted is not None:
        discovery_notes.append("Estrategia A: archivo DE_TAL_CUAL_TRANSMITIDO*.xml encontrado en artifacts externo.")
    else:
        transmitted = find_newest_file(artifacts_dir, "sent_lote_*.xml")
        if transmitted is not None:
            discovery_notes.append("Estrategia B: usando sent_lote_*.xml más reciente en artifacts externo.")
    if transmitted is None:
        transmitted, note = recover_transmitted_from_repo(artifacts_dir, tesaka_root, repo_root)
        if transmitted is not None and note:
            discovery_notes.append(note)

    consulta = find_newest_file(artifacts_dir, "consulta_lote_response_*.xml")
    if consulta is None:
        raise FileNotFoundError(
            f"No se encontró archivo consulta_lote_response_*.xml en {artifacts_dir}"
        )

    if transmitted is None:
        raise_missing_transmitted(artifacts_dir)

    return ArtifactPaths(
        transmitted_xml=transmitted,
        consulta_response_xml=consulta,
        discovery_notes=discovery_notes,
    )


def recover_transmitted_from_repo(
    artifacts_dir: Path, tesaka_root: Path, repo_root: Path
) -> tuple[Path | None, str | None]:
    log_path = find_newest_file(artifacts_dir, "run_test_follow_*.log")
    if not log_path:
        return None, None

    did = extract_did_from_log(log_path)
    if not did:
        return None, None

    search_dirs = gather_artifact_dirs(repo_root)
    search_dirs.insert(0, tesaka_root / "artifacts")
    search_dirs.insert(0, repo_root / "artifacts")

    source = find_sent_lote_in_dirs(did, search_dirs)
    if not source:
        return None, None

    dest = artifacts_dir / f"DE_TAL_CUAL_TRANSMITIDO_{did}.xml"
    shutil.copy2(source, dest)
    note = (
        f"Estrategia C: copiado {source} hacia {dest.name} usando dId={did} desde {log_path.name}."
    )
    return dest, note


def extract_did_from_log(log_path: Path) -> str | None:
    try:
        for line in reversed(log_path.read_text(encoding="utf-8", errors="ignore").splitlines()):
            match = LOG_DID_PATTERN.search(line)
            if match:
                return match.group(1)
    except OSError:
        return None
    return None


def gather_artifact_dirs(repo_root: Path) -> list[Path]:
    dirs: list[Path] = []
    stack: list[tuple[Path, int]] = [(repo_root, 0)]
    seen: set[Path] = set()

    while stack:
        current, depth = stack.pop()
        if depth > ARTIFACT_SEARCH_MAX_DEPTH:
            continue
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name in SKIP_DIR_NAMES:
                continue
            if entry.name == "artifacts" and entry not in seen:
                dirs.append(entry)
                seen.add(entry)
            if depth + 1 <= ARTIFACT_SEARCH_MAX_DEPTH:
                stack.append((entry, depth + 1))
    return dirs


def find_sent_lote_in_dirs(did: str, directories: Sequence[Path]) -> Path | None:
    pattern = f"sent_lote_{did}_*.xml"
    candidates: list[Path] = []
    for directory in directories:
        if not directory.exists():
            continue
        candidates.extend(directory.glob(pattern))
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def raise_missing_transmitted(artifacts_dir: Path) -> None:
    xml_json = list_files_with_limit(artifacts_dir, ("*.xml", "*.json"), MAX_LIST_FILES)
    logs = list_files_with_limit(artifacts_dir, ("*.log",), MAX_LIST_LOGS)
    lines = [
        "No encontré XML transmitido. Intenté las 3 estrategias (DE_TAL_CUAL, sent_lote, dId desde log).",
        "Archivos XML/JSON detectados (máx 30):",
    ]
    if xml_json:
        lines.extend(f"  - {name}" for name in xml_json)
    else:
        lines.append("  (sin XML/JSON)")
    lines.append("Logs detectados (máx 10):")
    if logs:
        lines.extend(f"  - {name}" for name in logs)
    else:
        lines.append("  (sin logs)")
    report = "\n".join(lines)
    print(f"⚠️  {report}", file=sys.stderr)
    raise RuntimeError("MISSING_TRANSMITTED")


def list_files_with_limit(artifacts_dir: Path, patterns: Sequence[str], limit: int) -> list[str]:
    hits: list[tuple[float, str]] = []
    for pattern in patterns:
        for path in artifacts_dir.glob(pattern):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            hits.append((mtime, path.name))
    hits.sort(key=lambda x: x[0], reverse=True)
    return [name for _, name in hits[:limit]]


def _localname(tag: str | None) -> str:
    if not tag:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    if ":" in tag:
        return tag.split(":", 1)[1]
    return tag


def parse_transmitted_xml(path: Path) -> etree._ElementTree:
    parser = etree.XMLParser(remove_blank_text=False, huge_tree=True)
    return etree.parse(str(path), parser=parser)


def format_snippet(path: Path, line: int, column: int | None = None) -> str:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return "(No se pudo leer el archivo para snippet)"

    lines = content.splitlines()
    if not lines:
        return "(Archivo vacío)"

    target_idx = max(0, min(line - 1, len(lines) - 1))
    snippet = lines[target_idx]
    if column is not None and column > 0:
        marker = " " * (max(0, column - 1)) + "^"
        snippet = f"{snippet}\n{marker}"

    if len(snippet) > MAX_SNIPPET_CHARS:
        snippet = snippet[: MAX_SNIPPET_CHARS - 3] + "..."

    return f"Linea {line}: {snippet}"


def locate_gtotsub(tree: etree._ElementTree) -> etree._Element:
    hits = tree.xpath(".//*[local-name()='gTotSub']")
    if not hits:
        raise ValueError("No se encontró nodo gTotSub en el XML transmitido")
    return hits[0]


def enumerate_children(element: etree._Element) -> list[str]:
    names: list[str] = []
    for child in element:
        if not isinstance(child.tag, str):
            continue
        names.append(_localname(child.tag))
    return names


def summarize_targets(children: Sequence[str]) -> list[str]:
    lines = []
    for target in TARGET_CHILDREN:
        if target in children:
            idx = children.index(target)
            lines.append(f"- {target}: idx={idx}")
        else:
            lines.append(f"- {target}: NO ENCONTRADO")
    return lines


def eval_order(children: Sequence[str], a: str, b: str) -> str:
    if a not in children or b not in children:
        missing = []
        if a not in children:
            missing.append(a)
        if b not in children:
            missing.append(b)
        return f"{a} BEFORE {b}? N/A (falta: {', '.join(missing)})"
    idx_a, idx_b = children.index(a), children.index(b)
    return f"{a} BEFORE {b}? {'YES' if idx_a < idx_b else 'NO'} (idx {idx_a} vs {idx_b})"


def build_report(paths: ArtifactPaths, children: Sequence[str], timestamp: str) -> list[str]:
    lines = [
        "=== agent_extract_0160_artifacts ===",
        f"Timestamp: {timestamp}",
        f"Artifacts dir: {paths.transmitted_xml.parent}",
        f"Transmitido: {paths.transmitted_xml}",
        f"Respuesta consulta: {paths.consulta_response_xml}",
        "",
    ]

    if paths.discovery_notes:
        lines.append("Notas de descubrimiento:")
        for note in paths.discovery_notes:
            lines.append(f"- {note}")
        lines.append("")

    lines.append(f"gTotSub hijos directos ({len(children)}):")
    for idx, name in enumerate(children):
        lines.append(f"  {idx:02d}. {name}")

    lines.append("")
    lines.append("Orden relativo esperado vs real:")
    target_positions = summarize_targets(children)
    lines.extend(target_positions)
    lines.append("")
    for a, b in zip(TARGET_CHILDREN, TARGET_CHILDREN[1:]):
        lines.append(eval_order(children, a, b))
    return lines


def save_report(artifacts_dir: Path, lines: Sequence[str], timestamp: str) -> Path:
    report_path = artifacts_dir / f"agent_report_0160_{timestamp}.txt"
    report_text = "\n".join(lines) + "\n"
    report_path.write_text(report_text, encoding="utf-8")
    return report_path


def print_summary(lines: Sequence[str], max_lines: int = 30) -> None:
    for line in lines[:max_lines]:
        print(line)
    if len(lines) > max_lines:
        print(f"... (truncado, ver reporte completo para {len(lines)} líneas)")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    artifacts_dir = Path(args.artifacts_dir).expanduser()
    if not artifacts_dir.exists() or not artifacts_dir.is_dir():
        print(f"❌ Directorio inválido: {artifacts_dir}", file=sys.stderr)
        return 1

    try:
        paths = resolve_paths(artifacts_dir)
    except FileNotFoundError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        if str(exc) == "MISSING_TRANSMITTED":
            return 2
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        tree = parse_transmitted_xml(paths.transmitted_xml)
    except etree.XMLSyntaxError as exc:
        print("❌ XML MAL FORMADO en transmitido", file=sys.stderr)
        line, column = exc.position if exc.position else (None, None)
        if line is not None:
            print(f"   Línea {line}, columna {column}", file=sys.stderr)
            snippet = format_snippet(paths.transmitted_xml, line, column)
            print("\n--- CONTEXTO ---", file=sys.stderr)
            print(snippet, file=sys.stderr)
            print("--- FIN CONTEXTO ---", file=sys.stderr)
        print(f"   Detalle: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"❌ Error al parsear XML transmitido: {exc}", file=sys.stderr)
        return 1

    try:
        gtot_sub = locate_gtotsub(tree)
    except ValueError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    children = enumerate_children(gtot_sub)
    report_lines = build_report(paths, children, timestamp)
    report_path = save_report(artifacts_dir, report_lines, timestamp)

    print_summary(report_lines)
    print(f"\nReporte guardado en: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
