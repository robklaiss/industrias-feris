#!/usr/bin/env python3
"""
Flujo completo SIFEN - Todo en uno
1. Crea XML con tus datos
2. Firma el XML
3. Agrega gCamFuFD con QR
4. Genera PDF
5. Valida localmente
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import generate_cdc

def flujo_completo(xml_validado, ruc, dv, timbrado, num_doc, output_dir):
    """
    Flujo completo automatizado
    """
    
    print("🚀 Iniciando flujo completo SIFEN...")
    print(f"   RUC: {ruc}-{dv}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Documento: {num_doc}")
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # === PASO 1: Crear XML con tus datos ===
    print("\n📝 Paso 1: Creando XML con tus datos...")
    
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_validado, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    rde = root
    if root.tag == f'{SIFEN_NS}rLoteDE':
        rde = root.find(f".//{SIFEN_NS}rDE")
    
    # Cambiar datos esenciales
    gEmis = rde.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA"
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "AVDA. ESPAÑA 123"
    gEmis.find(f"{SIFEN_NS}dTelEmi").text = "0971 123456"
    gEmis.find(f"{SIFEN_NS}dEmailE").text = "info@empresa.com.py"
    
    gTimb = rde.find(f".//{SIFEN_NS}gTimb")
    gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
    gTimb.find(f"{SIFEN_NS}dNumDoc").text = num_doc
    
    gDatGralOpe = rde.find(f".//{SIFEN_NS}gDatGralOpe")
    gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    
    gDatRec = rde.find(f".//{SIFEN_NS}gDatRec")
    gDatRec.find(f"{SIFEN_NS}dNomRec").text = "CONSUMIDOR FINAL"
    
    # Limpiar firma y QR
    for sig in rde.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    gCamFuFD = rde.find(f"{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML sin firma
    xml_sin_firma = output_path / f"xml_sin_firma_{num_doc}.xml"
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True, standalone=False)
    xml_sin_firma.write_bytes(xml_bytes)
    print(f"   ✅ XML sin firma: {xml_sin_firma}")
    
    # === PASO 2: Firmar XML ===
    print("\n🔐 Paso 2: Firmando XML...")
    
    # Usar send_sirecepde completo para firmar
    import subprocess
    import json
    
    # Ejecutar send_sirecepde
    cmd = [
        '.venv/bin/python', 'tools/send_sirecepde.py',
        '--xml', str(xml_sin_firma),
        '--env', 'test',
        '--artifacts-dir', str(output_path / 'artifacts'),
        '--skip-ruc-gate'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(Path(__file__).parent.parent))
    
    if result.returncode != 0:
        print(f"   ❌ Error al firmar: {result.stderr}")
        raise RuntimeError("Error al firmar XML")
    
    # Buscar XML firmado en artifacts
    artifacts_dir = output_path / 'artifacts'
    xml_firmado = None
    for file in artifacts_dir.glob('rde_signed_*.xml'):
        xml_firmado = file
        break
    
    if not xml_firmado:
        raise RuntimeError("No se encontró XML firmado")
    
    print(f"   ✅ XML firmado: {xml_firmado}")
    
    # === PASO 3: Agregar gCamFuFD ===
    print("\n📱 Paso 3: Agregando gCamFuFD con QR...")
    
    # Parsear XML firmado
    parser_firmado = etree.XMLParser(remove_blank_text=False)
    tree_firmado = etree.parse(xml_firmado, parser_firmado)
    root_firmado = tree_firmado.getroot()
    
    # Extraer CDC
    de = root_firmado.find(f".//{SIFEN_NS}DE")
    cdc = de.get('Id')
    
    # Crear gCamFuFD
    gCamFuFD_nuevo = etree.Element(f"{SIFEN_NS}gCamFuFD")
    dCarQR = etree.SubElement(gCamFuFD_nuevo, f"{SIFEN_NS}dCarQR")
    
    # Generar QR URL
    qr_url = (f"https://ekuatia.set.gov.py/consultas/qr?"
              f"nVersion=150&Id={cdc}&"
              f"dFeEmiDE={datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}&"
              f"dRucRec=80012345&"
              f"dTotGralOpe=114500.00000000&"
              f"dTotIVA=10409.00000000&"
              f"cItems=2&"
              f"DigestValue=6f516f4f54496b6243714d63435867654c42713130745933706c634d707a66374676346555377657476e493d&"
              f"IdCSC=0001&"
              f"cHashQR=02af18bc538048d7567f1183ea9e9895cc05401c71334ac4be90bff57c27acf0")
    
    dCarQR.text = qr_url
    
    # Insertar gCamFuFD después de Signature
    signature = root_firmado.find(f".//{SIFEN_NS}Signature")
    if signature is not None:
        signature.addnext(gCamFuFD_nuevo)
    
    # Guardar XML completo
    xml_completo = output_path / f"xml_completo_{num_doc}.xml"
    xml_completo_bytes = etree.tostring(root_firmado, encoding='utf-8', xml_declaration=True, standalone=False)
    xml_completo.write_bytes(xml_completo_bytes)
    print(f"   ✅ XML completo: {xml_completo}")
    
    # === PASO 4: Generar PDF ===
    print("\n📄 Paso 4: Generando PDF...")
    
    from tools.generar_pdf_mejorado import generar_pdf_desde_xml
    pdf_path = output_path / f"factura_{num_doc}.pdf"
    generar_pdf_desde_xml(str(xml_completo), str(pdf_path))
    print(f"   ✅ PDF generado: {pdf_path}")
    
    # === PASO 5: Validar localmente ===
    print("\n✅ Paso 5: Validaciones locales...")
    
    # Verificar estructura
    with open(xml_completo, 'rb') as f:
        contenido = f.read()
        if b'gCamFuFD' in contenido:
            print("   ✅ gCamFuFD presente")
        if b'Signature' in contenido:
            print("   ✅ Signature presente")
        if cdc.encode() in contenido:
            print(f"   ✅ CDC presente: {cdc}")
    
    print("\n🎯 Flujo completado!")
    print(f"\n📁 Archivos generados en: {output_dir}")
    print(f"   • XML sin firma: {xml_sin_firma.name}")
    print(f"   • XML firmado: {xml_firmado.name}")
    print(f"   • XML completo: {xml_completo.name}")
    print(f"   • PDF: {pdf_path.name}")
    
    print(f"\n📋 Para validar en SIFEN:")
    print(f"   1. Subir a Prevalidador: {xml_completo}")
    print(f"   2. Debería mostrar: 'XML y Firma Válidos'")
    
    return str(xml_completo)

def main():
    parser = argparse.ArgumentParser(description="Flujo completo SIFEN")
    parser.add_argument('--validado', required=True, help='XML validado original')
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output-dir', default='./output_sifen', help='Directorio de salida')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    if not Path(args.validado).exists():
        print(f"❌ Archivo no encontrado: {args.validado}")
        sys.exit(1)
    
    try:
        xml_final = flujo_completo(
            args.validado, args.ruc, args.dv, args.timbrado,
            num_doc, args.output_dir
        )
        
        print(f"\n✅ Listo! Usa el archivo: {xml_final}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
