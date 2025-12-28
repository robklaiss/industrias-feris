#!/usr/bin/env python3
"""
Validador de Comprobantes Virtuales Tesaka
Valida archivos JSON según los schemas de importación o exportación
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List

try:
    import jsonschema
    from jsonschema import Draft202012Validator, ValidationError
except ImportError:
    print("Error: jsonschema no está instalado. Instálalo con: pip install jsonschema", file=sys.stderr)
    sys.exit(1)


def load_schema(schema_name: str) -> Dict[str, Any]:
    """Carga el schema JSON desde el directorio schemas"""
    script_dir = Path(__file__).parent.parent
    schema_path = script_dir / "schemas" / f"{schema_name}.schema.json"
    
    if not schema_path.exists():
        print(f"Error: No se encontró el schema {schema_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_json(file_path: str) -> Any:
    """Carga el archivo JSON a validar"""
    if not os.path.exists(file_path):
        print(f"Error: El archivo {file_path} no existe", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: El archivo no es un JSON válido: {e}", file=sys.stderr)
        sys.exit(1)


def format_validation_error(error: ValidationError) -> str:
    """Formatea un error de validación de manera legible"""
    path = " -> ".join(str(p) for p in error.path)
    absolute_path = " -> ".join(str(p) for p in error.absolute_path)
    
    if path:
        location = f"Campo: {path} (ruta absoluta: {absolute_path})"
    else:
        location = f"Raíz del documento (ruta absoluta: {absolute_path})"
    
    message = error.message
    
    # Mejora mensajes comunes
    if error.validator == 'required':
        missing = error.validator_value
        if isinstance(missing, list) and len(missing) == 1:
            message = f"Campo requerido faltante: '{missing[0]}'"
        elif isinstance(missing, list):
            missing_str = ", ".join(f"'{m}'" for m in missing)
            message = f"Campos requeridos faltantes: {missing_str}"
    elif error.validator == 'enum':
        message = f"Valor inválido. Valores permitidos: {error.validator_value}"
    elif error.validator == 'pattern':
        message = f"Formato inválido. Patrón esperado: {error.validator_value}"
    elif error.validator == 'type':
        expected = error.validator_value
        message = f"Tipo incorrecto. Se esperaba: {expected}"
    elif error.validator == 'minItems':
        message = f"El array debe tener al menos {error.validator_value} elemento(s)"
    elif error.validator == 'minimum':
        message = f"El valor debe ser mayor o igual a {error.validator_value}"
    elif error.validator == 'maxLength':
        message = f"La longitud máxima permitida es {error.validator_value} caracteres"
    
    return f"{location}\n  Error: {message}"


def validate(data: Any, schema: Dict[str, Any]) -> List[str]:
    """Valida los datos contra el schema y retorna lista de errores formateados"""
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    
    if not errors:
        return []
    
    formatted_errors = []
    for error in errors:
        formatted_errors.append(format_validation_error(error))
    
    return formatted_errors


def main():
    """Función principal del CLI"""
    if len(sys.argv) != 3:
        print("Uso: python validate.py <import|export> <archivo.json>", file=sys.stderr)
        print("\nEjemplos:")
        print("  python validate.py import comprobante.json")
        print("  python validate.py export respuesta.json")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    file_path = sys.argv[2]
    
    if command not in ['import', 'export']:
        print(f"Error: Comando inválido '{command}'. Debe ser 'import' o 'export'", file=sys.stderr)
        sys.exit(1)
    
    # Cargar schema y datos
    schema = load_schema(command)
    data = load_json(file_path)
    
    # Validar
    errors = validate(data, schema)
    
    if errors:
        print(f"❌ Validación fallida para {file_path} ({len(errors)} error(es)):\n", file=sys.stderr)
        for i, error in enumerate(errors, 1):
            print(f"{i}. {error}\n", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"✅ Validación exitosa para {file_path}")
        sys.exit(0)


if __name__ == '__main__':
    main()

