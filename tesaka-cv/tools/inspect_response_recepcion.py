#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


# ----------------------------
# Helpers básicos
# ----------------------------

def pick_latest(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def is_scalar(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))


def walk(obj: Any):
    """DFS sobre dict/list; yield (path, value, last_key_norm, last_key_raw)."""
    stack = [(obj, "")]
    while stack:
        cur, p = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                nk = f"{p}.{k}" if p else str(k)
                yield nk, v, norm_key(str(k)), str(k)
                stack.append((v, nk))
        elif isinstance(cur, list):
            for i, it in enumerate(cur):
                nk = f"{p}[{i}]"
                yield nk, it, "", ""
                stack.append((it, nk))


def uniq(seq):
    seen = set()
    out = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def first_non_empty(hits: List[Tuple[str, Any]]) -> Optional[Tuple[str, Any]]:
    for p, v in hits:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return (p, v)
    return None


# ----------------------------
# Búsquedas por claves
# ----------------------------

def find_key_contains(data: Any, needles_raw: List[str]) -> List[Tuple[str, Any]]:
    """Match por 'contains' sobre clave normalizada (muy permisivo)."""
    needles = [norm_key(x) for x in needles_raw]
    hits: List[Tuple[str, Any]] = []
    for path, val, k_norm, _k_raw in walk(data):
        if not k_norm:
            continue
        if any(n in k_norm for n in needles):
            hits.append((path, val))
    # de-dup por path
    seen = set()
    out = []
    for p, v in hits:
        if p in seen:
            continue
        seen.add(p)
        out.append((p, v))
    return out


def find_key_exact(data: Any, keys_raw: List[str]) -> List[Tuple[str, Any]]:
    """Match exacto por clave normalizada."""
    want = {norm_key(k) for k in keys_raw}
    hits: List[Tuple[str, Any]] = []
    for path, val, k_norm, _k_raw in walk(data):
        if k_norm and k_norm in want:
            hits.append((path, val))
    # de-dup por path
    seen = set()
    out = []
    for p, v in hits:
        if p in seen:
            continue
        seen.add(p)
        out.append((p, v))
    return out


def print_kv(label: str, hit: Optional[Tuple[str, Any]]):
    if not hit:
        return
    p, v = hit
    print(f"{label:<12} => {p} = {v}")


# ----------------------------
# Heurística: encontrar "código/mensaje/estado"
# ----------------------------

STATE_WORDS = {"aceptado", "rechazado", "aprobado", "procesado", "pendiente", "observado", "error", "ok"}

def looks_like_code(v: Any) -> bool:
    if isinstance(v, int):
        return 0 <= v <= 99999
    if isinstance(v, str):
        s = v.strip()
        return bool(re.fullmatch(r"\d{3,5}", s))
    return False


def looks_like_state(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    s = v.strip().lower()
    return s in STATE_WORDS or any(w in s for w in STATE_WORDS)


def looks_like_message(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    s = v.strip()
    if len(s) < 6:
        return False
    # mensajes suelen tener letras/espacios
    return bool(re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", s))


def heuristic_candidates(data: Any) -> Dict[str, List[Tuple[str, Any]]]:
    """
    Busca leaf scalars y propone candidatos:
    - code: valores tipo 0362, 1003, etc
    - state: 'Rechazado', 'Aceptado', etc
    - msg: textos largos
    """
    codes: List[Tuple[str, Any]] = []
    states: List[Tuple[str, Any]] = []
    msgs: List[Tuple[str, Any]] = []

    for path, val, _k_norm, _k_raw in walk(data):
        if not is_scalar(val):
            continue
        if looks_like_code(val):
            codes.append((path, val))
        if looks_like_state(val):
            states.append((path, val))
        if looks_like_message(val):
            msgs.append((path, val))

    return {
        "codes": codes[:200],
        "states": states[:200],
        "msgs": msgs[:200],
    }


# ----------------------------
# Detectar listas "tipo documentos"
# ----------------------------

DOC_KEYS = {norm_key(k) for k in [
    "id", "cdc", "dcdc", "dEstRes", "estado", "dCodRes", "codigo", "dMsgRes", "mensaje",
    "gResProc", "resultado", "resproc"
]}

def score_doc_item(d: Dict[str, Any]) -> int:
    score = 0
    for k in d.keys():
        kn = norm_key(str(k))
        if kn in DOC_KEYS:
            score += 2
        if "cod" in kn and "res" in kn:
            score += 2
        if "msg" in kn and "res" in kn:
            score += 2
        if "est" in kn and "res" in kn:
            score += 2
        if kn in {"codigo", "mensaje", "estado"}:
            score += 2
    return score


def find_document_lists(data: Any) -> List[Tuple[str, List[Dict[str, Any]], int]]:
    """
    Busca cualquier lista de dicts que parezca lista de resultados por documento.
    Devuelve (path, list, score_total).
    """
    found: List[Tuple[str, List[Dict[str, Any]], int]] = []

    for path, val, _k_norm, _k_raw in walk(data):
        if isinstance(val, list) and val:
            dicts = [x for x in val if isinstance(x, dict)]
            if not dicts:
                continue
            # score por primeros N items
            s = sum(score_doc_item(d) for d in dicts[:10])
            if s >= 6:  # umbral: si hay varias llaves "buenas"
                found.append((path, dicts, s))

    found.sort(key=lambda t: t[2], reverse=True)
    return found


def get_from_dict_by_variants(d: Dict[str, Any], variants: List[str]) -> Optional[Any]:
    want = {norm_key(x) for x in variants}
    for k, v in d.items():
        if norm_key(str(k)) in want:
            return v
    return None


def print_docs_from_best_list(data: Any):
    candidates = find_document_lists(data)
    if not candidates:
        return
    path, dicts, score = candidates[0]
    print(f"\n--- DOCUMENTOS (heurístico desde {path}, score={score}) --- {len(dicts)}")

    for i, doc in enumerate(dicts[:50], 1):
        doc_id = get_from_dict_by_variants(doc, ["id", "cdc", "dCDC"])
        est = get_from_dict_by_variants(doc, ["dEstRes", "estado"])
        cod = get_from_dict_by_variants(doc, ["dCodRes", "codigo"])
        msg = get_from_dict_by_variants(doc, ["dMsgRes", "mensaje"])

        # a veces está anidado en gResProc
        rp = get_from_dict_by_variants(doc, ["gResProc", "resProc", "resultado", "g_res_proc"])
        if isinstance(rp, dict):
            cod2 = get_from_dict_by_variants(rp, ["dCodRes", "codigo"])
            msg2 = get_from_dict_by_variants(rp, ["dMsgRes", "mensaje"])
            if cod is None:
                cod = cod2
            if msg is None:
                msg = msg2

        print(f"\nDE #{i}")
        print("id      :", doc_id)
        print("estado  :", est)
        print("codigo  :", cod)
        print("mensaje :", msg)


# ----------------------------
# Main
# ----------------------------

def main():
    ap = argparse.ArgumentParser(description="Inspecciona artifacts response_recepcion_*.json (SIFEN) y saca resumen + heurística.")
    ap.add_argument("path", nargs="?", default=None, help="Path al JSON. Si no se pasa, usa el más reciente.")
    ap.add_argument("--all", action="store_true", help="Muestra info extra: claves raíz + candidatos heurísticos.")
    args = ap.parse_args()

    pattern = "artifacts/response_recepcion_*.json"
    path = args.path or pick_latest(pattern)
    if not path or not os.path.exists(path):
        print(f"❌ No encuentro archivo. Probé: {pattern}")
        sys.exit(1)

    print("📄 USANDO:", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 0) Diagnóstico: claves raíz
    if isinstance(data, dict):
        root_keys = list(data.keys())
    else:
        root_keys = []

    if args.all:
        print("\n--- ROOT KEYS ---")
        if root_keys:
            for k in root_keys[:200]:
                print("-", k)
        else:
            print("(no es dict en raíz)")

    # 1) Protocolo de lote: dProtConsLote / variantes
    prot_hits = find_key_contains(data, [
        "dProtConsLote", "d_prot_cons_lote", "protConsLote", "prot_lote", "protocolo", "lote"
    ])
    prot_num = []
    for p, v in prot_hits:
        if v is None:
            continue
        s = str(v).strip()
        if re.fullmatch(r"\d{10,30}", s):
            prot_num.append((p, s))

    print("\n--- CANDIDATOS (parecen protocolo numérico) ---")
    if prot_num:
        for p, s in prot_num[:50]:
            print(f"{p.split('.')[-1]} = {s} (len={len(s)})")
    else:
        print("⚠️  No encontré protocolo numérico obvio (dProtConsLote).")

    # 2) Resumen: buscar por variantes "fuertes"
    summary_map = {
        "dCodRes": ["dCodRes", "d_cod_res", "codigo", "codres", "cod_res", "codigorespuesta"],
        "dMsgRes": ["dMsgRes", "d_msg_res", "mensaje", "msgres", "msg_res", "mensajerespuesta"],
        "dEstRes": ["dEstRes", "d_est_res", "estado", "estres", "est_res", "estadorespuesta"],
        "dCodResLot": ["dCodResLot", "d_cod_res_lot", "codreslot", "codigolote"],
        "dMsgResLot": ["dMsgResLot", "d_msg_res_lot", "msgreslot", "mensajelote"],
        "dProt": ["dProt", "d_prot", "prot", "protocolo"],
    }

    print("\n--- RESUMEN (primer match por campo) ---")
    any_printed = False
    for label, vars_ in summary_map.items():
        hits = find_key_contains(data, vars_)
        hit = first_non_empty(hits)
        if hit:
            print_kv(label, hit)
            any_printed = True

    if not any_printed:
        print("⚠️  No encontré campos de resumen por nombre. Paso a heurística con --all.")

    # 3) Documentos: encontrar listas tipo documentos (sin depender del nombre)
    print_docs_from_best_list(data)

    # 4) Heurística (solo en --all)
    if args.all:
        h = heuristic_candidates(data)

        print("\n--- HEURÍSTICA: CÓDIGOS (valores tipo 0362/1003) ---")
        if h["codes"]:
            for p, v in h["codes"][:80]:
                print(f"{p} = {v}")
        else:
            print("(ninguno)")

        print("\n--- HEURÍSTICA: ESTADOS (Aceptado/Rechazado/etc) ---")
        if h["states"]:
            for p, v in h["states"][:80]:
                print(f"{p} = {v}")
        else:
            print("(ninguno)")

        print("\n--- HEURÍSTICA: MENSAJES (textos largos) ---")
        if h["msgs"]:
            for p, v in h["msgs"][:60]:
                print(f"{p} = {v}")
        else:
            print("(ninguno)")

    # 5) Extra: si viene el SOAP crudo en parsed_fields.xml, extraer campos útiles
    xml_hit = None
    for p, v, k_norm, _k_raw in walk(data):
        if k_norm == norm_key("xml") and isinstance(v, str) and "<env:Envelope" in v:
            # probablemente parsed_fields.xml
            xml_hit = (p, v)
            break

    if xml_hit:
        _p, soap = xml_hit
        def _grab(tag: str) -> Optional[str]:
            m = re.search(rf"<[^:>]*:{tag}>(.*?)</[^:>]*:{tag}>", soap)
            if not m:
                m = re.search(rf"<{tag}>(.*?)</{tag}>", soap)
            return m.group(1).strip() if m else None

        print("\n--- EXTRA (desde parsed_fields.xml) ---")
        print("dFecProc    :", _grab("dFecProc"))
        print("dTpoProces  :", _grab("dTpoProces"))
        print("dCodRes     :", _grab("dCodRes"))
        print("dMsgRes     :", _grab("dMsgRes"))
        print("dProtConsLote:", _grab("dProtConsLote"))

    sys.exit(0)


if __name__ == "__main__":
    main()
