"""
Rutas para emitir facturas electrónicas (SIFEN) - MVP
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from fastapi import Request, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from jinja2 import Environment

# Agregar paths para imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.send_sirecepde import send_sirecepde
from tools.build_de import build_de_xml
from tools.build_sirecepde import build_sirecepde_xml
from app.sifen_client.soap_client import SoapClient
from app.sifen_client.config import get_sifen_config


def register_emit_routes(app, jinja_env: Environment):
    """Registra las rutas de emisión"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.post("/api/v1/emitir")
    async def emitir_factura(request: Request):
        """
        Emite una factura electrónica a SIFEN
        
        Recibe JSON con datos de la factura y devuelve:
        - dId: ID del documento
        - CDC: Código de Control (QR)
        - dProtConsLote: Protocolo de lote
        - status: estado inicial
        """
        try:
            # Obtener datos del request
            data = await request.json()
            
            # Validaciones mínimas
            if not data.get("ruc"):
                raise HTTPException(status_code=400, detail="RUC es requerido")
            if not data.get("timbrado"):
                raise HTTPException(status_code=400, detail="Timbrado es requerido")
            
            # ===== GUARDRAIL MODO TEST - PROHIBIDO PROD =====
            # Forzar ambiente TEST sin importar lo que se reciba
            env = "test"
            if data.get("env") == "prod":
                raise HTTPException(status_code=400, detail="MODO TEST: Producción está deshabilitada. No se puede usar env=prod")
            # Usar siempre test
            print(f"🔒 SIFEN_ENV_FORCED=test (MODO TEST) - endpoint emitir")
            # =================================================
            
            # Generar DE XML
            de_xml = build_de_xml(
                ruc=data["ruc"],
                timbrado=data["timbrado"],
                establecimiento=data.get("establecimiento", "001"),
                punto_expedicion=data.get("punto_expedicion", "001"),
                numero_documento=data.get("numero_documento", "0000001"),
                tipo_documento=data.get("tipo_documento", "1"),
                fecha=data.get("fecha"),
                hora=data.get("hora"),
                csc=data.get("csc"),
                env=env
            )
            
            # Generar siRecepDE
            sirecepde_xml = build_sirecepde_xml(
                de_xml_content=de_xml,
                d_id="1"
            )
            
            # ===== SANITIZAR XML ANTES DE ENVIAR (ANTI-REGRESIÓN) =====
            # Eliminar prefijos ds: según reglas anti-regresión
            import re
            sirecepde_xml = re.sub(r'\bds:', '', sirecepde_xml)  # Quitar prefijo ds:
            sirecepde_xml = re.sub(r'\s+xmlns:ds="[^"]*"', '', sirecepde_xml)  # Quitar declaración xmlns:ds
            print("✅ XML sanitizado: prefijos ds: eliminados")
            # ==========================================================
            
            # Crear directorio de artifacts por dId
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            d_id = f"{data['ruc']}{timestamp}"
            artifacts_dir = Path(__file__).parent.parent / "artifacts" / d_id
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            
            # Guardar archivos
            de_path = artifacts_dir / "DE.xml"
            sirecepde_path = artifacts_dir / "siRecepDE.xml"
            de_path.write_text(de_xml, encoding="utf-8")
            sirecepde_path.write_text(sirecepde_xml, encoding="utf-8")
            
            # Enviar a SIFEN
            result = send_sirecepde(
                xml_path=sirecepde_path,
                env=env,
                artifacts_dir=artifacts_dir
            )
            
            # Extraer respuesta
            response_data = {
                "dId": d_id,
                "CDC": result.get("response", {}).get("cdc", ""),
                "dProtConsLote": result.get("response", {}).get("d_prot_cons_lote", ""),
                "status": result.get("response", {}).get("estado", "PENDIENTE"),
                "codigo": result.get("response", {}).get("codigo_respuesta", ""),
                "mensaje": result.get("response", {}).get("mensaje", ""),
                "success": result.get("success", False),
                "artifacts_dir": str(artifacts_dir.relative_to(Path(__file__).parent.parent))
            }
            
            return JSONResponse(content=response_data)
            
        except Exception as e:
            # En caso de error 0160, guardar evidencia
            if "0160" in str(e):
                error_dir = Path(__file__).parent.parent / "artifacts" / f"error_0160_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                error_dir.mkdir(parents=True, exist_ok=True)
                
                # Guardar archivos de evidencia
                if 'de_xml' in locals():
                    (error_dir / f"DE_TAL_CUAL_TRANSMITIDO_{d_id}.xml").write_text(de_xml, encoding="utf-8")
                if 'sirecepde_xml' in locals():
                    (error_dir / f"siRecepDE_TAL_CUAL_TRANSMITIDO_{d_id}.xml").write_text(sirecepde_xml, encoding="utf-8")
                
                # Ejecutar diagnóstico
                try:
                    from tools.agent_extract_0160_artifacts import extract_0160_artifacts
                    report = extract_0160_artifacts(str(artifacts_dir))
                    (error_dir / f"agent_report_0160_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt").write_text(report)
                except:
                    pass
            
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/api/v1/follow")
    async def follow_factura(
        request: Request,
        did: Optional[str] = Query(None, alias="did"),
        prot: Optional[str] = Query(None, alias="prot")
    ):
        """
        Consulta el estado de una factura en SIFEN
        
        Parámetros:
        - did: ID del documento
        - prot: Protocolo de lote (dProtConsLote)
        """
        try:
            if not did and not prot:
                raise HTTPException(status_code=400, detail="Se requiere 'did' o 'prot'")
            
            # Validar que prot no esté vacío si se proporciona
            if prot is not None and prot.strip() == "":
                raise HTTPException(status_code=400, detail="prot (dProtConsLote) es requerido y no puede estar vacío")
            
            # Si se proporcionó prot pero está vacío después de strip, error
            if prot == "":
                raise HTTPException(status_code=400, detail="prot (dProtConsLote) es requerido")
            
            # Usar prot si se proporciona, sino usar did
            dprot_cons_lote = prot if prot else did
            
            # ===== GUARDRAIL MODO TEST - PROHIBIDO PROD =====
            # Forzar ambiente TEST sin importar configuración
            env = "test"
            print(f"🔒 SIFEN_ENV_FORCED=test (MODO TEST) - endpoint follow")
            # ============================================
            config = get_sifen_config(env=env)
            client = SoapClient(config=config)
            
            # Determinar directorio de artifacts
            artifacts_dir = None
            if did:
                # Si tenemos did, usar artifacts/{did}/
                artifacts_dir = Path(__file__).parent.parent / "artifacts" / did
                artifacts_dir.mkdir(parents=True, exist_ok=True)
            else:
                # Si solo tenemos prot, usar artifacts/consulta_{prot}/
                artifacts_dir = Path(__file__).parent.parent / "artifacts" / f"consulta_{prot}"
                artifacts_dir.mkdir(parents=True, exist_ok=True)
            
            # Consultar lote usando el método raw (sin Zeep)
            result = client.consulta_lote_raw(
                dprot_cons_lote=dprot_cons_lote,
                did=did,
                artifacts_dir=artifacts_dir
            )
            
            # Extraer datos relevantes de la respuesta
            response_data = {
                "ok": result.get("ok", False),
                "dCodRes": result.get("codigo_respuesta", ""),
                "dMsgRes": result.get("mensaje", ""),
                "dProtConsLote": result.get("dprot_cons_lote", dprot_cons_lote),
                "dEstRes": result.get("estado", "PENDIENTE"),
                "dFecProc": result.get("fecha_hora", ""),
                "codigo": result.get("codigo_respuesta", ""),
                "mensaje": result.get("mensaje", ""),
                "estado": "APROBADO" if result.get("codigo_respuesta") == "01" else "RECHAZADO" if result.get("codigo_respuesta") == "02" else "PENDIENTE"
            }
            
            return JSONResponse(content=response_data)
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    
    @app.get("/ui/emitir", response_class=HTMLResponse)
    async def ui_emitir(request: Request):
        """Interfaz web mínima para emitir facturas"""
        return render_template_internal("emitir.html", request=request)
    
    @app.get("/ui/seguimiento", response_class=HTMLResponse)
    async def ui_seguimiento(request: Request):
        """Interfaz web para seguimiento de facturas"""
        return render_template_internal("seguimiento.html", request=request)
