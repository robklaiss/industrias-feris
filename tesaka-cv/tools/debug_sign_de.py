#!/usr/bin/env python3
"""
Script de prueba para firmar un DE con XMLDSig usando python-xmlsec.

Uso:
    python -m tools.debug_sign_de --xml artifacts/de_test.xml
    python -m tools.debug_sign_de --xml artifacts/de_test.xml --output artifacts/signed.xml
"""

import sys
import os
import argparse
import base64
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xmlsec_signer import sign_de_with_p12, XMLSecError

# Import lxml.etree - el linter puede no reconocerlo, pero funciona correctamente
import lxml.etree as etree  # noqa: F401


def main():
    parser = argparse.ArgumentParser(
        description="Firma un DE con XMLDSig según especificación SIFEN"
    )
    parser.add_argument(
        "--xml", "-x",
        type=Path,
        required=True,
        help="Archivo XML del DE a firmar"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("artifacts/signed.xml"),
        help="Archivo de salida (default: artifacts/signed.xml)"
    )
    parser.add_argument(
        "--p12",
        type=Path,
        help="Ruta al certificado P12/PFX (default: SIFEN_SIGN_P12_PATH)"
    )
    parser.add_argument(
        "--password",
        type=str,
        help="Contraseña del certificado (default: SIFEN_SIGN_P12_PASSWORD)"
    )
    
    args = parser.parse_args()
    
    # Resolver certificado y contraseña
    p12_path = args.p12 or os.getenv("SIFEN_SIGN_P12_PATH")
    p12_password = args.password or os.getenv("SIFEN_SIGN_P12_PASSWORD")
    
    if not p12_path:
        print("❌ Error: Falta certificado de firma")
        print("   Opciones:")
        print("   1) --p12 /ruta/al/certificado.p12 --password contraseña")
        print("   2) export SIFEN_SIGN_P12_PATH=/ruta/al/certificado.p12")
        print("      export SIFEN_SIGN_P12_PASSWORD=contraseña")
        return 1
    
    if not p12_password:
        print("❌ Error: Falta contraseña del certificado")
        print("   Opciones:")
        print("   1) --password contraseña")
        print("   2) export SIFEN_SIGN_P12_PASSWORD=contraseña")
        return 1
    
    # Leer XML como bytes
    xml_path = Path(args.xml)
    if not xml_path.exists():
        print(f"❌ Error: Archivo XML no encontrado: {xml_path}")
        return 1
    
    xml_bytes = xml_path.read_bytes()
    original_size = len(xml_bytes)
    print(f"📄 XML original: {original_size} bytes")
    
    # Extraer Id del DE antes de firmar
    try:
        root = etree.fromstring(xml_bytes)
        de_id = None
        for elem in root.iter():
            local_name = etree.QName(elem).localname
            if local_name == "DE":
                de_id = elem.get("Id") or elem.get("id")
                break
        print(f"📋 Id encontrado: {de_id or 'NO ENCONTRADO'}")
    except Exception as e:
        print(f"⚠️  No se pudo extraer Id: {e}")
        de_id = None
    
    # Firmar
    try:
        print(f"🔐 Firmando con certificado: {Path(p12_path).name}")
        print(f"   Algoritmos: RSA-SHA256 (SignatureMethod), SHA-256 (DigestMethod)")
        signed_xml_bytes = sign_de_with_p12(xml_bytes, str(p12_path), p12_password)
        
        signed_size = len(signed_xml_bytes)
        print(f"📄 XML firmado: {signed_size} bytes (delta: {signed_size - original_size:+d} bytes)")
        
        # Validación rápida de prefijo ds: - checks son fuente de verdad en BYTES firmados
        # Doc SIFEN: "no se podrá utilizar prefijos de namespace" - validar en bytes serializados
        # SOLO validar/imprimir, NO transformar (debug_sign_de.py solo hace checks)
        has_ds_prefix = b"<ds:" in signed_xml_bytes
        has_xmlns_ds = b'xmlns:ds=' in signed_xml_bytes
        has_default_ns = b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' in signed_xml_bytes
        
        if has_ds_prefix:
            print("❌ ERROR CRÍTICO: '<ds:' encontrado en XML serializado (Doc SIFEN: no se podrá utilizar prefijos)")
            raise ValueError("La firma tiene prefijo ds: en lugar de default namespace")
        if has_xmlns_ds:
            print("❌ ERROR CRÍTICO: 'xmlns:ds=' encontrado en XML serializado (Doc SIFEN: no se podrá utilizar prefijos)")
            raise ValueError("La firma tiene xmlns:ds= en lugar de default namespace")
        # Doc SIFEN: xmlns debe declararse en la etiqueta <Signature> como DEFAULT
        if not has_default_ns:
            print("❌ ERROR CRÍTICO: '<Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\"' NO encontrado (Doc SIFEN: xmlns en Signature)")
            raise ValueError("La firma no tiene default namespace correcto")
        print("✓ Validación de namespace: OK (sin prefijo ds:, sin xmlns:ds=, con default xmlns en Signature)")
        
        # Validar firma
        signed_root = etree.fromstring(signed_xml_bytes)
        
        # Buscar Signature (sin prefijo ds: - default namespace)
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        ns = {"ds": ds_ns}
        # Buscar sin prefijo (default namespace) - prioridad
        signatures_default = signed_root.xpath(f"//*[local-name()='Signature' and namespace-uri()='{ds_ns}']")
        # Buscar con prefijo ds: (fallback)
        signatures_ds = signed_root.xpath("//ds:Signature", namespaces=ns)
        
        signatures = signatures_default if signatures_default else signatures_ds
        has_signature = len(signatures) > 0
        print(f"✓ Signature encontrado: {'SÍ' if has_signature else 'NO'}")
        
        if not has_signature:
            raise ValueError("ERROR CRÍTICO: Signature NO encontrado en XML firmado. La firma no se aplicó correctamente.")
        
        if has_signature:
            sig = signatures[0]
            # Obtener tag real de signature (Clark notation: {namespace}localname)
            sig_tag_clark = sig.tag  # Ej: {http://www.w3.org/2000/09/xmldsig#}Signature
            sig_parent = sig.getparent()
            sig_parent_tag = etree.QName(sig_parent).text if sig_parent is not None else None
            
            print(f"   Tag signature (Clark): {sig_tag_clark}")
            print(f"   Parent signature: {sig_parent_tag}")
            
            # Verificar que NO tenga prefijo ds: ni xmlns:ds en el texto serializado (checks en BYTES)
            # Doc SIFEN: "no se podrá utilizar prefijos de namespace"
            has_ds_prefix = b"<ds:" in signed_xml_bytes
            has_xmlns_ds = b'xmlns:ds=' in signed_xml_bytes
            
            if has_ds_prefix:
                print("   ❌ ERROR: '<ds:' encontrado en XML serializado (Doc SIFEN: no prefijos)")
            else:
                print("   ✓ Confirmación: '<ds:' NO existe en bytes")
            
            if has_xmlns_ds:
                print("   ❌ ERROR: 'xmlns:ds=' encontrado en XML serializado (Doc SIFEN: no prefijos)")
            else:
                print("   ✓ Confirmación: 'xmlns:ds=' NO existe en bytes")
            
            # Verificar que SÍ exista default namespace en Signature
            # Doc SIFEN: xmlns debe declararse en la etiqueta <Signature> como DEFAULT
            if b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' in signed_xml_bytes:
                print("   ✓ Confirmación: '<Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\"' SÍ existe en bytes")
            else:
                print("   ❌ ERROR: '<Signature xmlns=\"http://www.w3.org/2000/09/xmldsig#\"' NO encontrado")
            
            # Confirmar ubicación: Signature es hijo directo de rDE y aparece después de DE (orden)
            # Doc SIFEN: Signature debe ir como HERMANO de DE dentro de rDE, inmediatamente después de </DE>
            if sig_parent_tag and "rDE" in sig_parent_tag:
                print("   ✓ Signature está dentro de rDE (correcto)")
                # Verificar orden: Signature debe estar después de DE
                rde_elem = sig_parent
                children_list = list(rde_elem)
                de_idx = -1
                sig_idx = -1
                for i, ch in enumerate(children_list):
                    if ch is sig:
                        sig_idx = i
                    elif etree.QName(ch).localname == "DE":
                        de_idx = i
                if de_idx != -1 and sig_idx != -1 and sig_idx > de_idx:
                    print(f"   ✓ Signature está después de DE (DE en índice {de_idx}, Signature en {sig_idx})")
                else:
                    print(f"   ⚠️  ADVERTENCIA: Orden incorrecto (DE en índice {de_idx}, Signature en {sig_idx})")
            else:
                print(f"   ⚠️  ADVERTENCIA: Signature parent es {sig_parent_tag} (se esperaba rDE)")
            
            # Si hay errores, no guardar archivo (post-check falla)
            has_default_ns = b'<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"' in signed_xml_bytes
            if has_ds_prefix or has_xmlns_ds or not has_default_ns:
                raise ValueError("Post-check falló: el XML contiene prefijo ds:/xmlns:ds= o falta default namespace. No se guardará el archivo.")
        
        if has_signature:
            # Extraer SignatureValue (buscar con y sin prefijo)
            sig_value_elems = signed_root.xpath("//ds:SignatureValue", namespaces=ns)
            if not sig_value_elems:
                sig_value_elems = signed_root.xpath(f"//*[local-name()='SignatureValue' and namespace-uri()='{ds_ns}']")
            if sig_value_elems:
                sig_value = sig_value_elems[0].text or ""
                print(f"✓ SignatureValue longitud: {len(sig_value)} caracteres")
                
                # Verificar que NO sea dummy
                try:
                    decoded = base64.b64decode(sig_value.strip())
                    decoded_str = decoded.decode("ascii", errors="ignore")
                    if "this is a test" in decoded_str.lower() or "dummy" in decoded_str.lower():
                        print("❌ ERROR: SignatureValue sigue siendo dummy/test")
                        print(f"   Contenido decodificado: {decoded_str[:100]}...")
                        raise ValueError(
                            "El SignatureValue decodifica a texto dummy. "
                            "La firma no se aplicó correctamente o el certificado no se usó."
                        )
                    else:
                        print("✓ SignatureValue es real (no dummy)")
                except ValueError:
                    # Re-lanzar errores de validación dummy
                    raise
                except Exception:
                    print("✓ SignatureValue es binario (probablemente real)")
            
            # Extraer X509Certificate (buscar con y sin prefijo)
            cert_elems = signed_root.xpath("//ds:X509Certificate", namespaces=ns)
            if not cert_elems:
                cert_elems = signed_root.xpath(f"//*[local-name()='X509Certificate' and namespace-uri()='{ds_ns}']")
            if cert_elems:
                cert_b64 = cert_elems[0].text or ""
                print(f"✓ X509Certificate encontrado: {len(cert_b64)} caracteres base64")
        
        # Guardar archivo firmado
        # Si el input es sirecepde_smoke_*.xml, generar signed_smoke_*.xml
        if "sirecepde_smoke" in xml_path.stem:
            output_path = xml_path.parent / f"{xml_path.stem}_signed.xml"
        else:
            output_path = Path(args.output)
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(signed_xml_bytes)
        
        print(f"✅ XML firmado guardado en: {output_path}")
        print(f"   Validar con: python -m tools.debug_compare_roshka")
        
        return 0
        
    except XMLSecError as e:
        print(f"❌ Error de firma: {e}")
        if os.getenv("SIFEN_DEBUG") == "1":
            import traceback
            traceback.print_exc()
        return 1
    except ValueError as e:
        # Error de validación dummy o namespace
        print(f"❌ {e}")
        if os.getenv("SIFEN_DEBUG") == "1":
            import traceback
            traceback.print_exc()
        return 1
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

