#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Consulta estado de Lote en SIFEN (async) a partir de dProtConsLote.

Uso:
  python -m tools.consulta_lote_de --env test --prot 47353168697315928
Requiere:
  export SIFEN_CERT_PATH="/ruta/al/cert.p12"
  export SIFEN_CERT_PASSWORD="TU_PASSWORD" (o se pedirá interactivamente)
"""

from __future__ import annotations

# SOAP 1.2 action para Consulta Lote (confirmado desde artifacts)
SIFEN_CONS_LOTE_ACTION = "siConsLoteDE"
import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from urllib.parse import urljoin, urlparse

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Helper: asegurar bytes (evita write_bytes(_ensure_bytes(None)))
def _ensure_bytes(x):
    if x is None:
        return b""
    if isinstance(x, (bytes, bytearray)):
        return bytes(x)
    if isinstance(x, str):
        return x.encode("utf-8", "ignore")
    return str(x).encode("utf-8", "ignore")


# dId requerido por SIFEN (15 dígitos tipo YYYYMMDDHHMMSSmmm)
def _make_did() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S%f')[:15]

try:
    import lxml.etree as etree  # noqa: F401
except ImportError:
    print("❌ Error: lxml no está instalado", file=sys.stderr)
    print("   Instale con: pip install lxml", file=sys.stderr)
    sys.exit(1)

try:
    from zeep import Client, Settings
    from zeep.transports import Transport
    from zeep.exceptions import Fault, TransportError
    from zeep.helpers import serialize_object
    from zeep.plugins import HistoryPlugin
    from zeep.wsdl.bindings.soap import Soap12Binding, Soap11Binding
    from zeep.cache import InMemoryCache
    import logging
    ZEEP_AVAILABLE = True
except ImportError:
    ZEEP_AVAILABLE = False
    print("❌ Error: zeep no está instalado", file=sys.stderr)
    print("   Instale con: pip install zeep", file=sys.stderr)
    sys.exit(1)

try:
    from app.sifen_client.config import (
        get_sifen_config,
        get_mtls_config,
    )
    from app.sifen_client.exceptions import SifenClientError
    from app.sifen_client.pkcs12_utils import p12_to_temp_pem_files, PKCS12Error
except ImportError as e:
    print(f"❌ Error: No se pudo importar módulos SIFEN: {e}", file=sys.stderr)
    print("   Asegúrate de que las dependencias estén instaladas:", file=sys.stderr)
    print("   Instale con: pip install -r requirements.txt", file=sys.stderr)
    print("   pip install zeep lxml cryptography requests", file=sys.stderr)
    sys.exit(1)

from requests import Session
from requests.exceptions import ConnectionError, HTTPError
from requests.adapters import HTTPAdapter
try:
    from urllib3.util.retry import Retry
    URLLIB3_RETRY_AVAILABLE = True
except ImportError:
    URLLIB3_RETRY_AVAILABLE = False


def resolve_p12_password(args: argparse.Namespace) -> str:
    """
    Resuelve la contraseña P12 desde múltiples fuentes en orden de prioridad.
    
    Orden de búsqueda:
    1. Argumento CLI --p12-password (si está presente)
    2. Variable de entorno SIFEN_CERT_PASSWORD
    3. Prompt interactivo (solo si no hay nada)
    """
    # 1. Argumento CLI
    if hasattr(args, 'p12_password') and args.p12_password:
        return args.p12_password
    
    # 2. Variable de entorno
    env_password = os.getenv('SIFEN_CERT_PASSWORD')
    if env_password:
        return env_password
    
    # 3. Prompt interactivo
    try:
        return getpass.getpass("Contraseña del certificado P12: ")
    except (KeyboardInterrupt, EOFError):
        print("\n❌ Error: Se requiere contraseña del certificado", file=sys.stderr)
        sys.exit(1)


def _die(msg: str, rc: int = 1) -> None:
    """Imprime error y sale."""
    print(f"❌ Error: {msg}", file=sys.stderr)
    sys.exit(rc)


def _artifact_bytes_from(obj: Any) -> Tuple[bytes, str]:
    """
    Convierte un objeto (bytes, str, lxml element) a bytes para guardar en artifact.
    Retorna (bytes, extension) donde extension es ".xml" o ".txt".
    """
    if isinstance(obj, bytes):
        return obj, ".xml"
    if isinstance(obj, str):
        # Intentar parsear como XML para validar
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(obj)
            return obj.encode("utf-8"), ".xml"
        except ET.ParseError:
            # No es XML válido, guardar como texto
            return repr(obj).encode("utf-8"), ".txt"
    # Objeto XML (lxml)
    if hasattr(obj, 'tag'):
        try:
            xml_bytes = etree.tostring(obj, encoding="utf-8", pretty_print=True)
            return xml_bytes, ".xml"
        except Exception:
            # Fallback a repr
            return repr(obj).encode("utf-8"), ".txt"
    # Cualquier otro objeto
    return repr(obj).encode("utf-8"), ".txt"


def cleanup_pem_files(*paths: Optional[str]) -> None:
    """Elimina archivos PEM temporales si existen."""
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.unlink(p)
            except Exception:
                pass


def _resolve_mtls(cert_path: Optional[str] = None, key_or_password: Optional[str] = None, is_pem_mode: Optional[bool] = None):
    """Centraliza resolución de certificados para PEM o P12.

    Si se pasan valores explícitos (como resultado de get_mtls_config) los usa,
    en caso contrario invoca get_mtls_config() internamente.
    Devuelve tuple (cert_tuple, temp_files, resolved_mode) donde:
      - cert_tuple: (cert, key) listo para session.cert
      - temp_files: (cert, key) temporales si se generaron (para cleanup)
      - resolved_mode: 'PEM' o 'P12'
    """

    if cert_path is None or key_or_password is None or is_pem_mode is None:
        cert_path, key_or_password, is_pem_mode = get_mtls_config()

    temp_files: Optional[Tuple[str, str]] = None

    if is_pem_mode:
        cert_tuple = (cert_path, key_or_password)
        return cert_tuple, temp_files, "PEM"

    cert_pem_path, key_pem_path = p12_to_temp_pem_files(cert_path, str(key_or_password))
    temp_files = (cert_pem_path, key_pem_path)
    return (cert_pem_path, key_pem_path), temp_files, "P12"


def create_zeep_transport(cert_path: str, cert_password: Optional[str], *, is_pem_mode: bool = False) -> Transport:
    """
    Crea un Transport de zeep con mTLS configurado.
    
    Args:
        cert_path: Ruta al certificado P12
        cert_password: Contraseña del certificado
        
    Returns:
        Transport configurado con mTLS
    """
    session = Session()
    
    try:
        cert_tuple, temp_files, mode = _resolve_mtls(
            cert_path=cert_path,
            key_or_password=cert_password,
            is_pem_mode=is_pem_mode,
        )
        if temp_files:
            cert_pem_path, key_pem_path = temp_files
            import os
            print(
                f"[SIFEN DEBUG] create_zeep_transport: cert_pem={os.path.basename(cert_pem_path)} exists={os.path.exists(cert_pem_path)}"
            )
            print(
                f"[SIFEN DEBUG] create_zeep_transport: key_pem={os.path.basename(key_pem_path)} exists={os.path.exists(key_pem_path)}"
            )
        session.cert = cert_tuple
    except PKCS12Error as e:
        raise SifenClientError(f"Error al convertir certificado P12 a PEM: {e}") from e
    
    session.verify = True
    
    # Configurar HTTPAdapter con retries para manejar ConnectionResetError
    if URLLIB3_RETRY_AVAILABLE:
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            backoff_factor=0.5,
            status_forcelist=[502, 503, 504],
            allowed_methods=frozenset(["GET", "POST"]),
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    else:
        adapter = HTTPAdapter(pool_connections=10, pool_maxsize=10)
    
    session.mount("https://", adapter)
    # NO setear "Connection: close" - dejar Keep-Alive para reutilizar conexiones y cookies
    
    timeout = (10, 30)
    
    # Debug: verificar configuración de la sesión
    print(f"[SIFEN NET] transport session cookies enabled; cert={'YES' if session.cert else 'NO'} verify={session.verify}")
    
    # Crear cache para WSDL/XSD
    cache = InMemoryCache()
    
    return Transport(
        session=session,
        timeout=timeout,  # connect 10s, read 30s
        operation_timeout=30,
        cache=cache,
    )


def call_consulta_lote_http(
    prot: str,
    env: str,
    artifacts_dir: Path,
    cert_tuple: Tuple[str, str],
    timeout: Tuple[int, int] = (10, 60),
    did: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Función principal HTTP manual para consultar lote (golden path).
    
    Args:
        prot: dProtConsLote (número de lote)
        env: Ambiente ('test' o 'prod')
        artifacts_dir: Directorio donde guardar artifacts
        cert_tuple: Tuple de certificados (cert_path, key_path)
        timeout: Timeout en segundos (connect, read)
        did: dId opcional (se genera si no se provee)
        
    Returns:
        Dict con resultado de la consulta
    """
    import xml.etree.ElementTree as ET
    
    # Validar prot
    prot = str(prot or "").strip()
    if not prot.isdigit():
        raise ValueError(f"dProtConsLote debe ser solo dígitos. Valor recibido: '{prot}'")
    
    # Generar did si no se provee
    if not did:
        did = _make_did()
    
    # Endpoint correcto (con .wsdl según funciona)
    if env == "prod":
        endpoint_url = "https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl"
    else:
        endpoint_url = "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl"
    
    # Namespace SIFEN
    sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"
    
    # Construir SOAP 1.2 envelope
    soap_body = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <rEnviConsLoteDe xmlns="{sifen_ns}">
            <dId>{did}</dId>
            <dProtConsLote>{prot}</dProtConsLote>
        </rEnviConsLoteDe>
    </soap12:Body>
</soap12:Envelope>'''
    
    # Headers SOAP 1.2
    headers = {
        "Content-Type": f'application/soap+xml; charset=utf-8; action="{SIFEN_CONS_LOTE_ACTION}"',
        "Accept": "application/soap+xml, text/xml, */*",
        "Connection": "close",
    }
    
    # Timestamp para artifacts
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Paths para artifacts
    req_path = artifacts_dir / f"consulta_lote_sent_{ts}.xml"
    resp_path = artifacts_dir / f"consulta_lote_response_{ts}.xml"
    meta_path = artifacts_dir / f"consulta_lote_headers_sent_{ts}.json"
    raw_path = artifacts_dir / f"consulta_lote_headers_sent_{ts}.raw_response.xml"
    
    # Guardar request SIEMPRE
    try:
        req_path.write_bytes(_ensure_bytes(soap_body))
        meta_path.write_text(
            json.dumps(
                {
                    "timestamp": datetime.now().isoformat(),
                    "env": env,
                    "endpoint": endpoint_url,
                    "timeout": timeout,
                    "sent_headers": headers,
                    "dId": did,
                    "dProtConsLote": prot,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"⚠️  Error guardando artifacts de request: {e}")
    
    # Crear sesión y hacer request
    session = Session()
    session.cert = cert_tuple
    session.verify = True
    
    result = {
        "ok": False,
        "dProtConsLote": prot,
        "http_status": None,
        "endpoint": endpoint_url,
        "sent_headers": headers,
        "raw_xml": None,
        "error_type": None,
        "error_message": None,
    }
    
    try:
        print(f"[SIFEN HTTP] Enviando consulta a {endpoint_url}")
        print(f"[SIFEN HTTP] dProtConsLote={prot} dId={did}")
        
        response = session.post(
            endpoint_url,
            data=soap_body.encode('utf-8'),
            headers=headers,
            timeout=timeout
        )
        
        # Guardar respuesta cruda SIEMPRE
        response_bytes = response.content or b""
        try:
            resp_path.write_bytes(response_bytes)
            raw_path.write_bytes(response_bytes)
        except Exception as e:
            print(f"⚠️  Error guardando response: {e}")
        
        # Actualizar metadata con headers de respuesta
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta.update({
                "http_status": response.status_code,
                "received_headers": dict(response.headers),
            })
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        
        # Procesar respuesta
        result["http_status"] = response.status_code
        
        if not response_bytes:
            raise RuntimeError("Respuesta vacía del servidor")
        
        # Parsear XML
        try:
            root = ET.fromstring(response_bytes)
            result["raw_xml"] = response_bytes.decode('utf-8', errors='ignore')
            
            # Extraer namespace dinámicamente
            # El response usa ns2 como prefijo para el namespace SIFEN
            ns = {}
            for key, value in root.attrib.items():
                if key.startswith('xmlns:'):
                    ns[key.split(':')[1]] = value
            
            # Parse robusto SIN prefijos (evita: prefix 'ns2' not found in prefix map)
            def _local(tag: str) -> str:
                return tag.split('}', 1)[-1] if '}' in tag else tag

            def _find_first_by_local(root_elem, local_name: str):
                for el in root_elem.iter():
                    if _local(el.tag) == local_name:
                        return el
                return None

            def _findall_by_local(root_elem, local_name: str):
                out = []
                for el in root_elem.iter():
                    if _local(el.tag) == local_name:
                        out.append(el)
                return out

            def _text_first(parent, local_name: str):
                el = _find_first_by_local(parent, local_name) if parent is not None else None
                txt = (el.text or '').strip() if el is not None else ''
                return txt or None

            # Buscar el Body SOAP por localname
            body = _find_first_by_local(root, 'Body')
            if body is None:
                raise RuntimeError('No se encontró SOAP Body')

            # Buscar rResEnviConsLoteDe (OK) o rRetEnviDe (error) por localname
            res_elem = _find_first_by_local(body, 'rResEnviConsLoteDe')
            response_type = 'consulta_lote' if res_elem is not None else None
            if res_elem is None:
                res_elem = _find_first_by_local(body, 'rRetEnviDe')
                response_type = 'ret_envi_de' if res_elem is not None else None

            if res_elem is None:
                raise RuntimeError('No se encontró rResEnviConsLoteDe ni rRetEnviDe en el SOAP Body')

            # Campos comunes
            d_fec_proc = _text_first(res_elem, 'dFecProc')
            result['dFecProc'] = d_fec_proc

            if response_type == 'consulta_lote':
                result['dCodResLot'] = _text_first(res_elem, 'dCodResLot')
                result['dMsgResLot'] = _text_first(res_elem, 'dMsgResLot')

                # gResProcLote (si existe)
                g_res_proc_lote = _find_first_by_local(res_elem, 'gResProcLote')
                if g_res_proc_lote is not None:
                    # documentos
                    documentos = []
                    for g_doc in _findall_by_local(g_res_proc_lote, 'gResProcDoc'):
                        doc_id = _text_first(g_doc, 'id')
                        doc_est = _text_first(g_doc, 'dEstRes')
                        if doc_id or doc_est:
                            documentos.append({'id': doc_id, 'estado': doc_est})
                    result['documentos'] = documentos

                    # estado/id del lote dentro de gResProcLote
                    lot_id = _text_first(g_res_proc_lote, 'id')
                    lot_est = _text_first(g_res_proc_lote, 'dEstRes')
                    if lot_id or lot_est:
                        result['lote_id'] = lot_id
                        result['dEstRes'] = lot_est

                    # gResProc interno (rechazo a nivel lote/doc)
                    g_inner = _find_first_by_local(g_res_proc_lote, 'gResProc')
                    if g_inner is not None:
                        result['dCodRes'] = _text_first(g_inner, 'dCodRes')
                        result['dMsgRes'] = _text_first(g_inner, 'dMsgRes')

            elif response_type == 'ret_envi_de':
                result['dEstRes'] = _text_first(res_elem, 'dEstRes')
                g_res_proc = _find_first_by_local(res_elem, 'gResProc')
                if g_res_proc is not None:
                    result['dCodRes'] = _text_first(g_res_proc, 'dCodRes')
                    result['dMsgRes'] = _text_first(g_res_proc, 'dMsgRes')

            result['ok'] = True
        except ET.ParseError as e:
            raise RuntimeError(f"XML mal formado: {e}")
        
    except Exception as e:
        result["error_type"] = type(e).__name__
        result["error_message"] = str(e)
        print(f"❌ Error en consulta HTTP: {e}")
    
    return result


def consulta_lote_cli(args: argparse.Namespace) -> int:
    """Subcomando CLI para consultar lote."""
    from app.sifen_client.config import get_sifen_config
    
    # Forzar ambiente desde args (anti-regresión 0160)
    force_env_from_args(args.env)
    
    env = args.env
    prot = args.prot
    out = args.out
    debug = args.debug
    artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else Path(__file__).parent.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Obtener configuración
    config = get_sifen_config(env=env)
    
    # Resolver certificado mTLS
    cert_path, cert_password, is_pem_mode = get_mtls_config()
    if not cert_path:
        cert_path = config.cert_path
    if not cert_password and not is_pem_mode:
        cert_password = config.cert_password
    
    cert_tuple, temp_files, mode = _resolve_mtls(cert_path, cert_password, is_pem_mode)
    
    # Llamar al método HTTP manual (golden path)
    result = call_consulta_lote_http(
        prot=prot,
        env=env,
        artifacts_dir=artifacts_dir,
        cert_tuple=cert_tuple,
        timeout=(10, 60)
    )
    
    # Guardar respuesta JSON
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if out:
        out_path = Path(out)
    else:
        out_path = artifacts_dir / f"consulta_lote_{timestamp}.json"
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n💾 Respuesta guardada en: {out_path}")
    
    # Cleanup
    if mode == "P12" and temp_files:
        cleanup_pem_files(temp_files[0], temp_files[1])
    
    return 0


def force_env_from_args(env: str) -> None:
    """Fuerza variables de entorno según args.env (anti-regresión 0160)."""
    if env not in ("test", "prod"):
        raise ValueError(f"Ambiente inválido: {env}. Debe ser 'test' o 'prod'.")
    
    # Forzar variables de entorno
    os.environ["SIFEN_ENV"] = env
    
    # Cargar config del ambiente específico
    config_file = Path(__file__).parent.parent / "config" / f"sifen_{env}.env"
    if config_file.exists():
        with open(config_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    print(f"📍 Ambiente forzado a: {env}")
    print(f"   Config cargada de: {config_file}")


def main() -> int:
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Consultar estado de lote en SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s --env test --prot 47353168697315928
  %(prog)s --env prod --prot 12345678901234567 --out response.json
  %(prog)s --env test --prot 47353168697315928 --debug --artifacts-dir /tmp/artifacts
        """
    )
    
    parser.add_argument(
        "--env",
        required=True,
        choices=["test", "prod"],
        help="Ambiente de SIFEN (test o prod)"
    )
    
    parser.add_argument(
        "--prot",
        required=True,
        help="Número de protocolo del lote (dProtConsLote)"
    )
    
    parser.add_argument(
        "--out",
        default=None,
        help="Archivo JSON de salida (default: artifacts/consulta_lote_YYYYMMDD_HHMMSS.json)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Activar modo debug (verbose)"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        default=None,
        help="Directorio para guardar artifacts (default: ./artifacts)"
    )
    
    parser.add_argument(
        "--p12-password",
        default=None,
        help="Contraseña del certificado P12 (alternativa a SIFEN_CERT_PASSWORD)"
    )
    
    # Legacy arguments for compatibility (ignored)
    parser.add_argument(
        "--wsdl-file",
        default=None,
        help=argparse.SUPPRESS  # Oculto, solo para compatibilidad
    )
    
    parser.add_argument(
        "--wsdl-cache-dir",
        default=None,
        help=argparse.SUPPRESS  # Oculto, solo para compatibilidad
    )
    
    args = parser.parse_args()
    
    # Configurar logging si debug
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    
    # Ejecutar subcomando
    return consulta_lote_cli(args)


if __name__ == "__main__":
    sys.exit(main())
