#!/usr/bin/env python3
"""
Crear un XML de prueba simple con namespace SIFEN en Signature
"""

from pathlib import Path

# XML simple con Signature con namespace SIFEN
xml_content = '''<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
  <xDE>
    <rDE xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
      <dVerFor>150</dVerFor>
      <DE Id="01045547378001001000000812026011616160675413">
        <dDVId>6</dDVId>
        <dFeEmiDE>2026-01-16</dFeEmiDE>
        <gOpeDE>
          <dTiOpe>01</dTiOpe>
        </gOpeDE>
        <gDatGralDE>
          <dFeEmTIm>01</dFeEmTIm>
          <dFeEmit>2026-01-16</dFeEmit>
          <gEmisDE>
            <dRucEm>80050172-1</dRucEm>
            <dDVEmi>1</dDVEmi>
            <dNomEm>DOCUMENTA S.A.</dNomEm>
          </gEmisDE>
        </gDatGralDE>
      </DE>
      <Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">
        <SignedInfo>
          <CanonicalizationMethod Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
          <SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
          <Reference URI="#01045547378001001000000812026011616160675413">
            <Transforms>
              <Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
              <Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
            </Transforms>
            <DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
            <DigestValue>mZkcc4U15NTeDOIYILXxUMCQhvWrxAuzzC9FGpI7aXE=</DigestValue>
          </Reference>
        </SignedInfo>
        <SignatureValue>...</SignatureValue>
        <KeyInfo>
          <X509Data>
            <X509Certificate>...</X509Certificate>
          </X509Data>
        </KeyInfo>
      </Signature>
      <gCamFuFD>
        <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150&amp;Id=01045547378001001000000812026011616160675413</dCarQR>
      </gCamFuFD>
    </rDE>
  </xDE>
</rLoteDE>'''

Path("artifacts/_debug_lote_from_xde.xml").write_text(xml_content)
print("✅ XML de prueba creado: artifacts/_debug_lote_from_xde.xml")
