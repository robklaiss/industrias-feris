"""
Script para crear una factura de prueba en la base de datos
"""
import json
import sys
from pathlib import Path

# Agregar el directorio app al path
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

from db import get_db, init_db

def create_test_invoice():
    """Crea una factura de prueba"""
    # Inicializar la base de datos si no existe
    init_db()
    
    # Datos de la factura de prueba basados en el ejemplo
    invoice_data = {
        "issue_date": "2024-01-15",
        "issue_datetime": "2024-01-15 10:30:00",
        "buyer": {
            "situacion": "CONTRIBUYENTE",
            "nombre": "Empresa Ejemplo S.A.",
            "ruc": "80012345",
            "dv": "7",
            "domicilio": "Av. Principal 123",
            "direccion": "Asunción",
            "telefono": "021-123456"
        },
        "transaction": {
            "condicionCompra": "CONTADO",
            "tipoComprobante": 1,
            "numeroComprobanteVenta": "001-001-00000001",
            "numeroTimbrado": "12345678",
            "fecha": "2024-01-15"
        },
        "items": [
            {
                "cantidad": 10.5,
                "tasaAplica": 10,
                "precioUnitario": 1000.0,
                "descripcion": "Producto de ejemplo"
            },
            {
                "cantidad": 5.0,
                "tasaAplica": 5,
                "precioUnitario": 2000.0,
                "descripcion": "Otro producto de prueba"
            }
        ],
        "retention": {
            "fecha": "2024-01-15",
            "moneda": "PYG",
            "retencionRenta": False,
            "retencionIva": False,
            "rentaPorcentaje": 0,
            "ivaPorcentaje5": 0,
            "ivaPorcentaje10": 0,
            "rentaCabezasBase": 0,
            "rentaCabezasCantidad": 0,
            "rentaToneladasBase": 0,
            "rentaToneladasCantidad": 0
        }
    }
    
    # Insertar en la base de datos
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO invoices (issue_date, buyer_name, data_json)
        VALUES (?, ?, ?)
    """, (
        invoice_data["issue_date"],
        invoice_data["buyer"]["nombre"],
        json.dumps(invoice_data, ensure_ascii=False)
    ))
    
    invoice_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    print(f"✅ Factura de prueba creada exitosamente!")
    print(f"   ID: {invoice_id}")
    print(f"   Comprador: {invoice_data['buyer']['nombre']}")
    print(f"   Fecha: {invoice_data['issue_date']}")
    print(f"   Items: {len(invoice_data['items'])}")
    print(f"\n   Puedes verla en: http://127.0.0.1:8600/invoices/{invoice_id}")
    
    return invoice_id

if __name__ == "__main__":
    create_test_invoice()

