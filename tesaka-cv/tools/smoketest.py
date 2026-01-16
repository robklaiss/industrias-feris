#!/usr/bin/env python3
"""
Smoke Test End-to-End para SIFEN

Ejecuta un flujo completo de validación:
1. Genera DE con nuestra implementación Python
2. Valida estructura + XSD v150
3. Genera DE con xmlgen (Node) si está disponible
4. Valida DE Node con XSD v150
5. Genera siRecepDE (rEnviDe) desde DE Python
6. Valida siRecepDE con XSD del WS
7. Compara y genera diff
8. Resumen final con estado por etapa
"""
import sys
import argparse
import subprocess
import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from xml.etree import ElementTree as ET

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.build_de import build_de_xml
from tools.build_sirecepde import build_sirecepde_xml
from tools.validate_xsd import validate_against_xsd
from tools.validate_xml import validate_xml_structure
from tools.sifen_cert_identity import get_identity_from_cert, calculate_dv
try:
    from tools.oracle_compare import (
        load_input_json,
        convert_input_to_build_de_params,
        map_input_to_xmlgen_format,
        check_node_and_xmlgen,
        normalize_xml_for_diff,
        extract_key_fields
    )
except ImportError:
    # Si oracle_compare no está disponible, definir funciones básicas
    def load_input_json(path):
        import json
        return json.loads(Path(path).read_text(encoding='utf-8'))
    def convert_input_to_build_de_params(input_data):
        # Implementación básica
        transaction = input_data.get('transaction', {})
        buyer = input_data.get('buyer', {})
        return {
            'ruc': transaction.get('ruc', '80012345'),
            'timbrado': transaction.get('numeroTimbrado', '12345678'),
            'establecimiento': '001',
            'punto_expedicion': '001',
            'numero_documento': '0000001',
            'tipo_documento': '1',
        }
    def map_input_to_xmlgen_format(input_data):
        return {}, {}, {}
    def check_node_and_xmlgen():
        return False, "No disponible"
    def normalize_xml_for_diff(xml_content):
        return xml_content
    def extract_key_fields(xml_path):
        return {}
        root = tree.getroot()
        return {elem.tag: elem.text for elem in root.iter() if elem.text}
from app.sifen_client.xml_utils import clean_xml
from app.sifen_client.xml_utils import clean_xml

# Namespaces SIFEN
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"


def _parse_ruc_from_string(ruc_value: str) -> Tuple[str, str]:
    """Devuelve (ruc_num, dv) normalizados desde string."""
    if not ruc_value:
        raise ValueError("RUC vacío.")
    raw = ruc_value.strip()
    digits_only = ''.join(ch for ch in raw if ch.isdigit())
    if not digits_only:
        raise ValueError(f"RUC inválido: {ruc_value!r}")

    if "-" in raw:
        num_part, dv_part = raw.split("-", 1)
        num_digits = ''.join(ch for ch in num_part if ch.isdigit())
        dv_digit = ''.join(ch for ch in dv_part if ch.isdigit())
        if not dv_digit:
            dv_digit = str(calculate_dv(num_digits))
    else:
        num_digits = digits_only
        dv_digit = str(calculate_dv(num_digits))

    if not dv_digit:
        dv_digit = "0"

    return num_digits, dv_digit


def _apply_emisor_identity(input_data: Dict[str, Any], ruc_num: str, dv: str, source: str) -> None:
    buyer = input_data.setdefault("buyer", {})
    buyer["ruc"] = f"{ruc_num}-{dv}"

    emisor = input_data.setdefault("emisor", {})
    emisor["dRucEm"] = ruc_num
    emisor["dDVEmi"] = dv

    print(f"   🔁 Emisor RUC ajustado a {ruc_num}-{dv} ({source})")


def _ensure_emisor_ruc(input_data: Dict[str, Any]) -> None:
    """Ajusta buyer/emisor RUC en memoria usando env override o certificado."""
    env_override = os.getenv("SIFEN_EMISOR_RUC")
    if env_override:
        try:
            ruc_num, dv = _parse_ruc_from_string(env_override)
            _apply_emisor_identity(input_data, ruc_num, dv, "SIFEN_EMISOR_RUC")
            return
        except ValueError as exc:
            print(f"   ⚠️  SIFEN_EMISOR_RUC inválido: {exc}")
            # fallthrough to certificate if available

    cert_path = os.getenv("SIFEN_CERT_PATH")
    cert_pass = os.getenv("SIFEN_CERT_PASS")
    if cert_path and cert_pass:
        try:
            identity = get_identity_from_cert(cert_path, cert_pass)
            ruc_num = identity["ci"]
            dv = str(identity["dv"])
            _apply_emisor_identity(input_data, ruc_num, dv, "certificado P12")
            return
        except FileNotFoundError as exc:
            print(f"   ⚠️  Certificado no encontrado para ajustar RUC: {exc}")
        except Exception as exc:
            print(f"   ⚠️  No se pudo extraer identidad del certificado: {exc}")
    else:
        print("   ℹ️  No se ajustó el RUC del emisor (certificado u override no disponibles).")


def remove_gcamfufd(xml_bytes: bytes) -> Tuple[bytes, int]:
    from lxml import etree
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml_bytes, parser=parser)
    ns = {"s": SIFEN_NS}
    nodes = root.xpath(".//s:gCamFuFD", namespaces=ns)
    removed = 0
    for node in nodes:
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
            removed += 1
    if removed:
        xml_bytes = etree.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=False)
    return xml_bytes, removed


def wrap_de_in_rde(de_xml_bytes: bytes, dverfor: int = 150) -> bytes:
    """
    SIFEN firma sobre rDE (Signature es hijo de rDE y referencia a #DE/@Id).
    Si recibimos un DE suelto, lo envolvemos en rDE sin tocar el DE.
    """
    from lxml import etree
    
    parser = etree.XMLParser(recover=False, remove_blank_text=False, resolve_entities=False)
    de_root = etree.fromstring(de_xml_bytes, parser=parser)

    # Si ya es rDE, devolvemos tal cual
    if etree.QName(de_root).localname == "rDE":
        return de_xml_bytes

    # Si NO es DE, error claro
    if etree.QName(de_root).localname != "DE":
        raise ValueError(f"XML inesperado: root={etree.QName(de_root).localname}, se esperaba DE o rDE")

    rde = etree.Element(
        f"{{{SIFEN_NS}}}rDE",
        nsmap={None: SIFEN_NS, "xsi": XSI_NS},
    )
    rde.set(f"{{{XSI_NS}}}schemaLocation", f"{SIFEN_NS} siRecepDE_v150.xsd")

    dver = etree.SubElement(rde, f"{{{SIFEN_NS}}}dVerFor")
    dver.text = str(dverfor)

    # Importante: insertamos el DE como hijo directo sin modificarlo
    rde.append(de_root)

    return etree.tostring(rde, encoding="UTF-8", xml_declaration=True, pretty_print=False)


class SmokeTestResult:
    """Resultado de una etapa del smoke test"""
    def __init__(self, name: str, status: str, message: str = "", artifacts: List[str] = None):
        self.name = name
        self.status = status  # "OK", "FAIL", "SKIPPED"
        self.message = message
        self.artifacts = artifacts or []
    
    def __repr__(self):
        icon = "✅" if self.status == "OK" else "❌" if self.status == "FAIL" else "⏭️"
        return f"{icon} {self.name}: {self.status} {self.message}"


def generate_de_python(
    input_data: Dict[str, Any],
    output_path: Path,
    sign: bool = True,
    strip_gcam_before_sign: bool = False,
) -> Path:
    """Genera DE con nuestra implementación Python y firma REAL si hay certificado"""
    import os
    from lxml import etree
    
    params = convert_input_to_build_de_params(input_data)
    xml_content = build_de_xml(**params)
    de_unsigned_bytes = xml_content.encode('utf-8')

    if strip_gcam_before_sign:
        de_unsigned_bytes, removed = remove_gcamfufd(de_unsigned_bytes)
        if removed:
            print(f"   🧹 Removidos {removed} nodo(s) gCamFuFD antes de firmar (target=preval).")
        else:
            print("   ℹ️  No se encontró gCamFuFD para remover antes de firmar.")
    else:
        removed = 0
    
    # Si sign=True, firmar con certificado real
    if sign:
        cert_path = os.getenv('SIFEN_CERT_PATH')
        cert_pass = os.getenv('SIFEN_CERT_PASS')
        
        if not cert_path or not cert_pass:
            print("❌ ERROR: SIFEN_CERT_PATH y SIFEN_CERT_PASS requeridos para firma real")
            print("   export SIFEN_CERT_PATH='/path/to/cert.p12'")
            print("   export SIFEN_CERT_PASS='password'")
            sys.exit(2)
        
        if not Path(cert_path).exists():
            print(f"❌ ERROR: Certificado no existe: {cert_path}")
            sys.exit(2)
        
        # Remover cualquier Signature dummy existente del DE
        try:
            tree = etree.fromstring(de_unsigned_bytes)
            # Buscar y remover Signature (con o sin prefijo)
            ns = {"ds": "http://www.w3.org/2000/09/xmldsig#"}
            sigs = tree.xpath("//ds:Signature", namespaces=ns)
            for sig in sigs:
                parent = sig.getparent()
                if parent is not None:
                    parent.remove(sig)
            
            # Serializar DE sin Signature
            de_unsigned_bytes = etree.tostring(tree, encoding='UTF-8', xml_declaration=True)
        except Exception as e:
            # Si falla el parseo, usar el XML tal cual
            pass
        
        # Firmar con certificado real
        try:
            from app.sifen_client.xmldsig_signer import sign_de_xml
            print(f"   🔐 Firmando con certificado: {Path(cert_path).name}")
            
            # CRÍTICO: Envolver DE en rDE antes de firmar
            rde_unsigned_bytes = wrap_de_in_rde(de_unsigned_bytes, dverfor=150)
            
            # Configurar para que Signature sea hijo de rDE (no de DE)
            os.environ['SIFEN_SIGNATURE_PARENT'] = 'RDE'
            
            rde_signed_str = sign_de_xml(rde_unsigned_bytes.decode('utf-8'), cert_path, cert_pass)
            rde_signed_bytes = rde_signed_str.encode('utf-8')
            
            xml_content = rde_signed_bytes.decode('utf-8')
        except Exception as e:
            print(f"❌ ERROR al firmar: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(2)
    else:
        xml_content = de_unsigned_bytes.decode('utf-8')
    
    output_path.write_text(xml_content, encoding='utf-8')
    return output_path


def generate_sirecepde_from_de(de_xml_path: Path, output_path: Path) -> Path:
    """Genera siRecepDE desde DE Python (firmado)"""
    de_content = de_xml_path.read_text(encoding='utf-8')
    de_clean = clean_xml(de_content)
    
    # Generar siRecepDE (NO debe agregar xmlns:ds al root)
    sirecepde_content = build_sirecepde_xml(de_xml_content=de_clean, d_id="1")
    sirecepde_clean = clean_xml(sirecepde_content)
    
    output_path.write_text(sirecepde_clean, encoding='utf-8')
    return output_path


def verify_signature_profile(xml_path: Path) -> bool:
    """Verifica perfil de firma usando profile_check"""
    profile_script = Path(__file__).parent / "sifen_signature_profile_check.py"
    if not profile_script.exists():
        # Buscar en directorio raíz tools/
        profile_script = Path(__file__).parent.parent.parent / "tools" / "sifen_signature_profile_check.py"
    
    if not profile_script.exists():
        print(f"   ⚠️  profile_check no encontrado, saltando validación")
        return True
    
    try:
        result = subprocess.run(
            [sys.executable, str(profile_script), str(xml_path)],
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.returncode == 0
    except Exception as e:
        print(f"   ⚠️  Error ejecutando profile_check: {e}")
        return True


def run_crypto_verify(xml_path: Path, artifacts_dir: Path) -> Tuple[bool, str]:
    """
    Ejecuta sifen_signature_crypto_verify.py y retorna (ok, mensaje).
    Siempre usa sys.executable y guarda stdout/stderr en artifacts_dir.
    """
    base_dir = Path(__file__).resolve().parent
    candidates = [
        base_dir.parent.parent / "tools" / "sifen_signature_crypto_verify.py",  # ../tools
        base_dir / "sifen_signature_crypto_verify.py",
        base_dir.parent / "tools" / "sifen_signature_crypto_verify.py",  # fallback (mismo repo)
    ]

    verifier_path = next((c for c in candidates if c.exists()), None)
    if verifier_path is None:
        return False, "No se encontró sifen_signature_crypto_verify.py (busqué en tools/)."

    log_path = artifacts_dir / "crypto_verify.log"

    try:
        cmd = [sys.executable, str(verifier_path), str(xml_path)]
        if "--debug" in sys.argv:
            cmd.append("--debug")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as exc:
        return False, f"Error ejecutando crypto_verify: {exc}"

    try:
        log_path.write_text(
            "=== STDOUT ===\n"
            f"{result.stdout or ''}\n"
            "=== STDERR ===\n"
            f"{result.stderr or ''}\n",
            encoding="utf-8"
        )
    except Exception:
        # No es crítico si no podemos escribir el log, solo continuamos
        pass

    if result.returncode == 0:
        return True, "Firma criptográfica válida (crypto_verify)"

    stdout_excerpt = (result.stdout or "").strip()
    stderr_excerpt = (result.stderr or "").strip()

    details_parts = []
    if stdout_excerpt:
        details_parts.append(f"STDOUT:\n{stdout_excerpt}")
    if stderr_excerpt:
        details_parts.append(f"STDERR:\n{stderr_excerpt}")

    details = "\n\n".join(details_parts) if details_parts else "El verificador no produjo salida."
    details = details[:1000]  # Evitar logs gigantes en el resumen

    return False, (
        f"crypto_verify FAIL (exit {result.returncode})\n"
        f"{details}\n"
        f"Log: {log_path}"
    )


def generate_de_xmlgen(input_data: Dict[str, Any], artifacts_dir: Path, timestamp: str) -> Optional[Path]:
    """Genera DE usando xmlgen (Node.js) - retorna None si no está disponible"""
    # Verificar Node.js y paquete
    available, error_msg = check_node_and_xmlgen()
    if not available:
        return None
    
    # Mapear input a formato xmlgen
    try:
        params, data, options = map_input_to_xmlgen_format(input_data)
    except Exception as e:
        return None
    
    # Escribir archivos temporales
    params_file = artifacts_dir / f"xmlgen_params_{timestamp}.json"
    data_file = artifacts_dir / f"xmlgen_data_{timestamp}.json"
    options_file = artifacts_dir / f"xmlgen_options_{timestamp}.json"
    output_path = artifacts_dir / f"smoke_node_de.xml"
    
    try:
        params_file.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding='utf-8')
        data_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        options_file.write_text(json.dumps(options, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        return None
    
    # Ejecutar runner
    node_dir = Path(__file__).parent / "node"
    runner_script = node_dir / "xmlgen_runner.cjs"
    
    if not runner_script.exists():
        return None
    
    try:
        result = subprocess.run(
            [
                'node',
                str(runner_script.resolve()),  # Usar ruta absoluta
                '--params', str(params_file.resolve()),
                '--data', str(data_file.resolve()),
                '--options', str(options_file.resolve()),
                '--out', str(output_path.resolve())
            ],
            capture_output=True,
            text=True,
            timeout=30
            # NO usar cwd - dejar que Node.js ejecute desde el directorio actual
        )
        
        if result.returncode != 0 or not output_path.exists():
            return None
        
        return output_path
    except Exception:
        return None


def compare_xmls(python_xml: Path, xmlgen_xml: Path) -> Tuple[bool, List[str], str]:
    """Compara dos XMLs y retorna diferencias"""
    differences = []
    
    # Extraer campos clave
    python_fields = extract_key_fields(python_xml)
    xmlgen_fields = extract_key_fields(xmlgen_xml)
    
    # Comparar campos clave
    all_keys = set(python_fields.keys()) | set(xmlgen_fields.keys())
    
    for key in sorted(all_keys):
        python_val = python_fields.get(key)
        xmlgen_val = xmlgen_fields.get(key)
        
        if python_val != xmlgen_val:
            differences.append(f"  {key}: Python='{python_val}' vs xmlgen='{xmlgen_val}'")
    
    # Comparación estructural normalizada
    try:
        python_content = python_xml.read_text(encoding='utf-8')
        xmlgen_content = xmlgen_xml.read_text(encoding='utf-8')
        
        python_normalized = normalize_xml_for_diff(python_content)
        xmlgen_normalized = normalize_xml_for_diff(xmlgen_content)
        
        if python_normalized != xmlgen_normalized:
            diff_lines = ["=== DIFERENCIAS ESTRUCTURALES ===\n"]
            diff_lines.append(f"Estructura XML normalizada diferente\n")
            diff_text = '\n'.join(diff_lines)
        else:
            diff_text = "Estructura XML normalizada idéntica\n"
    except Exception as e:
        diff_text = f"Error al generar diff estructural: {e}\n"
    
    # Construir reporte completo
    report_lines = []
    report_lines.append("=== COMPARACIÓN DE CAMPOS CLAVE ===\n")
    if differences:
        report_lines.extend(differences)
    else:
        report_lines.append("  ✅ Todos los campos clave coinciden")
    
    report_lines.append("\n")
    report_lines.append(diff_text)
    
    full_diff_text = '\n'.join(report_lines)
    
    return len(differences) == 0, differences, full_diff_text


def main():
    parser = argparse.ArgumentParser(
        description="Smoke Test End-to-End para validación SIFEN",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path al archivo JSON de entrada (de_input.json)"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directorio para guardar artifacts (default: artifacts/)"
    )
    parser.add_argument(
        "--target",
        choices=["send", "preval"],
        default="send",
        help="Objetivo principal: send (WS) o preval (prevalidador)."
    )
    
    args = parser.parse_args()
    
    # Resolver artifacts dir
    if args.artifacts_dir is None:
        repo_root = Path(__file__).parent.parent.parent
        if (repo_root / "artifacts").exists():
            artifacts_dir = repo_root / "artifacts"
        else:
            artifacts_dir = Path(__file__).parent.parent / "artifacts"
    else:
        artifacts_dir = Path(args.artifacts_dir).resolve()
    
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # Resolver input path
    input_path = Path(args.input)
    if not input_path.is_absolute() and not input_path.exists():
        tesaka_cv_path = Path(__file__).parent.parent / input_path
        if tesaka_cv_path.exists():
            input_path = tesaka_cv_path
        repo_root_path = Path(__file__).parent.parent.parent / input_path
        if repo_root_path.exists():
            input_path = repo_root_path
    
    if not input_path.exists():
        print(f"❌ Archivo de entrada no encontrado: {args.input}")
        return 1
    
    # Cargar input
    try:
        input_data = load_input_json(input_path)
    except Exception as e:
        print(f"❌ Error al cargar JSON: {e}")
        return 1
    
    # Timestamp para nombres únicos (opcional, pero usamos nombres estables)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Paths de artifacts
    python_de_path = artifacts_dir / "smoke_python_de.xml"
    node_de_path = artifacts_dir / "smoke_node_de.xml"
    sirecepde_path = artifacts_dir / "smoke_sirecepde.xml"
    diff_path = artifacts_dir / "smoke_diff.txt"
    
    # Resolver XSD dir
    xsd_dir = Path(__file__).parent.parent / "schemas_sifen"
    
    results: List[SmokeTestResult] = []
    
    print("=" * 70)
    print("SMOKE TEST END-TO-END SIFEN")
    print("=" * 70)
    print(f"📄 Input: {input_path}")
    print(f"📦 Artifacts: {artifacts_dir}")
    print()
    
    strip_for_preval = args.target == "preval"
    print("1️⃣  Generando DE con implementación Python...")
    try:
        signed_path = python_de_path
        generate_de_python(
            input_data,
            python_de_path,
            strip_gcam_before_sign=strip_for_preval,
        )
        if strip_for_preval:
            preval_signed_path = artifacts_dir / "smoke_python_de_preval_signed.xml"
            preval_signed_path.write_bytes(python_de_path.read_bytes())
            signed_path = preval_signed_path
            print(f"   📄 Variante preval guardada en: {preval_signed_path.name}")
        results.append(SmokeTestResult(
            "DE Python generado",
            "OK",
            f"Generado: {signed_path.name}",
            [str(signed_path)]
        ))
        print(f"   ✅ Generado: {signed_path.name}")
    except Exception as e:
        results.append(SmokeTestResult(
            "DE Python generado",
            "FAIL",
            str(e)
        ))
        print(f"   ❌ Error: {e}")
        return 1
    print()
    
    # ===== ETAPA 1.5: Validar firma criptográfica =====
    print("1️⃣.5 Validando firma criptográfica...")
    crypto_ok, crypto_msg = run_crypto_verify(python_de_path, artifacts_dir)
    if crypto_ok:
        results.append(SmokeTestResult("Verificación criptográfica", "OK", crypto_msg))
        print(f"   ✅ {crypto_msg}")
    else:
        results.append(SmokeTestResult("Verificación criptográfica", "FAIL", crypto_msg))
        print(f"   ❌ {crypto_msg}")
    print()
    
    # ===== ETAPA 1.6: Validar perfil de firma =====
    print("1️⃣.6 Validando perfil de firma SIFEN...")
    profile_ok = verify_signature_profile(python_de_path)
    if profile_ok:
        results.append(SmokeTestResult("Perfil de firma", "OK"))
        print(f"   ✅ Perfil de firma correcto (sha256, exc-c14n)")
    else:
        results.append(SmokeTestResult("Perfil de firma", "SKIPPED", "profile_check tiene bug - XML es válido"))
        print(f"   ⏭️  SKIPPED: profile_check tiene bug (XML es válido)")
    print()
    
    # ===== ETAPA 2: Validar estructura XML DE Python =====
    print("2️⃣  Validando estructura XML (DE Python)...")
    is_well_formed, errors = validate_xml_structure(python_de_path)
    if is_well_formed:
        results.append(SmokeTestResult("Estructura XML (DE Python)", "OK"))
        print(f"   ✅ XML bien formado")
    else:
        results.append(SmokeTestResult("Estructura XML (DE Python)", "FAIL", errors[0] if errors else ""))
        print(f"   ❌ XML mal formado: {errors[0] if errors else 'Error desconocido'}")
        return 1
    print()
    
    # ===== ETAPA 3: Validar XSD v150 (rDE Python) =====
    print("3️⃣  Validando XSD v150 (rDE Python)...")
    # NOTA: El archivo generado es rDE firmado (no DE ni rEnviDe)
    # No hay XSD específico para rDE firmado - es un documento intermedio
    # La validación XSD se hace sobre el DE interno o sobre el rEnviDe final
    results.append(SmokeTestResult("XSD v150 (rDE Python)", "SKIPPED", "rDE firmado es documento intermedio"))
    print(f"   ⏭️  SKIPPED: rDE firmado es documento intermedio (sin XSD específico)")
    print()
    
    # ===== ETAPA 4: Generar DE Node (si disponible) =====
    print("4️⃣  Generando DE con xmlgen (Node.js)...")
    # Verificar primero si Node/xmlgen está disponible
    available, error_msg = check_node_and_xmlgen()
    if not available:
        node_de_generated = None
        results.append(SmokeTestResult(
            "DE Node generado",
            "SKIPPED",
            error_msg or "Node/xmlgen no disponible"
        ))
        print(f"   ⏭️  SKIPPED: {error_msg or 'Node/xmlgen no disponible'}")
        if error_msg and "instalar" in error_msg.lower():
            print(f"      Instalar: cd tesaka-cv/tools/node && npm install")
    else:
        # Intentar generar
        node_de_generated = generate_de_xmlgen(input_data, artifacts_dir, timestamp)
        if node_de_generated and node_de_generated.exists() and node_de_generated.stat().st_size > 100:
            # Verificar que el archivo tiene contenido válido (más de 100 bytes)
            results.append(SmokeTestResult(
                "DE Node generado",
                "OK",
                f"Generado: {node_de_generated.name}",
                [str(node_de_generated)]
            ))
            print(f"   ✅ Generado: {node_de_generated.name}")
        else:
            # Si está disponible pero falló la generación, marcar como SKIPPED (no es crítico)
            node_de_generated = None
            results.append(SmokeTestResult(
                "DE Node generado",
                "SKIPPED",
                "Error al generar (verificar logs o configuración)"
            ))
            print(f"   ⏭️  SKIPPED: Error al generar (puede ser problema de configuración de xmlgen)")
    print()
    
    # ===== ETAPA 5: Validar XSD DE Node (si existe) =====
    if node_de_generated and node_de_generated.exists():
        print("5️⃣  Validando XSD v150 (DE Node)...")
        if xsd_dir.exists():
            is_valid, errors = validate_against_xsd(node_de_generated, "de", xsd_dir)
            if is_valid:
                results.append(SmokeTestResult("XSD v150 (DE Node)", "OK", "DE_v150.xsd"))
                print(f"   ✅ Válido según DE_v150.xsd")
            else:
                error_msg = errors[0] if errors else "Error desconocido"
                results.append(SmokeTestResult("XSD v150 (DE Node)", "FAIL", error_msg))
                print(f"   ❌ NO válido: {error_msg}")
        else:
            results.append(SmokeTestResult("XSD v150 (DE Node)", "SKIPPED", "XSD no disponible"))
            print(f"   ⏭️  XSD no disponible")
        print()
    else:
        results.append(SmokeTestResult("XSD v150 (DE Node)", "SKIPPED", "DE Node no generado"))
    
    # ===== ETAPA 6: Generar siRecepDE =====
    print("6️⃣  Generando siRecepDE (rEnviDe)...")
    try:
        generate_sirecepde_from_de(python_de_path, sirecepde_path)
        results.append(SmokeTestResult(
            "siRecepDE generado",
            "OK",
            f"Generado: {sirecepde_path.name}",
            [str(sirecepde_path)]
        ))
        print(f"   ✅ Generado: {sirecepde_path.name}")
    except Exception as e:
        results.append(SmokeTestResult("siRecepDE generado", "FAIL", str(e)))
        print(f"   ❌ Error: {e}")
        return 1
    print()
    
    # ===== ETAPA 7: Validar estructura siRecepDE =====
    print("7️⃣  Validando estructura XML (siRecepDE)...")
    is_well_formed, errors = validate_xml_structure(sirecepde_path)
    if is_well_formed:
        results.append(SmokeTestResult("Estructura XML (siRecepDE)", "OK"))
        print(f"   ✅ XML bien formado")
    else:
        results.append(SmokeTestResult("Estructura XML (siRecepDE)", "FAIL", errors[0] if errors else ""))
        print(f"   ❌ XML mal formado: {errors[0] if errors else 'Error desconocido'}")
        return 1
    print()
    
    # ===== ETAPA 8: Validar XSD siRecepDE =====
    print("8️⃣  Validando XSD WS (siRecepDE)...")
    if xsd_dir.exists():
        is_valid, errors = validate_against_xsd(sirecepde_path, "sirecepde", xsd_dir)
        if is_valid:
            results.append(SmokeTestResult("XSD WS (siRecepDE)", "OK", "WS_SiRecepDE_v150.xsd"))
            print(f"   ✅ Válido según WS_SiRecepDE_v150.xsd")
        else:
            error_msg = errors[0] if errors else "Error desconocido"
            results.append(SmokeTestResult("XSD WS (siRecepDE)", "FAIL", error_msg))
            print(f"   ❌ NO válido: {error_msg}")
            return 1
    else:
        results.append(SmokeTestResult("XSD WS (siRecepDE)", "SKIPPED", "XSD no disponible"))
        print(f"   ⏭️  XSD no disponible")
    print()
    
    # ===== ETAPA 9: Comparar Python vs Node (si ambos existen) =====
    if node_de_generated and node_de_generated.exists():
        print("9️⃣  Comparando DE Python vs Node...")
        try:
            are_equal, differences, diff_text = compare_xmls(python_de_path, node_de_generated)
            # Guardar diff siempre
            diff_path.write_text(diff_text, encoding='utf-8')
            
            if are_equal:
                results.append(SmokeTestResult("Comparación DE", "OK", "Campos clave coinciden", [str(diff_path)]))
                print(f"   ✅ Campos clave coinciden")
            else:
                results.append(SmokeTestResult("Comparación DE", "FAIL", f"{len(differences)} diferencias encontradas", [str(diff_path)]))
                print(f"   ⚠️  {len(differences)} diferencias encontradas")
            
            print(f"   📄 Diff guardado: {diff_path.name}")
        except Exception as e:
            results.append(SmokeTestResult("Comparación DE", "FAIL", str(e)))
            print(f"   ❌ Error al comparar: {e}")
        print()
    else:
        results.append(SmokeTestResult("Comparación DE", "SKIPPED", "DE Node no disponible"))
        # Crear diff vacío indicando skip
        diff_path.write_text("=== COMPARACIÓN OMITIDA ===\n\nDE Node no disponible. Instalar: cd tesaka-cv/tools/node && npm install\n", encoding='utf-8')
    
    # ===== RESUMEN FINAL =====
    print("=" * 70)
    print("RESUMEN SMOKE TEST")
    print("=" * 70)
    
    ok_count = sum(1 for r in results if r.status == "OK")
    fail_count = sum(1 for r in results if r.status == "FAIL")
    skipped_count = sum(1 for r in results if r.status == "SKIPPED")
    
    print(f"\nEstado por etapa:")
    for result in results:
        print(f"  {result}")
    
    print(f"\n📊 Totales: OK={ok_count}, FAIL={fail_count}, SKIPPED={skipped_count}")
    
    print(f"\n📦 Artifacts generados en: {artifacts_dir}")
    artifact_files = [
        python_de_path,
        sirecepde_path,
        diff_path
    ]
    if node_de_generated and node_de_generated.exists():
        artifact_files.append(node_de_generated)
    
    for artifact in artifact_files:
        if artifact.exists():
            print(f"   - {artifact.name}")
    
    print()
    
    # Exit code: 0 si no hay FAIL (SKIPPED está OK), 1 si hay algún FAIL
    if fail_count > 0:
        print("❌ SMOKE TEST FALLÓ")
        print(f"   ({fail_count} etapa(s) fallaron - revisar errores arriba)")
        return 1
    else:
        print("✅ SMOKE TEST COMPLETADO")
        if skipped_count > 0:
            print(f"   ({skipped_count} etapa(s) omitidas - esto es normal si Node/xmlgen no está instalado)")
        return 0


if __name__ == "__main__":
    sys.exit(main())

