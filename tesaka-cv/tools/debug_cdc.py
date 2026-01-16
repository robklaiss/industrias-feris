#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import lxml.etree as etree
from app.sifen_client.xml_generator_v150 import generate_cdc

def main():
    if len(sys.argv) != 2:
        print("Uso: python -m tools.debug_cdc <xml>")
        sys.exit(1)
    
    xml_path = Path(sys.argv[1])
    tree = etree.parse(xml_path)
    ns = {"s": "http://ekuatia.set.gov.py/sifen/xsd"}
    
    # El XML usa namespace default, no prefijo
    # Los campos están dentro de gTimb y gEmis
    de = tree.find(".//{http://ekuatia.set.gov.py/sifen/xsd}DE")
    
    cdc_xml = de.get("Id")
    
    # Extraer gTimb para algunos campos
    gTimb = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gTimb")
    gDatGralOpe = de.find("{http://ekuatia.set.gov.py/sifen/xsd}gDatGralOpe")
    
    # Validar que se encontraron los grupos
    if gTimb is None or gDatGralOpe is None:
        print("ERROR: No se encontraron gTimb o gDatGralOpe")
        print(f"  gTimb: {gTimb}")
        print(f"  gDatGralOpe: {gDatGralOpe}")
        sys.exit(1)
    
    # gEmis está dentro de gDatGralOpe
    gEmis = gDatGralOpe.find("{http://ekuatia.set.gov.py/sifen/xsd}gEmis")
    
    # Extraer campos
    ruc = gEmis.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dRucEm")
    dv = gEmis.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dDVEmi")
    tim = gTimb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dNumTim")
    est = gTimb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dEst")
    pun = gTimb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dPunExp")
    num = gTimb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dNumDoc")
    tip = gTimb.findtext("{http://ekuatia.set.gov.py/sifen/xsd}iTiDE")
    fec = gDatGralOpe.findtext("{http://ekuatia.set.gov.py/sifen/xsd}dFeEmiDE")
    
    # Validar que se encontraron todos los campos
    if not all([ruc, dv, tim, est, pun, num, tip, fec]):
        print("ERROR: No se encontraron todos los campos necesarios")
        print(f"  ruc: {ruc}")
        print(f"  dv: {dv}")
        print(f"  tim: {tim}")
        print(f"  est: {est}")
        print(f"  pun: {pun}")
        print(f"  num: {num}")
        print(f"  tip: {tip}")
        print(f"  fec: {fec}")
        sys.exit(1)
    
    # Normalizar fecha
    fec8 = "".join(c for c in fec if c.isdigit())[:8]
    
    print(f"CDC en XML: {cdc_xml}")
    print(f"RUC: {ruc}-{dv}")
    print(f"Timbrado: {tim}")
    print(f"Establecimiento: {est}")
    print(f"Punto Expedición: {pun}")
    print(f"Número Doc: {num}")
    print(f"Tipo Doc: {tip}")
    print(f"Fecha: {fec} -> {fec8}")
    
    # Calcular CDC
    cdc_calc = generate_cdc(
        ruc=f"{ruc}-{dv}",
        timbrado=tim,
        establecimiento=est,
        punto_expedicion=pun,
        numero_documento=num,
        tipo_documento=tip,
        fecha=fec8,
        monto="100000"
    )
    print(f"CDC calculado: {cdc_calc}")
    print(f"Coinciden: {'OK' if cdc_xml == cdc_calc else 'FAIL'}")

if __name__ == "__main__":
    main()
