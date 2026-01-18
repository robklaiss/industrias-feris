#!/usr/bin/env python3
"""
Smoke test para detectar error 0160 "XML Mal Formado" de SIFEN.
Este script debe ejecutarse obligatoriamente después de cambios en ZIP/envelope/namespaces/firma.

Uso:
    .venv/bin/python tools/smoke_send_0160_guardrail.py --xml path/to/signed.xml [--env test] [--dump-path path/to/dump.txt] [--timestamped-dump]

Ejemplos:
    # Test con XML firmado en ambiente de pruebas
    .venv/bin/python tools/smoke_send_0160_guardrail.py --xml artifacts/signed_lote.xml
    
    # Test con dump personalizado
    .venv/bin/python tools/smoke_send_0160_guardrail.py --xml artifacts/signed_lote.xml --dump-path debug/dump.txt
    
    # Selftest para verificar la detección
    .venv/bin/python tools/smoke_send_0160_guardrail.py --selftest
    
    # Test en producción (cuidado!)
    .venv/bin/python tools/smoke_send_0160_guardrail.py --xml artifacts/signed_lote.xml --env prod
"""

import argparse
import sys
import os
import re
from pathlib import Path

# Manejar selftest antes de importar módulos del proyecto
if "--selftest" in sys.argv:
    # Definir función de detección local para el test
    def detect_0160_in_response(response_str):
        """Detectar error 0160 con precisión, devolviendo (found, field_path, snippet)"""
        
        # 1) Buscar en dCodRes (prioridad máxima)
        dCodRes_pattern = r'<(?:ns1:)?dCodRes>(\d+)</(?:ns1:)?dCodRes>'
        match = re.search(dCodRes_pattern, response_str)
        if match and match.group(1) == "0160":
            start = max(0, match.start() - 50)
            end = min(len(response_str), match.end() + 50)
            snippet = response_str[start:end].replace('\n', ' ')
            return True, "dCodRes", snippet
        
        # 2) Buscar en codigoEstado
        codEstado_pattern = r'<(?:ns1:)?codigoEstado>(\d+)</(?:ns1:)?codigoEstado>'
        match = re.search(codEstado_pattern, response_str)
        if match and match.group(1) == "0160":
            start = max(0, match.start() - 50)
            end = min(len(response_str), match.end() + 50)
            snippet = response_str[start:end].replace('\n', ' ')
            return True, "codigoEstado", snippet
        
        # 3) Búsqueda textual contextual solo cerca de dCodRes o XML
        contextual_pattern = r'0160.{0,50}(?:dCodRes|XML|XML\s+Mal\s+Formado)'
        match = re.search(contextual_pattern, response_str, re.IGNORECASE)
        if match:
            start = max(0, match.start() - 50)
            end = min(len(response_str), match.end() + 50)
            snippet = response_str[start:end].replace('\n', ' ')
            return True, "contextual", snippet
        
        return False, None, None
    
    print("🧪 Ejecutando selftest del smoke test 0160...")
    
    # Test 1: Respuesta OK (sin 0160)
    ok_response = """
    <rResEnviDe>
        <dCodRes>0502</dCodRes>
        <dMsgRes>Procesado correctamente</dMsgRes>
    </rResEnviDe>
    """
    found, field, snippet = detect_0160_in_response(ok_response)
    if found:
        print(f"❌ Test OK falló: detectó 0160 en respuesta válida")
        print(f"   Campo: {field}")
        print(f"   Snippet: {snippet}")
        sys.exit(2)
    else:
        print("✅ Test OK pasado: no detectó 0160")
    
    # Test 2: Respuesta FAIL (con 0160)
    fail_response = """
    <rResEnviDe>
        <dCodRes>0160</dCodRes>
        <dMsgRes>XML Mal Formado</dMsgRes>
    </rResEnviDe>
    """
    found, field, snippet = detect_0160_in_response(fail_response)
    if not found:
        print("❌ Test FAIL falló: no detectó 0160")
        sys.exit(2)
    else:
        print(f"✅ Test FAIL pasado: detectó 0160 en campo {field}")
        print(f"   Snippet: {snippet[:100]}...")
    
    # Test 3: Falso positivo (0160 en CDC)
    false_positive = """
    <rResEnviDe>
        <dCodRes>0502</dCodRes>
        <CDC>016020260117000001234567890123456789012345678901234567890123456789</CDC>
    </rResEnviDe>
    """
    found, field, snippet = detect_0160_in_response(false_positive)
    if found:
        print(f"❌ Test falso positivo falló: detectó 0160 en CDC")
        sys.exit(2)
    else:
        print("✅ Test falso positivo pasado: no detectó 0160 en CDC")
    
    print("✅ Todos los tests pasados")
    sys.exit(0)

# Agregar el path del proyecto para importar módulos
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "tesaka-cv"))

try:
    from app.sifen_client.sifen_client import SIFENClient
except ImportError as e:
    print(f"ERROR: No se puede importar SIFENClient: {e}")
    print("Asegúrate de estar en el directorio del proyecto y con el venv activo")
    sys.exit(1)


def detect_0160_in_response(response_str):
    """Detectar error 0160 con precisión, devolviendo (found, field_path, snippet)"""
    
    # 1) Buscar en dCodRes (prioridad máxima)
    dCodRes_pattern = r'<(?:ns1:)?dCodRes>(\d+)</(?:ns1:)?dCodRes>'
    match = re.search(dCodRes_pattern, response_str)
    if match and match.group(1) == "0160":
        start = max(0, match.start() - 50)
        end = min(len(response_str), match.end() + 50)
        snippet = response_str[start:end].replace('\n', ' ')
        return True, "dCodRes", snippet
    
    # 2) Buscar en codigoEstado
    codEstado_pattern = r'<(?:ns1:)?codigoEstado>(\d+)</(?:ns1:)?codigoEstado>'
    match = re.search(codEstado_pattern, response_str)
    if match and match.group(1) == "0160":
        start = max(0, match.start() - 50)
        end = min(len(response_str), match.end() + 50)
        snippet = response_str[start:end].replace('\n', ' ')
        return True, "codigoEstado", snippet
    
    # 3) Búsqueda textual contextual solo cerca de dCodRes o XML
    # Buscar "0160" seguido de "dCodRes" o "XML" en un radio de 50 caracteres
    contextual_pattern = r'0160.{0,50}(?:dCodRes|XML|XML\s+Mal\s+Formado)'
    match = re.search(contextual_pattern, response_str, re.IGNORECASE)
    if match:
        start = max(0, match.start() - 50)
        end = min(len(response_str), match.end() + 50)
        snippet = response_str[start:end].replace('\n', ' ')
        return True, "contextual", snippet
    
    return False, None, None


def extract_codigo_from_response(response_str):
    """Extraer códigos de respuesta de SIFEN"""
    # Buscar patrones comunes de códigos
    patterns = [
        r'<dCodRes>(\d+)</dCodRes>',
        r'<ns1:dCodRes>(\d+)</ns1:dCodRes>',
        r'<codigoEstado>(\d+)</codigoEstado>',
        r'<ns1:codigoEstado>(\d+)</ns1:codigoEstado>',
        r'"dCodRes":\s*"(\d+)"',
        r'"codigoEstado":\s*"(\d+)"',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, response_str)
        if match:
            return match.group(1)
    
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Smoke test para detectar error 0160 de SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("--xml", required=not "--selftest" in sys.argv, help="Path al XML firmado a enviar")
    parser.add_argument("--env", default="test", choices=["test", "prod"], 
                       help="Ambiente (default: test)")
    parser.add_argument("--dump-path", default=None, 
                       help="Path donde guardar el HTTP dump (default: artifacts/http_last_dump.txt)")
    parser.add_argument("--timestamped-dump", action="store_true",
                       help="Agregar timestamp al nombre del dump")
    parser.add_argument("--selftest", action="store_true",
                       help="Ejecutar test unitario interno")
    
    args = parser.parse_args()
    
    # Verificar que el XML exista
    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"ERROR: No existe el archivo {xml_path}")
        sys.exit(1)
    
    # Crear directorio de artifacts si no existe
    artifacts_dir = project_root / "tesaka-cv" / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    
    # Determinar path del dump
    if args.dump_path:
        dump_file = Path(args.dump_path)
        # Crear directorio padre si no existe
        dump_file.parent.mkdir(parents=True, exist_ok=True)
    else:
        dump_file = artifacts_dir / "http_last_dump.txt"
    
    # Agregar timestamp si se solicitó
    if args.timestamped_dump:
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = dump_file.stem
        suffix = dump_file.suffix
        dump_file = dump_file.parent / f"{stem}_{timestamp}{suffix}"
    
    print(f"🚀 Smoke Test SIFEN - Detección de error 0160")
    print(f"📁 XML: {xml_path}")
    print(f"🌍 Ambiente: {args.env}")
    print("-" * 50)
    
    try:
        # Inicializar cliente SIFEN
        client = SIFENClient(env=args.env)
        
        # Enviar el lote con dump HTTP
        print("⏳ Enviando lote a SIFEN...")
        result = client.send_lote_de(
            xml_file=str(xml_path),
            dump_http=True
        )
        
        # Convertir resultado a string para análisis
        result_str = str(result)
        
        # Verificar respuesta con detección precisa
        found_0160, field_path, snippet = detect_0160_in_response(result_str)
        
        if found_0160:
            print("❌ FAIL: 0160 detectado")
            print(f"   Campo: {field_path}")
            print(f"   Snippet: {snippet[:200]}")
            
            # Buscar el dump más reciente generado por SIFENClient
            dump_pattern = "http_last_dump*.txt"
            dump_files = list(artifacts_dir.glob(dump_pattern))
            if dump_files:
                latest_dump = max(dump_files, key=os.path.getctime)
                # Mover/copiar al path especificado
                if latest_dump != dump_file:
                    import shutil
                    shutil.move(str(latest_dump), str(dump_file))
                print(f"📄 HTTP dump guardado en: {dump_file}")
            
            # Extraer y mostrar mensaje de error si está disponible
            codigo = extract_codigo_from_response(result_str)
            if codigo:
                print(f"📋 Código de respuesta: {codigo}")
            
            sys.exit(1)
        
        # Buscar códigos de éxito
        codigo = extract_codigo_from_response(result_str)
        
        if codigo == "0502" or "Estado Aceptado" in result_str or "ns1:codigoEstado>0502" in result_str:
            print("✅ OK: no 0160")
            if codigo:
                print(f"📋 Código de respuesta: {codigo}")
            print("✅ Respuesta contiene códigos de éxito (0502 o aceptado)")
        else:
            print("✅ OK: no 0160")
            if codigo:
                print(f"📋 Código de respuesta: {codigo}")
            print("⚠️  Respuesta sin error 0160 (verificar manualmente otros códigos)")
        
        # Mostrar resumen de la respuesta
        print("-" * 50)
        print("📄 Resumen de respuesta SIFEN:")
        
        # Extraer información relevante
        if codigo:
            print(f"   Código: {codigo}")
        
        # Buscar mensaje de respuesta
        msg_patterns = [
            r'<dMsgRes>([^<]+)</dMsgRes>',
            r'<ns1:dMsgRes>([^<]+)</ns1:dMsgRes>',
            r'"dMsgRes":\s*"([^"]+)"',
        ]
        
        for pattern in msg_patterns:
            match = re.search(pattern, result_str)
            if match:
                print(f"   Mensaje: {match.group(1)}")
                break
        
        # Mostrar primeros 500 chars del resultado para debug
        if len(result_str) > 500:
            print(f"\n📄 Respuesta completa (primeros 500 chars):")
            print(result_str[:500] + "...")
        else:
            print(f"\n📄 Respuesta completa:")
            print(result_str)
        
    except Exception as e:
        print(f"❌ ERROR durante el envío: {e}")
        import traceback
        print("\n📋 Traceback:")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
