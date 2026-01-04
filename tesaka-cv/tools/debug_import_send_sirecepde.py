#!/usr/bin/env python3
"""
Script de test rápido para verificar que tools.send_sirecepde se puede importar
y que local_tag está disponible a nivel módulo.
"""
import sys
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import importlib
    import importlib.util
    
    # Intentar importar el módulo
    # Si falla por dependencias, al menos verificar que el archivo se puede parsear
    module_path = Path(__file__).parent / "send_sirecepde.py"
    
    # Verificar sintaxis primero
    try:
        with open(module_path, 'r', encoding='utf-8') as f:
            code = f.read()
        compile(code, str(module_path), 'exec')
        print("✅ Sintaxis del archivo OK")
    except SyntaxError as e:
        print(f"❌ ERROR de sintaxis: {e}")
        sys.exit(1)
    
    # Intentar importar (puede fallar por dependencias, pero eso es OK para este test)
    try:
        m = importlib.import_module("tools.send_sirecepde")
        print("✅ MODULE FILE:", m.__file__)
        print("✅ hasattr(local_tag):", hasattr(m, "local_tag"))
        if hasattr(m, "local_tag"):
            print("✅ local_tag test:", m.local_tag("{ns}rDE"))
            print("✅ local_tag test (sin ns):", m.local_tag("rDE"))
            print("✅ local_tag test (QName completo):", m.local_tag("{http://ekuatia.set.gov.py/sifen/xsd}rDE"))
        else:
            print("❌ ERROR: local_tag no está disponible en el módulo")
            sys.exit(1)
    except ImportError as e:
        # Si falla por dependencias, al menos verificar que local_tag esté definida en el código
        print(f"⚠️  Advertencia: No se pudo importar módulo completo (dependencias faltantes: {e})")
        print("   Verificando que local_tag esté definida en el código...")
        
        # Buscar definición de local_tag en el código
        if 'def local_tag(tag: str) -> str:' in code:
            print("✅ local_tag está definida en el código")
            # Verificar que esté a nivel módulo (columna 0)
            lines = code.split('\n')
            for i, line in enumerate(lines, 1):
                if line.strip().startswith('def local_tag'):
                    if line.startswith('def local_tag'):
                        print(f"✅ local_tag definida a nivel módulo (línea {i}, columna 0)")
                        break
                    else:
                        print(f"❌ ERROR: local_tag NO está a nivel módulo (línea {i}, indentada)")
                        sys.exit(1)
        else:
            print("❌ ERROR: local_tag NO está definida en el código")
            sys.exit(1)
        
        print("\n⚠️  Nota: El módulo no se pudo importar completamente por dependencias faltantes,")
        print("   pero local_tag está correctamente definida en el código.")
        sys.exit(0)
    except Exception as e:
        print(f"❌ ERROR inesperado: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ Todos los tests pasaron correctamente")

