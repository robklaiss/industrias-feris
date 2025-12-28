#!/usr/bin/env python3
"""
Generador de Documento Electrónico (DE) crudo para SIFEN v150

Genera un XML DE que valida contra DE_v150.xsd (elemento DE de tipo tDE).

Uso:
    python -m tools.build_de --output de_test.xml
    python -m tools.build_de --ruc 80012345 --timbrado 12345678 --output de_test.xml
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import generate_cdc, calculate_digit_verifier
from app.sifen_client.config import get_sifen_config


def build_de_xml(
    ruc: str,
    timbrado: str,
    establecimiento: str = "001",
    punto_expedicion: str = "001",
    numero_documento: str = "0000001",
    tipo_documento: str = "1",
    fecha: Optional[str] = None,
    hora: Optional[str] = None,
    csc: Optional[str] = None,
) -> str:
    """
    Genera un XML DE crudo (elemento DE de tipo tDE) que valida contra DE_v150.xsd
    
    Args:
        ruc: RUC del contribuyente emisor (8 dígitos)
        timbrado: Número de timbrado (7+ dígitos)
        establecimiento: Código de establecimiento
        punto_expedicion: Código de punto de expedición
        numero_documento: Número de documento
        tipo_documento: Tipo de documento (1=Factura)
        fecha: Fecha de emisión (YYYY-MM-DD)
        hora: Hora de emisión (HH:MM:SS)
        csc: Código de Seguridad del Contribuyente
        
    Returns:
        XML DE crudo como string (solo el elemento DE, sin wrapper rDE)
    """
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")
    if hora is None:
        hora = datetime.now().strftime("%H:%M:%S")
    
    # Fecha formato SIFEN: YYYY-MM-DDTHH:MM:SS
    fecha_firma = f"{fecha}T{hora}"
    fecha_emision = fecha_firma
    
    # Monto para CDC (simplificado)
    monto = "100000"
    
    # Generar CDC
    cdc = generate_cdc(ruc, timbrado, establecimiento, punto_expedicion, 
                      numero_documento, tipo_documento, fecha.replace("-", ""), monto)
    
    # Calcular dígito verificador
    digits_in_cdc = ''.join(c for c in cdc if c.isdigit())
    dv_id = digits_in_cdc[-1] if digits_in_cdc else "0"
    
    # Código de seguridad (CSC)
    if csc:
        cod_seg_digits = ''.join(c for c in str(csc) if c.isdigit())
        cod_seg = cod_seg_digits[:9].zfill(9) if cod_seg_digits else "123456789"
    else:
        cod_seg = "123456789"
    
    # RUC debe ser máximo 8 dígitos
    ruc_str = str(ruc or "")
    if not ruc_str or not ruc_str.strip():
        ruc_str = "80012345"
    ruc_clean = ruc_str[:8].zfill(8) if len(ruc_str) < 8 else ruc_str[:8]
    
    # Calcular DV del RUC
    dv_ruc = "0"
    try:
        ruc_digits = ''.join(c for c in ruc_clean if c.isdigit())
        if ruc_digits:
            dv_ruc = str(sum(int(d) for d in ruc_digits) % 10)
    except:
        dv_ruc = "0"
    
    # Timbrado debe tener al menos 7 dígitos
    timbrado_str = str(timbrado or "")
    if not timbrado_str or not timbrado_str.strip():
        timbrado_str = "12345678"
    timbrado_clean = timbrado_str.strip()
    
    # Generar XML DE crudo (solo el elemento DE, sin wrapper rDE)
    # Este XML valida contra DE_v150.xsd (tipo tDE)
    xml = f"""<DE xmlns="http://ekuatia.set.gov.py/sifen/xsd" Id="{cdc}">
    <dDVId>{dv_id}</dDVId>
    <dFecFirma>{fecha_firma}</dFecFirma>
    <dSisFact>1</dSisFact>
    <gOpeDE>
        <iTipEmi>1</iTipEmi>
        <dDesTipEmi>Normal</dDesTipEmi>
        <dCodSeg>{cod_seg}</dCodSeg>
    </gOpeDE>
    <gTimb>
        <iTiDE>{tipo_documento}</iTiDE>
        <dDesTiDE>Factura electrónica</dDesTiDE>
        <dNumTim>{timbrado_clean}</dNumTim>
        <dEst>{establecimiento}</dEst>
        <dPunExp>{punto_expedicion}</dPunExp>
        <dNumDoc>{numero_documento}</dNumDoc>
        <dFeIniT>{fecha}</dFeIniT>
    </gTimb>
    <gDatGralOpe>
        <dFeEmiDE>{fecha_emision}</dFeEmiDE>
        <gEmis>
            <dRucEm>{ruc_clean}</dRucEm>
            <dDVEmi>{dv_ruc}</dDVEmi>
            <iTipCont>1</iTipCont>
            <dNomEmi>Contribuyente de Prueba S.A.</dNomEmi>
            <dDirEmi>Asunción</dDirEmi>
            <dNumCas>1234</dNumCas>
            <cDepEmi>1</cDepEmi>
            <dDesDepEmi>CAPITAL</dDesDepEmi>
            <cCiuEmi>1</cCiuEmi>
            <dDesCiuEmi>Asunción</dDesCiuEmi>
            <dTelEmi>021123456</dTelEmi>
            <dEmailE>test@example.com</dEmailE>
            <gActEco>
                <cActEco>471100</cActEco>
                <dDesActEco>Venta al por menor en comercios no especializados</dDesActEco>
            </gActEco>
        </gEmis>
        <gDatRec>
            <iNatRec>1</iNatRec>
            <iTiOpe>1</iTiOpe>
            <cPaisRec>PRY</cPaisRec>
            <dDesPaisRe>Paraguay</dDesPaisRe>
            <dRucRec>80012345</dRucRec>
            <dDVRec>7</dDVRec>
            <dNomRec>Cliente de Prueba</dNomRec>
            <dDirRec>Asunción</dDirRec>
            <dNumCasRec>5678</dNumCasRec>
            <cDepRec>1</cDepRec>
            <dDesDepRec>CAPITAL</dDesDepRec>
            <cCiuRec>1</cCiuRec>
            <dDesCiuRec>Asunción</dDesCiuRec>
        </gDatRec>
    </gDatGralOpe>
    <gDtipDE>
        <gCamItem>
            <dCodInt>001</dCodInt>
            <dDesProSer>Producto de Prueba</dDesProSer>
            <cUniMed>77</cUniMed>
            <dDesUniMed>UNI</dDesUniMed>
            <dCantProSer>1.00</dCantProSer>
            <gValorItem>
                <dPUniProSer>100000</dPUniProSer>
                <dTotBruOpeItem>100000</dTotBruOpeItem>
                <gValorRestaItem>
                    <dTotOpeItem>100000</dTotOpeItem>
                </gValorRestaItem>
            </gValorItem>
        </gCamItem>
    </gDtipDE>
    <gTotSub>
        <dSubExe>0</dSubExe>
        <dSubExo>0</dSubExo>
        <dSub5>0</dSub5>
        <dSub10>0</dSub10>
        <dTotOpe>100000</dTotOpe>
        <dTotDesc>0</dTotDesc>
        <dTotDescGlotem>0</dTotDescGlotem>
        <dTotAntItem>0</dTotAntItem>
        <dTotAnt>0</dTotAnt>
        <dPorcDescTotal>0</dPorcDescTotal>
        <dDescTotal>0</dDescTotal>
        <dAnticipo>0</dAnticipo>
        <dRedon>0</dRedon>
        <dTotGralOpe>100000</dTotGralOpe>
        <dIVA5>0</dIVA5>
        <dIVA10>0</dIVA10>
        <dLiqTotIVA5>0</dLiqTotIVA5>
        <dLiqTotIVA10>0</dLiqTotIVA10>
        <dIVAComi>0</dIVAComi>
        <dTotIVA>0</dTotIVA>
        <dBaseGrav5>0</dBaseGrav5>
        <dBaseGrav10>0</dBaseGrav10>
        <dTBasGraIVA>0</dTBasGraIVA>
        <dTotalGs>100000</dTotalGs>
    </gTotSub>
    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:SignedInfo>
            <ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
            <ds:SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
            <ds:Reference URI="">
                <ds:Transforms>
                    <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
                </ds:Transforms>
                <ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
                <ds:DigestValue>dGhpcyBpcyBhIHRlc3QgZGlnZXN0IHZhbHVl</ds:DigestValue>
            </ds:Reference>
        </ds:SignedInfo>
        <ds:SignatureValue>dGhpcyBpcyBhIHRlc3Qgc2lnbmF0dXJlIHZhbHVlIGZvciBwcnVlYmFzIG9ubHk=</ds:SignatureValue>
        <ds:KeyInfo>
            <ds:X509Data>
                <ds:X509Certificate>LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUVKakNDQWpLZ0F3SUJBZ0lEQW5CZ2txaGtpRzl3MEJBUXNGQUFEV1lqRU1NQW9HQTFVRUNoTURVbVZzWVcKd2dnRWlNQTBHQ1NxR1NJYjM=</ds:X509Certificate>
            </ds:X509Data>
        </ds:KeyInfo>
    </ds:Signature>
    <gCamFuFD>
        <dCarQR>TESTQRCODE12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890</dCarQR>
    </gCamFuFD>
</DE>"""
    
    return xml


def main():
    parser = argparse.ArgumentParser(
        description="Genera un XML DE crudo para SIFEN v150"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("de_test.xml"),
        help="Archivo de salida (default: de_test.xml)"
    )
    parser.add_argument(
        "--ruc",
        type=str,
        help="RUC del contribuyente (default: desde .env o 80012345)"
    )
    parser.add_argument(
        "--timbrado",
        type=str,
        help="Número de timbrado (default: desde .env o 12345678)"
    )
    parser.add_argument(
        "--csc",
        type=str,
        help="Código de Seguridad del Contribuyente (opcional)"
    )
    parser.add_argument(
        "--establecimiento",
        type=str,
        default="001",
        help="Código de establecimiento (default: 001)"
    )
    parser.add_argument(
        "--punto-expedicion",
        dest="punto_expedicion",
        type=str,
        default="001",
        help="Código de punto de expedición (default: 001)"
    )
    parser.add_argument(
        "--numero-documento",
        type=str,
        default="0000001",
        help="Número de documento (default: 0000001)"
    )
    parser.add_argument(
        "--tipo-documento",
        type=str,
        default="1",
        help="Tipo de documento (1=Factura, default: 1)"
    )
    parser.add_argument(
        "--fecha",
        type=str,
        help="Fecha de emisión (YYYY-MM-DD, default: hoy)"
    )
    parser.add_argument(
        "--hora",
        type=str,
        help="Hora de emisión (HH:MM:SS, default: ahora)"
    )
    
    args = parser.parse_args()
    
    # Obtener valores desde .env si no se proporcionaron
    if not args.ruc or not args.timbrado:
        try:
            config = get_sifen_config(env="test")
            ruc = args.ruc or config.test_ruc or "80012345"
            timbrado = args.timbrado or config.test_timbrado or "12345678"
            csc = args.csc or config.test_csc
        except:
            ruc = args.ruc or "80012345"
            timbrado = args.timbrado or "12345678"
            csc = args.csc
    else:
        ruc = args.ruc
        timbrado = args.timbrado
        csc = args.csc
    
    # Generar XML DE crudo
    de_xml = build_de_xml(
        ruc=ruc,
        timbrado=timbrado,
        establecimiento=args.establecimiento,
        punto_expedicion=args.punto_expedicion,
        numero_documento=args.numero_documento,
        tipo_documento=args.tipo_documento,
        fecha=args.fecha,
        hora=args.hora,
        csc=csc
    )
    
    # Agregar prolog XML
    xml_with_prolog = f'<?xml version="1.0" encoding="UTF-8"?>\n{de_xml}'
    
    # Escribir archivo
    output_path = Path(args.output)
    output_path.write_text(xml_with_prolog, encoding="utf-8")
    
    print(f"✅ DE crudo generado: {output_path}")
    print(f"   RUC: {ruc}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Validar con: python -m tools.validate_xsd --schema de {output_path}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

