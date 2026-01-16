#!/usr/bin/env python3
"""
Convertidor de factura interna a formato Tesaka de importación
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any

# Lazy import de jsonschema para evitar SystemExit durante collection
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
    script_dir = Path(__file__).parent.parent
    schema_path = script_dir / "schemas" / "importacion.schema.json"
    
    if not schema_path.exists():
        print(f"Error: No se encontró el schema {schema_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_invoice(file_path: str) -> Dict[str, Any]:
    """Carga la factura interna desde un archivo JSON"""
    if not Path(file_path).exists():
        print(f"Error: El archivo {file_path} no existe", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: El archivo no es un JSON válido: {e}", file=sys.stderr)
        sys.exit(1)


def format_validation_error(error: "ValidationError") -> str:
    """Formatea un error de validación de manera legible"""
    _require_jsonschema()
    
    # Si llegamos aquí, ValidationError es el tipo correcto de jsonschema
    # y tiene los atributos path, absolute_path y message
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


def convert_to_tesaka(invoice: Dict[str, Any]) -> list:
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


def validate_tesaka(tesaka_data: list, schema: Dict[str, Any]) -> list:
    """
    Valida los datos Tesaka contra el schema
    
    Returns:
        Lista de errores formateados (vacía si no hay errores)
    """
    _require_jsonschema()
    
    if Draft202012Validator is None:
        raise RuntimeError("jsonschema no está disponible")
    
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(tesaka_data))
    
    if not errors:
        return []
    
    # Ordenar errores de manera estable
    errors.sort(key=lambda e: ("/".join(str(p) for p in e.absolute_path), e.message))
    
    return [format_validation_error(err) for err in errors]


def main():
    """Función principal del CLI"""
    if len(sys.argv) != 3:
        print("Uso: python -m src.convert_to_import <input_invoice.json> <output_tesaka_import.json>", file=sys.stderr)
        print("\nEjemplo:", file=sys.stderr)
        print("  python -m src.convert_to_import examples/source_invoice_ok.json output.json", file=sys.stderr)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Cargar factura interna
    invoice = load_invoice(input_file)
    
    # Convertir a formato Tesaka
    try:
        tesaka_data = convert_to_tesaka(invoice)
    except KeyError as e:
        print(f"Error: Campo requerido faltante en la factura interna: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error durante la conversión: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Cargar schema y validar
    schema = load_schema()
    errors = validate_tesaka(tesaka_data, schema)
    
    if errors:
        print(f"❌ Validación fallida. El comprobante Tesaka generado no es válido:\n", file=sys.stderr)
        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}\n", file=sys.stderr)
        sys.exit(1)
    
    # Escribir salida (pretty printed)
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(tesaka_data, f, indent=2, ensure_ascii=False)
        print(f"✅ Conversión exitosa. Archivo generado: {output_file}")
        sys.exit(0)
    except Exception as e:
        print(f"Error al escribir el archivo de salida: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

