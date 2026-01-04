#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


def pick_latest(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def norm_key(s: str) -> str:
    # lower + quitar todo menos a-z0-9
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def is_scalar(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))


def walk(obj: Any):
    """
    DFS sobre dict/list.
    Yields: (path, value, last_key_norm, last_key_raw)
    """
    stack: List[Tuple[Any, str]] = [(obj, "")]
    while stack:
        cur, p = stack.pop()

        if isinstance(cur, dict):
            for k, v in cur.items():
                k_raw = str(k)
                nk = f"{p}.{k_raw}" if p else k_raw
                yield nk, v, norm_key(k_raw), k_raw
                stack.append((v, nk))

        elif isinstance(cur, list):
            for i, it in enumerate(cur):
                nk = f"{p}[{i}]"
                yield nk, it, "", ""
                stack.append((it, nk))


def first_non_empty(hits: List[Tuple[str, Any]]) -> Optional[Tuple[str, Any]]:
    for p, v in hits:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return (p, v)
    return None


def find_contains(data: Any, needles_raw: List[str]) -> List[Tuple[str, Any]]:
    """
    Match permisivo: si la clave normalizada CONTIENE cualquiera de los needles normalizados.
    """
    needles: List[str] = []
    for x in needles_raw:
        needles.append(norm_key(x))

    hits: List[Tuple[str, Any]] = []
    for path, val, k_norm, _k_raw in walk(data):
        if not k_norm:
            continue

        matched = False
        for n in needles:
            if n and (n in k_norm):
                matched = True
                break

        if matched:
            hits.append((path, val))

    # de-dup por path
    seen = set()
    out: List[Tuple[str, Any]] = []
    for p, v in hits:
        if p in seen:
            continue
        seen.add(p)
        out.append((p, v))
    return out


def get_from_dict_variants(d: Dict[str, Any], variants: List[str]) -> Optional[Any]:
    want = set()
    for v in variants:
        want.add(norm_key(v))

    for k, val in d.items():
        if norm_key(k) in want:
            return val
    return None


def print_lote_summary(data: Any):
    fec = None
    cod = None
    msg = None

    hit = first_non_empty(find_contains(data, ["dFecProc"]))
    if hit:
        fec = hit[1]

    hit = first_non_empty(find_contains(data, ["dCodResLot"]))
    if hit:
        cod = hit[1]

    hit = first_non_empty(find_contains(data, ["dMsgResLot"]))
    if hit:
        msg = hit[1]

    print("\n--- LOTE ---")
    print("dFecProc   :", fec)
    print("dCodResLot :", cod)
    print("dMsgResLot :", msg)


def print_docs(data: Any):
    # buscar lista tipo gResProcLote
    lote_hits = find_contains(data, ["gResProcLote"])
    lote_list = None
    lote_path = None

    for p, v in lote_hits:
        if isinstance(v, list):
            lote_list = v
            lote_path = p
            break

    if not isinstance(lote_list, list):
        print("\n--- DOCUMENTOS --- 0")
        return

    print(f"\n--- DOCUMENTOS --- {len(lote_list)}")
    if lote_path:
        print("path:", lote_path)

    for i, doc in enumerate(lote_list, 1):
        if not isinstance(doc, dict):
            continue

        doc_id = get_from_dict_variants(doc, ["id", "dId"])
        est = get_from_dict_variants(doc, ["dEstRes"])
        cod = get_from_dict_variants(doc, ["dCodRes"])
        msg = get_from_dict_variants(doc, ["dMsgRes"])

        # si viene anidado en gResProc (puede ser dict o list)
        rp = get_from_dict_variants(doc, ["gResProc"])

        if isinstance(rp, dict):
            cod2 = get_from_dict_variants(rp, ["dCodRes"])
            msg2 = get_from_dict_variants(rp, ["dMsgRes"])
            if cod is None:
                cod = cod2
            if msg is None:
                msg = msg2

        elif isinstance(rp, list):
            # tomar el primer dict que tenga dCodRes/dMsgRes
            for it in rp:
                if not isinstance(it, dict):
                    continue
                cod2 = get_from_dict_variants(it, ["dCodRes"])
                msg2 = get_from_dict_variants(it, ["dMsgRes"])
                if cod is None and cod2 is not None:
                    cod = cod2
                if msg is None and msg2 is not None:
                    msg = msg2
                # si ya tenemos ambos, cortamos
                if cod is not None and msg is not None:
                    break

        print(f"\nDE #{i}")
        print("id      :", doc_id)
        print("dEstRes :", est)
        print("dCodRes :", cod)
        print("dMsgRes :", msg)


def dump_relevant_paths(data: Any):
    needles = [
        "dCodRes", "dMsgRes", "dEstRes",
        "dCodResLot", "dMsgResLot",
        "gResProc", "gResProcLote",
        "dFecProc", "dProtConsLote",
    ]
    hits = find_contains(data, needles)

    print("\n--- DUMP PATHS (relevantes) ---")
    if not hits:
        print("(sin matches)")
        return

    for p, v in hits[:400]:
        if isinstance(v, (dict, list)):
            print(f"{p} = <{type(v).__name__}>")
        else:
            print(f"{p} = {v}")


def main():
    ap = argparse.ArgumentParser(description="Inspecciona artifacts/consulta_lote_*.json y extrae lote + documentos.")
    ap.add_argument("path", nargs="?", default=None, help="Path al JSON. Si no se pasa, usa el más reciente.")
    ap.add_argument("--dump-paths", action="store_true", help="Imprime paths relevantes encontrados en el JSON.")
    args = ap.parse_args()

    pattern = "artifacts/consulta_lote_*.json"
    path = args.path or pick_latest(pattern)

    if not path or not os.path.exists(path):
        print(f"❌ No encuentro archivo. Probé: {pattern}")
        sys.exit(1)

    print("📄 USANDO:", path)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print_lote_summary(data)
    print_docs(data)

    if args.dump_paths:
        dump_relevant_paths(data)

    sys.exit(0)


if __name__ == "__main__":
    main()
