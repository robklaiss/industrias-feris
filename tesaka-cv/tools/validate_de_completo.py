#!/usr/bin/env python3
"""
Validación completa del DE según especificaciones SIFEN v150
"""
import sys
from lxml import etree

def validate_de_completo(xml_path: str) -> int:
    tree = etree.parse(xml_path)
    root = tree.getroot()
    ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd'}
    
    # Encontrar el DE
    de = root.find('.//s:DE', namespaces=ns)
    if de is None:
        print("❌ No se encontró elemento DE")
        return 2
    
    print("=== VALIDACIÓN DE DE COMPLETO ===\n")
    
    # 1. Campos básicos
    print("1. CAMPOS BÁSICOS:")
    basicos = ['dDVId', 'dFecFirma', 'dSisFact']
    for campo in basicos:
        elem = de.find(f's:{campo}', namespaces=ns)
        if elem is not None:
            print(f"   ✅ {campo}: {elem.text}")
        else:
            print(f"   ❌ {campo}: FALTANTE")
    
    # 2. Grupos obligatorios
    print("\n2. GRUPOS OBLIGATORIOS:")
    grupos = [
        'gOpeDE', 'gTimb', 'gDatGralOpe', 
        'gEmis', 'gDatRec', 'gDtipDE', 
        'gCamDE', 'gCamItem', 'gValItem'
    ]
    
    for grupo in grupos:
        elem = de.find(f's:{grupo}', namespaces=ns)
        if elem is not None:
            print(f"   ✅ {grupo}: presente")
            # Verificar subelementos clave
            if grupo == 'gOpeDE':
                dTiOpe = elem.find('s:dTiOpe', namespaces=ns)
                print(f"      - dTiOpe: {dTiOpe.text if dTiOpe is not None else '❌'}")
            elif grupo == 'gTimb':
                dNumTim = elem.find('s:dNumTim', namespaces=ns)
                print(f"      - dNumTim: {dNumTim.text if dNumTim is not None else '❌'}")
            elif grupo == 'gEmis':
                dRucEm = elem.find('s:dRucEm', namespaces=ns)
                print(f"      - dRucEm: {dRucEm.text if dRucEm is not None else '❌'}")
            elif grupo == 'gDatRec':
                dRucRec = elem.find('s:dRucRec', namespaces=ns)
                print(f"      - dRucRec: {dRucRec.text if dRucRec is not None else '❌'}")
            elif grupo == 'gValItem':
                dTotGralOp = elem.find('s:dTotGralOp', namespaces=ns)
                print(f"      - dTotGralOp: {dTotGralOp.text if dTotGralOp is not None else '❌'}")
        else:
            print(f"   ❌ {grupo}: FALTANTE")
    
    # 3. Verificar gCamGen (opcional pero a veces requerido)
    print("\n3. GRUPOS OPCIONALES:")
    gcamgen = de.find('s:gCamGen', namespaces=ns)
    gcamcond = de.find('s:gCamCond', namespaces=ns)
    gcamncde = de.find('s:gCamNCDE', namespaces=ns)
    
    print(f"   gCamGen: {'✅' if gcamgen is not None else '❌ (opcional)'}")
    print(f"   gCamCond: {'✅' if gcamcond is not None else '❌ (opcional)'}")
    print(f"   gCamNCDE: {'✅' if gcamncde is not None else '❌ (opcional)'}")
    
    # 4. Verificar orden según XSD
    print("\n4. ORDEN DE ELEMENTOS:")
    orden_esperado = [
        'dDVId', 'dFecFirma', 'dSisFact',
        'gOpeDE', 'gTimb', 'gDatGralOpe',
        'gEmis', 'gDatRec', 'gDtipDE',
        'gCamDE', 'gCamItem', 'gValItem',
        'gCamGen', 'gCamCond', 'gCamNCDE'
    ]
    
    hijos = [c.tag.split('}')[-1] for c in de]
    print("   Orden actual:")
    for i, tag in enumerate(hijos):
        expected = "✅" if i < len(orden_esperado) and orden_esperado[i] == tag else "❌"
        print(f"   [{i:2d}] {tag} {expected}")
    
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python tools/validate_de_completo.py <archivo.xml>", file=sys.stderr)
        sys.exit(2)
    
    xml_path = sys.argv[1]
    sys.exit(validate_de_completo(xml_path))
