"""
Generador de XML para documentos electrónicos SIFEN v150

Estructura correcta según XSD v150
"""
from typing import Optional
from datetime import datetime
import hashlib
import base64


def generate_cdc(ruc: str, timbrado: str, establecimiento: str, punto_expedicion: str, 
                 numero_documento: str, tipo_documento: str, fecha: str, monto: str) -> str:
    """
    Genera un CDC (Código de Control) básico para pruebas
    
    Formato requerido: [0-9]{2}([0-9]{7}[0-9A-D])[0-9]{34}
    Total: 44 caracteres
    
    NOTA: En producción, el CDC debe generarse según algoritmo oficial de SIFEN.
    Este es solo para pruebas.
    """
    # Asegurar que timbrado tenga al menos 7 dígitos
    timbrado_clean = (timbrado or "").zfill(8)[:7]
    if not timbrado_clean or not timbrado_clean.isdigit():
        timbrado_clean = "1234567"
    
    # Para pruebas: generar CDC con formato válido
    # 2 dígitos iniciales
    cdc = "01"
    # 7 dígitos + 1 dígito hexadecimal (A-D) = 8 caracteres
    cdc += f"{int(timbrado_clean):07d}A"
    # 34 dígitos más (rellenar con números hasta 44 caracteres)
    # Usar hash para generar números pseudoaleatorios
    data = f"{ruc}{timbrado}{establecimiento}{punto_expedicion}{numero_documento}{fecha}"
    hash_hex = hashlib.md5(data.encode()).hexdigest()
    # Tomar solo dígitos del hash y completar hasta 34
    digits = ''.join(c for c in hash_hex if c.isdigit())
    if len(digits) < 34:
        digits = (digits * 10)[:34]
    else:
        digits = digits[:34]
    cdc += digits
    
    return cdc[:44]


def calculate_digit_verifier(cdc: str) -> str:
    """
    Calcula el dígito verificador del CDC
    
    NOTA: Algoritmo simplificado para pruebas
    """
    # Algoritmo simplificado - NO usar en producción
    suma = sum(ord(c) for c in cdc)
    return str(suma % 10)


def create_rde_xml_v150(
    ruc: str = "80012345",
    timbrado: str = "12345678",
    establecimiento: str = "001",
    punto_expedicion: str = "001",
    numero_documento: str = "0000001",
    tipo_documento: str = "1",
    fecha: Optional[str] = None,
    hora: Optional[str] = None,
    csc: Optional[str] = None,
) -> str:
    """
    Crea un XML rDE según estructura XSD v150
    
    Args:
        ruc: RUC del contribuyente emisor
        timbrado: Número de timbrado
        establecimiento: Código de establecimiento
        punto_expedicion: Código de punto de expedición
        numero_documento: Número de documento
        tipo_documento: Tipo de documento (1=Factura)
        fecha: Fecha de emisión (YYYY-MM-DD)
        hora: Hora de emisión (HH:MM:SS)
        csc: Código de Seguridad del Contribuyente
        
    Returns:
        XML como string
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
    
    # Generar CDC (simplificado para pruebas)
    cdc = generate_cdc(ruc, timbrado, establecimiento, punto_expedicion, 
                      numero_documento, tipo_documento, fecha.replace("-", ""), monto)
    
    # Calcular dígito verificador (dv del CDC)
    # El dDVId debe ser un dígito numérico [0-9], no la letra hexadecimal
    # Para pruebas: usar el último dígito numérico del CDC
    digits_in_cdc = ''.join(c for c in cdc if c.isdigit())
    dv_id = digits_in_cdc[-1] if digits_in_cdc else "0"
    
    # Código de seguridad (CSC) - debe ser entero de 9 dígitos según tiCodSe
    # Para pruebas: generar número de 9 dígitos
    if csc:
        # Asegurar que sea numérico de 9 dígitos
        cod_seg_digits = ''.join(c for c in str(csc) if c.isdigit())
        cod_seg = cod_seg_digits[:9].zfill(9) if cod_seg_digits else "123456789"
    else:
        cod_seg = "123456789"
    
    # RUC debe ser máximo 8 dígitos
    ruc_str = str(ruc or "")
    if not ruc_str or not ruc_str.strip():
        ruc_str = "80012345"
    ruc_clean = ruc_str[:8].zfill(8) if len(ruc_str) < 8 else ruc_str[:8]
    
    # Calcular DV del RUC (simplificado)
    # Asegurar que sea un dígito válido
    dv_ruc = "0"
    try:
        ruc_digits = ''.join(c for c in ruc_clean if c.isdigit())
        if ruc_digits:
            # Algoritmo simplificado para DV
            dv_ruc = str(sum(int(d) for d in ruc_digits) % 10)
    except:
        dv_ruc = "0"
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
    <dVerFor>150</dVerFor>
    <DE Id="{cdc}">
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
            <dNumTim>{timbrado}</dNumTim>
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
                <cUniMed>99</cUniMed>
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
            <dTotalGs>100000</dTotalGs>
        </gTotSub>
    </DE>
    <ds:Signature>
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
</rDE>"""
    
    return xml

