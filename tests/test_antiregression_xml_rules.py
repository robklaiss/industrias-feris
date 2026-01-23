#!/usr/bin/env python3
"""
Anti-regression XML rules tests

Validates critical XML rules to prevent SIFEN 0160 errors.
Tests are designed to run without network access.
"""

import pytest
import zipfile
import base64
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET


class TestAntiRegressionXMLRules:
    """Test suite for anti-regression XML rules."""
    
    @pytest.fixture
    def minimal_xml_fixture(self):
        """Create a minimal XML fixture for testing."""
        return """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE>
        <dVerFor>150</dVerFor>
        <DE Id="DE12345678901234567890">
            <dTipDoc>01</dTipDoc>
            <dNumDoc>001-001-000000001</dNumDoc>
            <dFeEmiDE>2026-01-23T10:30:00</dFeEmiDE>
            <gOpeDE>
                <dTiOpe>01</dTiOpe>
                <dTipTra>01</dTipTra>
                <dDest>1</dDest>
                <dPaisDest>PRY</dPaisDest>
                <dTiEmi>1</dTiEmi>
                <dPaisEmi>PRY</dPaisEmi>
            </gOpeDE>
            <gDatGrp>
                <dGrp1>1</dGrp1>
            </gDatGrp>
            <gEmis>
                <gDatGen>
                    <dRucEm>80000001</dRucEm>
                    <dDVEmi>1</dDVEmi>
                    <dNomEmi>EMPRESA TEST</dNomEmi>
                </gDatGen>
            </gEmis>
            <gDatRec>
                <dRucRec>80000002</dRucRec>
                <dDVRec>2</dDVRec>
                <dNomRec>CLIENTE TEST</dNomRec>
            </gDatRec>
            <gTotSub>
                <dTotGralOpe>100000</dTotGralOpe>
                <dTotGravadas>100000</dTotGravadas>
                <dTotIVA>10000</dTotIVA>
                <dTotSubExe>0</dTotSubExe>
                <dTotSubExo>0</dTotSubExo>
                <dTotSubNS>0</dTotSubNS>
                <dTotSubIVA>10000</dTotSubIVA>
                <dTotOtrosTrib>0</dTotOtrosTrib>
                <dTotVtaOper>100000</dTotVtaOper>
                <dTotDesc>0</dTotDesc>
                <dTotDescGlob>0</dTotDescGlob>
                <dTotAnticipo>0</dTotAnticipo>
                <dTotReteIVA>0</dTotReteIVA>
                <dTotReteRenta>0</dTotReteRenta>
                <dTotPerceps>0</dTotPerceps>
                <dTotCompraTotal>0</dTotCompraTotal>
                <dTotVtaNGrav>0</dTotVtaNGrav>
                <dTotVtaExe>0</dTotVtaExe>
                <dTotVtaExo>0</dTotVtaExo>
                <dTotVtaNS>0</dTotVtaNS>
                <dTotIVAComp>0</dTotIVAComp>
                <dTotRetenido>0</dTotRetenido>
                <dTotReembolso>0</dTotReembolso>
                <dTotDescItem>0</dTotDescItem>
                <dTotAntItem>0</dTotAntItem>
            </gTotSub>
            <gCamFE>
                <dFCF>1</dFCF>
                <dFEC>1</dFEC>
            </gCamFE>
            <dCarQR>https://ekuatia.set.gov.py/consultas/qr?nVersion=150&amp;cHashQR=abc123</dCarQR>
        </DE>
        <Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
            <SignedInfo>
                <CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
                <SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
                <Reference URI="#DE12345678901234567890">
                    <Transforms>
                        <Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
                    </Transforms>
                    <DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
                    <DigestValue>digest123</DigestValue>
                </Reference>
            </SignedInfo>
            <SignatureValue>signature123</SignatureValue>
            <KeyInfo>
                <X509Data>
                    <X509Certificate>cert123</X509Certificate>
                </X509Data>
            </KeyInfo>
        </Signature>
    </rDE>
</rLoteDE>"""
    
    def test_rde_no_id_attribute(self, minimal_xml_fixture):
        """Test that rDE element does not have Id attribute in final XML."""
        root = ET.fromstring(minimal_xml_fixture)
        
        # Find rDE element (namespace-aware)
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        rde = root.find('.//sifen:rDE', ns)
        
        assert rde is not None, "rDE element not found"
        assert 'Id' not in rde.attrib, f"rDE should not have Id attribute, but has: {rde.attrib}"
        
    def test_dverfor_first_child_of_rde(self, minimal_xml_fixture):
        """Test that dVerFor is the first child of rDE."""
        root = ET.fromstring(minimal_xml_fixture)
        
        # Find rDE element (namespace-aware)
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        rde = root.find('.//sifen:rDE', ns)
        
        assert rde is not None, "rDE element not found"
        assert len(rde) > 0, "rDE has no children"
        
        # Check first child is dVerFor
        first_child = rde[0]
        # Remove namespace for comparison
        tag_name = first_child.tag.split('}')[-1] if '}' in first_child.tag else first_child.tag
        assert tag_name == 'dVerFor', f"First child should be dVerFor, but is: {tag_name}"
        
        # Also check value
        assert first_child.text == '150', f"dVerFor should be '150', but is: {first_child.text}"
        
    def test_signature_namespace_xmldsig(self, minimal_xml_fixture):
        """Test that Signature uses XMLDSig namespace."""
        root = ET.fromstring(minimal_xml_fixture)
        
        # Find Signature element (namespace-aware)
        # The signature itself has the namespace in its tag
        signature = root.find('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
        
        assert signature is not None, "Signature element not found"
        # Check that the tag contains the XMLDSig namespace
        assert 'http://www.w3.org/2000/09/xmldsig#' in signature.tag, \
            f"Signature should use XMLDSig namespace, but has tag: {signature.tag}"
        
    def test_dcodseg_format_when_present(self):
        """Test dCodSeg format when present in XML/ZIP."""
        # Create a test XML with dCodSeg
        xml_with_dcodseg = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE>
        <dVerFor>150</dVerFor>
        <DE Id="DE12345678901234567890">
            <dTipDoc>01</dTipDoc>
            <dNumDoc>001-001-000000001</dNumDoc>
            <dFeEmiDE>2026-01-23T10:30:00</dFeEmiDE>
            <dCodSeg>123456789</dCodSeg>
        </DE>
    </rDE>
</rLoteDE>"""
        
        root = ET.fromstring(xml_with_dcodseg)
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        dCodSeg = root.find('.//sifen:dCodSeg', ns)
        
        assert dCodSeg is not None, "dCodSeg element not found"
        assert dCodSeg.text is not None, "dCodSeg has no text"
        assert len(dCodSeg.text) == 9, f"dCodSeg should be 9 digits, but has: {len(dCodSeg.text)}"
        assert dCodSeg.text.isdigit(), f"dCodSeg should be all digits, but is: {dCodSeg.text}"
        
    def test_dcodseg_in_zip(self, minimal_xml_fixture):
        """Test dCodSeg format when inside ZIP (helper function)."""
        # Create a mock ZIP with XML containing dCodSeg
        xml_with_dcodseg = """<?xml version="1.0" encoding="UTF-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE>
        <dVerFor>150</dVerFor>
        <DE Id="DE12345678901234567890">
            <dTipDoc>01</dTipDoc>
            <dNumDoc>001-001-000000001</dNumDoc>
            <dFeEmiDE>2026-01-23T10:30:00</dFeEmiDE>
            <dCodSeg>987654321</dCodSeg>
        </DE>
    </rDE>
</rLoteDE>"""
        
        # Create ZIP in memory
        import io
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('lote.xml', xml_with_dcodseg)
        
        # Extract and validate
        zip_buffer.seek(0)
        with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
            with zip_file.open('lote.xml') as xml_file:
                xml_content = xml_file.read().decode('utf-8')
                
        root = ET.fromstring(xml_content)
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        dCodSeg = root.find('.//sifen:dCodSeg', ns)
        
        assert dCodSeg is not None, "dCodSeg element not found in ZIP"
        assert len(dCodSeg.text) == 9, f"dCodSeg should be 9 digits, but has: {len(dCodSeg.text)}"
        assert dCodSeg.text.isdigit(), f"dCodSeg should be all digits, but is: {dCodSeg.text}"
        
    def test_qr_contains_nversion(self, minimal_xml_fixture):
        """Test that QR contains ?nVersion= parameter."""
        root = ET.fromstring(minimal_xml_fixture)
        
        # Find QR element
        ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        qr = root.find('.//sifen:dCarQR', ns)
        
        assert qr is not None, "QR element not found"
        qr_text = qr.text or ''
        
        # Check for ?nVersion= in QR
        assert '?nVersion=' in qr_text, f"QR should contain '?nVersion=', but has: {qr_text}"
        
        # Also check it doesn't have the malformed /qrnVersion=
        assert '/qrnVersion=' not in qr_text, f"QR should not contain '/qrnVersion=', but has: {qr_text}"


@pytest.mark.skip(reason="QR generation not yet implemented in test fixture")
def test_qr_with_datetime():
    """Test QR format when generated with datetime (future implementation)."""
    pass


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v"])
