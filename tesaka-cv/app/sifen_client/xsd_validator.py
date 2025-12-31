"""
Validador XSD local (offline) para documentos SIFEN.

Valida rDE y rLoteDE contra esquemas XSD locales, resolviendo includes/imports
desde el directorio local en lugar de URLs remotas.
"""
import os
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any

try:
    import lxml.etree as etree
except ImportError:
    raise ImportError("lxml es requerido para validación XSD. Instalar con: pip install lxml")

# Constantes de namespace
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"


class SifenLocalResolver(etree.Resolver):
    """Resolver que mapea URLs de SIFEN a archivos locales."""
    
    def __init__(self, xsd_dir: Path):
        """
        Args:
            xsd_dir: Directorio base donde están los XSD locales
        """
        super().__init__()
        self.xsd_dir = Path(xsd_dir).resolve()
    
    def resolve(self, url: str, pubid: str, context) -> Optional[etree._Entity]:
        """
        Resuelve una URL de SIFEN a un archivo local.
        
        Args:
            url: URL del XSD (puede ser https://ekuatia.set.gov.py/sifen/xsd/... o relativo)
            pubid: Public ID (no usado)
            context: Contexto del parser
            
        Returns:
            Entity resuelta o None si no se puede resolver
        """
        # Caso 1: URL absoluta de SIFEN
        if url.startswith("https://ekuatia.set.gov.py/sifen/xsd/") or \
           url.startswith("http://ekuatia.set.gov.py/sifen/xsd/"):
            # Extraer el nombre del archivo (último segmento)
            fname = url.split("/")[-1]
            local_path = self.xsd_dir / fname
            if local_path.exists():
                return self.resolve_filename(str(local_path), context)
        
        # Caso 2: URL relativa
        elif not url.startswith(("http://", "https://")):
            local_path = self.xsd_dir / url
            if local_path.exists():
                return self.resolve_filename(str(local_path), context)
        
        # No se puede resolver localmente
        return None


def _parser_with_resolver(xsd_dir: Path) -> etree.XMLParser:
    """
    Crea un parser XML con el resolver local configurado.
    
    Args:
        xsd_dir: Directorio base de XSD
        
    Returns:
        Parser configurado
    """
    parser = etree.XMLParser(
        remove_blank_text=False,
        resolve_entities=False,
        no_network=True,
        huge_tree=True
    )
    parser.resolvers.add(SifenLocalResolver(xsd_dir))
    return parser


def load_schema(main_xsd: Path, xsd_dir: Path) -> etree.XMLSchema:
    """
    Carga un esquema XSD desde un archivo, resolviendo includes/imports localmente.
    
    Args:
        main_xsd: Path al archivo XSD principal
        xsd_dir: Directorio base donde están los XSD (para resolver includes)
        
    Returns:
        Esquema XSD cargado y validado
        
    Raises:
        etree.XMLSchemaParseError: Si el XSD es inválido
        FileNotFoundError: Si el archivo no existe
    """
    main_xsd = Path(main_xsd).resolve()
    if not main_xsd.exists():
        raise FileNotFoundError(f"XSD no encontrado: {main_xsd}")
    
    parser = _parser_with_resolver(xsd_dir)
    doc = etree.parse(str(main_xsd), parser)
    return etree.XMLSchema(doc)


def validate_xml_bytes(
    xml_bytes: bytes,
    schema: etree.XMLSchema,
    xsd_dir: Path
) -> Tuple[bool, List[str]]:
    """
    Valida bytes XML contra un esquema XSD.
    
    Args:
        xml_bytes: Contenido XML a validar
        schema: Esquema XSD cargado
        xsd_dir: Directorio base de XSD (para resolver includes en el XML si aplica)
        
    Returns:
        Tupla (ok, lista_errores)
        - ok: True si válido, False si hay errores
        - lista_errores: Lista de strings con formato "line N: mensaje"
    """
    parser = _parser_with_resolver(xsd_dir)
    try:
        doc = etree.fromstring(xml_bytes, parser)
    except etree.XMLSyntaxError as e:
        return (False, [f"Error de sintaxis XML: {e}"])
    
    ok = schema.validate(doc)
    
    if ok:
        return (True, [])
    
    # Recopilar errores (máximo 30)
    errors = []
    for error in schema.error_log[:30]:
        line_info = f"line {error.line}" if error.line else "line ?"
        col_info = f", col {error.column}" if error.column else ""
        errors.append(f"{line_info}{col_info}: {error.message}")
    
    return (False, errors)


def find_xsd_declaring_global_element(
    xsd_dir: Path,
    element_name: str
) -> Optional[Path]:
    """
    Busca un archivo XSD que declare un elemento global con el nombre dado.
    
    Args:
        xsd_dir: Directorio donde buscar
        element_name: Nombre del elemento (ej: "rDE", "rLoteDE")
        
    Returns:
        Path al archivo XSD encontrado, o None si no se encuentra
    """
    xsd_dir = Path(xsd_dir).resolve()
    if not xsd_dir.exists():
        return None
    
    # Buscar en todos los .xsd
    candidates = []
    for xsd_file in xsd_dir.glob("*.xsd"):
        try:
            content = xsd_file.read_bytes()
            # Buscar patrón: <xs:element name="element_name"
            pattern = f'<xs:element name="{element_name}"'.encode('utf-8')
            if pattern in content:
                candidates.append(xsd_file)
        except Exception:
            continue
    
    if not candidates:
        return None
    
    # Preferir archivos con "siRecep" en el nombre si hay varios
    si_recep_candidates = [c for c in candidates if "siRecep" in c.name.lower()]
    if si_recep_candidates:
        return si_recep_candidates[0]
    
    return candidates[0]


def validate_rde_and_lote(
    rde_signed_bytes: bytes,
    lote_xml_bytes: Optional[bytes],
    xsd_dir: Path
) -> Dict[str, Any]:
    """
    Valida rDE firmado y (opcionalmente) lote.xml contra XSD locales.
    
    Args:
        rde_signed_bytes: XML del rDE firmado (bytes)
        lote_xml_bytes: XML del lote.xml (bytes) o None si no se proporciona
        xsd_dir: Directorio base donde están los XSD
        
    Returns:
        Dict con:
        {
            "rde_ok": bool,
            "rde_errors": List[str],
            "lote_ok": Optional[bool],
            "lote_errors": List[str],
            "schema_rde": str (path),
            "schema_lote": Optional[str] (path),
            "warning": Optional[str]
        }
    """
    xsd_dir = Path(xsd_dir).resolve()
    
    result = {
        "rde_ok": False,
        "rde_errors": [],
        "lote_ok": None,
        "lote_errors": [],
        "schema_rde": "",
        "schema_lote": None,
        "warning": None
    }
    
    # 1) Validar rDE
    # Preferir siRecepDE_v150.xsd si existe
    schema_rde_path = xsd_dir / "siRecepDE_v150.xsd"
    if not schema_rde_path.exists():
        # Buscar XSD que declare elemento global "rDE"
        schema_rde_path = find_xsd_declaring_global_element(xsd_dir, "rDE")
        if schema_rde_path is None:
            result["rde_errors"] = [
                f"No se encontró XSD para rDE en {xsd_dir}. "
                "Buscar siRecepDE_v150.xsd o archivo que declare elemento global 'rDE'."
            ]
            return result
    
    result["schema_rde"] = str(schema_rde_path)
    
    try:
        schema_rde = load_schema(schema_rde_path, xsd_dir)
        rde_ok, rde_errors = validate_xml_bytes(rde_signed_bytes, schema_rde, xsd_dir)
        result["rde_ok"] = rde_ok
        result["rde_errors"] = rde_errors
    except Exception as e:
        result["rde_errors"] = [f"Error al cargar/validar XSD rDE: {e}"]
        return result
    
    # 2) Validar lote.xml si se proporciona
    if lote_xml_bytes is not None:
        schema_lote_path = find_xsd_declaring_global_element(xsd_dir, "rLoteDE")
        if schema_lote_path is None:
            result["warning"] = "No se encontró XSD para rLoteDE; se validó solo rDE"
            result["lote_ok"] = None
        else:
            result["schema_lote"] = str(schema_lote_path)
            try:
                schema_lote = load_schema(schema_lote_path, xsd_dir)
                lote_ok, lote_errors = validate_xml_bytes(lote_xml_bytes, schema_lote, xsd_dir)
                result["lote_ok"] = lote_ok
                result["lote_errors"] = lote_errors
            except Exception as e:
                result["lote_errors"] = [f"Error al cargar/validar XSD lote: {e}"]
                result["lote_ok"] = False
    
    return result

