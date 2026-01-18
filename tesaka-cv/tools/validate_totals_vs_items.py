#!/usr/bin/env python3
"""
Validador de totales vs suma de ítems en XML DE SIFEN

Verifica que los totales en gTotSub coincidan con la suma de los ítems en gCamItem.
Esto ayuda a identificar el error 0160 cuando hay inconsistencia matemática.
"""
import sys
import argparse
from pathlib import Path
from lxml import etree
from typing import Dict, List, Tuple
import xml.etree.ElementTree as ET

# Namespaces SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
NS = {"s": SIFEN_NS}


def parse_amount(amount_str: str) -> int:
    """Convierte un string de monto SIFEN a entero (sin separadores)."""
    if not amount_str:
        return 0
    # Eliminar puntos y comas, luego convertir a entero
    return int(''.join(c for c in str(amount_str) if c.isdigit() or c == '-'))


def validate_totals_vs_items(xml_file: Path) -> Dict[str, any]:
    """
    Valida que los totales coincidan con la suma de ítems.
    
    Returns:
        Dict con resultado de validación y deltas encontrados
    """
    try:
        tree = etree.parse(str(xml_file))
        root = tree.getroot()
    except Exception as e:
        return {
            "valid": False,
            "error": f"No se pudo parsear XML: {e}",
            "deltas": {}
        }
    
    # Encontrar DE (puede ser root o estar dentro de rDE)
    de_elem = root
    if root.tag == f"{{{SIFEN_NS}}}rDE":
        de_elem = root.find(".//s:DE", NS)
    elif root.tag != f"{{{SIFEN_NS}}}DE":
        de_elem = root.find(".//s:DE", NS)
    
    if de_elem is None:
        return {
            "valid": False,
            "error": "No se encontró elemento DE en el XML",
            "deltas": {}
        }
    
    # Extraer totales de gTotSub
    tot_sub = de_elem.find(".//s:gTotSub", NS)
    if tot_sub is None:
        return {
            "valid": False,
            "error": "No se encontró gTotSub en el DE",
            "deltas": {}
        }
    
    # Leer totales
    d_tot_ope = parse_amount(tot_sub.findtext("s:dTotOpe", namespaces=NS))
    d_sub10 = parse_amount(tot_sub.findtext("s:dSub10", namespaces=NS))
    d_tot_iva = parse_amount(tot_sub.findtext("s:dTotIVA", namespaces=NS))
    d_base_grav10 = parse_amount(tot_sub.findtext("s:dBaseGrav10", namespaces=NS))
    d_iva10 = parse_amount(tot_sub.findtext("s:dIVA10", namespaces=NS))
    
    # Sumar ítems
    items = de_elem.findall(".//s:gCamItem", NS)
    if not items:
        return {
            "valid": False,
            "error": "No se encontraron ítems gCamItem en el DE",
            "deltas": {}
        }
    
    sum_d_tot_ope_item = 0
    sum_d_bas_grav_iva = 0
    sum_d_liq_iva_item = 0
    
    for item in items:
        # dTotOpeItem está dentro de gValorItem/gValorRestaItem
        valor_item = item.find(".//s:gValorItem", NS)
        if valor_item is not None:
            valor_resta = valor_item.find(".//s:gValorRestaItem", NS)
            if valor_resta is not None:
                sum_d_tot_ope_item += parse_amount(valor_resta.findtext("s:dTotOpeItem", namespaces=NS))
        
        # dBasGravIVA y dLiqIVAItem están en gCamIVA
        cam_iva = item.find(".//s:gCamIVA", NS)
        if cam_iva is not None:
            sum_d_bas_grav_iva += parse_amount(cam_iva.findtext("s:dBasGravIVA", namespaces=NS))
            sum_d_liq_iva_item += parse_amount(cam_iva.findtext("s:dLiqIVAItem", namespaces=NS))
    
    # Calcular deltas
    delta_tot_ope = d_tot_ope - sum_d_tot_ope_item
    delta_base_grav10 = d_base_grav10 - sum_d_bas_grav_iva
    delta_tot_iva = d_tot_iva - sum_d_liq_iva_item
    
    # Verificar si todos los deltas son cero
    is_valid = delta_tot_ope == 0 and delta_base_grav10 == 0 and delta_tot_iva == 0
    
    return {
        "valid": is_valid,
        "items_count": len(items),
        "totals": {
            "dTotOpe": d_tot_ope,
            "dSub10": d_sub10,
            "dTotIVA": d_tot_iva,
            "dBaseGrav10": d_base_grav10,
            "dIVA10": d_iva10
        },
        "items_sum": {
            "sum_dTotOpeItem": sum_d_tot_ope_item,
            "sum_dBasGravIVA": sum_d_bas_grav_iva,
            "sum_dLiqIVAItem": sum_d_liq_iva_item
        },
        "deltas": {
            "delta_dTotOpe": delta_tot_ope,
            "delta_dBaseGrav10": delta_base_grav10,
            "delta_dTotIVA": delta_tot_iva
        }
    }


def main():
    parser = argparse.ArgumentParser(
        description="Valida totales vs suma de ítems en XML DE SIFEN"
    )
    parser.add_argument(
        "xml_file",
        type=Path,
        help="Path al archivo XML DE (o lote.xml con rDE)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Mostrar detalle completo"
    )
    
    args = parser.parse_args()
    
    if not args.xml_file.exists():
        print(f"❌ El archivo no existe: {args.xml_file}")
        return 1
    
    result = validate_totals_vs_items(args.xml_file)
    
    print("\n" + "="*60)
    print("VALIDACIÓN DE TOTALES VS ÍTEMS")
    print("="*60)
    
    if not result["valid"] and "error" in result:
        print(f"❌ Error: {result['error']}")
        return 1
    
    print(f"📊 Cantidad de ítems: {result['items_count']}")
    
    if args.verbose:
        print("\n📈 TOTALES (gTotSub):")
        for key, value in result["totals"].items():
            print(f"  {key}: {value:,}")
        
        print("\n📈 SUMA DE ÍTEMS:")
        for key, value in result["items_sum"].items():
            print(f"  {key}: {value:,}")
    
    print("\n📈 DELTAS (Totales - SumaÍtems):")
    all_zero = True
    for key, value in result["deltas"].items():
        status = "✅" if value == 0 else "❌"
        print(f"  {key}: {value:,} {status}")
        if value != 0:
            all_zero = False
    
    print("\n" + "="*60)
    if result["valid"]:
        print("✅ VALIDACIÓN OK: Todos los deltas son cero")
    else:
        print("❌ VALIDACIÓN FALLIDA: Hay diferencias en los totales")
        print("💡 Esta inconsistencia puede causar error 0160 en SIFEN")
    print("="*60)
    
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
