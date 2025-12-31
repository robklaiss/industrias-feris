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
        timeout: Timeout en segundos
        
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
        # Construir XML rEnviConsLoteDe
        SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
        r_envi_cons = etree.Element(
            etree.QName(SIFEN_NS, "rEnviConsLoteDe"),
            nsmap={None: SIFEN_NS}
        )
        d_id = etree.SubElement(r_envi_cons, etree.QName(SIFEN_NS, "dId"))
        d_id.text = "1"
        d_prot_cons_lote = etree.SubElement(
            r_envi_cons, etree.QName(SIFEN_NS, "dProtConsLote")
        )
        d_prot_cons_lote.text = str(prot)
        
        xml_renvi_cons = etree.tostring(
            r_envi_cons, xml_declaration=True, encoding="UTF-8"
        ).decode("utf-8")
        
        # Usar método consulta_lote de SoapClient (usa WSDL correcto y guarda debug automáticamente)
        response_dict = client.consulta_lote(xml_renvi_cons, timeout=timeout)
        
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
    print(f"🔎 dProtConsLote: {prot}")
    if args.debug:
        print(f"🔐 Cert: {p12_path}")
    
    # Consultar lote usando SoapClient (sin WSDL)
    try:
        with SoapClient(config=config) as client:
            try:
                # Usar método consulta_lote_raw (no depende de WSDL)
                response_dict = client.consulta_lote_raw(dprot_cons_lote=prot, did=1)
                
                # Extraer campos principales
                result: Dict[str, Any] = {
                    "success": True,
                    "dProtConsLote": prot,
                    "http_status": response_dict.get("http_status", 0),
                    "response_xml": response_dict.get("raw_xml", ""),
                }
                
                # Mostrar HTTP status
                http_status = response_dict.get("http_status", 0)
                print(f"📡 HTTP Status: {http_status}")
                
                # Extraer dCodResLot y dMsgResLot si existen
                if "dCodResLot" in response_dict:
                    result["dCodResLot"] = response_dict["dCodResLot"]
                if "dMsgResLot" in response_dict:
                    result["dMsgResLot"] = response_dict["dMsgResLot"]
                
                # Determinar éxito basado en código
                cod_res_lot = result.get("dCodResLot", "")
                if cod_res_lot in ("0361", "0362"):
                    result["status"] = "ok"
                    print("✅ Consulta OK")
                elif cod_res_lot == "0364":
                    result["status"] = "requires_cdc"
                    print("⚠️  Lote requiere consulta por CDC")
                else:
                    result["status"] = "error"
                    print("❌ Error en consulta")
                
                if cod_res_lot:
                    print(f"   Código: {cod_res_lot}")
                if result.get("dMsgResLot"):
                    print(f"   Mensaje: {result['dMsgResLot']}")
                
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
