#!/usr/bin/env python3
"""
Guardrails para validar que el XML no tenga problemas de firma SHA-1 o placeholder
"""
import sys
import re
from pathlib import Path
from typing import List, Tuple

def validate_signature_problems(xml_content: str) -> Tuple[bool, List[str]]:
    """
    Valida que el XML no tenga problemas de firma SHA-1 o placeholder
    
    Returns:
        (is_valid, list_of_issues)
    """
    issues = []
    
    # 1) Verificar RSA-SHA1
    if re.search(r'rsa-sha1', xml_content, re.IGNORECASE):
        issues.append("❌ RSA-SHA1 encontrado (debe ser RSA-SHA256)")
    
    # 2) Verificar Digest SHA-1
    if re.search(r'xmldsig#sha1', xml_content, re.IGNORECASE):
        issues.append("❌ Digest SHA-1 encontrado (debe ser SHA-256)")
    
    # 3) Verificar firma placeholder/dummy
    if 'dGhpcyBpcyBhIHRlc3Q' in xml_content:
        issues.append("❌ Firma placeholder/dummy encontrada (dGhpcyBpcyBhIHRlc3Q)")
    
    # 4) Verificar SignatureMethod específico
    if re.search(r'<SignatureMethod[^>]*Algorithm="[^"]*rsa-sha1[^"]*"', xml_content, re.IGNORECASE):
        issues.append("❌ SignatureMethod RSA-SHA1 encontrado")
    
    # 5) Verificar DigestMethod específico
    if re.search(r'<DigestMethod[^>]*Algorithm="[^"]*xmldsig#sha1[^"]*"', xml_content, re.IGNORECASE):
        issues.append("❌ DigestMethod SHA-1 encontrado")
    
    # 6) Verificaciones positivas
    has_rsa_sha256 = bool(re.search(r'rsa-sha256', xml_content, re.IGNORECASE))
    has_sha256_digest = bool(re.search(r'xmlenc#sha256', xml_content, re.IGNORECASE))
    
    if not has_rsa_sha256:
        issues.append("⚠️  No se encuentra RSA-SHA256")
    
    if not has_sha256_digest:
        issues.append("⚠️  No se encuentra Digest SHA-256")
    
    return len(issues) == 0, issues

def validate_ruc_format(xml_content: str) -> Tuple[bool, List[str]]:
    """
    Valida que dRucEm no tenga cero inicial
    """
    issues = []
    
    # Buscar dRucEm
    ruc_match = re.search(r'<dRucEm>([^<]+)</dRucEm>', xml_content)
    if ruc_match:
        ruc_value = ruc_match.group(1)
        if ruc_value.startswith('0') and len(ruc_value) > 1:
            issues.append(f"❌ dRucEm tiene cero inicial: {ruc_value}")
        else:
            print(f"✅ dRucEm sin cero inicial: {ruc_value}")
    else:
        issues.append("❌ No se encontró dRucEm")
    
    return len(issues) == 0, issues

def validate_xml_file(xml_path: str) -> bool:
    """
    Valida un archivo XML completo
    """
    path = Path(xml_path)
    if not path.exists():
        print(f"❌ Archivo no encontrado: {xml_path}")
        return False
    
    print(f"🔍 Validando archivo: {xml_path}")
    
    # Leer contenido
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"❌ Error leyendo archivo: {e}")
        return False
    
    # Validar firma
    sig_ok, sig_issues = validate_signature_problems(content)
    
    # Validar RUC
    ruc_ok, ruc_issues = validate_ruc_format(content)
    
    # Mostrar resultados
    all_issues = sig_issues + ruc_issues
    
    if all_issues:
        print("\n🚨 Problemas detectados:")
        for issue in all_issues:
            print(f"   {issue}")
        return False
    else:
        print("\n✅ Todas las validaciones pasaron")
        return True

def main():
    if len(sys.argv) != 2:
        print("Uso: python validate_signature_guardrails.py <archivo.xml>")
        return 1
    
    xml_file = sys.argv[1]
    is_valid = validate_xml_file(xml_file)
    
    return 0 if is_valid else 1

if __name__ == "__main__":
    sys.exit(main())
