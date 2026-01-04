#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import glob
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple


def pick_latest(pattern: str) -> Optional[str]:
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    return files[0] if files else None


def norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def walk(obj: Any):
    """DFS sobre dict/list; yield (path, value, last_key_norm)."""
    stack = [(obj, "")]
    while stack:
        cur, p = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                nk = f"{p}.{k}" if p else str(k)
                yield nk, v, norm_key(str(k))
                stack.append((v, nk))
        elif isinstance(cur, list):
            for i, it in enumerate(cur):
                nk = f"{p}[{i}]"
                yield nk, it, ""
                stack.append((it, nk))


def find_key_contains(data: Any, needles_raw: List[str]) -> List[Tuple[str, Any]]:
    needles = [norm_key(x) for x in needles_raw]
    hits: List[Tuple[str, Any]] = []
    for path, val, k_norm in walk(data):
        if not k_norm:
            continue
        if any(n in k_norm for n in needles):
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


def first_non_empty(hits: List[Tuple[str, Any]]) -> Optional[Tuple[str, Any]]:
    for p, v in hits:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return (p, v)
    return None


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_prot_cons_lote(data: Any) -> Optional[str]:
    hits = find_key_contains(data, ["dProtConsLote", "d_prot_cons_lote", "protcons", "protocolo", "lote"])
    # prefer numérico 10-30 dígitos
    for _p, v in hits:
        if v is None:
            continue
        s = str(v).strip()
        if re.fullmatch(r"\d{10,30}", s):
            return s
    # fallback: primer valor no vacío
    h = first_non_empty(hits)
    if h:
        return str(h[1]).strip()
    return None


def pick_latest_consulta_json(artifacts_dir: str) -> Optional[str]:
    pattern = os.path.join(artifacts_dir, "consulta_lote_*.json")
    return pick_latest(pattern)


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

def _is_scalar(x: Any) -> bool:
    return x is None or isinstance(x, (str, int, float, bool))

def _walk(obj: Any):
    """DFS: yield (path, value, last_key_norm)."""
    stack = [(obj, "")]
    while stack:
        cur, p = stack.pop()
        if isinstance(cur, dict):
            for k, v in cur.items():
                nk = f"{p}.{k}" if p else str(k)
                yield nk, v, _norm_key(k)
                stack.append((v, nk))
        elif isinstance(cur, list):
            for i, it in enumerate(cur):
                nk = f"{p}[{i}]"
                yield nk, it, ""
                stack.append((it, nk))

def _first_non_empty(hits: List[Tuple[str, Any]]) -> Optional[Tuple[str, Any]]:
    for p, v in hits:
        if v is None:
            continue
        if isinstance(v, str) and v.strip() == "":
            continue
        return (p, v)
    return None

def _find_in_obj_contains(obj: Any, needles: List[str]) -> List[Tuple[str, Any]]:
    """Match por 'contains' sobre la clave normalizada (permisivo)."""
    nn = [_norm_key(x) for x in needles]
    out: List[Tuple[str, Any]] = []
    seen = set()
    for path, val, k_norm in _walk(obj):
        if not k_norm:
            continue
        if any(n in k_norm for n in nn):
            if path in seen:
                continue
            seen.add(path)
            out.append((path, val))
    return out

def _get_field_any(obj: Any, keys: List[str]) -> Optional[Any]:
    hits = _find_in_obj_contains(obj, keys)
    h = _first_non_empty(hits)
    return h[1] if h else None

def _looks_like_code(v: Any) -> bool:
    # 0300, 0362, 1003, etc.
    if isinstance(v, int):
        return 0 <= v <= 99999
    if isinstance(v, str):
        s = v.strip()
        return bool(re.fullmatch(r"\d{3,5}", s))
    return False

def _extract_doc_fields(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extrae id/estado/cod/msg desde cualquier nivel (incluye gResProc anidado),
    soportando variantes snake_case/camelCase.
    """
    # id y estado suelen estar en 1er nivel, pero igual buscamos recursivo
    doc_id = None
    est = None
    cod = None
    msg = None

    # 1) id
    v = _get_field_any(doc, ["id", "dId", "d_id", "cdc", "dCDC", "d_cdc"])
    if v is not None:
        doc_id = v

    # 2) estado
    v = _get_field_any(doc, ["dEstRes", "d_est_res", "estado", "estRes", "est_res"])
    if v is not None:
        est = v

    # 3) código/mensaje (primero intentamos en gResProc explícito)
    g_res = _get_field_any(doc, ["gResProc", "g_res_proc", "resProc", "res_proc", "resultado"])
    if isinstance(g_res, dict):
        v = _get_field_any(g_res, ["dCodRes", "d_cod_res", "codigo_respuesta", "codigo", "codRes"])
        if v is not None and _looks_like_code(v):
            cod = v
        v = _get_field_any(g_res, ["dMsgRes", "d_msg_res", "mensaje", "msgRes"])
        if v is not None:
            msg = v

    # 4) fallback: buscar recursivamente dentro del doc (por si gResProc no existe o viene distinto)
    if cod is None:
        # agarrar el primer valor que parezca código 3-5 dígitos asociado a una clave tipo codres
        hits = _find_in_obj_contains(doc, ["dCodRes", "d_cod_res", "codigo_respuesta", "codres", "cod_res", "codigo"])
        for _p, vv in hits:
            if vv is None:
                continue
            if _looks_like_code(vv):
                cod = vv
                break

    if msg is None:
        hits = _find_in_obj_contains(doc, ["dMsgRes", "d_msg_res", "mensaje", "msgres", "msg_res"])
        for _p, vv in hits:
            if vv is None:
                continue
            if isinstance(vv, str) and vv.strip():
                msg = vv
                break

    return {"id": doc_id, "dEstRes": est, "dCodRes": cod, "dMsgRes": msg}

def summarize_consulta_lote(cons_data: Any) -> Tuple[Optional[str], Optional[str], Optional[str], List[Dict[str, Any]]]:
    """
    Devuelve: dFecProc, dCodResLot, dMsgResLot, docs[]
    docs[]: dict con id, dEstRes, dCodRes, dMsgRes
    """
    d_fec = _get_field_any(cons_data, ["dFecProc", "d_fec_proc"])
    d_cod_lot = _get_field_any(cons_data, ["dCodResLot", "d_cod_res_lot", "codreslot"])
    d_msg_lot = _get_field_any(cons_data, ["dMsgResLot", "d_msg_res_lot", "msgreslot"])

    docs: List[Dict[str, Any]] = []

    # 1) intentar por nombre típico
    lote_list = None
    for _p, v in _find_in_obj_contains(cons_data, ["gResProcLote", "g_res_proc_lote", "gresproclote"]):
        if isinstance(v, list):
            lote_list = v
            break

    # 2) heurística: cualquier lista de dicts que parezca docs (contiene id/estado/cod/msg o gResProc)
    if lote_list is None:
        best = None
        best_score = -1
        for p, v, k_norm in _walk(cons_data):
            if isinstance(v, list) and v and all(isinstance(x, dict) for x in v[:3]):
                score = 0
                d0 = v[0]
                keys_norm = {_norm_key(kk) for kk in d0.keys()}
                if "id" in keys_norm: score += 3
                if "destres" in keys_norm: score += 3
                if "gresproc" in keys_norm or "g_res_proc" in keys_norm: score += 4
                if "dcodres" in keys_norm: score += 2
                if "dmsgres" in keys_norm: score += 2
                if score > best_score:
                    best_score = score
                    best = v
        if best_score >= 3:
            lote_list = best

    if isinstance(lote_list, list):
        for doc in lote_list:
            if not isinstance(doc, dict):
                continue
            docs.append(_extract_doc_fields(doc))

    def _s(x: Any) -> Optional[str]:
        if x is None:
            return None
        return str(x).strip()

    return (_s(d_fec), _s(d_cod_lot), _s(d_msg_lot), docs)


def looks_concluded(d_cod_res_lot: Optional[str], d_msg_res_lot: Optional[str]) -> bool:
    if d_cod_res_lot:
        # en tus ejemplos: 0362 => "concluido"
        if str(d_cod_res_lot).strip() in {"0362"}:
            return True
    if d_msg_res_lot:
        s = str(d_msg_res_lot).lower()
        if "concluido" in s or "conclu" in s:
            return True
    return False


def run_consulta_lote(env: str, prot: str, wsdl_file: Optional[str], wsdl_cache_dir: Optional[str]) -> int:
    cmd = [sys.executable, "-m", "tools.consulta_lote_de", "--env", env, "--prot", prot]
    if wsdl_file:
        cmd += ["--wsdl-file", wsdl_file]
    if wsdl_cache_dir:
        cmd += ["--wsdl-cache-dir", wsdl_cache_dir]

    # Heredar env vars explícitamente (asegurar que SIFEN_* se pasen)
    env_dict = os.environ.copy()
    p = subprocess.run(cmd, env=env_dict)
    return int(p.returncode)


def main():
    ap = argparse.ArgumentParser(
        description="Toma el dProtConsLote desde response_recepcion_*.json y hace polling con tools.consulta_lote_de hasta que el lote concluya."
    )
    ap.add_argument("json_path", nargs="?", default=None, help="Path a response_recepcion_*.json. Si no se pasa, usa el más reciente.")
    ap.add_argument("--env", choices=["test", "prod"], default="test", help="Ambiente SIFEN (default: test).")
    ap.add_argument("--wsdl-file", default=None, help="WSDL file a usar para consulta-lote (ej: artifacts/consulta-lote.wsdl.xml).")
    ap.add_argument("--wsdl-cache-dir", default="artifacts", help="Cache dir para WSDL (default: artifacts).")
    ap.add_argument("--artifacts-dir", default="artifacts", help="Directorio artifacts/ (default: artifacts).")
    ap.add_argument("--interval", type=int, default=5, help="Segundos entre consultas (default: 5).")
    ap.add_argument("--timeout", type=int, default=180, help="Timeout total en segundos (default: 180).")
    ap.add_argument("--once", action="store_true", help="Solo 1 consulta (sin polling).")
    args = ap.parse_args()

    pattern = "artifacts/response_recepcion_*.json"
    json_path = args.json_path or pick_latest(pattern)
    if not json_path or not os.path.exists(json_path):
        print(f"❌ No encuentro JSON. Probé: {pattern}")
        sys.exit(1)

    data = load_json(json_path)
    prot = extract_prot_cons_lote(data)
    if not prot or not re.fullmatch(r"\d{10,30}", str(prot).strip()):
        print("❌ No pude extraer dProtConsLote numérico desde:", json_path)
        sys.exit(2)

    print("📄 USANDO:", json_path)
    print("🔎 dProtConsLote:", prot)

    start = time.time()
    attempt = 0

    while True:
        attempt += 1
        print(f"\n=== CONSULTA #{attempt} ===")
        rc = run_consulta_lote(args.env, prot, args.wsdl_file, args.wsdl_cache_dir)
        if rc != 0:
            print(f"⚠️  tools.consulta_lote_de terminó con rc={rc}. Sigo igualmente (puede ser temporal).")

        cons_json = pick_latest_consulta_json(args.artifacts_dir)
        if not cons_json or not os.path.exists(cons_json):
            print("⚠️  No encontré consulta_lote_*.json en artifacts. ¿Se generó?")
            if args.once:
                sys.exit(3)
        else:
            cons_data = load_json(cons_json)
            d_fec, d_cod_lot, d_msg_lot, docs = summarize_consulta_lote(cons_data)

            print("📄 consulta JSON:", cons_json)
            print("--- LOTE ---")
            print("dFecProc   :", d_fec)
            print("dCodResLot :", d_cod_lot)
            print("dMsgResLot :", d_msg_lot)

            print(f"--- DOCUMENTOS --- {len(docs)}")
            for i, doc in enumerate(docs, 1):
                print(f"\nDE #{i}")
                print("id      :", doc.get("id"))
                print("dEstRes :", doc.get("dEstRes"))
                print("dCodRes :", doc.get("dCodRes"))
                print("dMsgRes :", doc.get("dMsgRes"))

            if looks_concluded(d_cod_lot, d_msg_lot):
                print("\n✅ Lote concluido (según dCodResLot/dMsgResLot).")
                sys.exit(0)

        if args.once:
            sys.exit(0)

        elapsed = time.time() - start
        if elapsed >= args.timeout:
            print(f"\n⏱️  Timeout alcanzado ({args.timeout}s). Último dProtConsLote={prot}")
            sys.exit(4)

        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()

