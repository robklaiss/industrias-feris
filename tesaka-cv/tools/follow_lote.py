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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


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


_DOC_ID_KEYS = {"id", "did", "d_id", "cdc", "dcdc", "d_cdc"}
_DOC_STATUS_KEYS = {"destres", "d_est_res", "estado", "estres"}
_DOC_CODE_KEYS = {"dcodres", "d_cod_res", "codigo", "codres", "cod_res"}
_DOC_MSG_KEYS = {"dmsgres", "d_msg_res", "mensaje", "msgres", "msg_res"}
_DOC_CONTAINER_KEYS = {"gresproc", "gresprocde", "gresproclote", "gresproclotede"}


def _looks_like_doc_dict(candidate: Dict[str, Any]) -> bool:
    keys = {_norm_key(k) for k in candidate.keys()}
    if not keys:
        return False
    identity = keys & (_DOC_ID_KEYS | _DOC_STATUS_KEYS)
    if not identity:
        return False
    score = 0
    for pool in (_DOC_ID_KEYS, _DOC_STATUS_KEYS, _DOC_CODE_KEYS, _DOC_MSG_KEYS, _DOC_CONTAINER_KEYS):
        if keys & pool:
            score += 1
    return score >= 2


def _normalize_doc_entry(doc: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _extract_doc_fields(doc)
    cdc = _get_field_any(doc, ["dCDC", "cdc", "d_cdc"])
    if cdc is not None:
        normalized["cdc"] = cdc
        if normalized.get("id") is None:
            normalized["id"] = cdc
    else:
        normalized["cdc"] = None
    return normalized


def parse_consulta_lote_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Devuelve lista de documentos normalizados (id/cdc + estado/código/mensaje)."""

    docs: List[Dict[str, Any]] = []
    seen: Set[Tuple[Any, Any, Any, Any, Any]] = set()

    for _path, node, _ in walk(data):
        if isinstance(node, dict) and _looks_like_doc_dict(node):
            normalized = _normalize_doc_entry(node)
            key = (
                normalized.get("id"),
                normalized.get("cdc"),
                normalized.get("dEstRes"),
                normalized.get("dCodRes"),
                normalized.get("dMsgRes"),
            )
            if key in seen:
                continue
            seen.add(key)
            docs.append(normalized)

    if docs:
        return docs

    # Fallback: buscar listas conocidas aunque no hayan coincidido con la heurística
    for _p, value in _find_in_obj_contains(
        data, ["gResProcLote", "gResProcLoteDE", "gResProcDE", "gResProc"]
    ):
        candidates: List[Any] = []
        if isinstance(value, list):
            candidates = value
        elif isinstance(value, dict):
            candidates = list(value.values())
        for doc in candidates:
            if not isinstance(doc, dict):
                continue
            normalized = _normalize_doc_entry(doc)
            key = (
                normalized.get("id"),
                normalized.get("cdc"),
                normalized.get("dEstRes"),
                normalized.get("dCodRes"),
                normalized.get("dMsgRes"),
            )
            if key in seen:
                continue
            seen.add(key)
            docs.append(normalized)

    return docs

def summarize_consulta_lote(cons_data: Any) -> Tuple[Optional[str], Optional[str], Optional[str], List[Dict[str, Any]]]:
    """
    Devuelve: dFecProc, dCodResLot, dMsgResLot, docs[]
    docs[]: dict con id, dEstRes, dCodRes, dMsgRes
    """
    d_fec = _get_field_any(cons_data, ["dFecProc", "d_fec_proc"])
    d_cod_lot = _get_field_any(cons_data, ["dCodResLot", "d_cod_res_lot", "codreslot"])
    d_msg_lot = _get_field_any(cons_data, ["dMsgResLot", "d_msg_res_lot", "msgreslot"])

    docs = parse_consulta_lote_response(cons_data)

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


def run_consulta_lote(
    env: str,
    prot: str,
    wsdl_file: Optional[str],
    wsdl_cache_dir: Optional[str],
    artifacts_dir: Optional[str],
    out_path: Optional[str] = None,
) -> int:
    cmd = [sys.executable, "-m", "tools.consulta_lote_de", "--env", env, "--prot", prot]
    if wsdl_file:
        cmd += ["--wsdl-file", wsdl_file]
    if wsdl_cache_dir:
        cmd += ["--wsdl-cache-dir", wsdl_cache_dir]
    if artifacts_dir:
        cmd += ["--artifacts-dir", artifacts_dir]
    if out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        cmd += ["--out", out_path]

    env_dict = os.environ.copy()
    proc = subprocess.run(cmd, env=env_dict)
    if proc.returncode == 0:
        return 0

    print("⚠️  tools.consulta_lote_de falló. Intentando fallback RAW directo...")
    fallback_rc = run_consulta_lote_raw_fallback(
        env=env,
        prot=prot,
        artifacts_dir=artifacts_dir,
        out_path=out_path,
    )
    return 0 if fallback_rc == 0 else int(proc.returncode)


def run_consulta_lote_raw_fallback(
    env: str,
    prot: str,
    artifacts_dir: Optional[str],
    out_path: Optional[str],
) -> int:
    try:
        from app.sifen_client.config import get_sifen_config
        from app.sifen_client.soap_client import SoapClient
    except ImportError as exc:
        print(f"❌ No se pudo importar SoapClient para fallback RAW: {exc}")
        return 1

    artifacts_base = Path(artifacts_dir or "artifacts")
    artifacts_base.mkdir(parents=True, exist_ok=True)

    target_path = Path(out_path) if out_path else artifacts_base / "consulta_lote_raw_fallback.json"
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        config = get_sifen_config(env=env)
        client = SoapClient(config)
        try:
            result = client.consulta_lote_raw(
                dprot_cons_lote=prot,
                artifacts_dir=artifacts_base,
            )
        finally:
            try:
                client.close()
            except Exception:
                pass

        target_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(f"✅ Fallback consulta_lote_raw guardó respuesta en: {target_path}")
        return 0
    except Exception as exc:
        print(f"❌ Fallback consulta_lote_raw también falló: {exc}")
        return 1


def build_consulta_output_path(artifacts_dir: str) -> str:
    os.makedirs(artifacts_dir, exist_ok=True)
    while True:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        candidate = os.path.join(artifacts_dir, f"consulta_lote_{ts}.json")
        if not os.path.exists(candidate):
            return candidate
        time.sleep(0.3)


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

    last_json_path: Optional[str] = None

    while True:
        attempt += 1
        print(f"\n=== CONSULTA #{attempt} ===")
        out_path = build_consulta_output_path(args.artifacts_dir)
        rc = run_consulta_lote(args.env, prot, args.wsdl_file, args.wsdl_cache_dir, args.artifacts_dir, out_path)
        last_json_path = out_path
        if rc != 0:
            print(f"⚠️  tools.consulta_lote_de terminó con rc={rc}. Sigo igualmente (puede ser temporal).")

        if not last_json_path or not os.path.exists(last_json_path):
            print("⚠️  No se encontró el JSON esperado de consulta. Ruta:", last_json_path)
            if args.once:
                if last_json_path:
                    print("🗂️  Último JSON esperado:", last_json_path)
                sys.exit(3)
            time.sleep(max(1, args.interval))
            continue

        cons_data = load_json(last_json_path)
        d_fec, d_cod_lot, d_msg_lot, docs = summarize_consulta_lote(cons_data)

        print("📄 consulta JSON:", last_json_path)
        print("--- LOTE ---")
        print("dFecProc   :", d_fec)
        print("dCodResLot :", d_cod_lot)
        print("dMsgResLot :", d_msg_lot)

        print(f"--- DOCUMENTOS --- {len(docs)}")
        for i, doc in enumerate(docs, 1):
            id_or_cdc = doc.get("id") or doc.get("cdc")
            print(f"\nDE #{i}")
            print("id/cdc  :", id_or_cdc)
            print("dEstRes :", doc.get("dEstRes"))
            print("dCodRes :", doc.get("dCodRes"))
            print("dMsgRes :", doc.get("dMsgRes"))

        if looks_concluded(d_cod_lot, d_msg_lot):
            print("\n✅ Lote concluido (según dCodResLot/dMsgResLot).")
            if last_json_path:
                print("🗂️  Último JSON consulta:", last_json_path)
            sys.exit(0)

        if args.once:
            if last_json_path:
                print("🗂️  Último JSON consulta:", last_json_path)
            sys.exit(0)

        elapsed = time.time() - start
        if elapsed >= args.timeout:
            print(f"\n⏱️  Timeout alcanzado ({args.timeout}s). Último dProtConsLote={prot}")
            if last_json_path:
                print("🗂️  Último JSON consulta:", last_json_path)
            sys.exit(4)

        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()

