#!/usr/bin/env python3
"""
Genera un diff unificado sin pager, incluso si los archivos no están trackeados en git.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

DEFAULT_OUT = Path("/tmp/diff.out")
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5MB


def git_available() -> bool:
    return shutil.which("git") is not None


def run_git_diff(a: Path, b: Path) -> bytes:
    env = os.environ.copy()
    env["PAGER"] = "cat"
    env["GIT_PAGER"] = "cat"

    cmd = [
        "git",
        "--no-pager",
        "diff",
        "--no-index",
        "--unified=3",
        str(a),
        str(b),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=False,
        env=env,
        check=False,
    )

    if proc.returncode in (0, 1):
        return proc.stdout

    raise RuntimeError(
        f"git diff devolvió código {proc.returncode}:\n{proc.stderr.decode('utf-8', 'replace')}"
    )


def run_git_stat(a: Path, b: Path) -> str:
    env = os.environ.copy()
    env["PAGER"] = "cat"
    env["GIT_PAGER"] = "cat"

    cmd = [
        "git",
        "--no-pager",
        "diff",
        "--no-index",
        "--stat",
        str(a),
        str(b),
    ]

    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    if proc.returncode in (0, 1):
        return proc.stdout.strip()

    raise RuntimeError(
        f"git diff --stat devolvió código {proc.returncode}:\n{proc.stderr}"
    )


def run_difflib(a: Path, b: Path) -> bytes:
    import difflib

    text_a = a.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    text_b = b.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

    diff = difflib.unified_diff(
        text_a,
        text_b,
        fromfile=str(a),
        tofile=str(b),
    )
    return "".join(diff).encode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diff sin pager ni bloqueos.")
    parser.add_argument("--a", required=True, help="Archivo 'antes'")
    parser.add_argument("--b", required=True, help="Archivo 'después'")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Archivo de salida (default /tmp/diff.out)")
    parser.add_argument("--stat", action="store_true", help="Mostrar resumen de cambios (--stat)")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=DEFAULT_MAX_BYTES,
        help="Límite máximo de bytes del diff (default 5MB)",
    )
    return parser.parse_args()


def ensure_file(path: Path, label: str) -> None:
    if not path.exists():
        print(f"❌ El archivo {label} no existe: {path}")
        raise SystemExit(2)


def main() -> int:
    args = parse_args()

    file_a = Path(os.path.expanduser(args.a)).resolve()
    file_b = Path(os.path.expanduser(args.b)).resolve()
    out_path = Path(os.path.expanduser(args.out)).resolve()
    max_bytes = int(args.max_bytes)

    ensure_file(file_a, "--a")
    ensure_file(file_b, "--b")

    if max_bytes <= 0:
        print("❌ --max-bytes debe ser > 0")
        return 2

    try_git = git_available()
    diff_bytes: bytes

    try:
        if try_git:
            diff_bytes = run_git_diff(file_a, file_b)
        else:
            diff_bytes = run_difflib(file_a, file_b)
    except Exception as exc:
        print(f"⚠️  Error usando git: {exc}")
        print("   Usando fallback difflib...")
        try:
            diff_bytes = run_difflib(file_a, file_b)
        except Exception as fallback_exc:
            print(f"❌ No se pudo generar diff: {fallback_exc}")
            return 2

    if len(diff_bytes) > max_bytes:
        print(f"❌ Diff demasiado grande ({len(diff_bytes)} bytes). Límite: {max_bytes} bytes.")
        return 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(diff_bytes)

    lines = diff_bytes.decode("utf-8", errors="replace").count("\n")
    size_bytes = len(diff_bytes)

    if size_bytes == 0:
        print("ℹ️  Diff sin cambios (archivo vacío).")

    print("✅ Diff generado correctamente")
    print(f"   Archivo: {out_path}")
    print(f"   Líneas : {lines}")
    print(f"   Bytes  : {size_bytes}")

    if args.stat:
        try:
            stat_output = run_git_stat(file_a, file_b)
            if stat_output:
                print("\nResumen (--stat):")
                print(stat_output)
        except Exception as exc:
            print(f"⚠️  No se pudo obtener --stat: {exc}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
