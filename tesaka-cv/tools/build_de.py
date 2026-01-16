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
import os
from pathlib import Path
from datetime import datetime
from typing import Optional

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.sifen_client.xml_generator_v150 import generate_cdc, calculate_digit_verifier
from app.sifen_client.config import get_sifen_config
from app.sifen_client.qr_generator import QRGenerator


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
    env: str = "test",
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
    
    # Parsear RUC: puede venir como "RUC-DV" (ej: "4554737-8") o solo "RUC" (ej: "80012345")
    ruc_str = str(ruc or "").strip()
    if not ruc_str:
        ruc_str = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC") or "4554737"
    
    # Separar RUC y DV si viene en formato RUC-DV
    if "-" in ruc_str:
        ruc_num, dv_ruc = ruc_str.split("-", 1)
        ruc_num = ruc_num.strip()
        dv_ruc = dv_ruc.strip()
        # Validar que DV sea un dígito
        if not dv_ruc.isdigit() or len(dv_ruc) != 1:
            raise ValueError(f"DV del RUC debe ser exactamente 1 dígito. Valor recibido: '{dv_ruc}'")
    else:
        # Si no viene con DV, usar el RUC tal cual y calcular DV
        ruc_num = ruc_str.strip()
        # Calcular DV del RUC
        try:
            ruc_digits = ''.join(c for c in ruc_num if c.isdigit())
            if ruc_digits:
                dv_ruc = str(sum(int(d) for d in ruc_digits) % 10)
            else:
                dv_ruc = "0"
        except:
            dv_ruc = "0"
    
    # Limpiar RUC: solo dígitos
    # IMPORTANTE:
    # - Para el CDC, SIFEN requiere RUC base de 8 dígitos (zero-left)
    # - Para el XML (dRucEm), se debe emitir el RUC numérico real, sin padding
    ruc_digits = ''.join(c for c in ruc_num if c.isdigit())
    if not ruc_digits:
        raise ValueError(f"RUC debe contener al menos un dígito. Valor recibido: '{ruc_num}'")

    ruc_xml = ruc_digits.lstrip("0") or "0"
    ruc_cdc = ruc_digits.zfill(8)[-8:]  # 8 dígitos para CDC
    
    # Monto para CDC (simplificado)
    monto = "100000"
    
    # Normalizar campos para CDC antes de generar
    establecimiento_cdc = str(establecimiento).zfill(3)[-3:]
    punto_expedicion_cdc = str(punto_expedicion).zfill(3)[-3:]
    numero_documento_cdc = str(numero_documento).zfill(7)[-7:]
    tipo_documento_cdc = str(tipo_documento).zfill(2)[-2:]
    
    # Generar CDC (usar campos normalizados)
    cdc = generate_cdc(ruc_cdc, timbrado, establecimiento_cdc, punto_expedicion_cdc, 
                      numero_documento_cdc, tipo_documento_cdc, fecha.replace("-", ""), monto)
    
    # Validación defensiva: asegurar que el CDC sea válido antes de usarlo
    from app.sifen_client.cdc_utils import validate_cdc, fix_cdc
    
    # Convertir a string si no lo es
    cdc = str(cdc).strip()
    
    # Validar longitud y formato
    if len(cdc) != 44:
        raise ValueError(
            f"CDC generado tiene longitud inválida: {len(cdc)} (esperado: 44). "
            f"CDC recibido: {cdc!r}"
        )
    
    # Validar que sea solo dígitos
    if not cdc.isdigit():
        raise ValueError(
            f"CDC generado contiene caracteres no numéricos: {cdc!r}. "
            f"El CDC debe ser exactamente 44 dígitos (0-9)."
        )
    
    # Validar DV
    es_valido, dv_orig, dv_calc = validate_cdc(cdc)
    if not es_valido:
        # Corregir automáticamente si el DV es incorrecto
        cdc = fix_cdc(cdc)
        # Re-validar después de corregir
        es_valido, _, _ = validate_cdc(cdc)
        if not es_valido:
            raise ValueError(
                f"CDC generado tiene DV inválido y no pudo corregirse. "
                f"CDC: {cdc!r}"
            )
    
    # Calcular dígito verificador (dv del CDC)
    # El dDVId es el último dígito del CDC (que ya está validado)
    dv_id = cdc[-1]
    
    # Código de seguridad (CSC)
    # IMPORTANTE: Debe coincidir con SIFEN_CODSEG usado en generate_cdc()
    if csc:
        cod_seg_digits = ''.join(c for c in str(csc) if c.isdigit())
        cod_seg = cod_seg_digits[:9].zfill(9) if cod_seg_digits else os.getenv("SIFEN_CODSEG", "000000001").strip()
    else:
        # Usar el mismo valor que generate_cdc() para consistencia
        cod_seg = os.getenv("SIFEN_CODSEG", "000000001").strip()
    
    # Timbrado debe tener al menos 7 dígitos
    timbrado_str = str(timbrado or "")
    if not timbrado_str or not timbrado_str.strip():
        timbrado_str = "12345678"
    timbrado_clean = timbrado_str.strip()
    
    # Determinar nombre del emisor según ambiente
    if env == "test":
        d_nom_emi = "DE generado en ambiente de prueba - sin valor comercial ni fiscal"
    else:
        d_nom_emi = (os.getenv("SIFEN_EMISOR_NOMBRE") or "Emisor").strip()
        if not d_nom_emi:
            d_nom_emi = "Emisor"
    
    # Normalizar campos numéricos para CDC
    establecimiento_norm = str(establecimiento).zfill(3)[-3:]  # 3 dígitos
    punto_expedicion_norm = str(punto_expedicion).zfill(3)[-3:]  # 3 dígitos
    numero_documento_norm = str(numero_documento).zfill(7)[-7:]  # 7 dígitos
    tipo_documento_norm = str(tipo_documento).zfill(2)[-2:]  # 2 dígitos para CDC
    
    # Generar QR code
    try:
        qr_csc = csc or os.getenv("SIFEN_CSC") or "ABCD0000000000000000000000000000"
        qr_gen = QRGenerator(csc=qr_csc, csc_id="0001", environment="TEST")
        qr_result = qr_gen.generate(
            d_id=cdc,
            d_fe_emi=fecha.replace("-", ""),
            d_ruc_em=ruc_xml,
            d_est=establecimiento_norm,
            d_pun_exp=punto_expedicion_norm,
            d_num_doc=numero_documento_norm,
            d_tipo_doc=tipo_documento_norm,
            d_tipo_cont="1",
            d_tipo_emi="1",
            d_dv_emi=dv_ruc
        )
        qr_url = qr_result['url_xml']
    except Exception as e:
        # Fallback: generar QR básico sin CSC
        qr_url = f"https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&amp;Id={cdc}"
    
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
        <dEst>{establecimiento_norm}</dEst>
        <dPunExp>{punto_expedicion_norm}</dPunExp>
        <dNumDoc>{numero_documento_norm}</dNumDoc>
        <dFeIniT>{fecha}</dFeIniT>
    </gTimb>
    <gDatGralOpe>
        <dFeEmiDE>{fecha_emision}</dFeEmiDE>
        <gOpeCom>
            <iTipTra>1</iTipTra>
            <dDesTipTra>Venta de mercadería</dDesTipTra>
            <iTImp>1</iTImp>
            <dDesTImp>IVA</dDesTImp>
            <cMoneOpe>PYG</cMoneOpe>
            <dDesMoneOpe>Guarani</dDesMoneOpe>
        </gOpeCom>
        <gEmis>
            <dRucEm>{ruc_xml}</dRucEm>
            <dDVEmi>{dv_ruc}</dDVEmi>
            <iTipCont>1</iTipCont>
            <dNomEmi>{d_nom_emi}</dNomEmi>
            <dDirEmi>Asunción</dDirEmi>
            <dNumCas>1234</dNumCas>
            <cDepEmi>1</cDepEmi>
            <dDesDepEmi>CAPITAL</dDesDepEmi>
            <cCiuEmi>1</cCiuEmi>
            <dDesCiuEmi>ASUNCION (DISTRITO)</dDesCiuEmi>
            <dTelEmi>021123456</dTelEmi>
            <dEmailE>test@example.com</dEmailE>
            <gActEco>
                <cActEco>64990</cActEco>
                <dDesActEco>OTRAS ACTIVIDADES DE SERVICIOS FINANCIEROS, EXCEPTO LA FINANCIACIÓN DE PLANES DE SEGUROS Y DE PENSIONES</dDesActEco>
            </gActEco>
        </gEmis>
        <gDatRec>
            <iNatRec>1</iNatRec>
            <iTiOpe>1</iTiOpe>
            <cPaisRec>PRY</cPaisRec>
            <dDesPaisRe>Paraguay</dDesPaisRe>
            <iTiContRec>2</iTiContRec>
            <dRucRec>80012345</dRucRec>
            <dDVRec>0</dDVRec>
            <dNomRec>Cliente de Prueba</dNomRec>
            <dDirRec>Asunción</dDirRec>
            <dNumCasRec>5678</dNumCasRec>
            <cDepRec>1</cDepRec>
            <dDesDepRec>CAPITAL</dDesDepRec>
            <cCiuRec>1</cCiuRec>
            <dDesCiuRec>ASUNCION (DISTRITO)</dDesCiuRec>
        </gDatRec>
    </gDatGralOpe>
    <gDtipDE>
        <gCamFE>
            <iIndPres>1</iIndPres>
            <dDesIndPres>Operación presencial</dDesIndPres>
        </gCamFE>
        <gCamCond>
            <iCondOpe>1</iCondOpe>
            <dDCondOpe>Contado</dDCondOpe>
            <gPaConEIni>
                <iTiPago>1</iTiPago>
                <dDesTiPag>Efectivo</dDesTiPag>
                <dMonTiPag>100000</dMonTiPag>
                <cMoneTiPag>PYG</cMoneTiPag>
                <dDMoneTiPag>Guarani</dDMoneTiPag>
            </gPaConEIni>
        </gCamCond>
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
            <gCamIVA>
                <iAfecIVA>1</iAfecIVA>
                <dDesAfecIVA>Gravado IVA</dDesAfecIVA>
                <dPropIVA>100</dPropIVA>
                <dTasaIVA>10</dTasaIVA>
                <dBasGravIVA>90909</dBasGravIVA>
                <dLiqIVAItem>9091</dLiqIVAItem>
                <dBasExe>0</dBasExe>
            </gCamIVA>
        </gCamItem>
    </gDtipDE>
    <gTotSub>
        <dSubExe>0</dSubExe>
        <dSubExo>0</dSubExo>
        <dSub5>0</dSub5>
        <dSub10>100000</dSub10>
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
        <dIVA10>9091</dIVA10>
        <dTotIVA>9091</dTotIVA>
        <dBaseGrav5>0</dBaseGrav5>
        <dBaseGrav10>90909</dBaseGrav10>
        <dTBasGraIVA>90909</dTBasGraIVA>
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
    parser.add_argument(
        "--env",
        type=str,
        choices=["test", "prod"],
        default="test",
        help="Ambiente SIFEN (test/prod, default: test)"
    )
    
    args = parser.parse_args()
    
    # Obtener timbrado: --timbrado tiene prioridad, luego SIFEN_TIMBRADO
    timbrado = args.timbrado
    if not timbrado:
        timbrado = os.getenv("SIFEN_TIMBRADO")
        if timbrado:
            timbrado = timbrado.strip()
    
    # Validar que timbrado no esté vacío
    if not timbrado or not timbrado.strip():
        print("❌ Error: Timbrado requerido (--timbrado o SIFEN_TIMBRADO)")
        return 1
    
    # Obtener RUC desde .env si no se proporcionó
    # IMPORTANTE: pasar el RUC completo (RUC-DV si existe) a build_de_xml()
    if not args.ruc:
        # Prioridad: SIFEN_EMISOR_RUC o SIFEN_TEST_RUC (puede venir como RUC-DV)
        env_ruc = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC")
        if env_ruc:
            ruc = env_ruc.strip()
        else:
            # Fallback a config
            try:
                config = get_sifen_config(env=args.env)
                ruc = config.test_ruc if args.env == "test" else getattr(config, "prod_ruc", None)
                if not ruc:
                    ruc = "80012345"
            except:
                ruc = "80012345"
    else:
        ruc = args.ruc
    
    # Obtener CSC
    csc = args.csc
    if not csc:
        try:
            config = get_sifen_config(env=args.env)
            csc = config.test_csc if args.env == "test" else getattr(config, "prod_csc", None)
        except:
            csc = None
    
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
        csc=csc,
        env=args.env
    )
    
    # Agregar prolog XML
    xml_with_prolog = f'<?xml version="1.0" encoding="UTF-8"?>\n{de_xml}'
    
    # Escribir archivo
    output_path = Path(args.output)
    output_path.write_text(xml_with_prolog, encoding="utf-8")
    
    # Recalcular CDC desde XML y setear DE@Id para asegurar consistencia
    try:
        from tools.cdc_fix import fix_de_id_in_file
        cdc_final = fix_de_id_in_file(str(output_path))
        print(f"🔒 CDC final seteado en DE@Id: {cdc_final}")
    except SystemExit as e:
        print(f"❌ Error al corregir DE@Id: {e}")
        return 1
    except Exception as e:
        print(f"❌ Error inesperado al corregir DE@Id: {e}")
        return 1
    
    print(f"✅ DE crudo generado: {output_path}")
    print(f"   RUC: {ruc}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Validar con: python -m tools.validate_xsd --schema de {output_path}")
    
    return 0


# SMOKETEST MANUAL (comentario para referencia):
# export SIFEN_EMISOR_RUC="4554737-8"
# export SIFEN_TIMBRADO="12345678"
# unset SIFEN_TEST_RUC
# python -m tools.build_de --output artifacts/de_real.xml --env test
# grep -n "<dRucEm>\\|<dDVEmi>" artifacts/de_real.xml
# # Esperado:
# #   <dRucEm>4554737</dRucEm>
# #   <dDVEmi>8</dDVEmi>


if __name__ == "__main__":
    sys.exit(main())

