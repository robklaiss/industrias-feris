#!/usr/bin/env python3
"""
Test mínimo para verificar que el fix de sign_key_path está aplicado.
"""
import os
import sys

# Agregar paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tesaka-cv'))

def test_fix_applied():
    """Verifica que el fix está aplicado en el código fuente."""
    
    # Leer el archivo fuente
    send_sirecepde_path = os.path.join(
        os.path.dirname(__file__), '..', 'tesaka-cv', 'tools', 'send_sirecepde.py'
    )
    
    with open(send_sirecepde_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Verificar que el fix está presente
    # Buscar la línea corregida donde se llama a build_and_sign_lote_from_xml
    lines = content.split('\n')
    
    # Encontrar la línea donde se llama a build_and_sign_lote_from_xml en re-firma
    for i, line in enumerate(lines):
        if 'build_and_sign_lote_from_xml(' in line and 'result = build_and_sign_lote_from_xml(' in line:
            # Revisar las siguientes líneas
            context = lines[i:i+15]
            context_str = '\n'.join(context)
            
            print(f"Línea {i+1}: Encontrada llamada a build_and_sign_lote_from_xml")
            print("-" * 60)
            print(context_str)
            print("-" * 60)
            
            # Verificar que no está el bug
            if 'key_path=sign_key_path' in context_str:
                print("❌ BUG DETECTADO: Todavía usa 'key_path=sign_key_path'")
                return False
            
            # Verificar que está el fix
            if 'cert_password=sign_cert_password' in context_str:
                print("✅ FIX APLICADO: Usa 'cert_password=sign_cert_password'")
                
                # Verificar que los parámetros son correctos
                if 'cert_path=sign_cert_path' in context_str:
                    print("✅ Parámetro cert_path correcto")
                else:
                    print("❌ Falta parámetro cert_path")
                    return False
                
                # Verificar que no hay parámetros incorrectos
                if 'sign_passphrase' not in context_str:
                    print("✅ No está el parámetro incorrecto 'sign_passphrase'")
                else:
                    print("❌ Todavía está el parámetro incorrecto 'sign_passphrase'")
                    return False
                
                return True
            else:
                print("❌ FIX NO APLICADO: No se encuentra 'cert_password=sign_cert_password'")
                return False
    
    print("❌ No se encontró la llamada a build_and_sign_lote_from_xml en re-firma")
    return False


def test_function_signature():
    """Verifica que la firma de build_and_sign_lote_from_xml es la correcta."""
    
    send_sirecepde_path = os.path.join(
        os.path.dirname(__file__), '..', 'tesaka-cv', 'tools', 'send_sirecepde.py'
    )
    
    with open(send_sirecepde_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Buscar la definición de la función
    if 'def build_and_sign_lote_from_xml(' in content:
        # Extraer la firma
        start = content.find('def build_and_sign_lote_from_xml(')
        end = content.find('):', start) + 2
        func_signature = content[start:end]
        
        print(f"\nFirma de la función:\n{func_signature}")
        
        # Verificar parámetros
        if 'cert_path: str' in func_signature:
            print("✅ Tiene parámetro cert_path: str")
        else:
            print("❌ Falta cert_path: str")
            
        if 'cert_password: str' in func_signature:
            print("✅ Tiene parámetro cert_password: str")
        else:
            print("❌ Falta cert_password: str")
            
        if 'key_path' not in func_signature:
            print("✅ No tiene parámetro key_path (correcto)")
        else:
            print("❌ Tiene parámetro key_path (incorrecto)")
            
        return True
    else:
        print("❌ No se encontró la función build_and_sign_lote_from_xml")
        return False


if __name__ == '__main__':
    print("=== Verificando fix de sign_key_path ===\n")
    
    fix_ok = test_fix_applied()
    print()
    sig_ok = test_function_signature()
    
    if fix_ok and sig_ok:
        print("\n✅ EL FIX ESTÁ APLICADO CORRECTAMENTE")
        print("   - No hay NameError: sign_key_path not defined")
        print("   - Los parámetros son los correctos")
    else:
        print("\n❌ EL FIX NO ESTÁ COMPLETO")
        sys.exit(1)
