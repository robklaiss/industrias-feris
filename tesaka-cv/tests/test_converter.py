"""
Tests para el convertidor de factura interna a formato Tesaka
"""
import pytest

# Skip si falta jsonschema (debe estar ANTES de importar src.*)
pytest.importorskip("jsonschema", reason="jsonschema requerido para tests de validación")

import json
from pathlib import Path
from jsonschema import Draft202012Validator, ValidationError

# Importar el convertidor
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.convert_to_import import (
    load_invoice,
    convert_to_tesaka,
    validate_tesaka,
    load_schema,
)


# Paths
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"


class TestConverter:
    """Tests para el convertidor de facturas internas"""
    
    def test_convert_source_invoice_ok_valid(self):
        """Valida que source_invoice_ok.json se convierte a un Tesaka válido"""
        # Cargar factura interna
        invoice_path = EXAMPLES_DIR / "source_invoice_ok.json"
        invoice = load_invoice(str(invoice_path))
        
        # Convertir a formato Tesaka
        tesaka_data = convert_to_tesaka(invoice)
        
        # Validar contra el schema
        schema = load_schema()
        errors = validate_tesaka(tesaka_data, schema)
        
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        assert len(errors) == 0, f"El resultado de la conversión debería ser válido, pero tiene errores:\n{error_msg}"
        
        # Verificar estructura básica
        assert isinstance(tesaka_data, list), "El resultado debería ser una lista"
        assert len(tesaka_data) == 1, "El resultado debería contener exactamente un comprobante"
        
        comprobante = tesaka_data[0]
        assert "atributos" in comprobante
        assert "informado" in comprobante
        assert "transaccion" in comprobante
        assert "detalle" in comprobante
        assert "retencion" in comprobante
        
        # Verificar que los campos se mapearon correctamente
        assert comprobante["atributos"]["fechaCreacion"] == invoice["issue_date"]
        assert comprobante["atributos"]["fechaHoraCreacion"] == invoice["issue_datetime"]
        assert comprobante["informado"]["situacion"] == invoice["buyer"]["situacion"]
        assert comprobante["informado"]["nombre"] == invoice["buyer"]["nombre"]
        assert comprobante["detalle"] == invoice["items"]
    
    def test_convert_source_invoice_bad_fails(self):
        """Valida que source_invoice_bad.json genera un Tesaka inválido"""
        # Cargar factura interna
        invoice_path = EXAMPLES_DIR / "source_invoice_bad.json"
        invoice = load_invoice(str(invoice_path))
        
        # Convertir a formato Tesaka
        tesaka_data = convert_to_tesaka(invoice)
        
        # Validar contra el schema (debería fallar)
        schema = load_schema()
        errors = validate_tesaka(tesaka_data, schema)
        
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        assert len(errors) > 0, f"El resultado de la conversión debería ser inválido, pero pasó la validación.\nErrores esperados:\n{error_msg}"
        
        # Verificar que al menos uno de los errores esperados está presente
        error_text = "\n".join(errors).lower()
        assert (
            "ruc" in error_text or 
            "dv" in error_text or 
            "cuotas" in error_text
        ), f"El error debería estar relacionado con campos requeridos faltantes (ruc/dv o cuotas), pero los errores fueron:\n{error_msg}"

