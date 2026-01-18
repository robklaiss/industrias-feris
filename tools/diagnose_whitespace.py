#!/usr/bin/env python3
"""
Diagnóstico y limpieza de whitespace en XML SIFEN
Basado en las reglas del knowledge base:
- NO incorporar: line-feed, carriage return, tab, espacios entre etiquetas
"""

import sys
import re
from pathlib import Path
from lxml import etree

def count_whitespace_nodes(xml_str):
    """Cuenta nodos de texto que son solo whitespace"""
    parser = etree.XMLParser(remove_blank_text=False)
    root = etree.fromstring(xml_str.encode('utf-8'), parser)
    
    whitespace_count = 0
    total_text_nodes = 0
    
    for element in root.iter():
        if element.text and element.text.strip() == '':
            whitespace_count += 1
        if element.text:
            total_text_nodes += 1
        if element.tail and element.tail.strip() == '':
            whitespace_count += 1
        if element.tail:
            total_text_nodes += 1
            
    return whitespace_count, total_text_nodes

def clean_whitespace(xml_str):
    """Elimina whitespace entre etiquetas"""
    # Parsear con remove_blank_text=True para eliminar whitespace insignificante
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(xml_str.encode('utf-8'), parser)
    
    # Eliminar cualquier text/tail que sea solo whitespace
    for element in root.iter():
        if element.text and element.text.strip() == '':
            element.text = None
        if element.tail and element.tail.strip() == '':
            element.tail = None
    
    # Serializar sin pretty_print y sin XML declaration
    cleaned = etree.tostring(root, encoding='UTF-8', method='xml', 
                           pretty_print=False, standalone=False)
    
    return cleaned.decode('utf-8')

def validate_xml_structure(xml_str):
    """Valida estructura básica según SIFEN v150"""
    parser = etree.XMLParser(remove_blank_text=True)
    root = etree.fromstring(xml_str.encode('utf-8'), parser)
    
    issues = []
    
    # Verificar que rLoteDE no tenga prefijo
    if root.tag.startswith('{'):
        issues.append(f"❌ rLoteDE tiene namespace con prefijo: {root.tag}")
    else:
        issues.append("✅ rLoteDE sin prefijos")
    
    # Verificar rDE
    rde = root.find('.//rDE')
    if rde is None:
        issues.append("❌ No se encontró rDE")
        return issues
    
    if rde.tag.startswith('{'):
        issues.append(f"❌ rDE tiene namespace con prefijo: {rde.tag}")
    else:
        issues.append("✅ rDE sin prefijos")
    
    # Verificar dVerFor como primer hijo
    children = list(rde)
    if children and children[0].tag == 'dVerFor':
        issues.append(f"✅ dVerFor es primer hijo de rDE (valor: {children[0].text})")
    else:
        issues.append("❌ dVerFor no es primer hijo de rDE")
    
    # Verificar Signature sin prefijos
    sig = root.find('.//Signature')
    if sig is not None:
        if sig.tag.startswith('{'):
            issues.append(f"❌ Signature tiene namespace con prefijo: {sig.tag}")
        else:
            issues.append("✅ Signature sin prefijos")
    
    # Verificar que no haya \n o \t fuera de valores
    if '\n' in xml_str or '\t' in xml_str:
        issues.append("❌ XML contiene \\n o \\t")
    else:
        issues.append("✅ XML sin \\n ni \\t")
    
    return issues

def main():
    if len(sys.argv) != 2:
        print("Uso: python diagnose_whitespace.py <archivo.xml>")
        sys.exit(1)
    
    xml_file = Path(sys.argv[1])
    if not xml_file.exists():
        print(f"Error: No existe el archivo {xml_file}")
        sys.exit(1)
    
    # Leer XML
    xml_str = xml_file.read_text('utf-8')
    
    print("=== ANÁLISIS DE WHITESPACE ===")
    print(f"Archivo: {xml_file}")
    print(f"Tamaño: {len(xml_str)} bytes")
    
    # Contar whitespace
    ws_count, total_count = count_whitespace_nodes(xml_str)
    print(f"\nNodos de texto con whitespace puro: {ws_count}")
    print(f"Total de nodos de texto: {total_count}")
    
    # Validar estructura
    print("\n=== VALIDACIÓN DE ESTRUCTURA ===")
    for issue in validate_xml_structure(xml_str):
        print(issue)
    
    # Limpiar whitespace
    print("\n=== LIMPIEZA DE WHITESPACE ===")
    cleaned = clean_whitespace(xml_str)
    
    # Verificar limpieza
    ws_count_after, _ = count_whitespace_nodes(cleaned)
    print(f"Whitespace después de limpiar: {ws_count_after}")
    print(f"Tamaño después de limpiar: {len(cleaned)} bytes")
    print(f"Reducción: {len(xml_str) - len(cleaned)} bytes ({(len(xml_str) - len(cleaned))/len(xml_str)*100:.1f}%)")
    
    # Guardar versión limpia
    output_file = xml_file.parent / f"{xml_file.stem}_cleaned.xml"
    output_file.write_text(cleaned, 'utf-8')
    print(f"\n✅ XML limpio guardado en: {output_file}")
    
    # Mostrar diferencias
    print("\n=== DIFERENCIAS (PRIMERAS LÍNEAS) ===")
    print("ANTES:")
    print('\n'.join(xml_str.split('\n')[:10]))
    print("\nDESPUÉS:")
    print(cleaned[:200] + "..." if len(cleaned) > 200 else cleaned)

if __name__ == "__main__":
    main()
