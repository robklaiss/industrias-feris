#!/usr/bin/env python3
"""Search XML/JSON/LOG artifacts for a given dId string without using rg."""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Iterator, Sequence

ALLOWED_SUFFIXES = {".xml", ".json", ".log"}
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB per requirements
DEFAULT_MAX_MATCHES = 20
MAX_OUTPUT_LINES = 30
CANDIDATE_LABEL = "CANDIDATO_XML_TRANSMITIDO"


@dataclass(slots=True)
class MatchEntry:
    path: Path
    mtime: float
    size: int
    is_candidate: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Busca archivos pequeños (.xml/.json/.log) que contengan el dId indicado "
            "y marca los candidatos a XML transmitido."
        )
    )
    parser.add_argument("did", help="dId a buscar dentro de los archivos (match byte a byte)")
    parser.add_argument(
        "roots",
        nargs="+",
        help="Directorios donde buscar (se expanden y resuelven, se ignoran duplicados)",
    )
    parser.add_argument(
        "--max-matches",
        type=int,
        default=DEFAULT_MAX_MATCHES,
        help="Cantidad máxima de coincidencias a mostrar (default: 20)",
    )
    return parser.parse_args()


def resolve_roots(raw_roots: Sequence[str]) -> list[Path]:
    resolved: list[Path] = []
    seen: set[Path] = set()
    for raw in raw_roots:
        candidate = Path(raw).expanduser()
        try:
            real = candidate.resolve()
        except OSError:
            real = candidate
        if real in seen:
            continue
        seen.add(real)
        resolved.append(candidate)
    return resolved


def walk_allowed_files(root: Path) -> Iterator[Path]:
    stack: list[Path] = [root]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as iterator:
                for entry in iterator:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            path = Path(entry.path)
                            if path.suffix.lower() in ALLOWED_SUFFIXES:
                                yield path
                    except OSError:
                        continue
        except (OSError, NotADirectoryError):
            continue


def human_readable_size(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}B"
            return f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"


def scan_roots(
    roots: Sequence[Path], did_bytes: bytes
) -> tuple[list[MatchEntry], int, int, int, int, int]:
    matches: list[MatchEntry] = []
    files_examined = 0
    files_scanned = 0
    skipped_large = 0
    read_errors = 0
    missing_roots = 0

    for root in roots:
        if not root.is_dir():
            missing_roots += 1
            continue
        for path in walk_allowed_files(root):
            files_examined += 1
            try:
                stat_result = path.stat()
            except OSError:
                read_errors += 1
                continue
            if stat_result.st_size > MAX_FILE_SIZE_BYTES:
                skipped_large += 1
                continue
            try:
                data = path.read_bytes()
            except OSError:
                read_errors += 1
                continue
            files_scanned += 1
            if did_bytes not in data:
                continue
            is_candidate = (
                path.suffix.lower() == ".xml"
                and b"<rLoteDE" in data
                and b"<Signature" in data
            )
            matches.append(
                MatchEntry(
                    path=path,
                    mtime=stat_result.st_mtime,
                    size=stat_result.st_size,
                    is_candidate=is_candidate,
                )
            )
    return matches, files_examined, files_scanned, skipped_large, read_errors, missing_roots


def format_time(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def emit_lines(lines: Iterable[str]) -> None:
    count = 0
    for line in lines:
        print(line)
        count += 1
        if count >= MAX_OUTPUT_LINES:
            print("[info] Salida truncada a 30 líneas.")
            break


def main() -> int:
    args = parse_args()
    did = args.did
    if not did:
        print("❌ dId vacío", file=sys.stderr)
        return 1
    roots = resolve_roots(args.roots)
    did_bytes = did.encode("utf-8", errors="ignore")
    matches, files_examined, files_scanned, skipped_large, read_errors, missing_roots = scan_roots(
        roots, did_bytes
    )

    sorted_matches = sorted(
        matches,
        key=lambda m: (0 if m.is_candidate else 1, -m.mtime),
    )
    total_matches = len(sorted_matches)
    max_matches = max(1, args.max_matches)
    displayed_matches = sorted_matches[:max_matches]

    output_lines: list[str] = []
    output_lines.append(
        f"[info] Roots escaneados ({len(roots)}): "
        + ", ".join(str(root) for root in roots)
    )
    output_lines.append(
        "[info] Resumen: revisados="
        f"{files_examined} elegibles<=5MB="
        f"{files_scanned} saltados_por_tamano={skipped_large}"
        f" errores_lectura={read_errors} roots_inaccesibles={missing_roots}"
    )

    if not sorted_matches:
        output_lines.append(f"[warn] Sin coincidencias para dId={did}")
        emit_lines(output_lines)
        return 2

    header = f"[info] Coincidencias (hasta {max_matches} de {total_matches}):"
    output_lines.append(header)
    for match in displayed_matches:
        label = CANDIDATE_LABEL if match.is_candidate else "match"
        output_lines.append(
            f"- [{label}] {format_time(match.mtime)} size={human_readable_size(match.size)} path={match.path}"
        )

    hidden = total_matches - len(displayed_matches)
    if hidden > 0:
        output_lines.append(f"[info] {hidden} coincidencia(s) adicionales no mostradas.")

    best_candidate = next((m for m in sorted_matches if m.is_candidate), None)
    if best_candidate is not None:
        output_lines.append(f"BEST_CANDIDATE={best_candidate.path}")
        emit_lines(output_lines)
        return 0

    output_lines.append("[warn] No se detectó CANDIDATO_XML_TRANSMITIDO en las coincidencias.")
    emit_lines(output_lines)
    return 3


if __name__ == "__main__":
    sys.exit(main())
