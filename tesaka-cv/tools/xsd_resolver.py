"""
Resolutor de dependencias XSD para validación local

Resuelve includes/imports de XSD usando archivos locales descargados
en lugar de intentar descargarlos desde URLs remotas.
"""
from pathlib import Path
from typing import Optional
from lxml import etree
import re
import urllib.parse


class LocalXsdResolver(etree.Resolver):
    """Resolutor personalizado para XSD que busca archivos locales primero"""
    
    def __init__(self, xsd_dir: Path):
        """
        Args:
            xsd_dir: Directorio donde están los archivos XSD descargados
        """
        super().__init__()
        self.xsd_dir = Path(xsd_dir).resolve()
        
    def resolve(self, url, pubid, context):
        """
        Resuelve una URL de XSD buscando primero en archivos locales
        
        Args:
            url: URL o ruta del XSD a resolver
            pubid: Public ID (opcional)
            context: Contexto de resolución
        """
        # Si es una URL HTTP/HTTPS, intentar encontrar el archivo local
        if url.startswith('http://') or url.startswith('https://'):
            # Extraer el nombre del archivo de la URL
            parsed = urllib.parse.urlparse(url)
            filename = Path(parsed.path).name
            
            # Buscar el archivo en el directorio local
            local_path = self.xsd_dir / filename
            if local_path.exists():
                return self.resolve_filename(str(local_path), context)
        
        # Si es una ruta relativa, buscar en el directorio XSD
        elif not Path(url).is_absolute():
            # Intentar como ruta relativa desde xsd_dir
            local_path = (self.xsd_dir / url).resolve()
            if local_path.exists() and self.xsd_dir in local_path.parents:
                return self.resolve_filename(str(local_path), context)
            
            # Intentar solo el nombre del archivo
            filename = Path(url).name
            local_path = self.xsd_dir / filename
            if local_path.exists():
                return self.resolve_filename(str(local_path), context)
        
        # Si es una ruta absoluta local, usar directamente
        elif Path(url).exists():
            return self.resolve_filename(url, context)
        
        # Si no se encuentra, lanzar error
        raise FileNotFoundError(
            f"No se pudo resolver XSD: {url}\n"
            f"Buscado en: {self.xsd_dir}\n"
            f"Ejecuta: python -m tools.download_xsd"
        )


def resolve_xsd_dependencies(xsd_path: Path, xsd_dir: Optional[Path] = None) -> etree.XMLSchema:
    """
    Carga un XSD y resuelve todas sus dependencias usando archivos locales
    
    Args:
        xsd_path: Ruta al archivo XSD principal
        xsd_dir: Directorio donde buscar dependencias (por defecto: directorio del XSD)
        
    Returns:
        Esquema XML validado y listo para usar
    """
    if xsd_dir is None:
        xsd_dir = xsd_path.parent
    
    # Crear parser con resolutor personalizado
    parser = etree.XMLParser()
    parser.resolvers.add(LocalXsdResolver(xsd_dir))
    
    # Parsear XSD
    try:
        xsd_doc = etree.parse(str(xsd_path), parser)
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Error de sintaxis en XSD: {e}")
    except FileNotFoundError as e:
        raise FileNotFoundError(str(e))
    
    # Crear schema
    try:
        schema = etree.XMLSchema(xsd_doc)
        return schema
    except etree.XMLSchemaParseError as e:
        # Intentar resolver dependencias faltantes
        error_msg = str(e)
        missing_files = re.findall(r"'(https?://[^']+\.xsd)'", error_msg)
        missing_files.extend(re.findall(r"'([^']+\.xsd)'", error_msg))
        
        if missing_files:
            raise FileNotFoundError(
                f"Faltan archivos XSD dependientes:\n"
                + "\n".join(f"  - {f}" for f in set(missing_files))
                + f"\n\nBuscados en: {xsd_dir}\n"
                f"Ejecuta: python -m tools.download_xsd"
            )
        else:
            raise ValueError(f"Error al crear esquema XSD: {e}")


def validate_xml_against_xsd(xml_path: Path, xsd_path: Path, xsd_dir: Optional[Path] = None) -> tuple[bool, list[str]]:
    """
    Valida un XML contra un XSD resolviendo dependencias localmente
    
    Args:
        xml_path: Ruta al archivo XML
        xsd_path: Ruta al archivo XSD principal
        xsd_dir: Directorio donde buscar dependencias XSD
        
    Returns:
        Tupla (es_valido, lista_errores)
    """
    errors = []
    
    try:
        # Parsear XML
        xml_doc = etree.parse(str(xml_path))
        
        # Resolver y cargar XSD con dependencias
        if xsd_dir is None:
            xsd_dir = xsd_path.parent
        
        schema = resolve_xsd_dependencies(xsd_path, xsd_dir)
        
        # Validar
        if schema.validate(xml_doc):
            return True, []
        else:
            for error in schema.error_log:
                errors.append(
                    f"Línea {error.line}, columna {error.column}: {error.message}"
                )
            return False, errors
            
    except FileNotFoundError as e:
        errors.append(str(e))
        return False, errors
    except etree.XMLSyntaxError as e:
        errors.append(f"Error de sintaxis XML: {str(e)}")
        return False, errors
    except Exception as e:
        errors.append(f"Error inesperado: {str(e)}")
        return False, errors

