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
    receptor_ruc: Optional[str] = None,
    receptor_dv: Optional[str] = None,
    receptor_nombre: Optional[str] = None,
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
        ruc_str = os.getenv("SIFEN_EMISOR_RUC") or os.getenv("SIFEN_TEST_RUC") or "80012345"
    
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
    ruc_digits = ''.join(c for c in ruc_num if c.isdigit())
    if not ruc_digits:
        raise ValueError(f"RUC debe contener al menos un dígito. Valor recibido: '{ruc_num}'")
    # En el XML (dRucEm) NO queremos cero a la izquierda. (Ej: 4554737, no 04554737)
    ruc_emisor = ruc_digits.lstrip('0') or '0'
    # Para CDC: normalizar a 8 dígitos (left-pad) como veníamos haciendo, pero SOLO para el CDC
    ruc_cdc = ruc_digits.zfill(8)[-8:]
    
    # GUARDRAIL: Asegurar que no hay cero a la izquierda en dRucEm
    if ruc_emisor.startswith('0') and len(ruc_emisor) > 1:
        raise ValueError(f"dRucEm no puede tener cero a la izquierda. RUC original: {ruc_str}, dRucEm: {ruc_emisor}")
    
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
    # Según XSD v150, dCodSeg debe ser un entero de 9 dígitos (tiCodSe)
    # El CSC puede venir alfanumérico, pero solo se usan los dígitos
    if csc:
        # Extraer solo dígitos del CSC (puede contener letras como A62e367A...)
        csc_digits = ''.join(c for c in str(csc) if c.isdigit())
        if csc_digits:
            # Usar hasta 9 dígitos, rellenando con ceros si es necesario
            cod_seg = csc_digits[:9].zfill(9)
        else:
            # Si no hay dígitos, usar valor por defecto
            cod_seg = "123456789"
            print(f"⚠️  Advertencia: CSC '{csc}' no contiene dígitos. Usando valor por defecto.")
    else:
        # Si no se proporciona CSC, usar valor por defecto
        cod_seg = "123456789"
        print("⚠️  Advertencia: No se proporcionó CSC. Usando valor por defecto 123456789.")
    
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
    
    # Receptor (parámetros + env vars como fallback)
    rec_ruc_env = (os.getenv("SIFEN_REC_RUC") or os.getenv("SIFEN_RECEPTOR_RUC") or "80012345")
    rec_dv_env = (os.getenv("SIFEN_REC_DV") or os.getenv("SIFEN_RECEPTOR_DV") or "7")
    rec_nombre_env = (os.getenv("SIFEN_REC_NOMBRE") or os.getenv("SIFEN_RECEPTOR_NOMBRE") or "Cliente de Prueba")

    rec_ruc_raw = (receptor_ruc or rec_ruc_env).strip()
    rec_dv_in = (receptor_dv or "").strip()
    rec_nombre = (receptor_nombre or rec_nombre_env).strip() or "Cliente de Prueba"

    # Permitir formato "RUC-DV" (ej: "7524653-8")
    if "-" in rec_ruc_raw:
        a, b = rec_ruc_raw.split("-", 1)
        rec_ruc_raw = a.strip()
        if not rec_dv_in:
            rec_dv_in = b.strip()

    # Guardrail + normalización: receptor_ruc solo puede contener dígitos y separadores simples
    rec_ruc_digits = ""
    for ch in rec_ruc_raw:
        if ch.isdigit():
            rec_ruc_digits += ch
        elif ch in " .-_/":
            # Separadores permitidos, se ignoran
            continue
        else:
            raise ValueError(
                f"receptor_ruc contiene carácter inválido {ch!r}. Solo se permiten dígitos y separadores simples."
            )

    if not rec_ruc_digits:
        raise ValueError(f"receptor_ruc debe contener al menos un dígito. Valor recibido: {rec_ruc_raw!r}")

    # Quitar ceros a la izquierda para dRucRec
    d_ruc_rec = rec_ruc_digits.lstrip("0") or "0"

    # Normalizar DV receptor
    rec_dv_digits = "".join(c for c in rec_dv_in if c.isdigit())
    if rec_dv_digits:
        if len(rec_dv_digits) != 1:
            raise ValueError(
                f"DV del receptor debe ser exactamente 1 dígito. Valor recibido: {rec_dv_in!r}"
            )
        d_dv_rec = rec_dv_digits
    else:
        env_dv_digits = "".join(c for c in rec_dv_env if c.isdigit())
        d_dv_rec = env_dv_digits[:1] if env_dv_digits else "7"

    d_nom_rec = rec_nombre

    # Normalizar campos numéricos para CDC
    establecimiento_norm = str(establecimiento).zfill(3)[-3:]  # 3 dígitos
    punto_expedicion_norm = str(punto_expedicion).zfill(3)[-3:]  # 3 dígitos
    numero_documento_norm = str(numero_documento).zfill(7)[-7:]  # 7 dígitos
    tipo_documento_norm = str(tipo_documento).zfill(2)[-2:]  # 2 dígitos para CDC
    
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
        <iTiDE>{tipo_documento_norm}</iTiDE>
        <dDesTiDE>Factura electrónica</dDesTiDE>
        <dNumTim>{timbrado_clean}</dNumTim>
        <dEst>{establecimiento_norm}</dEst>
        <dPunExp>{punto_expedicion_norm}</dPunExp>
        <dNumDoc>{numero_documento_norm}</dNumDoc>
        <dFeIniT>{fecha}</dFeIniT>
    </gTimb>
    <gDatGralOpe>
        <dFeEmiDE>{fecha_emision}</dFeEmiDE>
        <gEmis>
            <dRucEm>{ruc_emisor}</dRucEm>
            <dDVEmi>{dv_ruc}</dDVEmi>
            <iTipCont>1</iTipCont>
            <dNomEmi>{d_nom_emi}</dNomEmi>
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
            <dDesPaisRec>Paraguay</dDesPaisRec>
            <dRucRec>{d_ruc_rec}</dRucRec>
            <dDVRec>{d_dv_rec}</dDVRec>
            <dNomRec>{d_nom_rec}</dNomRec>
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
    
    # Obtener CSC desde config si no se proporciona por args
    if not args.csc:
        try:
            config = get_sifen_config(env=args.env)
            # Usar config.csc que ya maneja test/prod correctamente
            csc = config.csc if config.csc else None
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

