#!/usr/bin/env python3
"""
SIFEN CLI - Herramienta simple para generar XMLs de Documentos Electrónicos
Inspirado en rshk-jsifenlib para facilitar la generación de XMLs firmados.
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.xml_generator_v150 import create_rde_xml_v150
from tools.send_sirecepde import sign_and_normalize_rde_inside_xml
from app.sifen_client.cdc_builder import build_cdc_from_de_xml

class SifenCLI:
    """CLI principal para generación de XMLs SIFEN"""
    
    def __init__(self):
        self.config = {
            'env': 'test',
            'cert_path': os.getenv('SIFEN_SIGN_P12_PATH', '/Users/robinklaiss/.sifen/certs/F1T_65478.p12'),
            'cert_password': os.getenv('SIFEN_SIGN_P12_PASSWORD', 'bH1%T7EP'),
            'ruc': '4554737',
            'dv_ruc': '8',
            'timbrado': '12345678',
            'establecimiento': '001',
            'punto_expedicion': '001',
            'tipo_documento': '1',
            'csc': '123456789'
        }
    
    def generar_factura(self, numero_documento, ruc=None, items=None, **kwargs):
        """Genera una factura electrónica XML firmada"""
        
        # Actualizar config con parámetros
        if ruc:
            # Parsear RUC con formato XXXXXXX-DV
            if '-' in ruc:
                parts = ruc.split('-')
                if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                    self.config['ruc'] = parts[0]
                    self.config['dv_ruc'] = parts[1]
                else:
                    print(f"⚠️ Formato de RUC inválido: {ruc}. Usando RUC por defecto.")
            else:
                print(f"⚠️ RUC sin DV: {ruc}. Formato esperado: XXXXXXX-DV")
        
        # Formatear número de documento
        num_doc = str(numero_documento).zfill(7)[-7:]
        
        # Configurar ambiente
        os.environ['SIFEN_CODSEG'] = self.config['csc']
        os.environ['SIFEN_TIP_CONT'] = '1'
        os.environ['SI_TIP_EMI'] = '1'
        
        print(f"📄 Generando Factura Electrónica")
        print(f"   RUC: {self.config['ruc']}-{self.config['dv_ruc']}")
        print(f"   Timbrado: {self.config['timbrado']}")
        print(f"   Establecimiento: {self.config['establecimiento']}")
        print(f"   Punto Expedición: {self.config['punto_expedicion']}")
        print(f"   N° Documento: {num_doc}")
        
        # Generar XML completo (rDE con DE dentro)
        xml_str = create_rde_xml_v150(
            ruc=self.config['ruc'],
            dv_ruc=self.config['dv_ruc'],
            timbrado=self.config['timbrado'],
            establecimiento=self.config['establecimiento'],
            punto_expedicion=self.config['punto_expedicion'],
            numero_documento=num_doc,
            tipo_documento=self.config['tipo_documento'],
            fecha=datetime.now(timezone.utc).strftime('%Y-%m-%d'),
            hora=datetime.now(timezone.utc).strftime('%H:%M:%S'),
            csc=self.config['csc']
        )
        
        # Usar el sistema de firma que ya funciona
        print("🔐 Firmando XML...")
        from tools.send_sirecepde import sign_and_normalize_rde_inside_xml
        
        xml_bytes = xml_str.encode('utf-8')
        signed_bytes = sign_and_normalize_rde_inside_xml(
            xml_bytes,
            self.config['cert_path'],
            self.config['cert_password']
        )
        
        # Extraer CDC del XML firmado
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(signed_bytes, parser)
        SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
        de = root.find(f"{SIFEN_NS}DE")
        cdc = de.get('Id')
        
        return signed_bytes, cdc
    
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
    
    def configurar(self, **kwargs):
        """Actualiza la configuración"""
        self.config.update(kwargs)

def main():
    parser = argparse.ArgumentParser(
        description="SIFEN CLI - Generador de XMLs de Documentos Electrónicos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s generar 123 --output ./facturas
  %(prog)s generar 456 --ruc 80012345-7 --items 3
  %(prog)s configurar --ruc 80012345-7 --timbrado 98765432
        """
    )
    
    subparsers = parser.add_subparsers(dest='comando', help='Comandos disponibles')
    
    # Comando generar
    parser_gen = subparsers.add_parser('generar', help='Generar factura electrónica')
    parser_gen.add_argument('numero', type=int, help='Número de documento (7 dígitos)')
    parser_gen.add_argument('--ruc', help='RUC con DV (ej: 80012345-7)')
    parser_gen.add_argument('--output', '-o', help='Directorio de salida (default: Desktop)')
    parser_gen.add_argument('--filename', '-f', help='Nombre del archivo (default: auto)')
    parser_gen.add_argument('--no-validar', action='store_true', help='No validar después de generar')
    
    # Comando configurar
    parser_conf = subparsers.add_parser('configurar', help='Configurar parámetros por defecto')
    parser_conf.add_argument('--ruc', help='RUC con DV')
    parser_conf.add_argument('--timbrado', help='Número de timbrado')
    parser_conf.add_argument('--establecimiento', help='Código de establecimiento')
    parser_conf.add_argument('--punto-expedicion', help='Punto de expedición')
    parser_conf.add_argument('--cert', help='Ruta al certificado P12')
    parser_conf.add_argument('--cert-password', help='Contraseña del certificado')
    
    # Comando validar
    parser_val = subparsers.add_parser('validar', help='Validar XML existente')
    parser_val.add_argument('xml_path', help='Ruta al archivo XML')
    
    args = parser.parse_args()
    
    if not args.comando:
        parser.print_help()
        return
    
    cli = SifenCLI()
    
    if args.comando == 'generar':
        try:
            # Generar XML
            xml_bytes, cdc = cli.generar_factura(
                args.numero,
                ruc=args.ruc
            )
            
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
            sys.exit(1)
    
    elif args.comando == 'configurar':
        config_updates = {}
        if args.ruc:
            config_updates['ruc'] = args.ruc[:-1]
            config_updates['dv_ruc'] = args.ruc[-1]
        if args.timbrado:
            config_updates['timbrado'] = args.timbrado
        if args.establecimiento:
            config_updates['establecimiento'] = args.establecimiento
        if args.punto_exedicion:
            config_updates['punto_expedicion'] = args.punto_exedicion
        if args.cert:
            config_updates['cert_path'] = args.cert
        if args.cert_password:
            config_updates['cert_password'] = args.cert_password
        
        cli.configurar(**config_updates)
        print("✅ Configuración actualizada")
        
    elif args.comando == 'validar':
        if not Path(args.xml_path).exists():
            print(f"❌ Archivo no encontrado: {args.xml_path}")
            sys.exit(1)
        
        cli.validar_xml(args.xml_path)

if __name__ == "__main__":
    main()
