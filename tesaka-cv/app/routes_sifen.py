"""
Rutas para integración SIFEN
"""
import json
import os
from typing import Optional
from pathlib import Path as FSPath
from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment

from .sifen_client import SifenClient, SifenValidator, get_sifen_config, SifenClientError


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

