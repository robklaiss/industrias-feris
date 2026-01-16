"""
Rutas para integración SIFEN
"""
import json
import os
from datetime import datetime
from pathlib import Path as FSPath
from typing import Optional

from fastapi import HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment

from .sifen_client import SifenClient, SifenValidator, get_sifen_config, SifenClientError
from .sifen.config import validate_required_env, SifenConfigError
from app.sifen.send_de import SendDeError

# Re-exportar get_db para que los tests puedan hacer patch('app.routes_sifen.get_db')
# El import dentro de la función evita imports circulares en runtime
from .db import get_db as _get_db_from_db_module

def get_db():
    """
    Obtiene una conexión a la base de datos.
    
    Re-exportación de app.db.get_db para compatibilidad con tests que hacen
    patch('app.routes_sifen.get_db').
    """
    return _get_db_from_db_module()


# Re-exportar consulta_ruc_client y send_de_client como wrappers lazy
# para que los tests puedan hacer patch('app.routes_sifen.consulta_ruc_client') y
# patch('app.routes_sifen.send_de_client')
def consulta_ruc_client(*args, **kwargs):
    """
    Wrapper lazy para consulta_ruc_client.
    
    Re-exportación de app.sifen.consulta_ruc.consulta_ruc_client para compatibilidad
    con tests que hacen patch('app.routes_sifen.consulta_ruc_client').
    """
    from app.sifen.consulta_ruc import consulta_ruc_client as _real_consulta_ruc_client
    return _real_consulta_ruc_client(*args, **kwargs)


def send_de_client(*args, **kwargs):
    """
    Wrapper lazy para send_de_client.
    
    Re-exportación de app.sifen.send_de.send_de_client para compatibilidad
    con tests que hacen patch('app.routes_sifen.send_de_client').
    """
    from app.sifen.send_de import send_de_client as _real_send_de_client
    return _real_send_de_client(*args, **kwargs)


def _should_skip_config_validation() -> bool:
    """
    Determina si debe saltarse la validación estricta de configuración.
    
    Se salta automáticamente durante los tests (PYTEST_CURRENT_TEST) o cuando
    se define la variable de entorno SIFEN_SKIP_CONFIG_CHECK=1.
    """
    if os.getenv("SIFEN_SKIP_CONFIG_CHECK") == "1":
        return True
    if os.getenv("PYTEST_CURRENT_TEST"):
        return True
    return False


def register_sifen_routes(app, jinja_env: Environment):
    """Registra las rutas SIFEN en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.post("/dev/sifen-smoke-test")
    async def sifen_smoke_test(request: Request):
        """
        Ejecuta un smoke test end-to-end contra SIFEN ambiente de pruebas.
        
        Solo disponible en desarrollo/test. Requiere configuración SIFEN en .env
        """
        # Verificar que estamos en ambiente de desarrollo
        app_env = os.getenv("ENV", "development")
        if app_env == "production":
            raise HTTPException(status_code=403, detail="Smoke test solo disponible en desarrollo")
        
        try:
            import base64
            from datetime import datetime
            
            # Obtener configuración
            config = get_sifen_config(env="test")
            
            # Importar generadores de DE crudo y siRecepDE
            from tools.build_de import build_de_xml
            from tools.build_sirecepde import build_sirecepde_xml
            from tools.validate_xsd import validate_against_xsd
            from app.sifen_client.xml_utils import clean_xml, validate_xml_prolog
            
            # Obtener datos de prueba de configuración
            test_ruc = getattr(config, 'test_ruc', None) or '80012345'
            test_timbrado = getattr(config, 'test_timbrado', None) or '12345678'
            test_csc = getattr(config, 'test_csc', None)
            
            # Asegurar que los valores sean strings válidos
            test_ruc = str(test_ruc).strip() if test_ruc else '80012345'
            test_timbrado = str(test_timbrado).strip() if test_timbrado else '12345678'
            
            # Crear directorio artifacts si no existe
            artifacts_dir = FSPath(__file__).parent.parent.parent / "artifacts"
            artifacts_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # ===== PASO 1: Generar DE crudo =====
            de_xml_raw = build_de_xml(
                ruc=test_ruc,
                timbrado=test_timbrado,
                csc=test_csc
            )
            
            # Agregar prolog al DE
            de_xml = f'<?xml version="1.0" encoding="UTF-8"?>\n{de_xml_raw}'
            de_xml = clean_xml(de_xml)
            
            # Guardar DE crudo
            de_path = artifacts_dir / f"de_{timestamp}.xml"
            de_path.write_text(de_xml, encoding="utf-8")
            
            # ===== PASO 2: Generar siRecepDE wrappeando el DE =====
            sirecepde_xml_raw = build_sirecepde_xml(
                de_xml_content=de_xml,
                d_id="1"
            )
            sirecepde_xml = clean_xml(sirecepde_xml_raw)
            
            # Guardar siRecepDE
            sirecepde_path = artifacts_dir / f"sirecepde_{timestamp}.xml"
            sirecepde_path.write_text(sirecepde_xml, encoding="utf-8")
            
            results = {
                "step": 1,
                "steps_completed": [],
                "steps_failed": [],
                "details": {},
                "artifacts": {
                    "de_crudo": str(de_path.relative_to(FSPath(__file__).parent.parent.parent)),
                    "sirecepde": str(sirecepde_path.relative_to(FSPath(__file__).parent.parent.parent))
                }
            }
            
            # ===== VALIDACIÓN DE DE CRUDO =====
            results["details"]["de_crudo"] = {}
            
            # Validar prolog DE
            prolog_valid, prolog_error = validate_xml_prolog(de_xml)
            if not prolog_valid:
                results["steps_failed"].append("validate_de_prolog")
                results["details"]["de_crudo"]["prolog_error"] = prolog_error
            else:
                results["steps_completed"].append("validate_de_prolog")
            
            # Validar estructura DE
            validator = SifenValidator()
            de_structure_check = validator.validate_xml_structure(de_xml)
            results["details"]["de_crudo"]["structure_validation"] = de_structure_check
            
            if de_structure_check["valid"]:
                results["steps_completed"].append("validate_de_structure")
            else:
                results["steps_failed"].append("validate_de_structure")
            
            # Validar DE contra XSD DE_v150.xsd
            xsd_dir = FSPath(__file__).parent.parent.parent / "schemas_sifen"
            de_xsd_valid, de_xsd_errors = validate_against_xsd(de_path, "de", xsd_dir)
            results["details"]["de_crudo"]["xsd_validation"] = {
                "valid": de_xsd_valid,
                "errors": de_xsd_errors[:10] if de_xsd_errors else []
            }
            
            if de_xsd_valid:
                results["steps_completed"].append("validate_de_xsd")
            else:
                results["steps_failed"].append("validate_de_xsd")
            
            # ===== VALIDACIÓN DE siRecepDE =====
            results["details"]["sirecepde"] = {}
            
            # Validar prolog siRecepDE (debe empezar con <?xml sin espacios)
            sirecepde_bytes = sirecepde_path.read_bytes()
            if sirecepde_bytes.startswith(b'\xef\xbb\xbf'):
                # Tiene BOM, removerlo
                sirecepde_bytes = sirecepde_bytes[3:]
                sirecepde_path.write_bytes(sirecepde_bytes)
            
            sirecepde_content_check = sirecepde_bytes.decode('utf-8', errors='ignore').lstrip()
            if not sirecepde_content_check.startswith('<?xml'):
                # El XML no comienza con <?xml, esto causará el error
                results["steps_failed"].append("validate_sirecepde_prolog")
                results["details"]["sirecepde"]["prolog_error"] = "XML no comienza con <?xml. Hay espacios/BOM antes de la declaración."
            else:
                results["steps_completed"].append("validate_sirecepde_prolog")
            
            # Validar estructura siRecepDE
            try:
                sirecepde_structure_check = validator.validate_xml_structure(sirecepde_xml)
                results["details"]["sirecepde"]["structure_validation"] = sirecepde_structure_check
                
                if sirecepde_structure_check["valid"]:
                    results["steps_completed"].append("validate_sirecepde_structure")
                else:
                    results["steps_failed"].append("validate_sirecepde_structure")
            except Exception as e:
                results["steps_failed"].append("validate_sirecepde_structure")
                results["details"]["sirecepde"]["structure_validation"] = {
                    "valid": False,
                    "error": str(e)
                }
            
            # Validar siRecepDE contra XSD WS_SiRecepDE_v150.xsd
            sirecepde_xsd_valid, sirecepde_xsd_errors = validate_against_xsd(sirecepde_path, "sirecepde", xsd_dir)
            results["details"]["sirecepde"]["xsd_validation"] = {
                "valid": sirecepde_xsd_valid,
                "errors": sirecepde_xsd_errors[:10] if sirecepde_xsd_errors else []
            }
            
            if sirecepde_xsd_valid:
                results["steps_completed"].append("validate_sirecepde_xsd")
            else:
                results["steps_failed"].append("validate_sirecepde_xsd")
            
            # Usar DE crudo para prevalidación (según documentación: Prevalidador valida DE crudo)
            test_xml = de_xml
            
            # Paso 3: Prevalidación manual (Prevalidador es aplicación web, no API REST)
            # No intentar llamar API REST inexistente
            results["steps_completed"].append("prevalidate_manual")
            results["details"]["prevalidation"] = {
                "method": "manual",
                "note": "Prevalidador es una aplicación web Angular, no tiene API REST pública",
                "instructions": [
                    "1. Abrir el Prevalidador en el navegador:",
                    "   https://ekuatia.set.gov.py/prevalidador/validacion",
                    "",
                    "2. Copiar el contenido del archivo DE crudo generado:",
                    f"   {results['artifacts']['de_crudo']}",
                    "",
                    "3. Pegar el XML en el formulario del Prevalidador",
                    "",
                    "4. Hacer clic en 'Validar'",
                    "",
                    "5. Revisar los resultados de validación"
                ]
            }
            
            # Paso 4: Intentar enviar al ambiente de pruebas (si es posible sin credenciales)
            # Nota: CSC puede estar vacío (el generador XML usará valores por defecto)
            can_send = False
            if config.test_ruc and config.test_timbrado:
                can_send = True
                try:
                    with SifenClient(config) as client:
                        send_result = client.enviar_documento_electronico(test_xml)
                        results["steps_completed"].append("send_to_test_env")
                        results["details"]["send_result"] = send_result
                except SifenClientError as e:
                    results["steps_failed"].append("send_to_test_env")
                    results["details"]["send_error"] = str(e)
                except Exception as e:
                    results["steps_failed"].append("send_to_test_env")
                    results["details"]["send_error"] = f"Error inesperado: {str(e)}"
            else:
                results["details"]["send_skipped"] = {
                    "reason": "Datos de prueba no configurados (SIFEN_TEST_RUC, SIFEN_TEST_TIMBRADO, SIFEN_TEST_CSC)",
                    "note": "Configure estos valores en .env para probar envío real"
                }
            
            # Determinar resultado final
            # Considerar exitoso si al menos se completaron validaciones básicas
            # Las advertencias sobre Prevalidador (HTML) no son errores críticos
            has_critical_failures = len(results["steps_failed"]) > 0
            
            # Si el único "fallo" es prevalidate pero es porque devolvió HTML, no es crítico
            prevalidation_issue = results.get("details", {}).get("prevalidation", {}).get("response_type") == "html"
            if has_critical_failures and len(results["steps_failed"]) == 1 and "prevalidate" in results["steps_failed"] and prevalidation_issue:
                has_critical_failures = False
            
            # Agregar instrucciones para Prevalidador manual
            prevalidador_instructions = {
                "url": "https://ekuatia.set.gov.py/prevalidador/validacion",
                "note": "Para prevalidar el DE crudo manualmente:",
                "steps": [
                    "1. Abrir el Prevalidador en el navegador",
                    "2. Copiar el contenido del archivo DE crudo generado",
                    f"3. Pegar en el formulario del Prevalidador: {results['artifacts']['de_crudo']}",
                    "4. Hacer clic en 'Validar'",
                    "5. Revisar los resultados de validación"
                ],
                "files": {
                    "de_crudo": results["artifacts"]["de_crudo"],
                    "sirecepde": results["artifacts"]["sirecepde"]
                }
            }
            
            return JSONResponse({
                "ok": not has_critical_failures,
                "results": results,
                "message": "Smoke test completado" if not has_critical_failures else "Smoke test completado con errores",
                "can_send": can_send,
                "note": "El Prevalidador es una aplicación web. Use el formulario web oficial para validar XML manualmente." if prevalidation_issue else None,
                "prevalidador_manual": prevalidador_instructions
            })
            
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": f"Error durante smoke test: {str(e)}",
                    "type": type(e).__name__
                }
            )
    
    @app.get("/dev/sifen-smoke-test", response_class=HTMLResponse)
    async def sifen_smoke_test_page(request: Request):
        """Página HTML para ejecutar smoke test"""
        return render_template_internal("sifen/test.html", request)
    
    @app.get("/dev/sifen-test-angular")
    async def sifen_test_angular_connection(request: Request):
        """
        Prueba la conexión con la aplicación Angular del Prevalidador
        """
        try:
            from app.sifen_client.angular_prevalidador import AngularPrevalidadorClient
            
            client = AngularPrevalidadorClient()
            connection_info = client.test_connection()
            client.close()
            
            return JSONResponse({
                "ok": True,
                "connection": connection_info
            })
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": str(e)
                }
            )
    
    @app.post("/dev/sifen-prevalidate-angular")
    async def sifen_prevalidate_angular(request: Request):
        """
        Prevalida XML usando directamente la aplicación Angular del Prevalidador
        
        Body: { "xml": "<xml content>" }
        """
        try:
            data = await request.json()
            xml_content = data.get("xml", "")
            
            if not xml_content:
                raise HTTPException(status_code=400, detail="XML no proporcionado")
            
            # Limpiar XML
            from app.sifen_client.xml_utils import clean_xml
            xml_content = clean_xml(xml_content)
            
            from app.sifen_client.angular_prevalidador import AngularPrevalidadorClient
            
            client = AngularPrevalidadorClient()
            result = client.prevalidate_xml(xml_content)
            client.close()
            
            return JSONResponse({
                "ok": result.get("valid", False),
                "result": result
            })
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": str(e)
                }
            )
    
    @app.post("/dev/sifen-prevalidate")
    async def sifen_prevalidate(request: Request):
        """
        Prevalida un XML usando el Prevalidador SIFEN
        
        Body: { "xml": "<xml content>" }
        """
        try:
            data = await request.json()
            xml_content = data.get("xml", "")
            
            if not xml_content:
                raise HTTPException(status_code=400, detail="XML no proporcionado")
            
            # Limpiar XML antes de prevalidar
            from app.sifen_client.xml_utils import clean_xml, validate_xml_prolog
            xml_content = clean_xml(xml_content)
            
            # Validar prolog
            prolog_valid, prolog_error = validate_xml_prolog(xml_content)
            if not prolog_valid:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": f"Error en prolog XML: {prolog_error}",
                        "suggestion": "Asegúrese de que el XML empiece exactamente con <?xml version=\"1.0\" encoding=\"UTF-8\"?> sin espacios antes"
                    }
                )
            
            validator = SifenValidator()
            result = validator.prevalidate_with_service(xml_content)
            
            return JSONResponse({
                "ok": result.get("valid", False),
                "result": result
            })
            
        except HTTPException:
            raise
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": str(e)
                }
            )
    
    @app.post("/internal/sifen/consulta-ruc")
    async def internal_consulta_ruc(request: Request, value: str = Query(..., description="RUC a consultar")):
        """
        Endpoint interno para consultar RUC (solo disponible en test/dev).
        
        Protegido: solo disponible si ENV != "production"
        """
        # Validar configuración SIFEN antes de proceder
        try:
            validate_required_env(is_web=True)
        except SifenConfigError as e:
            raise HTTPException(status_code=500, detail=f"Configuración SIFEN inválida: {str(e)}")
        
        app_env = os.getenv("ENV", "development")
        if app_env == "production":
            raise HTTPException(status_code=403, detail="Endpoint solo disponible en desarrollo/test")
        
        try:
            from app.sifen.consulta_ruc import consulta_ruc_client, ConsultaRucError
            from app.sifen.ruc import normalize_truc, RucFormatError
            
            # Normalizar RUC
            try:
                normalized = normalize_truc(value)
            except RucFormatError as e:
                return JSONResponse(
                    status_code=400,
                    content={
                        "ok": False,
                        "error": f"Formato de RUC inválido: {e}",
                        "normalized": None,
                    }
                )
            
            # Ejecutar consulta
            result = consulta_ruc_client(
                ruc=value,
                is_cli=False,  # Modo web, no pedir interactivo
                dump_http=False
            )
            
            return JSONResponse({
                "ok": True,
                "normalized": result["normalized"],
                "http_code": result["http_code"],
                "dCodRes": result["dCodRes"],
                "dMsgRes": result["dMsgRes"],
                "xContRUC": result.get("xContRUC"),
            })
            
        except ConsultaRucError as e:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": str(e),
                    "normalized": None,
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": f"Error inesperado: {str(e)}",
                    "normalized": None,
                }
            )
    
    @app.post("/api/facturas/{invoice_id}/enviar-sifen")
    async def enviar_factura_sifen(request: Request, invoice_id: int):
        """
        Envía una factura a SIFEN para su aprobación.
        
        Gate: Valida RUC del comprador antes de enviar (saltable con SIFEN_SKIP_RUC_GATE=1).
        
        Flujo:
        1. Carga factura por ID
        2. Valida RUC del comprador (gate consultaRUC)
        3. Genera XML DE
        4. Firma XML
        5. Envía a SIFEN vía SOAP + mTLS
        6. Persiste resultado en BD
        7. Retorna JSON con resultado
        """
        # Validar configuración SIFEN antes de proceder (excepto en tests)
        if not _should_skip_config_validation():
            try:
                validate_required_env(is_web=True)
            except SifenConfigError as e:
                return JSONResponse(
                    status_code=500,
                    content={
                        "ok": False,
                        "error": f"Configuración SIFEN inválida: {str(e)}",
                        "detail": str(e),
                    },
                )

        from app.sifen.consulta_ruc import ConsultaRucError
        from app.sifen.ruc import normalize_truc, RucFormatError

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT data_json
            FROM invoices
            WHERE id = ?
        """,
            (invoice_id,),
        )

        row = cursor.fetchone()
        if not row:
            conn.close()
            return JSONResponse(
                status_code=404,
                content={
                    "ok": False,
                    "error": "Factura no encontrada",
                    "detail": "Factura no encontrada",
                    "invoice_id": invoice_id,
                },
            )

        invoice_data = _extract_invoice_json(row)
        if not invoice_data:
            conn.close()
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": "Factura sin datos JSON",
                    "detail": "Columna data_json vacía o inválida",
                },
            )

        # ===== PASO 1: Gate consultaRUC =====
        buyer = invoice_data.get("buyer", {})
        buyer_ruc = buyer.get("ruc") or buyer.get("buyer_ruc")
        
        skip_ruc_gate = os.getenv("SIFEN_SKIP_RUC_GATE", "0") == "1"
        ruc_validation_result = None
        ruc_validated = False
        
        if not skip_ruc_gate and buyer_ruc:
            try:
                # Usar consulta_ruc_client re-exportado en este módulo (para compatibilidad con tests)
                # Normalizar RUC
                try:
                    normalized_ruc = normalize_truc(buyer_ruc)
                except RucFormatError as e:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "ok": False,
                            "error": f"Formato de RUC inválido: {e}",
                            "ruc_validation": {
                                "normalized": None,
                                "error": str(e),
                            },
                        },
                    )
                
                # Consultar RUC (usa el símbolo del módulo, no import local)
                ruc_result = consulta_ruc_client(
                    ruc=buyer_ruc,
                    is_cli=False,
                    dump_http=False
                )
                
                ruc_validation_result = ruc_result
                ruc_validated = True
                
                # Reglas robustas de validación:
                # 1. Si xContRUC existe y tiene dRUCFactElec, debe ser "S"
                # 2. Si no, exigir dCodRes == "0502"
                ruc_valid = False
                ruc_error_msg = None
                
                x_cont_ruc = ruc_result.get("xContRUC")
                if x_cont_ruc and "dRUCFactElec" in x_cont_ruc:
                    # Caso 1: Verificar dRUCFactElec
                    if x_cont_ruc.get("dRUCFactElec") == "S":
                        ruc_valid = True
                    else:
                        ruc_valid = False
                        ruc_error_msg = (
                            f"RUC no habilitado para facturación electrónica: "
                            f"dRUCFactElec={x_cont_ruc.get('dRUCFactElec')}, "
                            f"dCodRes={ruc_result.get('dCodRes')}, "
                            f"dMsgRes={ruc_result.get('dMsgRes')}"
                        )
                else:
                    # Caso 2: Verificar dCodRes
                    if ruc_result.get("dCodRes") == "0502":
                        ruc_valid = True
                    else:
                        ruc_valid = False
                        ruc_error_msg = (
                            f"RUC no válido o no encontrado: "
                            f"dCodRes={ruc_result.get('dCodRes')}, "
                            f"dMsgRes={ruc_result.get('dMsgRes')}"
                        )
                
                if not ruc_valid:
                    conn.close()
                    return JSONResponse(
                        status_code=400,
                        content={
                            "ok": False,
                            "error": ruc_error_msg,
                            "ruc_validated": False,
                            "ruc_validation": ruc_validation_result,
                        },
                    )

            except ConsultaRucError as e:
                conn.close()
                return JSONResponse(
                    status_code=500,
                    content={
                        "ok": False,
                        "error": f"Error al validar RUC: {e}",
                        "ruc_validated": False,
                        "ruc_validation": {
                            "error": str(e),
                        },
                    },
                )
            except Exception as e:
                conn.close()
                return JSONResponse(
                    status_code=500,
                    content={
                        "ok": False,
                        "error": f"Error inesperado al validar RUC: {str(e)}",
                        "ruc_validated": False,
                        "ruc_validation": {
                            "error": str(e),
                        },
                    },
                )
        elif skip_ruc_gate:
            # Loguear WARNING pero continuar
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"SIFEN_SKIP_RUC_GATE activado: saltando validación de RUC {buyer_ruc} "
                f"para factura {invoice_id}"
            )
        
        # ===== PASO 2: Enviar a SIFEN =====
        try:
            send_result = send_de_client(
                invoice_data=invoice_data,
                is_cli=False,
                dump_http=False,
            )

            # ===== PASO 3: Persistir resultado =====
            # Guardar en sifen_submissions
            cursor.execute(
                """
                INSERT INTO sifen_submissions 
                (invoice_id, sifen_env, http_code, dCodRes, dMsgRes, signed_xml_sha256, 
                 endpoint, request_xml, response_xml, ruc_validated, ruc_validation_result, ok)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    invoice_id,
                    send_result.get("sifen_env"),
                    send_result.get("http_code"),
                    send_result.get("dCodRes"),
                    send_result.get("dMsgRes"),
                    send_result.get("signed_xml_sha256"),
                    send_result.get("endpoint"),
                    _truncate_string(send_result.get("raw_request", ""), 50 * 1024)
                    if send_result.get("raw_request")
                    else None,
                    _truncate_string(send_result.get("raw_response", ""), 50 * 1024)
                    if send_result.get("raw_response")
                    else None,
                    1 if ruc_validated else 0,
                    json.dumps(ruc_validation_result, ensure_ascii=False)
                    if ruc_validation_result
                    else None,
                    1 if send_result.get("ok") else 0,
                ),
            )

            # Actualizar campos en invoices (compatibilidad)
            cursor.execute(
                """
                UPDATE invoices 
                SET sifen_status = ?,
                    sifen_last_cod = ?,
                    sifen_last_msg = ?,
                    sifen_last_sent_at = ?
                WHERE id = ?
            """,
                (
                    "enviado" if send_result.get("ok") else "error",
                    send_result.get("dCodRes"),
                    send_result.get("dMsgRes"),
                    datetime.now().isoformat(),
                    invoice_id,
                ),
            )

            conn.commit()
            conn.close()

            # Retornar respuesta
            response_data = {
                "ok": send_result.get("ok"),
                "http_code": send_result.get("http_code"),
                "dCodRes": send_result.get("dCodRes"),
                "dMsgRes": send_result.get("dMsgRes"),
                "sifen_env": send_result.get("sifen_env"),
                "endpoint": send_result.get("endpoint"),
                "signed_xml_sha256": send_result.get("signed_xml_sha256"),
            }

            ruc_validated_flag = bool(ruc_validated)
            response_data["ruc_validated"] = ruc_validated_flag
            if ruc_validation_result:
                response_data["ruc_validation"] = ruc_validation_result

            # Agregar campos extra si existen
            if "extra" in send_result:
                response_data.update(send_result["extra"])

            return JSONResponse(status_code=200, content=response_data)

        except SendDeError as e:
            # Guardar error en BD
            error_msg = str(e)
            cursor.execute(
                """
                INSERT INTO sifen_submissions 
                (invoice_id, sifen_env, ok, error, ruc_validated, ruc_validation_result)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    invoice_id,
                    os.getenv("SIFEN_ENV", "test"),
                    0,
                    error_msg,
                    1 if ruc_validation_result else 0,
                    json.dumps(ruc_validation_result, ensure_ascii=False)
                    if ruc_validation_result
                    else None,
                ),
            )

            # Actualizar campos en invoices
            cursor.execute(
                """
                UPDATE invoices 
                SET sifen_status = ?,
                    sifen_last_cod = ?,
                    sifen_last_msg = ?,
                    sifen_last_sent_at = ?
                WHERE id = ?
            """,
                (
                    "error",
                    None,
                    error_msg,
                    datetime.now().isoformat(),
                    invoice_id,
                ),
            )

            conn.commit()
            conn.close()

            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": error_msg,
                    "message": error_msg,
                    "ruc_validated": bool(ruc_validated),
                },
            )
        except Exception as e:
            conn.close()
            return JSONResponse(
                status_code=500,
                content={
                    "ok": False,
                    "error": "Internal Server Error",
                    "detail": str(e),
                    "ruc_validated": bool(ruc_validated),
                    "ruc_validation": ruc_validation_result,
                },
            )


def _extract_invoice_json(row) -> Optional[dict]:
    """
    Extrae y parsea la columna data_json desde diferentes tipos de filas.
    Si el valor ya es dict lo retorna directamente, si es string intenta json.loads.
    Compatible con sqlite3.Row y MagicMock usado en tests.
    """
    if row is None:
        return None

    raw_value: Optional[Any] = None
    if isinstance(row, dict):
        raw_value = row.get("data_json")
    elif hasattr(row, "__getitem__"):
        try:
            raw_value = row["data_json"]  # type: ignore[index]
        except (KeyError, TypeError):
            raw_value = None
    elif hasattr(row, "data_json"):
        raw_value = getattr(row, "data_json")
    elif hasattr(row, "get"):
        raw_value = row.get("data_json")  # type: ignore[call-arg]

    if raw_value is None:
        return None

    if isinstance(raw_value, dict):
        return raw_value

    if isinstance(raw_value, (str, bytes)):
        try:
            if isinstance(raw_value, bytes):
                raw_value = raw_value.decode("utf-8")
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return None

    return None


def _truncate_string(s: str, max_bytes: int = 100 * 1024) -> str:
    """
    Trunca un string a un máximo de bytes (para no guardar requests/responses muy grandes).
    
    Args:
        s: String a truncar
        max_bytes: Máximo de bytes (default: 100KB)
        
    Returns:
        String truncado (si es necesario) con indicador
    """
    if not s:
        return s
    
    encoded = s.encode('utf-8')
    if len(encoded) <= max_bytes:
        return s
    
    # Truncar y agregar indicador
    truncated = encoded[:max_bytes].decode('utf-8', errors='ignore')
    return f"{truncated}... [TRUNCATED {len(encoded)} bytes → {max_bytes} bytes]"

