from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import subprocess, glob, json, os, time, re

app = FastAPI(title="SIFEN Web API", version="0.2")

# Configurar CORS para desarrollo
if os.getenv("TESAKA_DEV_MODE", "").lower() in ("1", "true", "yes"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:4200", "http://127.0.0.1:3000", "http://127.0.0.1:4200"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

class SmokeReq(BaseModel):
    env: str = "test"
    allow_placeholder: bool = True

class SendDeReq(BaseModel):
    env: str = "test"
    # por ahora stub: en el próximo paso este campo será el JSON real Tesaka
    payload: dict | None = None

@app.get("/health")
def health():
    return {"ok": True}

def _run_smoke(env: str, allow_placeholder: bool):
    cmd = [os.path.join(".venv","bin","python"), "tools/test_smoke_recibe_lote.py", "--env", env]
    if allow_placeholder:
        cmd.append("--allow-placeholder")

    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    dur_ms = int((time.time() - t0) * 1000)

    pattern = f"artifacts/smoke_test_metadata_{env}_*.json"
    metas = sorted(glob.glob(pattern), key=lambda x: Path(x).stat().st_mtime, reverse=True)
    meta_path = metas[0] if metas else None
    meta = {}
    if meta_path:
        try:
            meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
        except Exception:
            meta = {"_meta_read_error": True, "meta_path": meta_path}

    out_tail = (p.stdout or "").splitlines()[-120:]
    err_tail = (p.stderr or "").splitlines()[-120:]
    # dId: preferimos meta.json; si falta, intentamos extraer de stdout/stderr
    did = meta.get("dId") if isinstance(meta, dict) else None
    if not did:
        joined = "\n".join(out_tail + err_tail)
        m = re.search(r"\bdId:\s*(?:dId:\s*)?(\d{8,})\b", joined)
        if m:
            did = m.group(1)

    return {
        "exit_code": p.returncode,
        "duration_ms": dur_ms,
        "meta_path": meta_path,
        "meta": {
            "response_dCodRes": meta.get("response_dCodRes"),
            "response_dMsgRes": meta.get("response_dMsgRes"),
            "connectivity_ok": meta.get("connectivity_ok"),
            "biz_blocker": meta.get("biz_blocker"),
            "post_url": meta.get("post_url"),
            "http_status": meta.get("http_status"),
            "zip_sha256": meta.get("zip_sha256"),
            "request_sha256": meta.get("request_sha256"),
            "response_sha256": meta.get("response_sha256"),
            "dId": did,
        },
        "stdout_tail": out_tail,
        "stderr_tail": err_tail,
    }

@app.post("/smoke")
def smoke(req: SmokeReq):
    return _run_smoke(req.env, req.allow_placeholder)

@app.post("/send-de")
def send_de(req: SendDeReq):
    """
    Endpoint para enviar DE a SIFEN.
    Acepta: {"env": "test|prod", "payload": {...}}
    Devuelve: JSON con meta información
    """
    # STUB intencional:
    # hoy confirmamos que el canal técnico (mTLS+SOAP+firma) funciona.
    # próximo paso: reemplazar este stub por "payload -> DE real -> recepcion_lote".
    result = _run_smoke(req.env, allow_placeholder=True)
    
    # Asegurar que siempre devolvemos JSON con la estructura esperada
    response = {
        "meta": {
            "dId": result["meta"].get("dId"),
            "response_dCodRes": result["meta"].get("response_dCodRes"),
            "response_dMsgRes": result["meta"].get("response_dMsgRes"),
            "connectivity_ok": result["meta"].get("connectivity_ok"),
            "biz_blocker": result["meta"].get("biz_blocker"),
            "meta_path": result.get("meta_path"),
        },
        "exit_code": result.get("exit_code"),
        "duration_ms": result.get("duration_ms"),
        "note": "STUB: /send-de todavía no genera DE real desde payload. Solo prueba canal técnico.",
        "received_payload_keys": sorted(list((req.payload or {}).keys()))[:50],
        "stdout_tail": result.get("stdout_tail", []),
        "stderr_tail": result.get("stderr_tail", []),
    }
    
    return response
