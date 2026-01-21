#!/usr/bin/env python3
"""
Flujo completo SIFEN - Adaptar, Firmar, Enviar, Generar PDF
"""

import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from app.sifen_client.soap_client import SoapClient

class SifenFlujoCompleto:
    """Maneja el flujo completo de SIFEN"""
    
    def __init__(self, env='test'):
        self.env = env
        self.artifacts_dir = Path(f"artifacts/flujo_completo_{env}")
        self.artifacts_dir.mkdir(exist_ok=True)
    
    def adaptar_xml(self, xml_original, ruc, dv, timbrado=None):
        """Paso 1: Adaptar XML al RUC del emisor"""
        print("\n📝 Paso 1: Adaptando XML...")
        
        # Parsear XML
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(xml_original, parser)
        root = tree.getroot()
        
        SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
        de = root.find(f".//{SIFEN_NS}DE")
        
        # Actualizar datos del emisor
        gEmis = de.find(f".//{SIFEN_NS}gEmis")
        gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
        gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
        gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
        gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA S.A."
        gEmis.find(f"{SIFEN_NS}dDirEmi").text = "DIRECCION DE PRUEBA 123"
        gEmis.find(f"{SIFEN_NS}dDenSuc").text = "MATRIZ"
        
        # Actualizar timbrado si se especifica
        if timbrado:
            gTimb = de.find(f".//{SIFEN_NS}gTimb")
            gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
        
        # Actualizar fechas
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        de.find(f"{SIFEN_NS}dFecFirma").text = now.strftime('%Y-%m-%dT%H:%M:%S')
        gDatGralOpe = de.find(f".//{SIFEN_NS}gDatGralOpe")
        gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = now.strftime('%Y-%m-%dT%H:%M:%S')
        
        # Eliminar firma y QR
        for sig in root.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
            sig.getparent().remove(sig)
        gCamFuFD = root.find(f".//{SIFEN_NS}gCamFuFD")
        if gCamFuFD is not None:
            gCamFuFD.getparent().remove(gCamFuFD)
        
        # Guardar XML adaptado
        xml_adaptado = self.artifacts_dir / "xml_adaptado.xml"
        xml_bytes = etree.tostring(root, encoding='utf-8', xml_declaration=True)
        xml_adaptado.write_bytes(xml_bytes)
        
        print(f"✅ XML adaptado: {xml_adaptado}")
        return xml_adaptado
    
    def firmar_xml(self, xml_path):
        """Paso 2: Firmar XML"""
        print("\n🔐 Paso 2: Firmando XML...")
        
        # Usar send_sirecepde para firmar
        from tools.send_sirecepde import sign_and_normalize_rde_inside_xml
        
        xml_bytes = xml_path.read_bytes()
        cert_path = os.getenv("SIFEN_SIGN_P12_PATH", "/Users/robinklaiss/.sifen/certs/F1T_65478.p12")
        cert_pass = os.getenv("SIFEN_SIGN_P12_PASSWORD", "bH1%T7EP")
        
        signed_bytes = sign_and_normalize_rde_inside_xml(
            xml_bytes, cert_path, cert_pass, self.artifacts_dir
        )
        
        # Guardar XML firmado
        xml_firmado = self.artifacts_dir / "xml_firmado.xml"
        xml_firmado.write_bytes(signed_bytes)
        
        # Extraer CDC
        parser = etree.XMLParser(remove_blank_text=False)
        root = etree.fromstring(signed_bytes, parser)
        SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
        de = root.find(f"{SIFEN_NS}DE")
        cdc = de.get('Id')
        
        print(f"✅ XML firmado: {xml_firmado}")
        print(f"   CDC: {cdc}")
        
        return xml_firmado, cdc
    
    def enviar_a_sifen(self, xml_firmado):
        """Paso 3: Enviar a SIFEN"""
        print(f"\n📡 Paso 3: Enviando a SIFEN ({self.env})...")
        
        try:
            # Crear cliente SOAP
            client = SoapClient(env=self.env)
            
            # Enviar lote
            response = client.enviar_lote_desde_xml(xml_firmado.read_bytes())
            
            # Parsear respuesta
            root = etree.fromstring(response)
            ns = {'sif': 'http://ekuatia.set.gov.py/sifen/xsd'}
            
            resp = root.find('.//sif:rEnviLoteDERes', namespaces=ns)
            if resp is not None:
                cod_res = resp.find('sif:dCodRes', namespaces=ns)
                msg_res = resp.find('sif:dMsgRes', namespaces=ns)
                
                print(f"\n📊 Respuesta SIFEN:")
                print(f"   Código: {cod_res.text if cod_res is not None else 'N/A'}")
                print(f"   Mensaje: {msg_res.text if msg_res is not None else 'N/A'}")
                
                # Guardar respuesta
                resp_file = self.artifacts_dir / "respuesta_sifen.xml"
                resp_file.write_bytes(response)
                print(f"✅ Respuesta guardada: {resp_file}")
                
                return cod_res.text if cod_res is not None else None
            else:
                print("❌ No se pudo parsear la respuesta")
                return None
                
        except Exception as e:
            print(f"❌ Error enviando a SIFEN: {e}")
            return None
    
    def generar_pdf(self, xml_firmado):
        """Paso 4: Generar PDF con QR"""
        print("\n📄 Paso 4: Generando PDF...")
        
        # Usar el generador de PDF
        from tools.generar_pdf_sifen import SifenPDFGenerator
        
        pdf_path = self.artifacts_dir / "factura_con_qr.pdf"
        generator = SifenPDFGenerator()
        generator.generar_pdf(str(xml_firmado), str(pdf_path))
        
        print(f"✅ PDF generado: {pdf_path}")
        return pdf_path
    
    def ejecutar_flujo(self, xml_original, ruc, dv, timbrado=None):
        """Ejecuta todo el flujo"""
        print(f"\n🚀 Iniciando flujo SIFEN completo")
        print(f"   Ambiente: {self.env}")
        print(f"   RUC: {ruc}-{dv}")
        print(f"   Directorio: {self.artifacts_dir}")
        
        # Paso 1: Adaptar
        xml_adaptado = self.adaptar_xml(xml_original, ruc, dv, timbrado)
        
        # Paso 2: Firmar
        xml_firmado, cdc = self.firmar_xml(xml_adaptado)
        
        # Paso 3: Enviar
        cod_res = self.enviar_a_sifen(xml_firmado)
        
        # Paso 4: Generar PDF
        pdf_path = self.generar_pdf(xml_firmado)
        
        # Resumen
        print("\n" + "="*50)
        print("📋 RESUMEN DEL FLUJO")
        print("="*50)
        print(f"✅ XML adaptado: {xml_adaptado}")
        print(f"✅ XML firmado: {xml_firmado}")
        print(f"✅ CDC: {cdc}")
        print(f"✅ Código respuesta: {cod_res}")
        print(f"✅ PDF generado: {pdf_path}")
        
        if cod_res == "0000":
            print("\n🎉 ÉXITO: Documento aceptado por SIFEN!")
        else:
            print(f"\n⚠️  Documento con observaciones (código: {cod_res})")
        
        return {
            'xml_firmado': xml_firmado,
            'cdc': cdc,
            'cod_res': cod_res,
            'pdf': pdf_path
        }

def main():
    parser = argparse.ArgumentParser(description="Flujo completo SIFEN")
    parser.add_argument('--xml', required=True, help='XML original')
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', help='Timbrado')
    parser.add_argument('--env', choices=['test', 'prod'], default='test',
                       help='Ambiente (default: test)')
    
    args = parser.parse_args()
    
    if not Path(args.xml).exists():
        print(f"❌ Archivo no encontrado: {args.xml}")
        sys.exit(1)
    
    flujo = SifenFlujoCompleto(env=args.env)
    resultado = flujo.ejecutar_flujo(
        Path(args.xml),
        args.ruc,
        args.dv,
        args.timbrado
    )
    
    # Si todo fue bien, mostrar archivos útiles
    if resultado['cod_res'] == "0000":
        print(f"\n📂 Archivos importantes:")
        print(f"   XML para archivo: {resultado['xml_firmado']}")
        print(f"   PDF para cliente: {resultado['pdf']}")

if __name__ == "__main__":
    main()
