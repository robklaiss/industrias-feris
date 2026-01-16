#!/usr/bin/env python3
"""
Heurística offline para determinar si siRecepLoteDE espera rEnvioLote o rEnvioLoteDe.
Lee un WSDL previamente descargado (artifacts/recibe-lote.wsdl.xml).
"""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any


@dataclass
class WrapperGuess:
    wrapper: str
    reason: str
    evidence: List[str]


def _find_lines(text: str, pattern: str) -> List[str]:
    lines = []
    for idx, line in enumerate(text.splitlines(), 1):
        if pattern in line:
            snippet = line.strip()
            lines.append(f"L{idx}: {snippet[:200]}")
    return lines


def guess_wrapper_from_wsdl(wsdl_path: Path) -> WrapperGuess:
    if not wsdl_path.exists():
        return WrapperGuess("unknown", f"WSDL no encontrado: {wsdl_path}", [])

    text = wsdl_path.read_text(encoding="utf-8", errors="ignore")
    evidence: List[str] = []

    # Evidencia de elementos definidos
    has_envio_lote = bool(re.search(r'name=["\\\']rEnvioLote["\\\']', text))
    has_envio_lote_de = bool(re.search(r'name=["\\\']rEnvioLoteDe["\\\']', text))
    if has_envio_lote:
        evidence.extend(_find_lines(text, "rEnvioLote"))
    if has_envio_lote_de:
        evidence.extend(_find_lines(text, "rEnvioLoteDe"))

    # Buscar operaciones siRecepLoteDE y message/part
    si_receplote_refs = _find_lines(text, "siRecepLoteDE")
    evidence.extend(si_receplote_refs)

    wrapper = "unknown"
    reason_parts = []

    if has_envio_lote_de:
        wrapper = "rEnvioLoteDe"
        reason_parts.append("Se detectó elemento rEnvioLoteDe en el WSDL")
    elif has_envio_lote:
        wrapper = "rEnvioLote"
        reason_parts.append("Se detectó elemento rEnvioLote en el WSDL")

    if "rEnvioLoteDe" in "".join(si_receplote_refs):
        wrapper = "rEnvioLoteDe"
        reason_parts.append("siRecepLoteDE hace referencia a rEnvioLoteDe")
    elif "rEnvioLote" in "".join(si_receplote_refs):
        if wrapper == "unknown":
            wrapper = "rEnvioLote"
        reason_parts.append("siRecepLoteDE hace referencia a rEnvioLote")

    if wrapper == "unknown":
        reason_parts.append("No se encontraron patrones claros para rEnvioLote/De")

    reason = "; ".join(reason_parts) if reason_parts else "Sin evidencia concluyente"
    return WrapperGuess(wrapper=wrapper, reason=reason, evidence=evidence[:20])


def main() -> int:
    parser = argparse.ArgumentParser(description="Adivina el wrapper de siRecepLoteDE desde un WSDL ya descargado.")
    parser.add_argument(
        "--wsdl",
        type=Path,
        default=Path("artifacts/recibe-lote.wsdl.xml"),
        help="Path al WSDL descargado",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("artifacts/wsdl_wrapper_guess.json"),
        help="Archivo JSON con la evidencia",
    )
    args = parser.parse_args()

    guess = guess_wrapper_from_wsdl(args.wsdl)
    payload: Dict[str, Any] = {
        "wrapper_guess": guess.wrapper,
        "reason": guess.reason,
        "evidence": guess.evidence,
        "wsdl_path": str(args.wsdl),
    }
    try:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"💾 Guardado: {args.out}")
    except Exception:
        pass

    print(f"Wrapper guess: {guess.wrapper}")
    print(f"Reason: {guess.reason}")
    if guess.evidence:
        print("Evidence (sample):")
        for line in guess.evidence[:5]:
            print(f"  - {line}")

    return 0 if guess.wrapper != "unknown" else 1


if __name__ == "__main__":
    raise SystemExit(main())
