"""
Rutas para descarga de artifacts de SIFEN
"""
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException
from fastapi.responses import Response, JSONResponse, HTMLResponse, HTMLResponse
from jinja2 import Environment


def register_artifacts_routes(app, jinja_env: Environment):
    """Registra las rutas de artifacts en la app"""
    
    # Directorio de artifacts
    ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        from fastapi.responses import HTMLResponse
        return HTMLResponse(template.render(request=request, **kwargs))
    
    def find_latest_did() -> Optional[str]:
        """Encuentra el dId más reciente basado en los directorios de artifacts"""
        latest_dir = None
        latest_did = None
        
        # Buscar directorios que representen dIds
        for item in ARTIFACTS_DIR.iterdir():
            if item.is_dir() and validate_did(item.name):
                if latest_dir is None or item.stat().st_mtime > latest_dir.stat().st_mtime:
                    latest_dir = item
                    latest_did = item.name
        
        # Si no se encuentran directorios, fallback al método legacy con sent_lote
        if not latest_did:
            # Corregir regex para permitir "_" en dId
            pattern = re.compile(r'^sent_lote(.+?)_(\d+)_(\d+)\.xml$')
            latest_file = None
            
            for file_path in ARTIFACTS_DIR.glob("sent_lote*.xml"):
                match = pattern.match(file_path.name)
                if match:
                    did = match.group(1).lstrip('_')  # Quitar el guión bajo inicial si existe
                    if latest_file is None or file_path.stat().st_mtime > latest_file.stat().st_mtime:
                        latest_file = file_path
                        latest_did = did
        
        return latest_did
    
    def find_artifact_by_did(did: str, artifact_type: str) -> Optional[Path]:
        """
        Busca un artifact por dId y tipo.
        Soporta el modo folder (artifacts/<dId>/) y el modo legacy.
        
        artifact_type puede ser:
        - 'de': DE_TAL_CUAL_TRANSMITIDO.xml (el XML enviado)
        - 'rechazo': XML_DE_RECHAZO.xml (respuesta de rechazo)
        - 'meta': metadata.json
        """
        # Modo folder: artifacts/<dId>/
        base_dir = ARTIFACTS_DIR / did
        if base_dir.is_dir():
            if os.getenv('SIFEN_DEBUG') == '1':
                print(f"[DEBUG] Found folder for dId={did}: {base_dir}")
            
            if artifact_type == 'de':
                # Buscar en orden: DE_TAL_CUAL_TRANSMITIDO.xml, DE.xml, xml_bumped_*.xml (más nuevo)
                candidates = []
                
                # 1. DE_TAL_CUAL_TRANSMITIDO.xml
                de_transmitido = base_dir / "DE_TAL_CUAL_TRANSMITIDO.xml"
                if de_transmitido.exists():
                    candidates.append((de_transmitido.stat().st_mtime, de_transmitido))
                
                # 2. DE.xml
                de_xml = base_dir / "DE.xml"
                if de_xml.exists():
                    candidates.append((de_xml.stat().st_mtime, de_xml))
                
                # 3. xml_bumped_*.xml (el más nuevo)
                for bumped in base_dir.glob("xml_bumped_*.xml"):
                    candidates.append((bumped.stat().st_mtime, bumped))
                
                if candidates:
                    # Devolver el más nuevo
                    newest = max(candidates, key=lambda x: x[0])[1]
                    if os.getenv('SIFEN_DEBUG') == '1':
                        print(f"[DEBUG] Selected DE file: {newest}")
                    return newest
            
            elif artifact_type == 'meta':
                meta_json = base_dir / "meta.json"
                if meta_json.exists():
                    if os.getenv('SIFEN_DEBUG') == '1':
                        print(f"[DEBUG] Found meta.json: {meta_json}")
                    return meta_json
            
            elif artifact_type == 'rechazo':
                # Buscar rechazo.json o rechazo.xml
                rechazo_json = base_dir / "rechazo.json"
                rechazo_xml = base_dir / "rechazo.xml"
                
                if rechazo_json.exists():
                    if os.getenv('SIFEN_DEBUG') == '1':
                        print(f"[DEBUG] Found rechazo.json: {rechazo_json}")
                    return rechazo_json
                elif rechazo_xml.exists():
                    if os.getenv('SIFEN_DEBUG') == '1':
                        print(f"[DEBUG] Found rechazo.xml: {rechazo_xml}")
                    return rechazo_xml
        
        # Modo legacy: buscar en archivos sent_lote*.xml
        if os.getenv('SIFEN_DEBUG') == '1':
            print(f"[DEBUG] Using legacy mode for dId={did}, artifact_type={artifact_type}")
        
        if artifact_type == 'de':
            # Buscar el XML enviado con este dId
            # Formato: sent_lote_{did}_{timestamp}.xml o sent_lote-{did}_{timestamp}.xml
            # Corregir regex para permitir "_" en dId
            pattern1 = re.compile(f'^sent_lote_{re.escape(did)}_\\d+_\\d+\\.xml$')
            pattern2 = re.compile(f'^sent_lote-{re.escape(did)}_\\d+_\\d+\\.xml$')
            
            for file_path in ARTIFACTS_DIR.glob("sent_lote*.xml"):
                if pattern1.match(file_path.name) or pattern2.match(file_path.name):
                    return file_path
        
        elif artifact_type == 'rechazo':
            # Buscar respuesta de rechazo asociada al dId
            for file_path in ARTIFACTS_DIR.glob("response_recepcion_*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # El dId puede estar en el campo dId del response
                        if data.get('dId') == did or data.get('request_id', '').startswith(did):
                            return file_path
                except:
                    continue
        
        elif artifact_type == 'meta':
            # Buscar metadata asociada al dId
            # Puede estar en varios formatos, buscamos coincidencias
            for file_path in ARTIFACTS_DIR.glob(f"*{did}*.json"):
                if 'response' not in file_path.name and 'smoke_test' not in file_path.name:
                    return file_path
            
            # También buscar en archivos de consulta RUC
            for file_path in ARTIFACTS_DIR.glob("consulta_ruc_*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if data.get('dId') == did:
                            return file_path
                except:
                    continue
        
        return None
    
    # Registrar todas las rutas
    @app.get("/api/v1/artifacts/latest")
    async def get_latest_artifacts():
        """
        Retorna información del lote más reciente y los artifacts disponibles
        """
        try:
            latest_did = find_latest_did()
            
            if not latest_did:
                return JSONResponse({
                    "error": "No se encontraron artifacts",
                    "message": "No hay archivos de lote enviados"
                }, status_code=404)
            
            # Verificar qué archivos están disponibles para este dId
            available = {
                "de": find_artifact_by_did(latest_did, 'de') is not None,
                "rechazo": find_artifact_by_did(latest_did, 'rechazo') is not None,
                "meta": find_artifact_by_did(latest_did, 'meta') is not None
            }
            
            return JSONResponse({
                "dId": latest_did,
                "available": available,
                "endpoints": {
                    "de": f"/api/v1/artifacts/{latest_did}/de",
                    "rechazo": f"/api/v1/artifacts/{latest_did}/rechazo" if available["rechazo"] else None,
                    "meta": f"/api/v1/artifacts/{latest_did}/meta" if available["meta"] else None
                }
            })
            
        except Exception as e:
            return JSONResponse({
                "error": "Error interno",
                "message": str(e)
            }, status_code=500)
    
    @app.get("/api/v1/artifacts/{did}/de")
    async def download_de_xml(did: str):
        """
        Descarga el DE_TAL_CUAL_TRANSMITIDO.xml para un dId específico
        """
        # Validar dId
        if not validate_did(did):
            raise HTTPException(status_code=400, detail="dId inválido")
        
        # Buscar el archivo
        artifact_path = find_artifact_by_did(did, 'de')
        
        if not artifact_path or not artifact_path.exists():
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        
        # Leer el contenido
        try:
            content = artifact_path.read_bytes()
            
            return Response(
                content=content,
                media_type="application/xml",
                headers={
                    "Content-Disposition": f'attachment; filename="DE_TAL_CUAL_TRANSMITIDO_{did}.xml"'
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error leyendo archivo: {str(e)}")
    
    @app.get("/api/v1/artifacts/{did}/rechazo")
    async def download_rechazo_xml(did: str):
        """
        Descarga el XML_DE_RECHAZO.xml para un dId específico
        """
        # Validar dId
        if not validate_did(did):
            raise HTTPException(status_code=400, detail="dId inválido")
        
        # Buscar el archivo de respuesta
        response_path = find_artifact_by_did(did, 'rechazo')
        
        if not response_path or not response_path.exists():
            raise HTTPException(status_code=404, detail="Archivo de rechazo no encontrado")
        
        # Extraer el XML del response
        try:
            with open(response_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # El XML está en el campo raw_xml
            xml_content = data.get('raw_xml', '')
            
            if not xml_content:
                raise HTTPException(status_code=404, detail="No se encontró XML en la respuesta")
            
            return Response(
                content=xml_content.encode('utf-8'),
                media_type="application/xml",
                headers={
                    "Content-Disposition": f'attachment; filename="XML_DE_RECHAZO_{did}.xml"'
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error procesando archivo: {str(e)}")
    
    @app.get("/api/v1/artifacts/{did}/meta")
    async def download_meta_json(did: str):
        """
        Descarga la metadata JSON para un dId específico
        """
        # Validar dId
        if not validate_did(did):
            raise HTTPException(status_code=400, detail="dId inválido")
        
        # Buscar el archivo de metadata
        meta_path = find_artifact_by_did(did, 'meta')
        
        if not meta_path or not meta_path.exists():
            raise HTTPException(status_code=404, detail="Metadata no encontrada")
        
        # Leer el contenido
        try:
            content = meta_path.read_text(encoding='utf-8')
            
            # Validar que sea JSON válido
            try:
                json.loads(content)
            except json.JSONDecodeError:
                raise HTTPException(status_code=500, detail="El archivo no contiene JSON válido")
            
            return Response(
                content=content,
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="metadata_{did}.json"'
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error leyendo archivo: {str(e)}")
    
    @app.get("/api/v1/artifacts/{did}")
    async def get_artifacts_info(did: str):
        """
        Retorna información sobre los artifacts disponibles para un dId específico
        """
        # Validar dId
        if not validate_did(did):
            raise HTTPException(status_code=400, detail="dId inválido")
        
        # Verificar qué archivos están disponibles
        available = {
            "de": find_artifact_by_did(did, 'de') is not None,
            "rechazo": find_artifact_by_did(did, 'rechazo') is not None,
            "meta": find_artifact_by_did(did, 'meta') is not None
        }
        
        if not any(available.values()):
            raise HTTPException(status_code=404, detail=f"No se encontraron artifacts para dId={did}")
        
        return JSONResponse({
            "dId": did,
            "available": available,
            "endpoints": {
                "de": f"/api/v1/artifacts/{did}/de" if available["de"] else None,
                "rechazo": f"/api/v1/artifacts/{did}/rechazo" if available["rechazo"] else None,
                "meta": f"/api/v1/artifacts/{did}/meta" if available["meta"] else None
            }
        })
    
    # Página web para listar artifacts (opcional)
    @app.get("/artifacts", response_class=HTMLResponse)
    async def artifacts_list_page(request: Request):
        """Página web para listar y descargar artifacts"""
        # Obtener lista de todos los dIds disponibles
        dids = set()
        
        # Primero: listar directorios que sean dIds válidos
        for item in ARTIFACTS_DIR.iterdir():
            if item.is_dir() and validate_did(item.name):
                dids.add(item.name)
        
        # Si no hay directorios, fallback al método legacy
        if not dids:
            pattern = re.compile(r'^sent_lote(.+?)_(\d+)_(\d+)\.xml$')
            
            for file_path in ARTIFACTS_DIR.glob("sent_lote*.xml"):
                match = pattern.match(file_path.name)
                if match:
                    did = match.group(1).lstrip('_')  # Quitar el guión bajo inicial si existe
                    dids.add(did)
        
        # Ordenar dIds de más reciente a más antiguo
        dids_with_info = []
        for did in sorted(dids, reverse=True)[:50]:  # Limitar a los 50 más recientes
            available = {
                "de": find_artifact_by_did(did, 'de') is not None,
                "rechazo": find_artifact_by_did(did, 'rechazo') is not None,
                "meta": find_artifact_by_did(did, 'meta') is not None
            }
            dids_with_info.append({
                "did": did,
                "available": available
            })
        
        return render_template_internal("artifacts/list.html", request, artifacts=dids_with_info)


def validate_did(did: str) -> bool:
    """Valida que el dId tenga el formato correcto"""
    # El dId puede tener formatos:
    # - Solo dígitos: 1234567890
    # - Con guiones y guión bajo: 4554737-820260124_222451
    # Permitir dígitos, guiones y guión bajo
    if not did:
        return False
    # Validar que no contenga path traversal
    if '/' in did or '\\' in did or '..' in did:
        return False
    # Validar formato básico
    return bool(re.match(r'^[0-9][0-9\-_]+$', did))
