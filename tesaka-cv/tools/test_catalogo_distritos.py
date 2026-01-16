#!/usr/bin/env python3
"""
Script de prueba para validar catálogo de distritos
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.catalogos.distritos_py import get_descripcion_distrito, get_descripcion_departamento

def test_catalogo():
    """Prueba el catálogo de distritos con códigos conocidos"""
    
    print("🧪 Probando catálogo de distritos SIFEN")
    print("=" * 50)
    
    # Casos de prueba
    test_cases = [
        # (departamento, distrito, descripcion_esperada)
        ("11", "14", "HERNANDARIAS"),  # Alto Paraná - Hernandarias
        ("11", "1", "CIUDAD DEL ESTE"),  # Alto Paraná - Ciudad del Este
        ("12", "169", "LAMBARE"),  # Central - Lambare
        ("12", "1", "ASUNCION"),  # Central - Asunción
    ]
    
    for cod_dep, cod_dis, desc_esperada in test_cases:
        desc_obtenida = get_descripcion_distrito(cod_dep, cod_dis)
        desc_dep = get_descripcion_departamento(cod_dep)
        
        print(f"\nDepartamento: {cod_dep} ({desc_dep})")
        print(f"Distrito: {cod_dis}")
        print(f"Descripción esperada: {desc_esperada}")
        print(f"Descripción obtenida: {desc_obtenida}")
        
        if desc_obtenida == desc_esperada:
            print("✅ Coincide")
        else:
            print("❌ No coincide")
    
    print("\n" + "=" * 50)
    print("Prueba completada")

if __name__ == "__main__":
    test_catalogo()
