#!/usr/bin/env python3
"""
Debug CDC mismatch - Extrae CDC y campos del XML para comparar
"""
import sys
import re
from pathlib import Path
from lxml import etree
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import generate_cdc

def parse_xml_cdc(xml_path):
    """Parsea XML y extrae CDC y campos base"""
    tree = etree.parse(xml_path)
    root = tree.getroot()
    
    # Encontrar elemento DE
    de = root.find('.//{*}DE')
    if de is None:
        print("❌ No se encontró elemento DE")
        return None
    
    # Extraer CDC del atributo Id
    cdc_xml = de.get('Id')
    print(f"CDC en XML: {cdc_xml}")
    
    # Extraer campos que alimentan el CDC
    fields = {}
    
    # RUC y DV del emisor
    gEmis = root.find('.//{*}gEmis')
    if gEmis is not None:
        ruc = gEmis.findtext('.//{*}dRucEm', '').strip()
        dv = gEmis.findtext('.//{*}dDVEmi', '').strip()
        fields['ruc'] = ruc
        fields['dv'] = dv
    
    # Timbrado
    gTimb = root.find('.//{*}gTimb')
    if gTimb is not None:
        timbrado = gTimb.findtext('.//{*}dNumTim', '').strip()
        est = gTimb.findtext('.//{*}dEst', '').strip()
        punto = gTimb.findtext('.//{*}dPunExp', '').strip()
        num_doc = gTimb.findtext('.//{*}dNumDoc', '').strip()
        fields['timbrado'] = timbrado
        fields['establecimiento'] = est
        fields['punto_exp'] = punto
        fields['num_doc'] = num_doc
    
    # Fecha de emisión (la que debe usar el CDC)
    gDatGralOpe = root.find('.//{*}gDatGralOpe')
    if gDatGralOpe is not None:
        fecha_emision = gDatGralOpe.findtext('.//{*}dFeEmiDE', '').strip()
        fields['fecha_emision'] = fecha_emision
        # Convertir a YYYYMMDD para CDC
        if 'T' in fecha_emision:
            fecha_cdc = fecha_emision.split('T')[0].replace('-', '')
        else:
            fecha_cdc = re.sub(r'\D', '', fecha_emision)
        fields['fecha_cdc'] = fecha_cdc
    
    # Tipo de documento (iTiDE está en gTimb)
    gTimb = root.find('.//{*}gTimb')
    if gTimb is not None:
        iTiDE = gTimb.findtext('.//{*}iTiDE', '').strip()
        # Para CDC: "1" -> "01", "001" -> "01" (siempre 2 dígitos)
        fields['tipo_doc'] = iTiDE.zfill(2)  # Normalizar a 2 dígitos para CDC
    
    return cdc_xml, fields

def main():
    if len(sys.argv) != 2:
        print("Uso: python debug_cdc_v2.py <xml_file>")
        sys.exit(1)
    
    xml_path = sys.argv[1]
    
    # Parsear XML
    result = parse_xml_cdc(xml_path)
    if result is None:
        sys.exit(1)
    
    cdc_xml, fields = result
    
    print("\n📋 Campos extraídos del XML:")
    for k, v in fields.items():
        print(f"   {k}: {v}")
    
    # Calcular CDC con nuestros datos
    print("\n🔧 Calculando CDC con los campos extraídos...")
    try:
        cdc_calc = generate_cdc(
            fields['ruc'],
            fields['timbrado'],
            fields['establecimiento'],
            fields['punto_exp'],
            fields['num_doc'],
            fields['tipo_doc'],
            fields['fecha_cdc'],
            "114500"  # monto (no afecta el CDC)
        )
        print(f"CDC calculado: {cdc_calc}")
        
        # Comparar
        print("\n🔍 Comparación:")
        print(f"   CDC en XML:   {cdc_xml}")
        print(f"   CDC calculado: {cdc_calc}")
        
        if cdc_xml == cdc_calc:
            print("   ✅ CDC coincide!")
        else:
            print("   ❌ CDC NO coincide!")
            
            # Decodificar para ver dónde difiere
            print("\n📊 Decodificación CDC:")
            print("   Posición | XML | Calc | Campo")
            print("   --------|-----|------|------")
            campos = [
                ("Tipo", 0, 2, "tipo_doc"),
                ("RUC", 2, 10, "ruc"),
                ("DV", 10, 11, "dv"),
                ("Est", 11, 14, "establecimiento"),
                ("Pto", 14, 17, "punto_exp"),
                ("Doc", 17, 24, "num_doc"),
                ("Cont", 24, 25, "tipo_cont"),
                ("Fecha", 25, 33, "fecha_cdc"),
                ("Emi", 33, 34, "tipo_emi"),
                ("CodSeg", 34, 43, "codseg"),
            ]
            
            for nombre, pos, end, campo in campos:
                xml_val = cdc_xml[pos:end] if cdc_xml else "?"
                calc_val = cdc_calc[pos:end] if cdc_calc else "?"
                match = "✅" if xml_val == calc_val else "❌"
                valor = fields.get(campo, "?")
                print(f"   {nombre:8} | {xml_val:3} | {calc_val:3} | {match} ({valor})")
    
    except Exception as e:
        print(f"❌ Error calculando CDC: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
