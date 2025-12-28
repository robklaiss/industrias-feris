"""
Tests para el adaptador de facturas "crudas" al formato estándar
"""
import json
import pytest
from pathlib import Path

# Importar el adaptador y convertidor
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.adapt_from_my_system import adapt
from src.convert_to_import import (
    convert_to_tesaka,
    validate_tesaka,
    load_schema,
)


# Paths
PROJECT_ROOT = Path(__file__).parent.parent
EXAMPLES_DIR = PROJECT_ROOT / "examples"


def load_example(example_name: str):
    """Carga un ejemplo JSON"""
    example_path = EXAMPLES_DIR / example_name
    with open(example_path, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestAdapter:
    """Tests para el adaptador de facturas crudas"""
    
    def test_adapt_raw_invoice_sample_valid(self):
        """Valida que raw_invoice_sample.json se adapta y genera un Tesaka válido"""
        # Cargar factura cruda
        raw_invoice = load_example("raw_invoice_sample.json")
        
        # Adaptar al formato estándar
        standard_invoice = adapt(raw_invoice)
        
        # Verificar que la adaptación fue exitosa
        assert "issue_date" in standard_invoice
        assert "buyer" in standard_invoice
        assert "transaction" in standard_invoice
        assert "items" in standard_invoice
        assert "retention" in standard_invoice
        
        # Verificar que los campos se mapearon correctamente
        assert standard_invoice["issue_date"] == "2024-01-15"
        assert standard_invoice["issue_datetime"] == "2024-01-15 10:30:00"
        assert standard_invoice["buyer"]["nombre"] == "Empresa Ejemplo S.A."
        assert standard_invoice["buyer"]["ruc"] == "80012345"
        assert standard_invoice["buyer"]["dv"] == "7"
        assert standard_invoice["transaction"]["condicionCompra"] == "CONTADO"
        assert standard_invoice["transaction"]["tipoComprobante"] == 1
        assert standard_invoice["transaction"]["numeroComprobanteVenta"] == "001-001-00000001"
        assert len(standard_invoice["items"]) == 1
        assert standard_invoice["items"][0]["cantidad"] == 10.5
        assert standard_invoice["items"][0]["tasaAplica"] == 10
        
        # Convertir a formato Tesaka
        tesaka_data = convert_to_tesaka(standard_invoice)
        
        # Validar contra el schema
        schema = load_schema()
        errors = validate_tesaka(tesaka_data, schema)
        
        error_msg = "\n".join(f"  {i+1}. {err}" for i, err in enumerate(errors))
        assert len(errors) == 0, f"El resultado de la adaptación y conversión debería ser válido, pero tiene errores:\n{error_msg}"
        
        # Verificar estructura básica
        assert isinstance(tesaka_data, list), "El resultado debería ser una lista"
        assert len(tesaka_data) == 1, "El resultado debería contener exactamente un comprobante"
        
        comprobante = tesaka_data[0]
        assert "atributos" in comprobante
        assert "informado" in comprobante
        assert "transaccion" in comprobante
        assert "detalle" in comprobante
        assert "retencion" in comprobante
    
    def test_adapt_missing_critical_field_fails(self):
        """Valida que falta un campo crítico genera un error claro"""
        # Factura sin issue_date
        raw_invoice = {
            "cliente": {
                "situacion": "CONTRIBUYENTE",
                "nombre": "Test"
            },
            "transaccion": {
                "condicion_compra": "CONTADO",
                "tipo_comprobante": 1,
                "numero_comprobante_venta": "001-001-00000001",
                "numero_timbrado": "12345678"
            },
            "lineas": [],
            "retencion": {
                "fecha": "2024-01-15",
                "moneda": "PYG",
                "retencion_renta": False,
                "retencion_iva": False,
                "renta_porcentaje": 0,
                "iva_porcentaje_5": 0,
                "iva_porcentaje_10": 0,
                "renta_cabezas_base": 0,
                "renta_cabezas_cantidad": 0,
                "renta_toneladas_base": 0,
                "renta_toneladas_cantidad": 0
            }
        }
        
        with pytest.raises(ValueError) as exc_info:
            adapt(raw_invoice)
        
        assert "issue_date" in str(exc_info.value) or "fecha" in str(exc_info.value) or "fecha_emision" in str(exc_info.value)
    
    def test_adapt_missing_buyer_fails(self):
        """Valida que falta buyer genera un error claro"""
        raw_invoice = {
            "fecha": "2024-01-15",
            "transaccion": {
                "condicion_compra": "CONTADO",
                "tipo_comprobante": 1,
                "numero_comprobante_venta": "001-001-00000001",
                "numero_timbrado": "12345678"
            },
            "lineas": [],
            "retencion": {
                "fecha": "2024-01-15",
                "moneda": "PYG",
                "retencion_renta": False,
                "retencion_iva": False,
                "renta_porcentaje": 0,
                "iva_porcentaje_5": 0,
                "iva_porcentaje_10": 0,
                "renta_cabezas_base": 0,
                "renta_cabezas_cantidad": 0,
                "renta_toneladas_base": 0,
                "renta_toneladas_cantidad": 0
            }
        }
        
        with pytest.raises(ValueError) as exc_info:
            adapt(raw_invoice)
        
        assert "buyer" in str(exc_info.value) or "cliente" in str(exc_info.value) or "customer" in str(exc_info.value)

