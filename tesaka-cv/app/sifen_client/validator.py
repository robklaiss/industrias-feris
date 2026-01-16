"""
Validación de XML para SIFEN
"""
import xml.etree.ElementTree as ET
from lxml import etree
from typing import Dict, Any, List, Optional
from pathlib import Path
import httpx

try:
    from .angular_bridge import AngularBridge
    from .xml_utils import clean_xml, validate_xml_prolog, ensure_utf8_encoding
except ImportError:
    AngularBridge = None
    clean_xml = lambda x: x.strip()
    validate_xml_prolog = lambda x: (True, None)
    ensure_utf8_encoding = lambda x: x.encode('utf-8')


class SifenValidator:
    """
    Validador de XML para Documentos Electrónicos SIFEN
    """
    
    def __init__(self):
        """Inicializa el validador"""
        # TODO: Cargar esquema XSD cuando esté disponible
        # self.xsd_schema = self._load_xsd_schema()
        self.prevalidador_url = "https://ekuatia.set.gov.py/prevalidador/validacion"
        # Posibles endpoints API del Prevalidador Angular (comúnmente tienen API REST detrás)
        self.prevalidador_api_urls = [
            "https://ekuatia.set.gov.py/prevalidador/api/validar",  # Tentativo
            "https://ekuatia.set.gov.py/api/prevalidador/validar",  # Tentativo
            "https://ekuatia.set.gov.py/prevalidador/validar",  # Tentativo
        ]
        # Bridge para descubrir APIs de aplicación Angular
        if AngularBridge:
            self.angular_bridge = AngularBridge("https://ekuatia.set.gov.py/prevalidador")
        else:
            self.angular_bridge = None
    
    def _load_xsd_schema(self) -> Optional[Any]:
        """
        Carga el esquema XSD de SIFEN
        
        TODO: Implementar cuando se tenga el XSD oficial
        - Descargar desde documentación oficial
        - Guardar en schemas/sifen/
        - Usar lxml o xmlschema para validar
        """
        xsd_path = Path(__file__).parent.parent.parent / "schemas" / "sifen" / "de.xsd"
        
        if xsd_path.exists():
            # TODO: Implementar carga de XSD
            # from xmlschema import XMLSchema
            # return XMLSchema(str(xsd_path))
            pass
        
        return None
    
    def validate_xml_structure(self, xml_content: str) -> Dict[str, Any]:
        """
        Valida la estructura básica del XML (well-formed)
        
        Args:
            xml_content: Contenido XML
            
        Returns:
            Resultado de validación
        """
        errors = []
        
        try:
            ET.fromstring(xml_content)
            return {
                "valid": True,
                "errors": []
            }
        except ET.ParseError as e:
            errors.append(f"XML mal formado: {str(e)}")
            return {
                "valid": False,
                "errors": errors
            }
    
    def validate_against_xsd(self, xml_content: str) -> Dict[str, Any]:
        """
        Valida el XML contra el esquema XSD de SIFEN
        
        Args:
            xml_content: Contenido XML
            
        Returns:
            Resultado de validación
        """
        # Validar estructura básica primero
        structure_check = self.validate_xml_structure(xml_content)
        if not structure_check["valid"]:
            return structure_check
        
        # Intentar validar contra XSD si está disponible
        from pathlib import Path
        try:
            from lxml import etree
            from .xml_utils import clean_xml
            
            xml_clean = clean_xml(xml_content)
            errors = []
            
            # Buscar XSD en directorio xsd/
            xsd_dir = Path(__file__).parent.parent.parent / "xsd"
            xsd_path = None
            
            # Detectar elemento raíz del XML para usar el XSD correcto
            try:
                xml_doc_test = etree.fromstring(xml_clean.encode('utf-8'))
                root_tag = xml_doc_test.tag
                
                # Si el elemento raíz es rDE, usar siRecepDE_v150.xsd
                if 'rDE' in root_tag or root_tag.endswith('}rDE'):
                    for pattern in ["siRecepDE_v150.xsd", "siRecepDE_v141.xsd", "siRecepDE_v130.xsd"]:
                        candidate = xsd_dir / pattern
                        if candidate.exists():
                            xsd_path = candidate
                            break
            except:
                pass
            
            # Si no se encontró o el raíz es DE, usar DE_v150.xsd
            if xsd_path is None:
                for pattern in ["DE_v150.xsd", "DE_v1.5.0.xsd", "DE_v130.xsd", "DE_v1.3.0.xsd", "DE.xsd"]:
                    candidate = xsd_dir / pattern
                    if candidate.exists():
                        xsd_path = candidate
                        break
            
            if xsd_path is None:
                # Buscar cualquier siRecepDE*.xsd primero, luego DE*.xsd
                recep_xsd_files = list(xsd_dir.glob("siRecepDE*.xsd"))
                if recep_xsd_files:
                    xsd_path = recep_xsd_files[0]
                else:
                    de_xsd_files = list(xsd_dir.glob("DE*.xsd"))
                    if de_xsd_files:
                        xsd_path = de_xsd_files[0]
            
            if xsd_path is None or not xsd_path.exists():
                return {
                    "valid": None,
                    "errors": [],
                    "note": "Esquema XSD no encontrado. Ejecuta: python -m tools.download_xsd"
                }
            
            try:
                # Usar resolutor de dependencias local
                import sys
                sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
                try:
                    from xsd_resolver import resolve_xsd_dependencies
                    
                    # Parsear XML
                    xml_doc = etree.fromstring(xml_clean.encode('utf-8'))
                    
                    # Resolver XSD con dependencias
                    schema = resolve_xsd_dependencies(xsd_path, xsd_dir)
                    
                    # Validar
                    if schema.validate(xml_doc):
                        return {
                            "valid": True,
                            "errors": [],
                            "xsd_used": str(xsd_path.name)
                        }
                    else:
                        for error in schema.error_log:
                            errors.append(
                                f"Línea {error.line}, columna {error.column}: {error.message}"
                            )
                        return {
                            "valid": False,
                            "errors": errors,
                            "xsd_used": str(xsd_path.name)
                        }
                except ImportError:
                    # Fallback si no se puede importar el resolutor
                    # Parsear XML
                    xml_doc = etree.fromstring(xml_clean.encode('utf-8'))
                    
                    # Parsear y validar XSD (puede fallar si hay dependencias)
                    xsd_doc = etree.parse(str(xsd_path))
                    schema = etree.XMLSchema(xsd_doc)
                    
                    # Validar
                    if schema.validate(xml_doc):
                        return {
                            "valid": True,
                            "errors": [],
                            "xsd_used": str(xsd_path.name)
                        }
                    else:
                        for error in schema.error_log:
                            errors.append(
                                f"Línea {error.line}, columna {error.column}: {error.message}"
                            )
                        return {
                            "valid": False,
                            "errors": errors,
                            "xsd_used": str(xsd_path.name)
                        }
                    
            except etree.XMLSyntaxError as e:
                return {
                    "valid": False,
                    "errors": [f"Error de sintaxis XML: {str(e)}"],
                    "xsd_used": None
                }
            except etree.XMLSchemaParseError as e:
                return {
                    "valid": None,
                    "errors": [f"Error al parsear XSD: {str(e)}"],
                    "xsd_used": str(xsd_path.name) if xsd_path else None,
                    "note": "Verifica que el XSD y sus dependencias estén correctamente descargados"
                }
            except Exception as e:
                return {
                    "valid": None,
                    "errors": [f"Error inesperado: {str(e)}"],
                    "xsd_used": str(xsd_path.name) if xsd_path else None
                }
        except ImportError:
            return {
                "valid": None,
                "errors": [],
                "note": "lxml no está instalado. Instala con: pip install lxml"
            }
    
    def prevalidate_with_service(
        self,
        xml_content: str,
        modo: Optional[int] = None,
        captcha: Optional[str] = None,
        cookie: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Prevalida usando el servicio Prevalidador SIFEN
        
        Este método realiza POST directo al endpoint oficial de SIFEN:
        https://ekuatia.set.gov.py/validar/validar?modo={0|1}
        
        Args:
            xml_content: Contenido XML del DE
            modo: Modo del validador (0=Prod, 1=Test). Si None, usa SIFEN_ENV.
            captcha: Valor del header 'captcha' (requerido por SIFEN)
            cookie: Cookie header opcional para sesión
            
        Returns:
            Resultado de prevalidación
        """
        # Auto-detectar modo desde SIFEN_ENV si no se especificó
        if modo is None:
            try:
                from .env_validator import get_current_env, env_to_modo
                current_env = get_current_env()
                modo = env_to_modo(current_env)
            except ImportError:
                return {
                    "valid": False,
                    "error": "Parámetro 'modo' es requerido (0=PROD, 1=TEST) o configurar SIFEN_ENV"
                }
        
        if captcha is None:
            return {
                "valid": False,
                "error": "Falta captcha (copiar del navegador: DevTools > Network > validar > Request Headers > captcha)",
                "suggestion": "Abrir https://ekuatia.set.gov.py/prevalidador/validacion, resolver captcha, copiar valor del header 'captcha' en DevTools"
            }
        
        # Limpiar XML antes de enviarlo (remover BOM, espacios iniciales)
        xml_content_clean = clean_xml(xml_content)
        
        # Verificar coherencia QR vs modo
        try:
            from .qr_inspector import extract_dcar_qr, detect_qr_env
            
            qr_url = extract_dcar_qr(xml_content_clean)
            if qr_url:
                qr_env = detect_qr_env(qr_url)
                
                # Detectar mismatch
                mismatch = None
                if modo == 0 and qr_env == "TEST":
                    mismatch = "QR TEST detectado con modo=0 (prod). Esto causará error 2502."
                elif modo == 1 and qr_env == "PROD":
                    mismatch = "QR PROD detectado con modo=1 (test). Esto causará error 2502."
                
                if mismatch:
                    return {
                        "valid": False,
                        "error": mismatch,
                        "qr_env": qr_env,
                        "modo": modo,
                        "suggestion": f"Regenerar el XML con SIFEN_ENV={'prod' if modo == 0 else 'test'} para que el QR coincida con el modo de validación."
                    }
        except ImportError:
            pass  # qr_inspector no disponible, continuar sin verificación
        
        # Validar prolog antes de enviar
        prolog_valid, prolog_error = validate_xml_prolog(xml_content_clean)
        if not prolog_valid:
            return {
                "valid": False,
                "error": f"Error en prolog XML: {prolog_error}",
                "suggestion": "Asegúrese de que el XML empiece exactamente con <?xml version=\"1.0\" encoding=\"UTF-8\"?> sin espacios antes"
            }
        
        # Convertir a bytes UTF-8 sin BOM
        xml_bytes = ensure_utf8_encoding(xml_content_clean)
        
        # POST directo al endpoint oficial SIFEN
        sifen_url = "https://ekuatia.set.gov.py/validar/validar"
        
        headers = {
            "accept": "application/json, text/plain, */*",
            "content-type": "application/xml;charset=UTF-8",
            "origin": "https://ekuatia.set.gov.py",
            "referer": "https://ekuatia.set.gov.py/prevalidador/validacion",
            "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "captcha": captcha,
        }
        
        if cookie:
            headers["cookie"] = cookie
        
        try:
            response = httpx.post(
                sifen_url,
                params={"modo": str(modo)},
                headers=headers,
                content=xml_bytes,
                timeout=60,
                follow_redirects=False
            )
            
            ct = (response.headers.get("content-type") or "").lower()
            
            # Parsear respuesta JSON
            if "application/json" in ct:
                try:
                    json_data = response.json()
                    
                    # Mapear respuesta SIFEN a formato estándar
                    valid = None
                    if isinstance(json_data, dict):
                        # Intentar detectar si es válido
                        if "valido" in json_data:
                            valid = json_data["valido"]
                        elif "valid" in json_data:
                            valid = json_data["valid"]
                        elif "errores" in json_data:
                            valid = len(json_data.get("errores", [])) == 0
                        elif "estado" in json_data:
                            valid = json_data["estado"] in ["APROBADO", "OK", "VALIDO"]
                    
                    return {
                        "valid": valid,
                        "status_code": response.status_code,
                        "response": json_data,
                        "errores": json_data.get("errores", []),
                        "format": "json",
                        "endpoint": sifen_url,
                        "modo": modo
                    }
                except Exception as e:
                    return {
                        "valid": None,
                        "error": f"Error parseando JSON: {str(e)}",
                        "response_text": response.text[:500],
                        "status_code": response.status_code
                    }
            
            # Respuesta HTML (captcha inválido, cookies faltantes, etc.)
            else:
                text = response.text or ""
                return {
                    "valid": None,
                    "error": "Respuesta HTML recibida (no JSON)",
                    "status_code": response.status_code,
                    "snippet": text[:600],
                    "suggestion": "Posibles causas: captcha inválido/expirado, cookies faltantes, endpoint cambió, o modo incorrecto para el QR"
                }
        
        except httpx.TimeoutException:
            return {
                "valid": None,
                "error": "Timeout al conectar con SIFEN (60s)",
                "suggestion": "Verificar conectividad o intentar más tarde"
            }
        except httpx.RequestError as e:
            return {
                "valid": None,
                "error": f"Error de conexión: {str(e)}",
                "suggestion": "Verificar conectividad a https://ekuatia.set.gov.py"
            }
        except Exception as e:
            return {
                "valid": None,
                "error": f"Error inesperado: {str(e)}",
            }
    
    def validate(self, xml_content: str, use_prevalidador: bool = True) -> Dict[str, Any]:
        """
        Valida un XML de Documento Electrónico
        
        Args:
            xml_content: Contenido XML
            use_prevalidador: Si usar el Prevalidador SIFEN además de validación local
            
        Returns:
            Resultado completo de validación
        """
        results = {
            "valid": False,
            "errors": [],
            "warnings": [],
        }
        
        # 1. Validar estructura básica
        structure_result = self.validate_xml_structure(xml_content)
        if not structure_result["valid"]:
            results["errors"].extend(structure_result["errors"])
            return results
        
        # 2. Validar contra XSD (si disponible)
        xsd_result = self.validate_against_xsd(xml_content)
        if not xsd_result["valid"]:
            results["errors"].extend(xsd_result.get("errors", []))
        if xsd_result.get("note"):
            results["warnings"].append(xsd_result["note"])
        
        # 3. Prevalidar con servicio (opcional)
        if use_prevalidador:
            prevalidation = self.prevalidate_with_service(xml_content)
            if not prevalidation.get("valid"):
                results["errors"].append(
                    f"Prevalidador: {prevalidation.get('error', 'Errores no especificados')}"
                )
            results["prevalidation"] = prevalidation
        
        # Determinar validez final
        results["valid"] = len(results["errors"]) == 0
        
        return results

