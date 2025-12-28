#!/usr/bin/env python3
"""
Script para crear archivo .env con configuración SIFEN
Uso: python scripts/create_env.py
"""
import os
from pathlib import Path

# Obtener directorio del proyecto (raíz del repositorio)
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
ENV_FILE = PROJECT_ROOT / ".env"

ENV_CONTENT = """# ============================================
# CONFIGURACIÓN SIFEN - Ambiente de Pruebas
# ============================================
#
# IMPORTANTE: Estos son valores de EJEMPLO para desarrollo básico.
# Para usar el ambiente de pruebas real, debes obtener valores oficiales de la SET.
#
# Ver: tesaka-cv/docs/DATOS_PRUEBA_SIFEN.md para más información
# Portal: https://ekuatia.set.gov.py

# ============================================
# AMBIENTE SIFEN
# ============================================
SIFEN_ENV=test

# ============================================
# DATOS DE PRUEBA (Ambiente Test)
# ============================================
# ⚠️ NOTA: Estos son valores de EJEMPLO para desarrollo básico.
# Para ambiente de pruebas real, contactar a la SET: consultas@set.gov.py
#
# RUC de prueba (formato: 7-9 dígitos)
SIFEN_TEST_RUC=80012345

# Número de timbrado de prueba (8 dígitos)
SIFEN_TEST_TIMBRADO=12345678

# CSC (Código de Seguridad del Contribuyente) de prueba
# Dejar vacío si no se tiene - el sistema usará valores por defecto
SIFEN_TEST_CSC=

# Razón social de prueba (opcional)
SIFEN_TEST_RAZON_SOCIAL=Contribuyente de Prueba S.A.

# ============================================
# CONFIGURACIÓN DE SERVICIOS
# ============================================
# Timeout para requests HTTP/SOAP (segundos)
SIFEN_REQUEST_TIMEOUT=30

# ============================================
# AUTENTICACIÓN (Opcional - para envío real)
# ============================================
# Solo necesario si se va a enviar documentos reales al ambiente de pruebas
SIFEN_USE_MTLS=false

# Certificado digital (.p12 o .pfx) - Solo si SIFEN_USE_MTLS=true
# SIFEN_CERT_PATH=/ruta/al/certificado.p12
# SIFEN_CERT_PASSWORD=password_del_certificado
# SIFEN_CA_BUNDLE_PATH=/ruta/al/ca-bundle.pem
"""

def main():
    print("============================================")
    print("Crear archivo .env para configuración SIFEN")
    print("============================================")
    print()
    
    # Verificar si .env ya existe
    if ENV_FILE.exists():
        print("⚠️  El archivo .env ya existe.")
        respuesta = input("¿Deseas sobrescribirlo? (s/N): ").strip().lower()
        if respuesta != 's':
            print("❌ Operación cancelada.")
            return
    
    # Crear .env
    try:
        ENV_FILE.write_text(ENV_CONTENT, encoding='utf-8')
        print(f"✅ Archivo .env creado en: {ENV_FILE}")
        print()
        print("📝 Próximos pasos:")
        print(f"   1. Revisar el archivo: {ENV_FILE}")
        print("   2. Si tienes valores oficiales de la SET, editar y reemplazar los valores de ejemplo")
        print("   3. Ver documentación: tesaka-cv/docs/DATOS_PRUEBA_SIFEN.md")
        print()
        print("📋 Valores configurados (de ejemplo):")
        print("   - SIFEN_TEST_RUC=80012345")
        print("   - SIFEN_TEST_TIMBRADO=12345678")
        print("   - SIFEN_TEST_CSC=(vacío - usar valores por defecto)")
        print()
        print("💡 Para obtener valores oficiales:")
        print("   - Contactar a la SET: consultas@set.gov.py")
        print("   - Portal: https://ekuatia.set.gov.py")
        print("   - Ver: tesaka-cv/docs/DATOS_PRUEBA_SIFEN.md")
    except Exception as e:
        print(f"❌ Error al crear archivo .env: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())

