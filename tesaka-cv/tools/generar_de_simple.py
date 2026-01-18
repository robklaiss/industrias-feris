#!/usr/bin/env python3
"""
Generador de Documentos Electrónicos (DE) simplificados para SIFEN.
Basado en el formato exitoso de diciembre 2025 (112 tags).

Uso:
    python -m tools.generar_de_simple --timbrado 18578288 --est 029 --pun 010 --doc 18
"""

import argparse
import os
import random
import string
from datetime import datetime
from pathlib import Path

SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

def generar_codigo_seguridad():
    """Genera código de seguridad de 9 dígitos."""
    return ''.join(random.choices(string.digits, k=9))

def calcular_dv(cdc_sin_dv: str) -> int:
    """Calcula el dígito verificador del CDC usando módulo 11."""
    # Algoritmo SIFEN (Roshka): pesos de 2 a 11
    base_max = 11
    k = 2
    total = 0
    
    # Recorrer desde la derecha (último dígito primero)
    for digit in reversed(cdc_sin_dv):
        if k > base_max:
            k = 2
        total += int(digit) * k
        k += 1
    
    # Calcular DV (algoritmo Roshka)
    remainder = total % 11
    if remainder > 1:
        dv = 11 - remainder
    else:
        dv = 0
    
    return dv

def generar_cdc(ruc: str, dv_emisor: str, establecimiento: str, punto_exp: str, 
                num_doc: str, tipo_de: int, fecha: datetime, tipo_emision: int,
                codigo_seguridad: str) -> str:
    """
    Genera el CDC (Código de Control) del documento electrónico.
    Formato: 44 caracteres + 1 dígito verificador = 45 caracteres
    """
    # Formato del CDC según manual técnico SIFEN
    # iTiDE (2) + dRucEm (8) + dDVEmi (1) + dEst (3) + dPunExp (3) + dNumDoc (7) + 
    # iTipCont (1) + dFecEmiDE (8 AAAAMMDD) + iTipEmi (1) + dCodSeg (9) + dDVId (1)
    
    fecha_str = fecha.strftime("%Y%m%d")
    
    cdc_sin_dv = (
        f"{tipo_de:02d}"  # iTiDE - 2 dígitos
        f"{ruc:>08}"  # dRucEm - 8 dígitos
        f"{dv_emisor}"  # dDVEmi - 1 dígito
        f"{establecimiento:>03}"  # dEst - 3 dígitos
        f"{punto_exp:>03}"  # dPunExp - 3 dígitos
        f"{num_doc:>07}"  # dNumDoc - 7 dígitos
        f"{tipo_emision}"  # iTipCont - 1 dígito
        f"{fecha_str}"  # dFecEmiDE - 8 dígitos (AAAAMMDD)
        f"{tipo_emision}"  # iTipEmi - 1 dígito
        f"{codigo_seguridad:>09}"  # dCodSeg - 9 dígitos
    )
    
    dv = calcular_dv(cdc_sin_dv)
    return cdc_sin_dv + str(dv)

def generar_de_xml(
    timbrado: str,
    establecimiento: str,
    punto_expedicion: str,
    numero_documento: str,
    ruc_emisor: str = "4554737",
    dv_emisor: str = "8",
    nombre_emisor: str = "Industrias Feris",
    ruc_receptor: str = "4554737",
    dv_receptor: str = "8",
    nombre_receptor: str = "Cliente de Prueba",
    monto_total: int = 100000,
    fecha_emision: datetime = None,
) -> str:
    """
    Genera un XML de DE simplificado compatible con SIFEN.
    Usa la estructura exacta del formato exitoso de diciembre 2025.
    """
    if fecha_emision is None:
        fecha_emision = datetime.now()
    
    fecha_str = fecha_emision.strftime("%Y-%m-%d")
    hora_str = fecha_emision.strftime("%H:%M:%S")
    fecha_firma = fecha_emision.strftime("%Y-%m-%dT%H:%M:%S")
    
    codigo_seguridad = generar_codigo_seguridad()
    
    # Calcular CDC
    cdc = generar_cdc(
        ruc=ruc_emisor,
        dv_emisor=dv_emisor,
        establecimiento=establecimiento,
        punto_exp=punto_expedicion,
        num_doc=numero_documento,
        tipo_de=1,  # Factura electrónica
        fecha=fecha_emision,
        tipo_emision=1,  # Normal
        codigo_seguridad=codigo_seguridad
    )
    
    dv_id = calcular_dv(cdc[:-1])
    
    # Calcular IVA 10%
    base_gravada = int(monto_total / 1.1)
    iva_10 = monto_total - base_gravada
    
    xml = f'''<?xml version='1.0' encoding='utf-8'?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd" Id="rDE{cdc}">
<DE Id="{cdc}">
    <dDVId>{dv_id}</dDVId>
    <dFecFirma>{fecha_firma}</dFecFirma>
    <dSisFact>1</dSisFact>
    <gOpeDE>
        <iTipEmi>1</iTipEmi>
        <dDesTipEmi>Normal</dDesTipEmi>
        <dCodSeg>{codigo_seguridad}</dCodSeg>
    </gOpeDE>
    <gTimb>
        <iTiDE>1</iTiDE>
        <dNumTim>{timbrado}</dNumTim>
        <dEst>{establecimiento}</dEst>
        <dPunExp>{punto_expedicion}</dPunExp>
        <dNumDoc>{numero_documento}</dNumDoc>
        <dSerieNum>AA</dSerieNum>
    </gTimb>
    <gDatGralOpe>
        <iTipEmi>1</iTipEmi>
        <dDesTipEmi>Normal</dDesTipEmi>
        <dFeEmiDE>{fecha_str}</dFeEmiDE>
        <dHoEmiDE>{hora_str}</dHoEmiDE>
        <iCondOpe>1</iCondOpe>
        <dDesCondOpe>Contado</dDesCondOpe>
        <iTipoCont>1</iTipoCont>
        <dDesTipoCont>Efectivo</dDesTipoCont>
        <iCondCred>1</iCondCred>
        <dPlazoCre>0</dPlazoCre>
        <dCuotas>0</dCuotas>
        <gEmis>
            <dRucEm>{ruc_emisor}</dRucEm>
            <dDVEmi>{dv_emisor}</dDVEmi>
            <dNomEmi>{nombre_emisor}</dNomEmi>
            <dDirEmi>Lambare</dDirEmi>
            <dNumCasEmi>0</dNumCasEmi>
            <cDepEmi>12</cDepEmi>
            <dDesDepEmi>CENTRAL</dDesDepEmi>
            <cCiuEmi>6106</cCiuEmi>
            <dDesCiuEmi>LAMBARE</dDesCiuEmi>
            <dTelEmi>021123456</dTelEmi>
            <dEmailEmi>info@empresa.com.py</dEmailEmi>
            <gActEco>
                <cActEco>471100</cActEco>
                <dDesActEco>Venta al por menor</dDesActEco>
            </gActEco>
        </gEmis>
        <gDatRec>
            <iNatRec>1</iNatRec>
            <iTiOpe>1</iTiOpe>
            <cPaisRec>PRY</cPaisRec>
            <dDesPaisRe>Paraguay</dDesPaisRe>
            <dRucRec>{ruc_receptor}</dRucRec>
            <dDVRec>{dv_receptor}</dDVRec>
            <dNomRec>{nombre_receptor}</dNomRec>
            <dDirRec>Asuncion</dDirRec>
            <dNumCasRec>100</dNumCasRec>
            <cDepRec>1</cDepRec>
            <dDesDepRec>CAPITAL</dDesDepRec>
            <cCiuRec>1</cCiuRec>
            <dDesCiuRec>Asuncion</dDesCiuRec>
        </gDatRec>
    </gDatGralOpe>
    <gDtipDE>
        <gCamItem>
            <dCodInt>001</dCodInt>
            <dDesProSer>Producto de prueba</dDesProSer>
            <cUniMed>77</cUniMed>
            <dDesUniMed>UNI</dDesUniMed>
            <dCantProSer>1.00</dCantProSer>
            <gValorItem>
                <dPUniProSer>{base_gravada}</dPUniProSer>
                <dTotBruOpeItem>{base_gravada}</dTotBruOpeItem>
                <gValorRestaItem>
                    <dTotOpeItem>{monto_total}</dTotOpeItem>
                </gValorRestaItem>
            </gValorItem>
        </gCamItem>
    </gDtipDE>
    <gTotSub>
        <dSubExe>0</dSubExe>
        <dSubExo>0</dSubExo>
        <dSub5>0</dSub5>
        <dSub10>{base_gravada}</dSub10>
        <dTotOpe>{base_gravada}</dTotOpe>
        <dTotDesc>0</dTotDesc>
        <dTotDescGlotem>0</dTotDescGlotem>
        <dTotAntItem>0</dTotAntItem>
        <dTotAnt>0</dTotAnt>
        <dPorcDescTotal>0</dPorcDescTotal>
        <dDescTotal>0</dDescTotal>
        <dAnticipo>0</dAnticipo>
        <dRedon>0</dRedon>
        <dTotGralOpe>{monto_total}</dTotGralOpe>
        <dIVA5>0</dIVA5>
        <dIVA10>{iva_10}</dIVA10>
        <dLiqTotIVA5>0</dLiqTotIVA5>
        <dLiqTotIVA10>{iva_10}</dLiqTotIVA10>
        <dIVAComi>0</dIVAComi>
        <dTotIVA>{iva_10}</dTotIVA>
        <dBaseGrav5>0</dBaseGrav5>
        <dBaseGrav10>{base_gravada}</dBaseGrav10>
        <dTBasGraIVA>{base_gravada}</dTBasGraIVA>
        <dTotalGs>{monto_total}</dTotalGs>
    </gTotSub>
</DE>
</rDE>'''
    
    return xml, cdc


def main():
    parser = argparse.ArgumentParser(description="Genera DE simplificado para SIFEN")
    parser.add_argument("--timbrado", required=True, help="Número de timbrado")
    parser.add_argument("--est", required=True, help="Establecimiento (3 dígitos)")
    parser.add_argument("--pun", required=True, help="Punto de expedición (3 dígitos)")
    parser.add_argument("--doc", required=True, help="Número de documento (7 dígitos)")
    parser.add_argument("--monto", type=int, default=110000, help="Monto total en Gs (default: 110000)")
    parser.add_argument("--output", "-o", help="Archivo de salida (default: artifacts/de_simple_CDC.xml)")
    
    args = parser.parse_args()
    
    xml, cdc = generar_de_xml(
        timbrado=args.timbrado,
        establecimiento=args.est.zfill(3),
        punto_expedicion=args.pun.zfill(3),
        numero_documento=args.doc.zfill(7),
        monto_total=args.monto,
    )
    
    # Guardar archivo
    output_path = args.output or f"artifacts/de_simple_{cdc}.xml"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml)
    
    print(f"✅ DE generado: {output_path}")
    print(f"   CDC: {cdc}")
    print(f"   Timbrado: {args.timbrado}")
    print(f"   Documento: {args.est}-{args.pun}-{args.doc}")
    print(f"   Monto: {args.monto:,} Gs")
    print()
    print("Para enviar a SIFEN:")
    print(f'  .venv/bin/python -m tools.send_sirecepde --env test --xml "{output_path}" --dump-http')


if __name__ == "__main__":
    main()
