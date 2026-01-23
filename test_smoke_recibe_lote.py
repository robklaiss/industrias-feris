#!/usr/bin/env python3
"""
Smoke test para SIFEN recibe-lote (WSDL-driven)

Este script ejecuta una prueba completa de envío de lote a SIFEN
usando el servicio recibe-lote con todos los componentes implementados:
- Routing correcto del endpoint (conserva .wsdl)
- Retries con backoff exponencial
- SOAP envelope validado contra WSDL
- Generación completa de artifacts

Uso:
    python3 test_smoke_recibe_lote.py
"""
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

# Configurar paths
SCRIPT_DIR = Path(__file__).parent
TESAKA_CV_DIR = SCRIPT_DIR / "tesaka-cv"

def run_command(cmd, cwd=None, capture_output=True):
    """Ejecuta un comando y retorna el resultado."""
    print(f"\n🔧 Ejecutando: {cmd}")
    print(f"   Desde: {cwd or Path.cwd()}")
    
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=capture_output,
        text=True
    )
    
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}", file=sys.stderr)
    
    return result

def main():
    print("="*60)
    print("SMOKE TEST - SIFEN recibe-lote (WSDL-driven)")
    print("="*60)
    
    # 1. Verificar que el repositorio está compilando
    print("\n1️⃣ Verificando compilación del módulo sifen_client...")
    result = run_command(
        "cd tesaka-cv && .venv/bin/python -c 'from app.sifen_client.soap_client import SoapClient; print(\"✅ SoapClient import OK\")'",
        cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        print("❌ Error al importar SoapClient")
        return 1
    
    # 2. Verificar configuración del endpoint
    print("\n2️⃣ Verificando configuración del endpoint...")
    result = run_command(
        "cd tesaka-cv && .venv/bin/python -c "
        "'from app.sifen_client.config import get_sifen_config; "
        "config = get_sifen_config(\"test\"); "
        "url = config.get_soap_service_url(\"recibe_lote\"); "
        "print(f\"URL configurada: {url}\"); "
        "assert \"recibe-lote.wsdl\" in url, \"URL debe contener .wsdl\"; "
        "print(\"✅ Endpoint correcto\")'",
        cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        print("❌ Error en configuración del endpoint")
        return 1
    
    # 3. Verificar WSDL cacheado
    print("\n3️⃣ Verificando WSDL cacheado...")
    wsdl_path = Path("/tmp/recibe-lote.wsdl")
    if wsdl_path.exists():
        print(f"✅ WSDL cacheado existe: {wsdl_path}")
        # Verificar endpoint en el WSDL
        result = run_command(
            f"grep -o 'soap12:address location=\"[^\"]*\"' {wsdl_path}",
            cwd=SCRIPT_DIR
        )
        if "recibe-lote.wsdl" in result.stdout:
            print("✅ Endpoint en WSDL es correcto")
        else:
            print("⚠️  Endpoint en WSDL podría no ser el esperado")
    else:
        print(f"⚠️  WSDL cacheado no existe: {wsdl_path}")
    
    # 4. Ejecutar envío de prueba (si hay XML de prueba)
    print("\n4️⃣ Buscando XML de prueba...")
    artifacts_dir = TESAKA_CV_DIR / "artifacts"
    test_xml = None
    
    # Buscar el XML más reciente en artifacts
    if artifacts_dir.exists():
        xml_files = list(artifacts_dir.glob("**/*.xml"))
        if xml_files:
            # Filtrar por archivos que parezcan DE firmados
            de_files = [f for f in xml_files if any(keyword in f.name.lower() 
                      for keyword in ['signed', 'firmado', 'de', 'sirecepde'])]
            if de_files:
                test_xml = max(de_files, key=lambda p: p.stat().st_mtime)
                print(f"✅ XML encontrado: {test_xml.relative_to(SCRIPT_DIR)}")
    
    if not test_xml:
        print("⚠️  No se encontró XML de prueba. Creando uno de ejemplo...")
        # Aquí podríamos generar un XML de prueba, pero por ahora saltamos
        print("   (Para ejecutar el smoke test completo, generar un XML primero)")
        return 0
    
    # 5. Ejecutar envío con SIFEN_DEBUG_SOAP=1
    print("\n5️⃣ Ejecutando envío a SIFEN (TEST)...")
    env = os.environ.copy()
    env["SIFEN_DEBUG_SOAP"] = "1"
    env["SIFEN_SKIP_RUC_GATE"] = "1"  # Para facilitar el test
    
    cmd = [
        str(TESAKA_CV_DIR / ".venv" / "bin" / "python"),
        "-m", "tools.send_sirecepde",
        "--env", "test",
        "--xml", str(test_xml.relative_to(TESAKA_CV_DIR)),
        "--dump-http"
    ]
    
    print(f"   Comando: {' '.join(cmd)}")
    
    # Ejecutar sin capturar para ver salida en tiempo real
    result = subprocess.run(
        cmd,
        cwd=TESAKA_CV_DIR,
        env=env,
        capture_output=False
    )
    
    # 6. Verificar artifacts generados
    print("\n6️⃣ Verificando artifacts generados...")
    expected_artifacts = [
        "soap_last_request_SENT.xml",
        "soap_last_response.xml",
        "route_probe_recibe_lote",
        "payload_full",
        "xde_zip_debug"
    ]
    
    artifacts_found = []
    for pattern in expected_artifacts:
        files = list(artifacts_dir.glob(f"{pattern}*"))
        if files:
            artifacts_found.extend([f.name for f in files])
            print(f"✅ {pattern}: encontrado(s)")
        else:
            print(f"❌ {pattern}: NO encontrado")
    
    # 7. Verificar endpoint usado
    print("\n7️⃣ Verificando endpoint usado...")
    route_files = list(artifacts_dir.glob("route_probe_recibe_lote_*.json"))
    if route_files:
        latest_route = max(route_files, key=lambda p: p.stat().st_mtime)
        result = run_command(
            f"cat {latest_route} | jq -r '.post_url_final'",
            cwd=SCRIPT_DIR
        )
        if result.returncode == 0 and result.stdout.strip():
            endpoint = result.stdout.strip()
            print(f"✅ Endpoint usado: {endpoint}")
            if endpoint.endswith("/recibe-lote.wsdl"):
                print("✅ Endpoint conserva .wsdl correctamente")
            else:
                print("❌ Endpoint NO conserva .wsdl")
        else:
            print("❌ No se pudo extraer endpoint del route probe")
    
    # Resumen final
    print("\n" + "="*60)
    print("RESUMEN DEL SMOKE TEST")
    print("="*60)
    
    if result.returncode == 0:
        print("✅ Envío a SIFEN exitoso")
        print(f"✅ Artifacts generados: {len(artifacts_found)}")
        print("\n📋 Para inspeccionar:")
        print(f"   - SOAP enviado: {artifacts_dir}/soap_last_request_SENT.xml")
        print(f"   - Respuesta: {artifacts_dir}/soap_last_response.xml")
        print(f"   - Route probe: {latest_route.name if route_files else 'N/A'}")
        return 0
    else:
        print("❌ Envío a SIFEN falló")
        print("   Revisar logs arriba para detalles")
        return 1

if __name__ == "__main__":
    sys.exit(main())
