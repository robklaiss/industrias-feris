#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Wrapper seguro para tools.send_sirecepde que:
- Solicita contraseña P12 de forma segura (sin echo)
- Verifica la contraseña contra el certificado antes de ejecutar
- Configura variables de entorno necesarias
"""

import argparse
import os
import subprocess
import sys
from getpass import getpass
from pathlib import Path


def verify_p12_password(cert_path: str, password: str) -> bool:
    """
    Verifica que la contraseña sea correcta para el certificado P12.
    Usa openssl sin exponer la contraseña en la línea de comandos.
    
    Returns:
        True si la contraseña es válida, False en caso contrario.
    """
    if not os.path.exists(cert_path):
        print(f"❌ Certificado no encontrado: {cert_path}")
        return False
    
    # openssl pkcs12 -in CERT -info -noout -passin stdin
    cmd = [
        "openssl",
        "pkcs12",
        "-in", cert_path,
        "-info",
        "-noout",
        "-passin", "stdin"
    ]
    
    # Preparar input: password + newline
    password_input = (password + "\n").encode("utf-8")
    
    try:
        result = subprocess.run(
            cmd,
            input=password_input,
            capture_output=True,
            timeout=10
        )
        
        # Verificar que el comando exitó con éxito
        if result.returncode != 0:
            return False
        
        # Verificar que la salida contiene "MAC verified OK"
        output = result.stdout.decode("utf-8", errors="ignore")
        error_output = result.stderr.decode("utf-8", errors="ignore")
        combined = output + error_output
        
        if "MAC verified OK" in combined:
            return True
        
        return False
    
    except subprocess.TimeoutExpired:
        print("❌ Timeout al verificar certificado")
        return False
    except Exception as e:
        print(f"❌ Error al verificar certificado: {e}")
        return False


def prompt_password(cert_path: str, max_tries: int = 3) -> str:
    """
    Solicita la contraseña del certificado de forma segura.
    
    Returns:
        Contraseña ingresada por el usuario o desde variables de entorno.
        
    Raises:
        SystemExit si se agotan los intentos o no se encuentra password en env.
    """
    # 1) Primero: permitir modo no-interactivo
    env_pw = os.environ.get("SIFEN_P12_PASSWORD")
    if env_pw:
        return env_pw
    
    # 2) Si no hay TTY, no podemos usar getpass
    if not sys.stdin.isatty():
        raise SystemExit(
            "❌ No hay TTY para pedir la contraseña. "
            "Seteá SIFEN_P12_PASSWORD y reintentá."
        )
    
    # 3) Caso normal: getpass con reintentos
    for attempt in range(1, max_tries + 1):
        if attempt > 1:
            print(f"\n⚠️  Intento {attempt}/{max_tries}")
        
        password = getpass(f"🔐 Contraseña para {Path(cert_path).name}: ")
        
        if not password:
            print("❌ Contraseña vacía. Intenta de nuevo.")
            continue
        
        if verify_p12_password(cert_path, password):
            print("✅ Contraseña verificada correctamente")
            return password
        
        print("❌ Contraseña incorrecta")
    
    raise SystemExit(f"❌ No se pudo verificar la contraseña del P12 después de {max_tries} intentos.")


def main():
    ap = argparse.ArgumentParser(
        description="Wrapper seguro para tools.send_sirecepde con verificación de contraseña P12."
    )
    ap.add_argument("--env", required=True, choices=["test", "prod"], help="Ambiente SIFEN (test/prod)")
    ap.add_argument("--xml", required=True, help="Path al archivo XML (rDE o siRecepDE)")
    ap.add_argument("--cert", required=True, help="Path al certificado P12 (para firma y mTLS)")
    ap.add_argument("--artifacts-dir", default="artifacts", help="Directorio para artifacts (default: artifacts)")
    ap.add_argument("--debug-soap", action="store_true", help="Activar debug SOAP (SIFEN_DEBUG_SOAP=1)")
    ap.add_argument("--validate-xsd", action="store_true", help="Activar validación XSD (SIFEN_VALIDATE_XSD=1)")
    ap.add_argument("--tries", type=int, default=3, help="Número de intentos para la contraseña (default: 3)")
    
    args = ap.parse_args()
    
    # Validar que el certificado existe
    if not os.path.exists(args.cert):
        print(f"❌ Certificado no encontrado: {args.cert}")
        sys.exit(1)
    
    # Validar que el XML existe
    if not os.path.exists(args.xml):
        print(f"❌ Archivo XML no encontrado: {args.xml}")
        sys.exit(1)
    
    # Solicitar y verificar contraseña
    password = prompt_password(args.cert, max_tries=args.tries)
    
    # Preparar variables de entorno (copiar el entorno actual)
    env = os.environ.copy()
    
    # Configurar todas las variables de entorno necesarias con el password
    # Usar ruta absoluta del certificado
    cert_path_abs = os.path.abspath(args.cert)
    
    # Certificado genérico (SIFEN_CERT_*)
    env["SIFEN_CERT_PATH"] = cert_path_abs
    env["SIFEN_CERT_PASSWORD"] = password
    
    # Certificado de firma (SIFEN_SIGN_P12_*)
    env["SIFEN_SIGN_P12_PATH"] = cert_path_abs
    env["SIFEN_SIGN_P12_PASSWORD"] = password
    
    # Certificado mTLS (SIFEN_MTLS_P12_*)
    env["SIFEN_MTLS_P12_PATH"] = cert_path_abs
    env["SIFEN_MTLS_P12_PASSWORD"] = password
    
    # NOTA: El password NO se imprime, NO se agrega a la línea de comando,
    # y NO se guarda en archivos. Solo se pasa por env al child process.
    
    # Flags opcionales
    if args.debug_soap:
        env["SIFEN_DEBUG_SOAP"] = "1"
    
    if args.validate_xsd:
        env["SIFEN_VALIDATE_XSD"] = "1"
    
    # Ejecutar tools.send_sirecepde
    cmd = [
        sys.executable,
        "-m",
        "tools.send_sirecepde",
        "--env", args.env,
        "--xml", args.xml,
        "--artifacts-dir", args.artifacts_dir
    ]
    
    print(f"\n🚀 Ejecutando: {' '.join(cmd)}")
    print(f"📁 Certificado: {args.cert}")
    print(f"📄 XML: {args.xml}")
    print(f"🌍 Ambiente: {args.env}")
    print()
    
    # Ejecutar y pasar el código de salida
    result = subprocess.run(cmd, env=env)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()

