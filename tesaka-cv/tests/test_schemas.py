from typing import List
"""
Tests de validación de schemas para comprobantes virtuales Tesaka
"""
import json
import pytest
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError


# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SCHEMAS_DIR = PROJECT_ROOT / "schemas"
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def load_schema(schema_name: str):
    """Carga un schema JSON"""
    schema_path = SCHEMAS_DIR / f"{schema_name}.schema.json"
    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_example(example_name: str):
    """Carga un ejemplo JSON"""
    example_path = EXAMPLES_DIR / example_name
    with open(example_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_validation_error(error: ValidationError) -> str:
    """Formatea un error de validación con la ruta del campo"""
    path = " -> ".join(str(p) for p in error.path)
    absolute_path = " -> ".join(str(p) for p in error.absolute_path)
    
    if path:
        location = f"Campo: {path} (ruta absoluta: {absolute_path})"
    else:
        location = f"Raíz del documento (ruta absoluta: {absolute_path})"
    
    return f"{location}\n  Error: {error.message}"


def validate_with_errors(data, schema) -> List[str]:
    """Valida datos contra schema y retorna lista de errores formateados"""
    validator = Draft202012Validator(schema)
    errors = list(validator.iter_errors(data))
    # Orden estable para que los tests sean determinísticos
    errors.sort(
        key=lambda e: (
            "/".join(str(p) for p in e.absolute_path),
            e.message,
        )
    )
    return [format_validation_error(err) for err in errors]


class TestImportacionSchema:
    """Tests para schema de importación"""
    
    def test_import_ok_valid(self):
        """Valida que import_ok.json pasa la validación"""
        schema = load_schema("importacion")
        data = load_example("import_ok.json")
        
        errors = validate_with_errors(data, schema)
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        
        assert len(errors) == 0, f"El ejemplo import_ok.json debería ser válido, pero tiene errores:\n{error_msg}"
    
    def test_import_bad_invalid(self):
        """Valida que import_bad.json falla la validación"""
        schema = load_schema("importacion")
        data = load_example("import_bad.json")
        
        errors = validate_with_errors(data, schema)
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        
        assert len(errors) > 0, f"El ejemplo import_bad.json debería fallar la validación, pero pasó.\nErrores esperados:\n{error_msg}"
        
        # Verificar que al menos uno de los errores esperados está presente
        error_text = "\n".join(errors)
        assert (
            "ruc" in error_text.lower() or 
            "dv" in error_text.lower() or 
            "cuotas" in error_text.lower()
        ), f"El error debería estar relacionado con campos requeridos faltantes (ruc/dv o cuotas), pero los errores fueron:\n{error_msg}"


class TestExportacionSchema:
    """Tests para schema de exportación"""
    
    def test_export_ok_valid(self):
        """Valida que export_ok.json pasa la validación"""
        schema = load_schema("exportacion")
        data = load_example("export_ok.json")
        
        errors = validate_with_errors(data, schema)
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        
        assert len(errors) == 0, f"El ejemplo export_ok.json debería ser válido, pero tiene errores:\n{error_msg}"
    
    def test_export_bad_invalid(self):
        """Valida que export_bad.json falla la validación"""
        schema = load_schema("exportacion")
        data = load_example("export_bad.json")
        
        errors = validate_with_errors(data, schema)
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        
        assert len(errors) > 0, f"El ejemplo export_bad.json debería fallar la validación, pero pasó.\nErrores esperados:\n{error_msg}"
        
        # Verificar que al menos uno de los errores esperados está presente
        error_text = "\n".join(errors).lower()
        assert (
            "impuestototal" in error_text or 
            "tipocambio" in error_text or 
            "conceptorenta" in error_text
        ), f"El error debería estar relacionado con totales.impuestoTotal, tipoCambio o conceptoRenta, pero los errores fueron:\n{error_msg}"

