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

import argparse
import getpass
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import lxml.etree as etree  # noqa: F401
except ImportError:
    print("❌ Error: lxml no está instalado", file=sys.stderr)
    print("   Instale con: pip install lxml", file=sys.stderr)
    sys.exit(1)

try:
    from app.sifen_client.config import get_sifen_config
    from app.sifen_client.soap_client import SoapClient
    from app.sifen_client.exceptions import SifenClientError
except ImportError as e:
    print(f"❌ Error: No se pudo importar módulos SIFEN: {e}", file=sys.stderr)
    print("   Asegúrate de que las dependencias estén instaladas:", file=sys.stderr)
    print("   pip install zeep lxml cryptography requests", file=sys.stderr)
    sys.exit(1)


def _die(msg: str, code: int = 2) -> None:
    """Imprime mensaje de error y termina el programa."""
    print(f"❌ {msg}", file=sys.stderr)
    raise SystemExit(code)


def call_consulta_lote_raw(
    session: Any, env: str, prot: str, timeout: int = 60
) -> str:
    """
    Consulta el estado de un lote usando SoapClient con WSDL correcto.
    
    Esta función es usada por lote_checker.py y otros módulos internos.
    
    Args:
        session: requests.Session con mTLS configurado (puede ser None, se creará uno nuevo)
        env: Ambiente ('test' o 'prod')
        prot: dProtConsLote (número de lote)
        timeout: Timeout en segundos (no usado, se mantiene para compatibilidad)
        
    Returns:
        XML de respuesta como string
    """
    from app.sifen_client.config import get_sifen_config
    
    # Obtener configuración
    config = get_sifen_config(env=env)
    
    # Crear cliente SOAP (usará el WSDL correcto desde config)
    # Nota: SoapClient crea su propia sesión con mTLS, no acepta requests_session
    from app.sifen_client.soap_client import SoapClient
    client = SoapClient(config=config)
    
    try:
        # Usar método consulta_lote_de de SoapClient (usa WSDL correcto y guarda debug automáticamente)
        response_dict = client.consulta_lote_de(dprot_cons_lote=prot, did=1)
        
        # Retornar XML de respuesta
        return response_dict.get("response_xml", "")
    finally:
        client.close()


def main() -> int:
    """Función principal del script."""
    parser = argparse.ArgumentParser(
        description="Consultar estado de lote SIFEN (dProtConsLote).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default="test",
        help="Ambiente SIFEN (default: test)",
    )
    parser.add_argument(
        "--prot",
        required=True,
        help="dProtConsLote devuelto por siRecepLoteDE",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Guardar respuesta en JSON (ruta). Si no se especifica, se guarda en artifacts/",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Logs extra de debug",
    )
    parser.add_argument(
        "--wsdl",
        default=None,
        help="Override WSDL (opcional). Ej: https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl",
    )
    args = parser.parse_args()
    
    # Validar prot
    prot = str(args.prot).strip()
    if not prot or not prot.isdigit():
        _die("dProtConsLote debe ser un número (solo dígitos).")
    
    # Obtener certificado desde env
    p12_path = os.getenv("SIFEN_CERT_PATH", "").strip()
    if not p12_path:
        _die("Falta SIFEN_CERT_PATH en el entorno.")
    
    p12_path_obj = Path(p12_path)
    if not p12_path_obj.exists():
        _die(f"Certificado no encontrado: {p12_path}")
    
    # Obtener password (desde env o pedir interactivamente)
    p12_password = os.getenv("SIFEN_CERT_PASSWORD", "").strip()
    if not p12_password:
        try:
            p12_password = getpass.getpass("🔐 Contraseña del certificado P12: ")
            if not p12_password:
                _die("Contraseña requerida.")
        except (EOFError, KeyboardInterrupt):
            print("\n❌ Operación cancelada.", file=sys.stderr)
            sys.exit(1)
    
    # Configurar WSDL override si se proporciona --wsdl
    if args.wsdl:
        wsdl_url = args.wsdl.strip()
        os.environ["SIFEN_WSDL_CONSULTA_LOTE"] = wsdl_url
    elif os.getenv("SIFEN_WSDL_CONSULTA_LOTE"):
        wsdl_url = os.getenv("SIFEN_WSDL_CONSULTA_LOTE").strip()
    else:
        # Usar WSDL por defecto según ambiente
        from app.sifen_client.config import SifenConfig
        config_temp = SifenConfig(env=args.env)
        wsdl_url = config_temp.get_soap_service_url("consulta_lote")
    
    # Configurar cliente SIFEN
    try:
        config = get_sifen_config(env=args.env)
        # Asegurar que cert_path y cert_password estén configurados
        from app.sifen_client.config import get_cert_path_and_password
        env_cert_path, env_cert_password = get_cert_path_and_password()
        config.cert_path = config.cert_path or env_cert_path or p12_path
        config.cert_password = config.cert_password or env_cert_password or p12_password
    except Exception as e:
        _die(f"Error al configurar cliente SIFEN: {e}")
    
    # Mostrar información
    print(f"🔧 Ambiente: {args.env}")
    print(f"🌐 WSDL (consulta_lote): {wsdl_url}")
    print(f"🔎 dProtConsLote: {prot}")
    if args.debug:
        print(f"🔐 Cert: {p12_path}")
    
    # Consultar lote usando SoapClient (WSDL-driven)
    try:
        with SoapClient(config=config) as client:
            try:
                # Usar método consulta_lote_de (WSDL-driven)
                response_dict = client.consulta_lote_de(dprot_cons_lote=prot, did=1)
                
                # Extraer campos principales
                result: Dict[str, Any] = {
                    "success": response_dict.get("ok", False),
                    "dProtConsLote": prot,
                    "response_xml": response_dict.get("response_xml", ""),
                }
                
                # Extraer código y mensaje
                codigo_respuesta = response_dict.get("codigo_respuesta")
                mensaje = response_dict.get("mensaje")
                
                if codigo_respuesta:
                    result["dCodResLot"] = codigo_respuesta
                if mensaje:
                    result["dMsgResLot"] = mensaje
                
                # Extraer parsed_fields para información adicional
                parsed_fields = response_dict.get("parsed_fields", {})
                
                # Mostrar resultado
                if response_dict.get("ok"):
                    print("✅ Consulta OK")
                    result["status"] = "ok"
                else:
                    if codigo_respuesta == "0364":
                        result["status"] = "requires_cdc"
                        print("⚠️  Lote requiere consulta por CDC")
                    else:
                        result["status"] = "error"
                        print("❌ Error en consulta")
                
                if codigo_respuesta:
                    print(f"   Código: {codigo_respuesta}")
                if mensaje:
                    print(f"   Mensaje: {mensaje}")
                
                # Mostrar gResProcLote si está presente (resultados por DE)
                g_res_proc_lote = parsed_fields.get("gResProcLote")
                if g_res_proc_lote and isinstance(g_res_proc_lote, list):
                    print(f"\n   Documentos en lote: {len(g_res_proc_lote)}")
                    for idx, de_res in enumerate(g_res_proc_lote, 1):
                        de_id = de_res.get("dId", "N/A")
                        de_est_res = de_res.get("dEstRes", "N/A")
                        de_cod_res = de_res.get("dCodRes", "N/A")
                        de_msg_res = de_res.get("dMsgRes", "N/A")
                        print(f"   DE #{idx}: id={de_id}, estado={de_est_res}, código={de_cod_res}")
                        if de_msg_res and de_msg_res != "N/A":
                            print(f"      mensaje: {de_msg_res}")
                    result["gResProcLote"] = g_res_proc_lote
                
            except Exception as e:
                _die(f"Error al consultar lote: {e}")
    
    except SifenClientError as e:
        _die(f"Error del cliente SIFEN: {e}")
    except Exception as e:
        _die(f"Error inesperado: {e}")
    
    # Guardar respuesta
    if args.out:
        out_path = Path(args.out)
    else:
        # Guardar en artifacts/ con timestamp
        artifacts_dir = Path(__file__).parent.parent / "artifacts"
        artifacts_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = artifacts_dir / f"consulta_lote_{timestamp}.json"
    
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"\n💾 Respuesta guardada en: {out_path}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# USAGE
# =====
# # Configurar certificado
# export SIFEN_CERT_PATH="/ruta/al/certificado.p12"
#
# # Opción 1: Password desde env var
# export SIFEN_CERT_PASSWORD="tu_password"
# python -m tools.consulta_lote_de --env test --prot 47353168697315928
#
# # Opción 2: Password interactivo (más seguro)
# python -m tools.consulta_lote_de --env test --prot 47353168697315928
# # (se pedirá la contraseña sin mostrarla)
#
# # Con debug y output personalizado
# python -m tools.consulta_lote_de --env test --prot 47353168697315928 --debug --out /tmp/respuesta.json
