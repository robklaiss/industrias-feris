#!/usr/bin/env python3
"""Crear un payload nuevo sin doble wrapper"""

import os
os.environ["SIFEN_EMISOR_RUC"] = "4554737-8"

from pathlib import Path
from tools.send_sirecepde import build_and_sign_lote_from_xml
from app.sifen_client.config import SifenConfig
from app.sifen_client.soap_client import SoapClient
import base64
import zipfile
import io

# Cargar certificado
config = SifenConfig()
cert_path = config.cert_path
cert_password = config.cert_password

# XML de prueba simple
test_xml = """<?xml version="1.0" encoding="UTF-8"?>
<DE Id="01800455473701001000000120260118113224123456789">
  <dDVId>1</dDVId>
  <dFecFirma>2026-01-18T11:32:24.159953</dFecFirma>
  <dSisFact>1</dSisFact>
  <gOpeDE>
    <iTipEmi>1</iTipEmi>
    <dDesTipEmi>Normal</dDesTipEmi>
    <dCodSeg>000000023</dCodSeg>
    <dInfoEmi>1</dInfoEmi>
    <dInfoFisc>Información de interés del Fisco respecto al DE</dInfoFisc>
  </gOpeDE>
  <gTimb>
    <iTiDE>1</iTiDE>
    <dDesTiDE>Factura electrónica</dDesTiDE>
    <dNumTim>12345678</dNumTim>
    <dEst>001</dEst>
    <dPunExp>001</dPunExp>
    <dNumDoc>1000050</dNumDoc>
    <dSerieNum>AB</dSerieNum>
    <dFeIniT>2019-08-13</dFeIniT>
  </gTimb>
  <gDatGralOpe>
    <dFeEmiDE>2026-01-18T11:32:24.159975</dFeEmiDE>
    <gOpeCom>
      <iTipTra>1</iTipTra>
      <dDesTipTra>Venta de mercadería</dDesTipTra>
      <iTImp>1</iTImp>
      <dDesTImp>IVA</dDesTImp>
      <cMoneOpe>PYG</cMoneOpe>
      <dDesMoneOpe>Guarani</dDesMoneOpe>
    </gOpeCom>
    <gEmis>
      <dRucEm>4554737</dRucEm>
      <dDVEmi>8</dDVEmi>
      <iTipCont>2</iTipCont>
      <cTipReg>3</cTipReg>
      <dNomEmi>Industrias Feris S.A.</dNomEmi>
      <dDirEmi>CALLE 1 CASI CALLE 2</dDirEmi>
      <dNumCas>0</dNumCas>
      <cDepEmi>1</cDepEmi>
      <dDesDepEmi>CAPITAL</dDesDepEmi>
      <cCiuEmi>1</cCiuEmi>
      <dDesCiuEmi>ASUNCION (DISTRITO)</dDesCiuEmi>
      <dTelEmi>012123456</dTelEmi>
      <dEmailE>correo@correo.com</dEmailE>
      <gActEco>
        <cActEco>46510</cActEco>
        <dDesActEco>COMERCIO AL POR MAYOR DE EQUIPOS INFORMÁTICOS Y SOFTWARE</dDesActEco>
      </gActEco>
    </gEmis>
    <gDatRec>
      <iNatRec>1</iNatRec>
      <iTiOpe>1</iTiOpe>
      <cPaisRec>PRY</cPaisRec>
      <dDesPaisRe>Paraguay</dDesPaisRe>
      <iTiContRec>2</iTiContRec>
      <dRucRec>4567890</dRucRec>
      <dDVRec>1</dDVRec>
      <dNomRec>RECEPTOR DEL DOCUMENTO</dNomRec>
      <dDirRec>CALLE 1 ENTRE CALLE 2 Y CALLE 3</dDirRec>
      <dNumCasRec>123</dNumCasRec>
      <cDepRec>1</cDepRec>
      <dDesDepRec>CAPITAL</dDesDepRec>
      <cDisRec>1</cDisRec>
      <dDesDisRec>ASUNCION (DISTRITO)</dDesDisRec>
      <cCiuRec>1</cCiuRec>
      <dDesCiuRec>ASUNCION (DISTRITO)</dDesCiuRec>
      <dTelRec>012123456</dTelRec>
      <dCodCliente>AAA</dCodCliente>
    </gDatRec>
  </gDatGralOpe>
  <gDtipDE>
    <gCamFE>
      <iIndPres>1</iIndPres>
      <dDesIndPres>Operación presencial</dDesIndPres>
    </gCamFE>
    <gCamCond>
      <iCondOpe>2</iCondOpe>
      <dDCondOpe>Crédito</dDCondOpe>
      <gPagCred>
        <iCondCred>1</iCondCred>
        <dDCondCred>Plazo</dDCondCred>
        <dPlazoCre>28</dPlazoCre>
      </gPagCred>
    </gCamCond>
    <gCamItem>
      <dCodInt>CAC/CTAC</dCodInt>
      <dDesProSer>CUENTAS ACTIVAS</dDesProSer>
      <cUniMed>77</cUniMed>
      <dDesUniMed>UNI</dDesUniMed>
      <dCantProSer>1</dCantProSer>
      <dInfItem>21</dInfItem>
      <gValorItem>
        <dPUniProSer>1100000</dPUniProSer>
        <dTotBruOpeItem>1100000</dTotBruOpeItem>
        <gValorRestaItem>
          <dDescItem>0</dDescItem>
          <dPorcDesIt>0</dPorcDesIt>
          <dDescGloItem>0</dDescGloItem>
          <dTotOpeItem>1100000</dTotOpeItem>
        </gValorRestaItem>
      </gValorItem>
      <gCamIVA>
        <iAfecIVA>1</iAfecIVA>
        <dDesAfecIVA>Gravado IVA</dDesAfecIVA>
        <dPropIVA>100</dPropIVA>
        <dTasaIVA>10</dTasaIVA>
        <dBasGravIVA>1000000</dBasGravIVA>
        <dLiqIVAItem>100000</dLiqIVAItem>
      </gCamIVA>
    </gCamItem>
  </gDtipDE>
  <gTotSub>
    <dSubExe>0</dSubExe>
    <dSubExo>0</dSubExo>
    <dSub5>0</dSub5>
    <dSub10>2200000</dSub10>
    <dTotOpe>2200000</dTotOpe>
    <dTotDesc>0</dTotDesc>
    <dTotDescGlotem>0</dTotDescGlotem>
    <dTotAntItem>0</dTotAntItem>
    <dTotAnt>0</dTotAnt>
    <dPorcDescTotal>0</dPorcDescTotal>
    <dDescTotal>0.0</dDescTotal>
    <dAnticipo>0</dAnticipo>
    <dRedon>0.0</dRedon>
    <dTotGralOpe>2200000</dTotGralOpe>
    <dIVA5>0</dIVA5>
    <dIVA10>200000</dIVA10>
    <dTotIVA>200000</dTotIVA>
    <dBaseGrav5>0</dBaseGrav5>
    <dBaseGrav10>2000000</dBaseGrav10>
    <dTBasGraIVA>2000000</dTBasGraIVA>
  </gTotSub>
</DE>
"""

print("Generando lote fresco...")

# Construir y firmar lote
try:
    result = build_and_sign_lote_from_xml(
        xml_bytes=test_xml.encode('utf-8'),
        cert_path=cert_path,
        cert_password=cert_password,
        return_debug=True
    )
    
    if isinstance(result, tuple):
        zip_base64, lote_xml_bytes, zip_bytes, _ = result
        
        # Extraer y verificar el XML del ZIP
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        with zf.open('xml_file.xml') as f:
            xml_content = f.read().decode('utf-8')
        
        print("\n=== XML GENERADO ===")
        print(xml_content[:500])
        print()
        
        # Verificar estructura
        open_count = xml_content.count('<rLoteDE')
        close_count = xml_content.count('</rLoteDE>')
        
        if open_count == 1 and close_count == 1:
            print("✅ ESTRUCTURA CORRECTA: Un solo <rLoteDE>")
        else:
            print(f"❌ ESTRUCTURA INCORRECTA: {open_count} apertura, {close_count} cierre")
            
        # Extraer el lote sin XML declaration para el payload
        import re
        lote_sin_decl = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', xml_content)
        
        # Crear payload SOAP
        dId = "01800455473701001000000120260118"  # 15 dígitos
        payload = f'<rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd"><dId>{dId}</dId><xDE>{zip_base64}</xDE></rEnvioLote>'
        
        # Enviar con SOAP client
        client = SoapClient(config)
        print("\nEnviando con payload nuevo...")
        result = client.send_recibe_lote(payload, dump_http=True)
        
        print(f"\n=== RESULTADO ===")
        print(f"Código: {result.get('dCodRes', 'N/A')}")
        print(f"Mensaje: {result.get('dMsgRes', 'N/A')}")
        
    else:
        print("Error: resultado no es tupla")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
