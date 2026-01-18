#!/usr/bin/env python3
import sys
import re
from difflib import unified_diff

def normalize_soap(content):
    # Normalizar contenido de <dId> a __DID__
    content = re.sub(r'<[^>]*:dId[^>]*>.*?</[^>]*:dId[^>]*>', '__DID__', content, flags=re.DOTALL)
    
    # Eliminar whitespace dentro de <xDE>...</xDE>
    content = re.sub(r'(<[^>]*:xDE[^>]*>)(.*?)(</[^>]*:xDE[^>]*>)', 
                     lambda m: m.group(1) + re.sub(r'\s+', '', m.group(2)) + m.group(3),
                     content, flags=re.DOTALL)
    
    # Compactar whitespace entre tags
    content = re.sub(r'>\s+<', '><', content)
    
    return content

def main():
    if len(sys.argv) != 3:
        print("Uso: python3 compare_soap_requests.py <file1> <file2>")
        sys.exit(1)
    
    file1, file2 = sys.argv[1], sys.argv[2]
    
    # Leer archivos
    try:
        with open(file1, 'r', encoding='utf-8', errors='replace') as f:
            content1 = f.read()
    except Exception as e:
        print(f"Error leyendo {file1}: {e}")
        sys.exit(1)
    
    try:
        with open(file2, 'r', encoding='utf-8', errors='replace') as f:
            content2 = f.read()
    except Exception as e:
        print(f"Error leyendo {file2}: {e}")
        sys.exit(1)
    
    # Normalizar
    norm1 = normalize_soap(content1)
    norm2 = normalize_soap(content2)
    
    # Comparar
    if norm1 == norm2:
        print("IDENTICOS")
        return
    
    print("DIFERENTES")
    
    # Generar diff
    lines1 = norm1.splitlines(keepends=True)
    lines2 = norm2.splitlines(keepends=True)
    
    diff = unified_diff(lines1, lines2, fromfile=file1, tofile=file2, lineterm='')
    
    # Guardar diff completo
    try:
        with open('artifacts/soap_diff_full.txt', 'w', encoding='utf-8') as f:
            f.writelines(diff)
    except Exception as e:
        print(f"Error guardando diff completo: {e}")
        sys.exit(1)
    
    # Imprimir primeras 120 líneas
    diff_lines = list(diff)
    head_lines = diff_lines[:120]
    
    for line in head_lines:
        print(line)
    
    if len(diff_lines) > 120:
        print(f"\n... ({len(diff_lines) - 120} líneas más en artifacts/soap_diff_full.txt)")

if __name__ == "__main__":
    main()
