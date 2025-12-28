#!/usr/bin/env python3
"""
Adaptador de facturas "crudas" de sistemas externos al formato estándar interno
"""
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List

from .convert_to_import import convert_to_tesaka, validate_tesaka, load_schema


def get_value(data: Dict[str, Any], *keys: str) -> Optional[Any]:
    """
    Busca un valor en el diccionario probando múltiples claves posibles.
    Retorna el primer valor encontrado o None si ninguna clave existe.
    """
    for key in keys:
        if key in data:
            return data[key]
    return None


def get_nested_value(data: Dict[str, Any], base_keys: List[str], *field_keys: str) -> Optional[Any]:
    """
    Busca un valor anidado probando múltiples claves base y múltiples claves de campo.
    Ejemplo: get_nested_value(data, ['buyer', 'cliente'], 'nombre', 'name')
    busca en data['buyer']['nombre'], data['buyer']['name'], data['cliente']['nombre'], etc.
    """
    for base_key in base_keys:
        if base_key in data and isinstance(data[base_key], dict):
            for field_key in field_keys:
                if field_key in data[base_key]:
                    return data[base_key][field_key]
    return None


def adapt(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapta un JSON "crudo" de un sistema externo al formato estándar interno.
    
    Args:
        raw: Diccionario con la factura en formato "crudo"
        
    Returns:
        Diccionario en formato estándar (formato_factura_interna.md)
        
    Raises:
        ValueError: Si faltan campos críticos requeridos
    """
    # issue_date: puede venir como issue_date | fecha | fecha_emision
    issue_date = get_value(raw, "issue_date", "fecha", "fecha_emision")
    if not issue_date:
        raise ValueError("Campo crítico faltante: se requiere 'issue_date', 'fecha' o 'fecha_emision'")
    
    # issue_datetime: opcional
    issue_datetime = get_value(raw, "issue_datetime", "fecha_hora", "fecha_hora_emision", "fecha_datetime")
    
    # buyer: puede venir como buyer | cliente | customer
    buyer_base = get_value(raw, "buyer", "cliente", "customer")
    if not buyer_base or not isinstance(buyer_base, dict):
        raise ValueError("Campo crítico faltante: se requiere 'buyer', 'cliente' o 'customer' (objeto)")
    
    # Construir buyer estándar
    buyer = {}
    
    # situacion: requerido
    buyer["situacion"] = get_nested_value(raw, ["buyer", "cliente", "customer"], "situacion", "situation")
    if not buyer["situacion"]:
        raise ValueError("Campo crítico faltante: buyer.situacion")
    
    # nombre: requerido
    buyer["nombre"] = get_nested_value(raw, ["buyer", "cliente", "customer"], "nombre", "name", "nombre_cliente")
    if not buyer["nombre"]:
        raise ValueError("Campo crítico faltante: buyer.nombre (o cliente.nombre, customer.name)")
    
    # ruc y dv: requeridos si situacion = CONTRIBUYENTE
    buyer["ruc"] = get_nested_value(raw, ["buyer", "cliente", "customer"], "ruc", "RUC")
    buyer["dv"] = get_nested_value(raw, ["buyer", "cliente", "customer"], "dv", "DV", "digito_verificador")
    
    # Otros campos opcionales de buyer
    buyer["tipoIdentificacion"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                                   "tipoIdentificacion", "tipo_identificacion", "tipoIdentidad")
    buyer["identificacion"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                              "identificacion", "identificacion_numero", "numero_identificacion")
    buyer["correoElectronico"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                                  "correoElectronico", "correo", "email", "email_cliente")
    buyer["pais"] = get_nested_value(raw, ["buyer", "cliente", "customer"], "pais", "country")
    buyer["tieneRepresentante"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                                    "tieneRepresentante", "tiene_representante", "has_representative")
    buyer["tieneBeneficiario"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                                  "tieneBeneficiario", "tiene_beneficiario", "has_beneficiary")
    buyer["domicilio"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                         "domicilio", "address", "direccion_completa")
    buyer["direccion"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                          "direccion", "address_line", "direccion_linea")
    buyer["telefono"] = get_nested_value(raw, ["buyer", "cliente", "customer"], 
                                        "telefono", "phone", "telefono_cliente")
    
    # representante y beneficiario (objetos anidados)
    for base_key in ["buyer", "cliente", "customer"]:
        if base_key in raw and isinstance(raw[base_key], dict):
            base_obj = raw[base_key]
            
            # representante
            if "representante" in base_obj or "representative" in base_obj:
                rep = base_obj.get("representante") or base_obj.get("representative")
                if isinstance(rep, dict):
                    buyer["representante"] = {
                        "tipoIdentificacion": rep.get("tipoIdentificacion") or rep.get("tipo_identificacion") or rep.get("tipoIdentidad"),
                        "identificacion": rep.get("identificacion") or rep.get("identificacion_numero") or rep.get("numero_identificacion"),
                        "nombre": rep.get("nombre") or rep.get("name")
                    }
            
            # beneficiario
            if "beneficiario" in base_obj or "beneficiary" in base_obj:
                ben = base_obj.get("beneficiario") or base_obj.get("beneficiary")
                if isinstance(ben, dict):
                    buyer["beneficiario"] = {
                        "tipoIdentificacion": ben.get("tipoIdentificacion") or ben.get("tipo_identificacion") or ben.get("tipoIdentidad"),
                        "identificacion": ben.get("identificacion") or ben.get("identificacion_numero") or ben.get("numero_identificacion"),
                        "nombre": ben.get("nombre") or ben.get("name")
                    }
            break
    
    # Limpiar campos None de buyer
    buyer = {k: v for k, v in buyer.items() if v is not None}
    
    # transaction: puede venir como transaction | transaccion
    transaction_base = get_value(raw, "transaction", "transaccion", "transaccion_data")
    if not transaction_base or not isinstance(transaction_base, dict):
        raise ValueError("Campo crítico faltante: se requiere 'transaction' o 'transaccion' (objeto)")
    
    # Construir transaction estándar
    transaction = {}
    transaction["condicionCompra"] = get_nested_value(raw, ["transaction", "transaccion", "transaccion_data"], 
                                                      "condicionCompra", "condicion_compra", "condicion", "payment_condition")
    if not transaction["condicionCompra"]:
        raise ValueError("Campo crítico faltante: transaction.condicionCompra")
    
    transaction["cuotas"] = get_nested_value(raw, ["transaction", "transaccion", "transaccion_data"], 
                                             "cuotas", "numero_cuotas", "cuotas_numero")
    transaction["tipoComprobante"] = get_nested_value(raw, ["transaction", "transaccion", "transaccion_data"], 
                                                     "tipoComprobante", "tipo_comprobante", "tipo", "document_type")
    if transaction["tipoComprobante"] is None:
        raise ValueError("Campo crítico faltante: transaction.tipoComprobante")
    
    transaction["numeroComprobanteVenta"] = get_nested_value(raw, ["transaction", "transaccion", "transaccion_data"], 
                                                            "numeroComprobanteVenta", "numero_comprobante_venta", 
                                                            "numero_comprobante", "numero", "comprobante_numero")
    if not transaction["numeroComprobanteVenta"]:
        raise ValueError("Campo crítico faltante: transaction.numeroComprobanteVenta")
    
    # Asegurar que numeroComprobanteVenta sea string
    if not isinstance(transaction["numeroComprobanteVenta"], str):
        transaction["numeroComprobanteVenta"] = str(transaction["numeroComprobanteVenta"])
    
    transaction["numeroTimbrado"] = get_nested_value(raw, ["transaction", "transaccion", "transaccion_data"], 
                                                    "numeroTimbrado", "numero_timbrado", "timbrado", "timbrado_numero")
    if not transaction["numeroTimbrado"]:
        raise ValueError("Campo crítico faltante: transaction.numeroTimbrado")
    
    # Asegurar que numeroTimbrado sea string
    if not isinstance(transaction["numeroTimbrado"], str):
        transaction["numeroTimbrado"] = str(transaction["numeroTimbrado"])
    
    transaction["fecha"] = get_nested_value(raw, ["transaction", "transaccion", "transaccion_data"], 
                                           "fecha", "fecha_transaccion", "transaction_date")
    
    # Limpiar campos None de transaction
    transaction = {k: v for k, v in transaction.items() if v is not None}
    
    # items: puede venir como items | detalle | lineas
    items = get_value(raw, "items", "detalle", "lineas", "line_items", "items_list")
    if not items:
        raise ValueError("Campo crítico faltante: se requiere 'items', 'detalle' o 'lineas' (array)")
    
    if not isinstance(items, list):
        raise ValueError("Campo 'items' debe ser un array")
    
    if len(items) == 0:
        raise ValueError("El array 'items' no puede estar vacío")
    
    # Adaptar cada item
    adapted_items = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Cada item debe ser un objeto")
        
        adapted_item = {}
        adapted_item["cantidad"] = get_value(item, "cantidad", "qty", "quantity", "cant")
        if adapted_item["cantidad"] is None:
            raise ValueError("Campo crítico faltante en item: cantidad")
        
        adapted_item["tasaAplica"] = get_value(item, "tasaAplica", "tasa_aplica", "tasa", "tax_rate", "iva_tasa")
        if adapted_item["tasaAplica"] is None:
            raise ValueError("Campo crítico faltante en item: tasaAplica")
        
        adapted_item["precioUnitario"] = get_value(item, "precioUnitario", "precio_unitario", "precio", "price", "unit_price", "precio_unidad")
        if adapted_item["precioUnitario"] is None:
            raise ValueError("Campo crítico faltante en item: precioUnitario")
        
        adapted_item["descripcion"] = get_value(item, "descripcion", "description", "desc", "producto", "product", "item_descripcion")
        if not adapted_item["descripcion"]:
            raise ValueError("Campo crítico faltante en item: descripcion")
        
        adapted_items.append(adapted_item)
    
    # retention: puede venir como retention | retencion
    retention_base = get_value(raw, "retention", "retencion", "retenciones")
    if not retention_base or not isinstance(retention_base, dict):
        raise ValueError("Campo crítico faltante: se requiere 'retention' o 'retencion' (objeto)")
    
    # Construir retention estándar
    retention = {}
    retention["fecha"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                         "fecha", "fecha_retencion", "retention_date")
    if not retention["fecha"]:
        raise ValueError("Campo crítico faltante: retention.fecha")
    
    retention["moneda"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                          "moneda", "currency", "moneda_codigo")
    if not retention["moneda"]:
        raise ValueError("Campo crítico faltante: retention.moneda")
    
    retention["tipoCambio"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                              "tipoCambio", "tipo_cambio", "exchange_rate", "tipo_cambio_moneda")
    retention["retencionRenta"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                   "retencionRenta", "retencion_renta", "has_rent_retention", "renta_retencion")
    if retention["retencionRenta"] is None:
        raise ValueError("Campo crítico faltante: retention.retencionRenta")
    
    retention["conceptoRenta"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                 "conceptoRenta", "concepto_renta", "rent_concept")
    retention["retencionIva"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                 "retencionIva", "retencion_iva", "has_iva_retention", "iva_retencion")
    if retention["retencionIva"] is None:
        raise ValueError("Campo crítico faltante: retention.retencionIva")
    
    retention["conceptoIva"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                               "conceptoIva", "concepto_iva", "iva_concept")
    retention["rentaPorcentaje"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                    "rentaPorcentaje", "renta_porcentaje", "rent_percentage")
    if retention["rentaPorcentaje"] is None:
        raise ValueError("Campo crítico faltante: retention.rentaPorcentaje")
    
    retention["ivaPorcentaje5"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                   "ivaPorcentaje5", "iva_porcentaje_5", "iva_5_percent")
    if retention["ivaPorcentaje5"] is None:
        raise ValueError("Campo crítico faltante: retention.ivaPorcentaje5")
    
    retention["ivaPorcentaje10"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                    "ivaPorcentaje10", "iva_porcentaje_10", "iva_10_percent")
    if retention["ivaPorcentaje10"] is None:
        raise ValueError("Campo crítico faltante: retention.ivaPorcentaje10")
    
    retention["rentaCabezasBase"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                      "rentaCabezasBase", "renta_cabezas_base", "heads_base")
    if retention["rentaCabezasBase"] is None:
        raise ValueError("Campo crítico faltante: retention.rentaCabezasBase")
    
    retention["rentaCabezasCantidad"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                        "rentaCabezasCantidad", "renta_cabezas_cantidad", "heads_quantity")
    if retention["rentaCabezasCantidad"] is None:
        raise ValueError("Campo crítico faltante: retention.rentaCabezasCantidad")
    
    retention["rentaToneladasBase"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                      "rentaToneladasBase", "renta_toneladas_base", "tons_base")
    if retention["rentaToneladasBase"] is None:
        raise ValueError("Campo crítico faltante: retention.rentaToneladasBase")
    
    retention["rentaToneladasCantidad"] = get_nested_value(raw, ["retention", "retencion", "retenciones"], 
                                                          "rentaToneladasCantidad", "renta_toneladas_cantidad", "tons_quantity")
    if retention["rentaToneladasCantidad"] is None:
        raise ValueError("Campo crítico faltante: retention.rentaToneladasCantidad")
    
    # Limpiar campos None de retention
    retention = {k: v for k, v in retention.items() if v is not None}
    
    # Construir factura estándar
    standard_invoice = {
        "issue_date": issue_date,
        "buyer": buyer,
        "transaction": transaction,
        "items": adapted_items,
        "retention": retention
    }
    
    # Agregar issue_datetime solo si existe
    if issue_datetime:
        standard_invoice["issue_datetime"] = issue_datetime
    
    return standard_invoice


def main():
    """Función principal del CLI"""
    if len(sys.argv) != 3:
        print("Uso: python -m src.adapt_from_my_system <raw_input.json> <output_tesaka_import.json>", file=sys.stderr)
        print("\nEjemplo:", file=sys.stderr)
        print("  python -m src.adapt_from_my_system examples/raw_invoice_sample.json output.json", file=sys.stderr)
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    # Cargar JSON crudo
    if not Path(input_file).exists():
        print(f"Error: El archivo {input_file} no existe", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: El archivo no es un JSON válido: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Adaptar al formato estándar
    try:
        standard_invoice = adapt(raw_data)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error durante la adaptación: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Convertir a formato Tesaka
    try:
        tesaka_data = convert_to_tesaka(standard_invoice)
    except KeyError as e:
        print(f"Error: Campo requerido faltante después de la adaptación: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error durante la conversión a Tesaka: {e}", file=sys.stderr)
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
        print(f"✅ Adaptación y conversión exitosa. Archivo generado: {output_file}")
        sys.exit(0)
    except Exception as e:
        print(f"Error al escribir el archivo de salida: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()

