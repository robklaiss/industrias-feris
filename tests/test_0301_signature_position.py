#!/usr/bin/env python3
"""
Test de regresión para verificar que la Signature esté en la posición correcta.
Según la solución del error 0160, la Signature debe estar:
- Dentro de rDE
- Como hermano de DE (después)
- Antes de gCamFuFD si existe
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
DSIG_NS = "http://www.w3.org/2000/09/xmldsig#"

def test_signature_position():
    """Verifica que la Signature esté en la posición correcta según solución error 0160."""
    # Cargar el XML del último envío
    lote_path = Path("artifacts/lote_from_006.xml")
    if not lote_path.exists():
        print("❌ No se encontró lote_from_006.xml")
        return False
    
    # Parsear XML
    lote = ET.parse(lote_path)
    root = lote.getroot()
    
    # Encontrar rDE
    rde = root.find(f".//{{{SIFEN_NS}}}rDE")
    if rde is None:
        print("❌ No se encontró rDE")
        return False
    
    # Obtener hijos en orden
    children = list(rde)
    child_tags = [child.tag.split('}')[-1] if '}' in child.tag else child.tag 
                  for child in children]
    
    print("Estructura encontrada:")
    for i, tag in enumerate(child_tags):
        print(f"  {i}: {tag}")
    
    # Verificar estructura esperada según error 0160
    expected_order = ["dVerFor", "DE", "Signature", "gCamFuFD"]
    
    # 1. dVerFor debe ser primero
    if child_tags[0] != "dVerFor":
        print(f"❌ dVerFor no es primero: {child_tags[0]}")
        return False
    
    # 2. DE debe estar después de dVerFor
    if "DE" not in child_tags[1:]:
        print("❌ DE no encontrado después de dVerFor")
        return False
    
    # 3. Signature debe estar después de DE
    de_idx = child_tags.index("DE")
    sig_idx = None
    for i, tag in enumerate(child_tags):
        if tag == "Signature":
            sig_idx = i
            break
    
    if sig_idx is None:
        print("❌ Signature no encontrado")
        return False
    
    if sig_idx <= de_idx:
        print(f"❌ Signature no está después de DE (DE={de_idx}, Sig={sig_idx})")
        return False
    
    # 4. gCamFuFD debe estar después de Signature (si existe)
    if "gCamFuFD" in child_tags:
        gcam_idx = child_tags.index("gCamFuFD")
        if gcam_idx <= sig_idx:
            print(f"❌ gCamFuFD no está después de Signature (Sig={sig_idx}, gCam={gcam_idx})")
            return False
    
    # 5. Verificar que Signature NO esté dentro de DE
    de_elem = rde.find(f".//{{{SIFEN_NS}}}DE")
    if de_elem is not None:
        sig_in_de = de_elem.find(f".//{{{DSIG_NS}}}Signature")
        if sig_in_de is not None:
            print("❌ Signature está DENTRO de DE (incorrecto)")
            return False
    
    print("✅ Estructura correcta según solución error 0160")
    return True

if __name__ == "__main__":
    success = test_signature_position()
    sys.exit(0 if success else 1)
