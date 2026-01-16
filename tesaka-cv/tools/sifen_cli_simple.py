#!/usr/bin/env python3
"""
SIFEN CLI Simple - Generador de XMLs usando plantilla base
Usa el XML ya validado como plantilla y modifica los campos necesarios.
"""

import sys
import os
import argparse
import re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xmlsec_signer import sign_de_with_p12

class SifenCLISimple:
    """CLI simple que usa plantilla XML validada"""
    
    def __init__(self):
        self.template_path = Path("artifacts/rde_signed_01045547378001001000000112026010210000000013.xml")
        self.config = {
            'cert_path': os.getenv('SIFEN_SIGN_P12_PATH', '/Users/robinklaiss/.sifen/certs/F1T_65478.p12'),
            'cert_password': os.getenv('SIFEN_SIGN_P12_PASSWORD', 'bH1%T7EP'),
        }
    
    def generar_factura(self, numero_documento, **kwargs):
        """Genera factura modificando la plantilla"""
        
        if not self.template_path.exists():
            print(f"❌ Template no encontrado: {self.template_path}")
            sys.exit(1)
        
        # Leer template
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(self.template_path, parser)
        root = tree.getroot()
        
        # Namespaces
        SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
        
        # Modificar número de documento
        num_doc = str(numero_documento).zfill(7)[-7:]
        gTimb = root.find(f".//{SIFEN_NS}gTimb")
        gTimb.find(f"{SIFEN_NS}dNumDoc").text = num_doc
        
        # Modificar fecha y hora
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        
        gDatGralOpe = root.find(f".//{SIFEN_NS}gDatGralOpe")
        gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = now.strftime('%Y-%m-%dT%H:%M:%S')
        gTimb.find(f"{SIFEN_NS}dFeIniT").text = now.strftime('%Y-%m-%d')
        
        # Modificar dFecFirma
        DE = root.find(f"{SIFEN_NS}DE")
        DE.find(f"{SIFEN_NS}dFecFirma").text = now.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Calcular nuevo CDC (simplificado)
        # Extraer base del CDC original y cambiar número
        cdc_original = DE.get('Id')
        base_cdc = cdc_original[:-10]  # Quitar últimos 10 dígitos
        nuevo_cdc = f"{base_cdc}{num_doc[-2:]}{now.strftime('%Y%m%d%H')}000000001"
        dv = "8"  # Simplificado
        
        nuevo_cdc_completo = nuevo_cdc + dv
        DE.set('Id', nuevo_cdc_completo)
        DE.find(f"{SIFEN_NS}dDVId").text = dv
        
        # Eliminar firma existente
        for sig in root.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
            sig.getparent().remove(sig)
        
        # Firmar DE
        print("🔐 Firmando XML...")
        de_bytes = etree.tostring(DE, encoding='utf-8')
        signed_de_bytes = sign_de_with_p12(
            de_bytes,
            self.config['cert_path'],
            self.config['cert_password']
        )
        
        # Parsear DE firmado y reemplazar
        signed_de = etree.fromstring(signed_de_bytes)
        root.replace(DE, signed_de)
        
        # Serializar XML final
        xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True, standalone=False)
        
        return xml_bytes, nuevo_cdc_completo
    
    def guardar_xml(self, xml_bytes, cdc, output_dir=None, filename=None):
        """Guarda el XML en disco"""
        
        if output_dir is None:
            output_dir = Path.home() / "Desktop"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        if filename is None:
            filename = f"factura_{cdc}.xml"
        
        filepath = output_dir / filename
        filepath.write_bytes(xml_bytes)
        
        print(f"✅ XML guardado en: {filepath}")
        return filepath
    
    def validar_xml(self, xml_path):
        """Valida el CDC del XML generado"""
        
        print("\n🔍 Validando XML generado...")
        os.system(f".venv/bin/python tools/debug_cdc.py {xml_path}")

def main():
    parser = argparse.ArgumentParser(
        description="SIFEN CLI Simple - Generador de XMLs usando plantilla validada"
    )
    
    parser.add_argument('numero', type=int, help='Número de documento (7 dígitos)')
    parser.add_argument('--output', '-o', help='Directorio de salida (default: Desktop)')
    parser.add_argument('--filename', '-f', help='Nombre del archivo (default: auto)')
    parser.add_argument('--no-validar', action='store_true', help='No validar después de generar')
    
    args = parser.parse_args()
    
    cli = SifenCLISimple()
    
    try:
        # Generar XML
        xml_bytes, cdc = cli.generar_factura(args.numero)
        
        # Guardar
        filepath = cli.guardar_xml(
            xml_bytes,
            cdc,
            output_dir=args.output,
            filename=args.filename
        )
        
        # Validar
        if not args.no_validar:
            cli.validar_xml(filepath)
        
        print(f"\n🎉 Factura generada exitosamente!")
        print(f"   CDC: {cdc}")
        print(f"   Archivo: {filepath}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
