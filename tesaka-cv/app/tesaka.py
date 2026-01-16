"""
Lógica de conversión a formato Tesaka (reutilizable)
"""
import json
from pathlib import Path
from typing import Dict, Any, List

# Lazy import de jsonschema para evitar ImportError durante collection
try:
    from jsonschema import Draft202012Validator, ValidationError
    _HAS_JSONSCHEMA = True
except ImportError:
    Draft202012Validator = None  # type: ignore
    ValidationError = Exception  # type: ignore
    _HAS_JSONSCHEMA = False


def _require_jsonschema():
    """Verifica que jsonschema esté disponible, lanza RuntimeError si no"""
    if not _HAS_JSONSCHEMA:
        raise RuntimeError(
            "Missing dependency: jsonschema. Install with: pip install jsonschema"
        )


def load_schema() -> Dict[str, Any]:
    """Carga el schema de importación"""
    schema_path = Path(__file__).parent.parent / "schemas" / "importacion.schema.json"
    
    if not schema_path.exists():
        raise FileNotFoundError(f"No se encontró el schema {schema_path}")
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_validation_error(error: "ValidationError") -> str:
    """Formatea un error de validación de manera legible"""
    _require_jsonschema()
    
    try:
        path = " -> ".join(str(p) for p in error.path)
        absolute_path = " -> ".join(str(p) for p in error.absolute_path)
        message = error.message
    except AttributeError:
        # Fallback si el error no tiene la estructura esperada
        return f"Error de validación: {error}"
    
    if path:
        location = f"Campo: {path} (ruta absoluta: {absolute_path})"
    else:
        location = f"Raíz del documento (ruta absoluta: {absolute_path})"
    
    return f"{location}\n  Error: {message}"


def convert_to_tesaka(invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Convierte una factura interna al formato Tesaka de importación
    
    Args:
        invoice: Diccionario con la factura interna
        
    Returns:
        Lista con un único comprobante Tesaka
    """
    # Atributos
    atributos = {
        "fechaCreacion": invoice["issue_date"]
    }
    issue_datetime = invoice.get("issue_datetime")
    if issue_datetime and isinstance(issue_datetime, str) and issue_datetime.strip():
        atributos["fechaHoraCreacion"] = issue_datetime
    
    # Informado (copiar directamente desde buyer)
    informado = invoice["buyer"].copy()
    
    # Transacción (copiar y agregar fecha si no existe)
    transaccion = invoice["transaction"].copy()
    # Si no hay fecha en transaction, usar issue_date
    if "fecha" not in transaccion:
        transaccion["fecha"] = invoice["issue_date"]
    
    # Detalle (copiar items directamente)
    detalle = list(invoice["items"])
    
    # Retención (copiar directamente)
    retencion = dict(invoice["retention"])
    
    # Construir el comprobante Tesaka
    comprobante = {
        "atributos": atributos,
        "informado": informado,
        "transaccion": transaccion,
        "detalle": detalle,
        "retencion": retencion
    }
    
    # Retornar como array con un único comprobante
    return [comprobante]


def validate_tesaka(tesaka_data: List[Dict[str, Any]], schema: Dict[str, Any] = None) -> List[str]:
    """
    Valida los datos Tesaka contra el schema
    
    Args:
        tesaka_data: Lista con comprobante(s) Tesaka
        schema: Schema JSON (si no se proporciona, se carga automáticamente)
    
    Returns:
        Lista de errores formateados (vacía si no hay errores)
    """
    _require_jsonschema()
    
    if Draft202012Validator is None:
        raise RuntimeError("jsonschema no está disponible")
    
    if schema is None:
        schema = load_schema()
    
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(tesaka_data))
    
    if not errors:
        return []
    
    # Ordenar errores de manera estable
    errors.sort(key=lambda e: ("/".join(str(p) for p in e.absolute_path), e.message))
    
    return [format_validation_error(err) for err in errors]


def format_validation_error_simple(error: "ValidationError") -> str:
    """Formatea un error de validación con formato simple para mostrar en UI"""
    _require_jsonschema()
    
    try:
        path_parts = []
        for p in error.absolute_path:
            path_parts.append(str(p))
        message = error.message
    except AttributeError:
        # Fallback si el error no tiene la estructura esperada
        return f"Error de validación: {error}"
    
    if path_parts:
        path_str = " -> ".join(path_parts)
    else:
        path_str = "raíz"
    
    return f"{path_str}: {message}"

