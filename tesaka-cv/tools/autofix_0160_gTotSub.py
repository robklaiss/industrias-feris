#!/usr/bin/env python3
"""
Auto-fix 0160 gTotSub - Loop automático para corregir orden de tags en gTotSub

Este script implementa un loop que:
1. Envía XML a SIFEN
2. Consulta el estado del lote
3. Si recibe error 0160 por orden incorrecto en gTotSub, corrige el XML
4. Reenvía el XML corregido
5. Repite hasta que el error sea diferente o se alcance el máximo de iteraciones
"""

import argparse
import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List
import lxml.etree as ET

# Importar helpers
from _autofix_helpers import (
    find_latest_file,
    run_command,
    validate_file_exists,
    print_separator
)




def parse_error_message(dMsgRes: str) -> Optional[str]:
    """
    Parsea el mensaje de error 0160 para extraer el tag esperado.
    
    Ejemplos:
    - "XML malformado: [El elemento esperado es: dTotOpe en lugar de: dTotIVA]"
    - "XML malformado: [El elemento esperado es: dTotGrav  en lugar de: dTotIVA]"
    - "XML malformado: [El elemento esperado es: dTotExe en lugar de: dTotIVA]"
    
    Retorna: "dTotOpe", "dTotGrav", "dTotExe", etc.
    """
    if "XML malformado:" not in dMsgRes:
        return None
    
    # Buscar el patrón: "El elemento esperado es: X en lugar de: Y"
    # Permitir espacios extra después del tag
    match = re.search(r'El elemento esperado es: (\w+)\s*en lugar de:', dMsgRes)
    if match:
        return match.group(1)
    
    return None


def fix_gtotsub_order(xml_path: Path, expected_tag: str) -> Path:
    """
    Corrige el orden de tags en gTotSub asegurando que expected_tag esté antes de dTotIVA.
    
    Retorna el path del XML corregido.
    """
    # Parsear XML con lxml para preservar namespaces
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    # Obtener namespace principal (sin prefijo)
    ns_map = root.nsmap
    main_ns = ns_map.get(None)
    if not main_ns:
        # Si no hay namespace por defecto, buscar el primer namespace
        for prefix, uri in ns_map.items():
            if prefix is not None and 'sifen' in uri:
                main_ns = uri
                break
    
    if not main_ns:
        print("⚠️  No se pudo determinar el namespace del XML")
        return xml_path
    
    # Configurar namespaces para XPath
    ns = {'sifen': main_ns}
    
    # Encontrar todos los nodos gTotSub
    gtotsubs = root.xpath('.//sifen:gTotSub', namespaces=ns)
    
    if not gtotsubs:
        print("⚠️  No se encontraron nodos gTotSub en el XML")
        return xml_path
    
    made_changes = False
    fixed_count = 0
    
    for gtotsub in gtotsubs:
        # Encontrar dTotIVA
        dtotiva = gtotsub.find('sifen:dTotIVA', namespaces=ns)
        if dtotiva is None:
            print(f"⚠️  gTotSub sin dTotIVA encontrado, omitiendo")
            continue
        
        # Encontrar el tag esperado
        expected_elem = gtotsub.find(f'sifen:{expected_tag}', namespaces=ns)
        
        if expected_elem is None:
            # Crear el elemento faltante con valor "0"
            expected_elem = ET.SubElement(gtotsub, f'{{{main_ns}}}{expected_tag}')
            expected_elem.text = "0"
            # Insertarlo antes de dTotIVA
            gtotsub.insert(gtotsub.index(dtotiva), expected_elem)
            made_changes = True
            fixed_count += 1
            print(f"   ✅ Creado tag {expected_tag} con valor '0'")
        else:
            # Verificar si está después de dTotIVA
            expected_idx = gtotsub.index(expected_elem)
            dtotiva_idx = gtotsub.index(dtotiva)
            
            if expected_idx > dtotiva_idx:
                # Moverlo antes de dTotIVA
                gtotsub.insert(dtotiva_idx, expected_elem)
                made_changes = True
                fixed_count += 1
                print(f"   ✅ Movido tag {expected_tag} antes de dTotIVA")
    
    if made_changes:
        # Guardar XML corregido
        iter_num = get_iteration_from_path(xml_path)
        output_path = xml_path.parent / f"autofix_iter{iter_num}_{expected_tag}.xml"
        
        # Escribir XML sin pretty print para preservar firma
        tree.write(output_path, encoding='utf-8', xml_declaration=True, standalone=False)
        
        print(f"✅ XML corregido: {fixed_count} gTotSub modificados")
        print(f"   Guardado en: {output_path.name}")
        return output_path
    else:
        print(f"ℹ️  No se necesitaron cambios para el tag {expected_tag}")
        return xml_path


def get_iteration_from_path(path: Path) -> int:
    """Extrae el número de iteración del nombre del archivo"""
    match = re.search(r'iter(\d+)', path.name)
    if match:
        return int(match.group(1))
    return 0


def run_send_sirecepde(env: str, xml_path: Path, artifacts_dir: Path, 
                      iteration: int, bump_doc: bool, dump_http: bool) -> Path:
    """Ejecuta send_sirecepde.py y retorna el path del response JSON"""
    cmd = [
        sys.executable, 'tools/send_sirecepde.py',
        '--env', env,
        '--xml', str(xml_path),
        '--artifacts-dir', str(artifacts_dir),
        '--iteration', str(iteration)
    ]
    
    if bump_doc:
        cmd.extend(['--bump-doc', '1'])
    if dump_http:
        cmd.append('--dump-http')
    
    print(f"📤 Enviando XML (iter {iteration})...")
    
    result = run_command(cmd)
    
    if result.returncode != 0:
        sys.exit(1)
    
    # Buscar el response más reciente
    response_file = find_latest_file("response_recepcion_*_iter*.json", artifacts_dir)
    if not response_file:
        print("❌ No se encontró el response JSON")
        sys.exit(1)
    
    print(f"✅ Response guardado en: {response_file.name}")
    return response_file


def run_follow_lote(response_json: Path, artifacts_dir: Path) -> Path:
    """Ejecuta follow_lote.py y retorna el path del consulta_lote JSON"""
    cmd = [
        sys.executable, 'tools/follow_lote.py',
        '--once', str(response_json)
    ]
    
    print(f"🔍 Consultando estado del lote...")
    
    result = run_command(cmd)
    
    if result.returncode != 0:
        sys.exit(1)
    
    # Buscar el consulta_lote más reciente
    consulta_file = find_latest_file("consulta_lote_*.json", artifacts_dir)
    if not consulta_file:
        print("❌ No se encontró el consulta_lote JSON")
        sys.exit(1)
    
    print(f"✅ Consulta guardada en: {consulta_file.name}")
    return consulta_file


def extract_result_from_consulta(consulta_json: Path) -> Tuple[str, str]:
    """Extrae dCodRes y dMsgRes del JSON de consulta"""
    with open(consulta_json, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Buscar el primer DE con resultado
    for item in data.get('items', []):
        if 'prot' in item and 'dCodRes' in item['prot']:
            return item['prot']['dCodRes'], item['prot'].get('dMsgRes', '')
    
    return "", ""


def main():
    parser = argparse.ArgumentParser(description='Auto-fix 0160 gTotSub - Loop automático')
    parser.add_argument('--env', required=True, choices=['prod', 'test'], help='Ambiente')
    parser.add_argument('--xml', required=True, type=Path, help='XML inicial a enviar')
    parser.add_argument('--artifacts-dir', required=True, type=Path, help='Directorio de artifacts')
    parser.add_argument('--max-iters', type=int, default=20, help='Máximo de iteraciones')
    parser.add_argument('--start-iteration', type=int, default=1, help='Número de iteración inicial')
    parser.add_argument('--bump-doc', type=int, choices=[0, 1], default=1, help='Incrementar número de documento')
    parser.add_argument('--dump-http', action='store_true', help='Mostrar HTTP dump')
    
    args = parser.parse_args()
    
    # Validar que el XML inicial exista
    validate_file_exists(args.xml, "el archivo XML")
    
    # Crear directorio de artifacts si no existe
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    current_xml = args.xml
    iteration = args.start_iteration
    
    print_separator("Auto-fix 0160 gTotSub")
    print(f"🚀 Configuración:")
    print(f"   Env: {args.env}")
    print(f"   XML inicial: {current_xml.name}")
    print(f"   Artifacts: {args.artifacts_dir}")
    print(f"   Max iteraciones: {args.max_iters}")
    print(f"   Iniciar en iteración: {iteration}")
    print(f"   Bump doc: {'Sí' if args.bump_doc else 'No'}")
    print()
    
    while iteration <= args.max_iters:
        print_separator(f"Iteración {iteration}")
        
        # 1. Enviar XML
        response_json = run_send_sirecepde(
            args.env, current_xml, args.artifacts_dir, 
            iteration, args.bump_doc == 1, args.dump_http
        )
        
        # 2. Consultar lote
        consulta_json = run_follow_lote(response_json, args.artifacts_dir)
        
        # 3. Extraer resultado
        dCodRes, dMsgRes = extract_result_from_consulta(consulta_json)
        
        print(f"📋 Resultado: dCodRes={dCodRes}")
        
        if dCodRes != "0160":
            print_separator("Resultado final")
            if dCodRes == "0":
                print("✅ APROBADO - El lote fue aceptado")
            else:
                print(f"⚠️  RECHAZADO con código {dCodRes}")
                if dMsgRes:
                    print(f"   Mensaje: {dMsgRes}")
            print()
            print("🎯 Resumen del proceso:")
            print(f"   Iteraciones realizadas: {iteration - args.start_iteration + 1}")
            print(f"   XML final: {current_xml.name}")
            print(f"   Código final: {dCodRes}")
            break
        
        # 4. Parsear error 0160
        print(f"❌ Error 0160: {dMsgRes}")
        expected_tag = parse_error_message(dMsgRes)
        
        if not expected_tag:
            print("⚠️  Error 0160 pero no coincide con el patrón esperado. Deteniendo.")
            break
        
        print(f"🔧 Tag esperado encontrado: {expected_tag}")
        
        # 5. Corregir XML
        print_separator(f"Corrigiendo XML: {expected_tag}")
        fixed_xml = fix_gtotsub_order(current_xml, expected_tag)
        
        if fixed_xml == current_xml:
            print("⚠️  No se realizaron cambios en el XML. Deteniendo.")
            break
        
        # Preparar siguiente iteración
        current_xml = fixed_xml
        iteration += 1
        print()
    
    if iteration > args.max_iters:
        print_separator("Límite alcanzado")
        print(f"⏹️  Alcanzado el máximo de iteraciones ({args.max_iters})")
        print(f"   Último XML: {current_xml.name}")


if __name__ == "__main__":
    main()
