#!/usr/bin/env python3
"""Utility to locate sent_lote XML files by dId without scanning the whole repo."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable, List

PROJECT_ROOT = Path("/Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado")
TESAKA_CV_ROOT = PROJECT_ROOT / "tesaka-cv"
BASE_ARTIFACT_DIRECTORIES: tuple[Path, ...] = (
    TESAKA_CV_ROOT / "artifacts",
    TESAKA_CV_ROOT / "tesaka-final" / "artifacts",
    PROJECT_ROOT / "artifacts",
)


def _gather_artifact_roots() -> list[Path]:
    """Return artifact directories, including tesaka-final and one extra depth under tesaka-cv."""

    roots: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path) -> None:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            return
        seen.add(resolved)
        roots.append(path)

    for base in BASE_ARTIFACT_DIRECTORIES:
        _add(base)

    if TESAKA_CV_ROOT.is_dir():
        for child in TESAKA_CV_ROOT.iterdir():
            if not child.is_dir():
                continue
            artifacts_dir = child / "artifacts"
            if artifacts_dir.is_dir():
                _add(artifacts_dir)

    return roots


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find the sent_lote_*.xml file that contains the provided dId without "
            "scanning the entire repository."
        )
    )
    parser.add_argument("did", help="dId string to search for inside sent_lote XML files")
    parser.add_argument(
        "--limit",
        type=int,
        default=60,
        help="Maximum number of files (ordered by mtime desc) to inspect (default: 60)",
    )
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=300_000,
        help="Maximum number of bytes to read from each file (default: 300000)",
    )
    parser.add_argument(
        "--copy-to",
        type=str,
        help="Directory where the matching XML will be copied as DE_TAL_CUAL_TRANSMITIDO_<dId>.xml",
    )
    return parser.parse_args()


def _iter_sent_lote_files(roots: Iterable[Path]) -> Iterable[Path]:
    for base_dir in roots:
        if not base_dir.is_dir():
            continue
        yield from base_dir.glob("sent_lote_*.xml")


def collect_candidates(limit: int, roots: List[Path]) -> List[Path]:
    entries: list[tuple[float, Path]] = []
    for path in _iter_sent_lote_files(roots):
        if not path.is_file():
            continue
        try:
            stat_result = path.stat()
        except OSError:
            continue
        entries.append((stat_result.st_mtime, path))
    entries.sort(key=lambda item: item[0], reverse=True)
    if limit < 1:
        return []
    return [path for _, path in entries[:limit]]


def copy_match(source: Path, dest_dir: Path, did: str) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f"DE_TAL_CUAL_TRANSMITIDO_{did}.xml"
    shutil.copy2(source, dest_file)


def main() -> int:
    args = parse_args()
    did = args.did
    limit = args.limit
    max_bytes = args.max_bytes

    if limit < 1:
        print("NOT_FOUND (checked 0 files)")
        return 2
    if max_bytes < 1:
        print("NOT_FOUND (checked 0 files)")
        return 2

    artifact_roots = _gather_artifact_roots()
    candidates = collect_candidates(limit, artifact_roots)
    did_bytes = did.encode("utf-8")

    for path in candidates:
        try:
            with path.open("rb") as handle:
                chunk = handle.read(max_bytes)
        except OSError:
            continue
        if did_bytes in chunk:
            print(f"FOUND {path}")
            if args.copy_to:
                copy_match(path, Path(args.copy_to), did)
            return 0

    print(f"NOT_FOUND (checked {len(candidates)} files)")
    for recent_path in candidates[:5]:
        print(recent_path)
    if artifact_roots:
        print("Roots inspected:")
        for root in artifact_roots[:5]:
            print(f" - {root}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
