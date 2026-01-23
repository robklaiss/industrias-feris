#!/usr/bin/env python3
"""
Validador XSD local para documentos SIFEN
"""
import os
from pathlib import Path
from lxml import etree
from typing import Tuple, Optional

class SifenXSDValidator:
    """Validador de XML contra XSDs de SIFEN con resolución local"""
    
    def __init__(self, schemas_dir: Optional[Path] = None):
        """
        Inicializar el validador con directorio de schemas
        
        Args:
            schemas_dir: Directorio donde están los XSDs (default: schemas_sifen/)
        """
        if schemas_dir is None:
            # Buscar en el directorio del script o en el project root
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            schemas_dir = project_root / "schemas_sifen"
        
        self.schemas_dir = Path(schemas_dir)
        if not self.schemas_dir.exists():
            raise ValueError(f"Directorio de schemas no encontrado: {self.schemas_dir}")
        
        # Cache de schemas ya cargados
        self._schema_cache = {}
    
    def _get_local_resolver(self) -> etree.Resolver:
        """Crear un resolver que busca los XSDs localmente"""
        
        def local_resolver(url, public_id, context):
            # Convertir URL a path local
            if url.startswith("https://ekuatia.set.gov.py/sifen/xsd/"):
                filename = url.split("/")[-1]
                local_path = self.schemas_dir / filename
                if local_path.exists():
                    return etree.parse(str(local_path))
            
            # Si no es URL de SIFEN, intentar resolver normalmente
            if url.startswith("file://"):
                return etree.parse(url[7:])
            
            return None
        
        return etree.Resolver(local_resolver)
    
    def _load_schema(self, xsd_name: str) -> etree.XMLSchema:
        """
        Cargar un XSD con resolución de includes/imports local
        
        Args:
            xsd_name: Nombre del archivo XSD (ej: "DE_v150.xsd")
            
        Returns:
            Schema XML de lxml validado
        """
        if xsd_name in self._schema_cache:
            return self._schema_cache[xsd_name]
        
        xsd_path = self.schemas_dir / xsd_name
        if not xsd_path.exists():
            raise FileNotFoundError(f"XSD no encontrado: {xsd_path}")
        
        # Crear un parser custom que resuelve URLs localmente
        class LocalXMLSchema(etree.XMLSchema):
            def __init__(self, etree_xml, **kwargs):
                super().__init__(etree_xml, **kwargs)
        
        # Crear un diccionario de mapeo de URLs a archivos locales
        url_map = {
            "https://ekuatia.set.gov.py/sifen/xsd/Paises_v100.xsd": str(self.schemas_dir / "Paises_v100.xsd"),
            "https://ekuatia.set.gov.py/sifen/xsd/Departamentos_v141.xsd": str(self.schemas_dir / "Departamentos_v141.xsd"),
            "https://ekuatia.set.gov.py/sifen/xsd/Monedas_v150.xsd": str(self.schemas_dir / "Monedas_v150.xsd"),
            "https://ekuatia.set.gov.py/sifen/xsd/Unidades_Medida_v141.xsd": str(self.schemas_dir / "Unidades_Medida_v141.xsd"),
            "https://ekuatia.set.gov.py/sifen/xsd/DE_Types_v150.xsd": str(self.schemas_dir / "DE_Types_v150.xsd"),
            "https://ekuatia.set.gov.py/sifen/xsd/xmldsig-core-schema.xsd": str(self.schemas_dir / "xmldsig-core-schema.xsd"),
        }
        
        # Leer el XSD y reemplazar las URLs de include con archivos locales
        xsd_content = xsd_path.read_text(encoding='utf-8')
        for url, local_path in url_map.items():
            if Path(local_path).exists():
                # Reemplazar schemaLocation con el archivo local
                xsd_content = xsd_content.replace(url, f"file://{local_path}")
        
        # Parsear el XSD modificado
        xsd_doc = etree.fromstring(xsd_content.encode('utf-8'))
        schema = LocalXMLSchema(xsd_doc)
        
        # Cache
        self._schema_cache[xsd_name] = schema
        return schema
    
    def validate_de(self, xml_bytes: bytes, xsd_version: str = "150") -> Tuple[bool, Optional[str]]:
        """
        Validar un Documento Electrónico (DE) contra su XSD
        
        Args:
            xml_bytes: XML del DE en bytes
            xsd_version: Versión del XSD (default: "150")
            
        Returns:
            Tuple (valido, error_message)
        """
        try:
            schema = self._load_schema(f"DE_v{xsd_version}.xsd")
            xml_doc = etree.fromstring(xml_bytes)
            
            if schema.validate(xml_doc):
                return True, None
            else:
                # Obtener errores de validación
                errors = []
                for error in schema.error_log:
                    errors.append(f"Línea {error.line}: {error.message}")
                return False, "\n".join(errors)
                
        except etree.XMLSyntaxError as e:
            return False, f"Error de sintaxis XML: {e}"
        except Exception as e:
            return False, f"Error validando: {e}"
    
    def validate_lote(self, xml_bytes: bytes, xsd_version: str = "150") -> Tuple[bool, Optional[str]]:
        """
        Validar un lote (rLoteDE) contra su XSD
        
        Args:
            xml_bytes: XML del lote en bytes
            xsd_version: Versión del XSD (default: "150")
            
        Returns:
            Tuple (valido, error_message)
        """
        try:
            schema = self._load_schema(f"rLoteDE_v{xsd_version}.xsd")
            xml_doc = etree.fromstring(xml_bytes)
            
            if schema.validate(xml_doc):
                return True, None
            else:
                # Obtener errores de validación
                errors = []
                for error in schema.error_log:
                    errors.append(f"Línea {error.line}: {error.message}")
                return False, "\n".join(errors)
                
        except etree.XMLSyntaxError as e:
            return False, f"Error de sintaxis XML: {e}"
        except Exception as e:
            return False, f"Error validando: {e}"
    
    def list_available_schemas(self) -> list:
        """Listar todos los XSDs disponibles en el directorio"""
        xsd_files = []
        for file in self.schemas_dir.glob("*.xsd"):
            xsd_files.append(file.name)
        return sorted(xsd_files)


# Funciones de conveniencia para uso directo
def validate_de_xsd(xml_bytes: bytes, version: str = "150") -> Tuple[bool, Optional[str]]:
    """
    Validar DE contra XSD (función de conveniencia)
    
    Args:
        xml_bytes: XML del DE en bytes
        version: Versión del XSD (default: "150")
        
    Returns:
        Tuple (valido, error_message)
    """
    validator = SifenXSDValidator()
    return validator.validate_de(xml_bytes, version)


def validate_lote_xsd(xml_bytes: bytes, version: str = "150") -> Tuple[bool, Optional[str]]:
    """
    Validar lote contra XSD (función de conveniencia)
    
    Args:
        xml_bytes: XML del lote en bytes
        version: Versión del XSD (default: "150")
        
    Returns:
        Tuple (valido, error_message)
    """
    validator = SifenXSDValidator()
    return validator.validate_lote(xml_bytes, version)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Uso: python xsd_validate.py <archivo.xml> [tipo] [versión]")
        print("  tipo: 'de' (default) o 'lote'")
        print("  versión: '150' (default)")
        sys.exit(1)
    
    xml_file = Path(sys.argv[1])
    if not xml_file.exists():
        print(f"Error: Archivo no encontrado: {xml_file}")
        sys.exit(1)
    
    xml_type = sys.argv[2] if len(sys.argv) > 2 else "de"
    version = sys.argv[3] if len(sys.argv) > 3 else "150"
    
    # Leer XML
    xml_bytes = xml_file.read_bytes()
    
    # Validar
    if xml_type == "de":
        valid, error = validate_de_xsd(xml_bytes, version)
    elif xml_type == "lote":
        valid, error = validate_lote_xsd(xml_bytes, version)
    else:
        print(f"Error: Tipo desconocido: {xml_type}")
        sys.exit(1)
    
    if valid:
        print(f"✅ XML válido contra XSD v{version}")
        sys.exit(0)
    else:
        print(f"❌ XML inválido contra XSD v{version}:")
        print(error)
        sys.exit(1)
