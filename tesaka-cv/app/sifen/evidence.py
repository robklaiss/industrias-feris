"""
Módulo para guardar evidencia de requests/responses SIFEN sin secretos

Guarda XMLs y metadata para debugging y certificación, sin incluir:
- Passwords
- PEMs completos
- Datos sensibles
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from .config import get_sifen_config


def write_evidence(
    kind: str,
    request_xml: Optional[str] = None,
    response_xml: Optional[str] = None,
    meta_dict: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """
    Guarda evidencia de un intercambio SIFEN.
    
    Args:
        kind: Tipo de operación ('consulta_ruc', 'send_de', etc.)
        request_xml: XML del request (opcional)
        response_xml: XML del response (opcional)
        meta_dict: Metadata adicional (http_code, dCodRes, dMsgRes, etc.)
    
    Returns:
        Dict con paths de archivos guardados:
        - request_path: Path al archivo request (si se guardó)
        - response_path: Path al archivo response (si se guardó)
        - meta_path: Path al archivo metadata
    """
    # Obtener ambiente desde config
    try:
        config = get_sifen_config()
        env = config.env
    except Exception:
        env = os.getenv("SIFEN_ENV", "test")
    
    # Determinar directorio base de evidencia
    # Intentar desde tesaka-cv/evidence, si no existe usar raíz del repo
    script_dir = Path(__file__).parent.parent.parent
    evidence_base = script_dir / "evidence"
    
    # Crear estructura: evidence/sifen_{env}/YYYY-MM-DD/
    today = datetime.now().strftime("%Y-%m-%d")
    evidence_dir = evidence_base / f"sifen_{env}" / today
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Timestamp para nombres únicos
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # milisegundos
    
    saved_paths = {}
    
    # Guardar request XML
    if request_xml:
        request_path = evidence_dir / f"request_{kind}_{timestamp}.xml"
        with open(request_path, "w", encoding="utf-8") as f:
            f.write(request_xml)
        saved_paths["request_path"] = str(request_path)
    
    # Guardar response XML
    if response_xml:
        response_path = evidence_dir / f"response_{kind}_{timestamp}.xml"
        with open(response_path, "w", encoding="utf-8") as f:
            f.write(response_xml)
        saved_paths["response_path"] = str(response_path)
    
    # Guardar metadata (sin secretos)
    meta_clean = {}
    if meta_dict:
        # Copiar solo campos seguros
        safe_fields = [
            "http_code", "dCodRes", "dMsgRes", "dCDC", "endpoint",
            "normalized_ruc", "sifen_env", "ok", "timestamp"
        ]
        for field in safe_fields:
            if field in meta_dict:
                meta_clean[field] = meta_dict[field]
        
        # Agregar timestamp si no está
        if "timestamp" not in meta_clean:
            meta_clean["timestamp"] = datetime.now().isoformat()
    
    meta_path = evidence_dir / f"meta_{kind}_{timestamp}.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta_clean, f, indent=2, ensure_ascii=False)
    saved_paths["meta_path"] = str(meta_path)
    
    return saved_paths
