#!/usr/bin/env python3
"""
Validador de facturas XML generadas contra el modelo SIFEN.
Este script verifica que el XML generado tenga todos los elementos requeridos.
"""

import xml.etree.ElementTree as ET
import sys
import os

# Namespace SIFEN
NS_SIFEN = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}

def validar_factura(xml_file):
    """
    Valida que el XML de la factura contenga todos los elementos requeridos.
    
    Args:
        xml_file (str): Ruta del archivo XML a validar
    
    Returns:
        tuple: (bool, list) - True si es válido, False si no. Lista de errores.
    """
    try:
        tree = ET.parse(xml_file)
        root = tree.getroot()
    except ET.ParseError as e:
        return False, [f"Error parseando XML: {e}"]
    
    errores = []
    
    # Validar namespace
    if root.tag != "{http://ekuatia.set.gov.py/sifen/xsd}rDE":
        errores.append("Raíz debe ser rDE con namespace SIFEN")
    
    # Validar dVerFor
    dVerFor = root.find("s:dVerFor", NS_SIFEN)
    if dVerFor is None or dVerFor.text != "150":
        errores.append("dVerFor debe existir y tener valor 150")
    
    # Validar DE
    de = root.find("s:DE", NS_SIFEN)
    if de is None:
        errores.append("Elemento DE no encontrado")
        return len(errores) == 0, errores
    
    # Validar atributos de DE
    if de.get("Id") is None:
        errores.append("DE debe tener atributo Id")
    
    # Validar campos obligatorios de DE
    campos_obligatorios = [
        "s:dDVId",
        "s:dFecFirma", 
        "s:dSisFact",
        "s:gOpeDE",
        "s:gTimb",
        "s:gDatGralOpe",
        "s:gDtipDE",
        "s:gTotSub"
    ]
    
    for campo in campos_obligatorios:
        elem = de.find(campo, NS_SIFEN)
        if elem is None:
            errores.append(f"Campo obligatorio faltante: {campo}")
    
    # Validar gOpeDE
    gOpeDE = de.find("s:gOpeDE", NS_SIFEN)
    if gOpeDE is not None:
        if gOpeDE.find("s:iTipEmi", NS_SIFEN) is None:
            errores.append("iTipEmi es obligatorio en gOpeDE")
        if gOpeDE.find("s:dCodSeg", NS_SIFEN) is None:
            errores.append("dCodSeg es obligatorio en gOpeDE")
    
    # Validar gTimb
    gTimb = de.find("s:gTimb", NS_SIFEN)
    if gTimb is not None:
        campos_timbrado = ["s:iTiDE", "s:dNumTim", "s:dEst", "s:dPunExp", "s:dNumDoc"]
        for campo in campos_timbrado:
            if gTimb.find(campo, NS_SIFEN) is None:
                errores.append(f"Campo de timbrado faltante: {campo}")
    
    # Validar gDatGralOpe
    gDatGralOpe = de.find("s:gDatGralOpe", NS_SIFEN)
    if gDatGralOpe is not None:
        if gDatGralOpe.find("s:dFeEmiDE", NS_SIFEN) is None:
            errores.append("dFeEmiDE es obligatorio")
        if gDatGralOpe.find("s:gOpeCom", NS_SIFEN) is None:
            errores.append("gOpeCom es obligatorio")
        if gDatGralOpe.find("s:gEmis", NS_SIFEN) is None:
            errores.append("gEmis es obligatorio")
        if gDatGralOpe.find("s:gDatRec", NS_SIFEN) is None:
            errores.append("gDatRec es obligatorio")
    
    # Validar gDtipDE
    gDtipDE = de.find("s:gDtipDE", NS_SIFEN)
    if gDtipDE is not None:
        # Debe tener al menos un item
        items = gDtipDE.findall("s:gCamItem", NS_SIFEN)
        if len(items) == 0:
            errores.append("Debe haber al menos un item en gDtipDE")
    
    # Validar gTotSub
    gTotSub = de.find("s:gTotSub", NS_SIFEN)
    if gTotSub is not None:
        campos_totales = ["s:dTotOpe", "s:dTotGralOpe", "s:dTotIVA"]
        for campo in campos_totales:
            if gTotSub.find(campo, NS_SIFEN) is None:
                errores.append(f"Campo de totales faltante: {campo}")
    
    return len(errores) == 0, errores


def main():
    """
    Función principal.
    """
    if len(sys.argv) != 2:
        print("Uso: python3 validar_factura.py <archivo.xml>")
        sys.exit(1)
    
    xml_file = sys.argv[1]
    
    if not os.path.exists(xml_file):
        print(f"Error: El archivo {xml_file} no existe")
        sys.exit(1)
    
    print(f"Validando factura: {xml_file}")
    print("=" * 60)
    
    es_valido, errores = validar_factura(xml_file)
    
    if es_valido:
        print("✅ Factura VÁLIDA")
        print("Todos los campos requeridos están presentes")
    else:
        print("❌ Factura INVÁLIDA")
        print("\nErrores encontrados:")
        for i, error in enumerate(errores, 1):
            print(f"{i}. {error}")
    
    print("=" * 60)
    sys.exit(0 if es_valido else 1)


if __name__ == "__main__":
    main()
