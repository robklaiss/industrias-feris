#!/usr/bin/env python3
"""
CLI tool para probar consulta RUC (siConsRUC) de forma aislada.

Uso:
    python -m tools.consulta_ruc --env test --ruc 4554737 --dump-http
    python -m tools.consulta_ruc --env prod --ruc 80012345 --dump-http --artifacts-dir ./my_artifacts

Propósito:
    Permite probar la operación siConsRUC sin necesidad de enviar un lote completo.
    Útil para diagnosticar problemas de conectividad, endpoints, o validar habilitación FE de un RUC.

Salida:
    - dCodRes / dMsgRes de la respuesta SIFEN
    - HTTP status code
    - Información de habilitación FE (dRUCFactElec)
    - Si --dump-http: guarda artifacts en artifacts/ o --artifacts-dir
"""
import argparse
import sys
import os
import datetime as _dt
from pathlib import Path
from typing import Optional, Tuple
import json
import difflib

# Agregar tesaka-cv al path para imports
TESAKA_CV_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TESAKA_CV_DIR))

from zeep import Client, Settings  # type: ignore
from zeep.transports import Transport  # type: ignore
from zeep.plugins import HistoryPlugin  # type: ignore

from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import get_sifen_config, get_artifacts_dir
from app.sifen_client.ruc_format import normalize_sifen_truc
from app.sifen_client.exceptions import SifenClientError
import lxml.etree as etree


def _latest_attempt_json(artifacts_dir: Path) -> Optional[Path]:
    attempts = sorted(
        artifacts_dir.glob("consulta_ruc_attempt_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return attempts[0] if attempts else None


def _save_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _resolve_wsdl_url(wsdl_url: str) -> str:
    if "?" in wsdl_url:
        return wsdl_url
    return f"{wsdl_url}?wsdl" if not wsdl_url.endswith("?wsdl") else wsdl_url


def _local_wsdl_fallback() -> Optional[Path]:
    candidates = [
        TESAKA_CV_DIR.parent / "rshk-jsifenlib" / "docs" / "set" / "test" / "v150" / "wsdl" / "consultas" / "consulta-ruc.wsdl",
        TESAKA_CV_DIR.parent / "tmp" / "roshka-sifen" / "docs" / "set" / "test" / "v150" / "wsdl" / "consultas" / "consulta-ruc.wsdl",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def _wsdl_introspect(wsdl_url: str, transport: Transport, out_path: Path) -> Tuple[str, str]:
    history = HistoryPlugin()
    settings = Settings(strict=False, xml_huge_tree=True)
    local_wsdl = _local_wsdl_fallback()
    try:
        client = Client(wsdl=wsdl_url, transport=transport, settings=settings, plugins=[history])
    except Exception:
        alt = _resolve_wsdl_url(wsdl_url)
        try:
            client = Client(wsdl=alt, transport=transport, settings=settings, plugins=[history])
        except Exception:
            if local_wsdl:
                client = Client(wsdl=str(local_wsdl), transport=transport, settings=settings, plugins=[history])
            else:
                raise

    lines = [f"WSDL: {wsdl_url}"]
    for svc_name, svc in client.wsdl.services.items():
        lines.append(f"Service: {svc_name}")
        for port_name, port in svc.ports.items():
            binding = port.binding
            soap_ver = getattr(binding, "soap_version", getattr(binding, "soapversion", "unknown"))
            lines.append(f"  Port: {port_name} (binding: {binding.__class__.__name__}, soap={soap_ver}, location={port.address})")
            for op_name, op in binding._operations.items():
                lines.append(f"    Operation: {op_name}")
                lines.append(f"      input: {op.input.signature()}")
                lines.append(f"      output: {op.output.signature()}")

    text = "\n".join(lines)
    out_path.write_text(text, encoding="utf-8")
    return next(iter(client.wsdl.services.keys())), next(iter(client.wsdl.services.values())).ports.keys().__iter__().__next__()


def _build_canonical_request(wsdl_url: str, transport: Transport, ruc: str, did: str, out_path: Path) -> None:
    history = HistoryPlugin()
    settings = Settings(strict=False, xml_huge_tree=True)
    local_wsdl = _local_wsdl_fallback()
    try:
        client = Client(wsdl=wsdl_url, transport=transport, settings=settings, plugins=[history])
    except Exception:
        alt = _resolve_wsdl_url(wsdl_url)
        try:
            client = Client(wsdl=alt, transport=transport, settings=settings, plugins=[history])
        except Exception:
            if local_wsdl:
                client = Client(wsdl=str(local_wsdl), transport=transport, settings=settings, plugins=[history])
            else:
                raise
    # Asumimos operación rEnviConsRUC; WSDL la expone así
    message = client.create_message(client.service, "rEnviConsRUC", dId=did, dRUCCons=ruc)
    xml_str = _element_to_string(message)
    out_path.write_text(xml_str, encoding="utf-8")


def _element_to_string(elem) -> str:
    from lxml import etree

    return etree.tostring(elem, encoding="unicode", pretty_print=True)


def _save_diff(a_text: str, b_text: str, out_path: Path, a_label: str, b_label: str) -> None:
    diff = difflib.unified_diff(
        a_text.splitlines(),
        b_text.splitlines(),
        fromfile=a_label,
        tofile=b_label,
        lineterm="",
    )
    out_path.write_text("\n".join(diff), encoding="utf-8")


def _parse_response_fields(xml_text: str) -> Tuple[Optional[str], Optional[str], dict]:
    if not xml_text:
        return None, None, {}
    root = etree.fromstring(xml_text.encode("utf-8"))
    ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
    def find_text(xpath: str) -> Optional[str]:
        el = root.find(xpath, namespaces=ns)
        return el.text.strip() if el is not None and el.text else None
    cod = find_text(".//s:dCodRes")
    msg = find_text(".//s:dMsgRes")
    x_cont = root.find(".//s:xContRUC", namespaces=ns)
    info = {}
    if x_cont is not None:
        for field in ("dRUCCons", "dRazCons", "dCodEstCons", "dDesEstCons", "dRUCFactElec"):
            val = find_text(f".//s:{field}")
            if val is not None:
                info[field] = val
    return cod, msg, info


def _zeep_call(wsdl_url: str, transport: Transport, ruc: str, did: str, dump_http: bool, artifacts_dir: Path) -> dict:
    history = HistoryPlugin()
    settings = Settings(strict=False, xml_huge_tree=True)
    local_wsdl = _local_wsdl_fallback()
    try:
        client = Client(wsdl=wsdl_url, transport=transport, settings=settings, plugins=[history])
    except Exception:
        alt = _resolve_wsdl_url(wsdl_url)
        try:
            client = Client(wsdl=alt, transport=transport, settings=settings, plugins=[history])
        except Exception:
            if local_wsdl:
                client = Client(wsdl=str(local_wsdl), transport=transport, settings=settings, plugins=[history])
            else:
                raise SifenClientError("No se pudo cargar el WSDL (remoto vacío y sin fallback local)")

    try:
        response = client.service.rEnviConsRUC(dId=did, dRUCCons=ruc)
    except Exception as exc:
        raise SifenClientError(f"Error al invocar rEnviConsRUC vía Zeep: {exc}") from exc

    # Capturar request/response raw
    def _to_xml(obj) -> str:
        if obj is None:
            return ""
        if hasattr(obj, "decode"):
            return obj.decode("utf-8")
        try:
            return etree.tostring(obj, encoding="unicode")
        except Exception:
            return str(obj)

    req_xml = _to_xml(history.last_sent["envelope"] if history.last_sent else None)
    resp_xml = _to_xml(history.last_received["envelope"] if history.last_received else None)
    http_status = history.last_received["http_response"].status_code if history.last_received else None

    result = {
        "http_status": http_status,
        "raw_xml": resp_xml,
        "request_body": req_xml,
        "response_body": resp_xml,
        "endpoint": wsdl_url,
    }

    cod, msg, xcont = _parse_response_fields(resp_xml)
    if cod:
        result["dCodRes"] = cod
    if msg:
        result["dMsgRes"] = msg
    if xcont:
        result["xContRUC"] = xcont

    if dump_http:
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        (artifacts_dir / f"consulta_ruc_fixed_request_{ts}.xml").write_text(req_xml, encoding="utf-8")
        (artifacts_dir / f"consulta_ruc_fixed_response_{ts}.xml").write_text(resp_xml, encoding="utf-8")
        (artifacts_dir / f"consulta_ruc_fixed_{ts}.log").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Consulta RUC en SIFEN (siConsRUC) - testing aislado",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Test básico
  python -m tools.consulta_ruc --env test --ruc 4554737

  # Con dump HTTP (guarda artifacts)
  python -m tools.consulta_ruc --env test --ruc 4554737 --dump-http

  # Producción con artifacts custom
  python -m tools.consulta_ruc --env prod --ruc 80012345 --dump-http --artifacts-dir ./consultas

Variables de entorno requeridas:
  SIFEN_SIGN_P12_PATH       - Ruta al certificado P12 para firma
  SIFEN_SIGN_P12_PASSWORD   - Contraseña del certificado P12
  SIFEN_MTLS_P12_PATH       - Ruta al certificado P12 para mTLS (puede ser el mismo)
  SIFEN_MTLS_P12_PASSWORD   - Contraseña del certificado mTLS

Códigos de respuesta comunes:
  0502 - RUC encontrado (éxito)
  0500 - RUC inexistente
  0501 - Sin permiso para consultar
  0160 - XML mal formado (error de formato)
  0183 - RUC del certificado no activo/válido
        """
    )
    
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default="test",
        help="Ambiente SIFEN (default: test)"
    )
    
    parser.add_argument(
        "--ruc",
        required=True,
        help="RUC a consultar (7-8 dígitos, puede incluir guión: ej. 4554737 o 4554737-8)"
    )
    
    parser.add_argument(
        "--dump-http",
        action="store_true",
        help="Guardar artifacts de request/response HTTP en artifacts/"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=str,
        default="artifacts",
        help="Directorio para guardar artifacts (default: artifacts/)"
    )

    parser.add_argument(
        "--introspect",
        action="store_true",
        help="Solo inspecciona el WSDL y genera request canónico (no envía)."
    )
    
    parser.add_argument(
        "--did",
        type=str,
        help="dId personalizado (15 dígitos). Si no se especifica, se genera automáticamente"
    )
    
    args = parser.parse_args()
    
    # Validar variables de entorno
    required_env_vars = [
        "SIFEN_SIGN_P12_PATH",
        "SIFEN_SIGN_P12_PASSWORD",
        "SIFEN_MTLS_P12_PATH",
        "SIFEN_MTLS_P12_PASSWORD",
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print("❌ ERROR: Faltan variables de entorno requeridas:")
        for var in missing_vars:
            print(f"   - {var}")
        print("\nVer --help para más información sobre variables de entorno.")
        return 1
    
    # Configurar artifacts dir si se especificó
    if args.artifacts_dir != "artifacts":
        os.environ["SIFEN_ARTIFACTS_DIR"] = args.artifacts_dir
    artifacts_dir = get_artifacts_dir()
    
    print("=" * 70)
    print("CONSULTA RUC SIFEN (siConsRUC) - Testing Aislado")
    print("=" * 70)
    print(f"Ambiente:     {args.env.upper()}")
    print(f"RUC:          {args.ruc}")
    print(f"Dump HTTP:    {'SÍ' if args.dump_http else 'NO'}")
    print(f"Artifacts:    {args.artifacts_dir}")
    if args.did:
        print(f"dId custom:   {args.did}")
    print("=" * 70)
    print()
    
    try:
        # Crear configuración SIFEN
        config = get_sifen_config(env=args.env)
        
        # Obtener endpoint que se usará
        endpoint = config.get_soap_service_url("consulta_ruc")
        print(f"📡 Endpoint WSDL: {endpoint}")
        print()

        # Crear cliente SOAP
        with SoapClient(config) as client:
            # Transport de Zeep (reutiliza mTLS ya configurado)
            transport = Transport(session=client.transport.session, timeout=client.read_timeout)

            # Solo introspección
            if args.introspect:
                ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
                out_txt = artifacts_dir / f"consulta_ruc_wsdl_introspect_{ts}.txt"
                try:
                    _wsdl_introspect(endpoint, transport, out_txt)
                except Exception as exc:
                    out_txt.write_text(f"ERROR al cargar WSDL: {exc}\n", encoding="utf-8")
                    print(f"⚠️  No se pudo introspectar WSDL: {exc}")
                    return 1

                # Canonical request (no se envía)
                did = args.did or _dt.datetime.now().strftime("%Y%m%d%H%M%S") + "0"
                canon_path = artifacts_dir / f"consulta_ruc_wsdl_canonical_request_{ts}.xml"
                _build_canonical_request(endpoint, transport, normalize_sifen_truc(args.ruc), did, canon_path)

                # Current request (último intento previo) si existe
                latest = _latest_attempt_json(artifacts_dir)
                if latest:
                    data = json.loads(latest.read_text(encoding="utf-8"))
                    current_req = data.get("request_body", "")
                    curr_path = artifacts_dir / f"consulta_ruc_current_request_{ts}.xml"
                    _save_text(curr_path, current_req)
                    diff_path = artifacts_dir / f"consulta_ruc_wsdl_diff_{ts}.txt"
                    canonical_text = canon_path.read_text(encoding="utf-8")
                    _save_diff(current_req, canonical_text, diff_path, "current_request", "wsdl_canonical")

                print(f"Introspección guardada en: {out_txt}")
                print(f"Request canónico: {canon_path}")
                return 0

            print(f"🔍 Consultando RUC {args.ruc} en SIFEN...")
            print()
            
            # Ejecutar consulta vía Zeep (ajustada a WSDL)
            did_val = args.did or _dt.datetime.now().strftime("%Y%m%d%H%M%S") + "0"
            normalized_ruc = normalize_sifen_truc(args.ruc)
            try:
                result = _zeep_call(
                    wsdl_url=_resolve_wsdl_url(endpoint),
                    transport=transport,
                    ruc=normalized_ruc,
                    did=did_val,
                    dump_http=args.dump_http,
                    artifacts_dir=artifacts_dir,
                )
            except Exception as exc:
                print(f"⚠️  Zeep call falló, usando fallback consulta_ruc_raw: {exc}")
                result = client.consulta_ruc_raw(
                    ruc=args.ruc,
                    dump_http=args.dump_http,
                    did=args.did
                )
            
            # Extraer campos clave
            http_status = result.get("http_status", 0)
            cod_res = result.get("dCodRes", "")
            msg_res = result.get("dMsgRes", "")
            x_cont_ruc = result.get("xContRUC", {})
            
            # Mostrar resultado HTTP
            print("=" * 70)
            print("RESULTADO HTTP")
            print("=" * 70)
            print(f"HTTP Status:  {http_status}")
            
            if http_status != 200:
                print(f"⚠️  WARNING: HTTP status != 200")
                raw_xml = result.get("raw_xml", "")
                if raw_xml:
                    print(f"\nRespuesta (primeros 500 chars):")
                    print(raw_xml[:500])
            
            print()
            
            # Mostrar resultado SIFEN
            print("=" * 70)
            print("RESULTADO SIFEN")
            print("=" * 70)
            print(f"dCodRes:      {cod_res or '(vacío)'}")
            print(f"dMsgRes:      {msg_res or '(vacío)'}")
            print()
            
            # Interpretar código
            if cod_res == "0502":
                print("✅ RUC ENCONTRADO")
            elif cod_res == "0500":
                print("❌ RUC INEXISTENTE")
            elif cod_res == "0501":
                print("❌ SIN PERMISO PARA CONSULTAR")
            elif cod_res == "0160":
                print("❌ XML MAL FORMADO (error de formato/endpoint)")
            elif cod_res == "0183":
                print("❌ RUC DEL CERTIFICADO NO ACTIVO/VÁLIDO")
            elif cod_res:
                print(f"⚠️  CÓDIGO NO RECONOCIDO: {cod_res}")
            else:
                print("❌ SIN CÓDIGO DE RESPUESTA (posible error de parseo)")
            
            print()
            
            # Mostrar información del RUC si está disponible
            if x_cont_ruc and isinstance(x_cont_ruc, dict):
                print("=" * 70)
                print("INFORMACIÓN DEL RUC")
                print("=" * 70)
                
                ruc_cons = x_cont_ruc.get("dRUCCons", "")
                razon = x_cont_ruc.get("dRazCons", "")
                cod_est = x_cont_ruc.get("dCodEstCons", "")
                des_est = x_cont_ruc.get("dDesEstCons", "")
                fact_elec = x_cont_ruc.get("dRUCFactElec", "")
                
                print(f"RUC:              {ruc_cons}")
                print(f"Razón Social:     {razon}")
                print(f"Estado:           {des_est} (código: {cod_est})")
                print(f"Fact. Electrónica: {fact_elec}")
                print()
                
                # Interpretar habilitación FE
                fact_elec_norm = str(fact_elec).strip().upper()
                if fact_elec_norm in ("1", "S", "SI"):
                    print("✅ RUC HABILITADO para Facturación Electrónica")
                elif fact_elec_norm in ("0", "N", "NO"):
                    print("❌ RUC NO HABILITADO para Facturación Electrónica")
                else:
                    print(f"⚠️  Estado de habilitación FE desconocido: {fact_elec!r}")
                
                print()
            
            # Mostrar artifacts guardados
            if args.dump_http:
                print("=" * 70)
                print("ARTIFACTS GUARDADOS")
                print("=" * 70)
                artifacts_path = Path(args.artifacts_dir)
                
                # Listar archivos consulta_ruc_* más recientes
                if artifacts_path.exists():
                    consulta_files = sorted(
                        artifacts_path.glob("consulta_ruc_*"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True
                    )[:10]  # Últimos 10 archivos
                    
                    if consulta_files:
                        print("Archivos generados (más recientes):")
                        for f in consulta_files:
                            size_kb = f.stat().st_size / 1024
                            print(f"  - {f.name} ({size_kb:.1f} KB)")
                    else:
                        print("⚠️  No se encontraron artifacts consulta_ruc_*")
                else:
                    print(f"⚠️  Directorio {artifacts_path} no existe")
                
                print()
            
            # Exit code según resultado
            if cod_res == "0502":
                print("=" * 70)
                print("✅ ÉXITO: Consulta completada correctamente")
                print("=" * 70)
                return 0
            elif cod_res in ("0500", "0501"):
                print("=" * 70)
                print("⚠️  CONSULTA COMPLETADA CON ADVERTENCIA")
                print("=" * 70)
                return 0  # No es error del cliente, es respuesta válida de SIFEN
            else:
                print("=" * 70)
                print("❌ ERROR: Consulta falló o respuesta inesperada")
                print("=" * 70)
                return 1
    
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ ERROR FATAL")
        print("=" * 70)
        print(f"{type(e).__name__}: {e}")
        print()
        
        if args.dump_http:
            print(f"Ver artifacts en {args.artifacts_dir}/ para más detalles")
        
        import traceback
        print("\nTraceback completo:")
        traceback.print_exc()
        
        return 1


if __name__ == "__main__":
    sys.exit(main())
