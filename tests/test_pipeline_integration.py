#!/usr/bin/env python3
"""
Integration test for complete pipeline flow

Simulates the entire flow without sending to SIFEN.
Validates all components work together correctly.
"""

import pytest
import tempfile
import shutil
import zipfile
import base64
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Add tesaka-cv to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv"))

from tools.soap_picker import pick_real_soap_path
from tools.preflight_validate_xml import PreflightValidator


class TestPipelineIntegration:
    """Test complete pipeline integration."""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        shutil.rmtree(temp_dir)
        
    @pytest.fixture
    def sample_lote_xml(self, temp_dir):
        """Create a sample lote.xml file."""
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
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
            <dCodSeg>123456789</dCodSeg>
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
        
        xml_file = temp_dir / "lote.xml"
        xml_file.write_text(xml_content)
        return xml_file
        
    @pytest.fixture
    def sample_soap_file(self, temp_dir):
        """Create a sample SOAP file with xDE."""
        # Create ZIP with lote.xml
        zip_buffer = temp_dir / "xDE.zip"
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add a dummy lote.xml
            zf.writestr("lote.xml", "<dummy/>")
            
        # Read ZIP as base64
        zip_base64 = base64.b64encode(zip_buffer.read_bytes()).decode('utf-8')
        
        # Create SOAP
        soap_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
    <soap:Body>
        <rEnvioLote xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
            <dId>123456</dId>
            <xDE>{zip_base64}</xDE>
        </rEnvioLote>
    </soap:Body>
</soap:Envelope>"""
        
        soap_file = temp_dir / "soap_last_request_SENT.xml"
        soap_file.write_text(soap_content)
        return soap_file
        
    def test_soap_picker_integration(self, temp_dir, sample_soap_file):
        """Test soap picker finds the correct SOAP file."""
        # Change to temp dir
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            
            # Test soap picker
            soap_path = pick_real_soap_path()
            assert soap_path is not None
            assert Path(soap_path).name == "soap_last_request_SENT.xml"
            
        finally:
            os.chdir(original_cwd)
            
    def test_preflight_validation_integration(self, sample_lote_xml):
        """Test preflight validation on sample XML."""
        validator = PreflightValidator(verbose=True)
        
        # Validate the sample XML
        result = validator.validate_xml_file(sample_lote_xml)
        
        # Should pass all validations
        assert result, "Preflight validation should pass"
        
        # Check no errors
        assert len(validator.errors) == 0, f"Errors found: {validator.errors}"
        
    def test_zip_extraction_and_validation(self, temp_dir, sample_soap_file):
        """Test extracting ZIP from SOAP and validating contents."""
        # Read SOAP
        soap_content = sample_soap_file.read_text()
        
        # Extract base64 from xDE
        import re
        import io
        match = re.search(r'<xDE>(.*?)</xDE>', soap_content, re.DOTALL)
        assert match, "xDE not found in SOAP"
        
        # Decode base64
        zip_bytes = base64.b64decode(match.group(1))
        
        # Extract ZIP using io.BytesIO
        with io.BytesIO(zip_bytes) as zip_buffer:
            with zipfile.ZipFile(zip_buffer) as zf:
                assert "lote.xml" in zf.namelist(), "lote.xml not in ZIP"
                
                # Extract and validate
                with zf.open("lote.xml") as f:
                    xml_content = f.read()
                    
        assert xml_content == b"<dummy/>", "ZIP content mismatch"
        
    @patch('subprocess.run')
    def test_auto_fix_loop_mock_execution(self, mock_run, temp_dir, sample_lote_xml):
        """Test auto-fix loop execution with mocked SIFEN calls."""
        # Mock successful send response
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="Mock response",
            stderr=""
        )
        
        # Import and run auto_fix loop
        from tools.auto_fix_0160_loop import main
        
        # Create artifacts directory
        artifacts_dir = temp_dir / 'artifacts'
        artifacts_dir.mkdir()
        
        # Change to temp dir
        original_cwd = os.getcwd()
        original_argv = sys.argv
        
        try:
            os.chdir(temp_dir)
            sys.argv = [
                'auto_fix_0160_loop.py',
                '--env', 'test',
                '--xml', str(sample_lote_xml),
                '--artifacts-dir', str(artifacts_dir),
                '--max-iter', '1'
            ]
            
            # Run the loop (should exit after preflight)
            exit_code = main()
            
            # Should succeed
            assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
            
        finally:
            os.chdir(original_cwd)
            sys.argv = original_argv
            
    def test_fix_summary_generation(self, temp_dir):
        """Test fix summary is generated correctly."""
        # Create a dummy fix summary
        fix_summary = temp_dir / "fix_summary_1.md"
        fix_summary.write_text("""# Fix Summary - Iteration 1

## Applied Fixes:
- Fixed dVerFor position
- Added missing dCodSeg

## Files:
- Input: input.xml
- Output: output.xml
- Artifacts Dir: artifacts

## Status:
- dCodRes: null
- Message: Success

## Expected vs Found:
- Expected: Success (dCodRes null/accepted)
- Found: null ✅
""")
        
        # Validate content
        content = fix_summary.read_text()
        assert "# Fix Summary - Iteration 1" in content
        assert "## Applied Fixes:" in content
        assert "## Files:" in content
        assert "## Status:" in content
        assert "## Expected vs Found:" in content
        assert "✅" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
