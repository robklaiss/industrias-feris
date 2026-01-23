#!/usr/bin/env python3
"""Test that dCodRes=1264 is treated as connectivity OK"""

import sys
import os
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent  # Go up to industrias-feris-facturacion-electronica-simplificado
tesaka_cv_dir = project_root / "tesaka-cv"
sys.path.insert(0, str(tesaka_cv_dir))

# Change to tesaka-cv directory for imports
os.chdir(tesaka_cv_dir)

from tools.test_smoke_recibe_lote import main, parse_args, save_artifacts

def test_1264_connectivity_ok():
    """Test that dCodRes=1264 returns exit code 0 and sets connectivity_ok=true"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Change to temp directory
        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        
        try:
            # Create artifacts directory
            Path("artifacts").mkdir()
            
            # Mock the necessary functions to simulate dCodRes=1264
            mock_metadata = {
                "response_dCodRes": "1264",
                "response_dMsgRes": "RUC no habilitado para el servicio",
                "post_url": "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl",
                "http_status": 200,
                "ok": True
            }
            
            mock_response = b"<soap:Envelope>...</soap:Envelope>"
            mock_request = b"<soap:Envelope>...</soap:Envelope>"
            
            # Mock create_minimal_lote to return dummy bytes
            mock_zip = b"dummy_zip_content"
            
            # Mock send_lote_to_sifen to return our test data
            def mock_send_lote(env, zip_bytes):
                return mock_metadata, mock_response, mock_request
            
            # Mock the entire flow
            with patch('tools.test_smoke_recibe_lote.create_minimal_lote', return_value=mock_zip), \
                 patch('tools.test_smoke_recibe_lote.send_lote_to_sifen', side_effect=mock_send_lote), \
                 patch('tools.test_smoke_recibe_lote.save_artifacts'), \
                 patch('sys.argv', ['test_smoke_recibe_lote.py', '--env', 'test', 
                                   '--sign-p12-path', 'dummy.p12', 
                                   '--sign-p12-password', 'dummy']):
                
                # Run the test
                exit_code = main()
                
                # Verify exit code is 0 (success)
                assert exit_code == 0, f"Expected exit code 0, got {exit_code}"
                
                # Check that metadata was saved with correct fields
                metadata_files = list(Path("artifacts").glob("smoke_test_metadata_test_*.json"))
                assert len(metadata_files) > 0, "No metadata file found"
                
                with open(metadata_files[0]) as f:
                    saved_metadata = json.load(f)
                
                # Verify connectivity_ok is true
                assert saved_metadata.get("connectivity_ok") == True, \
                    f"Expected connectivity_ok=true, got {saved_metadata.get('connectivity_ok')}"
                
                # Verify biz_blocker is set correctly
                assert saved_metadata.get("biz_blocker") == "RUC_NOT_ENABLED_FOR_SERVICE", \
                    f"Expected biz_blocker=RUC_NOT_ENABLED_FOR_SERVICE, got {saved_metadata.get('biz_blocker')}"
                
                print("✅ Test passed: dCodRes=1264 treated as connectivity OK")
                return True
                
        finally:
            os.chdir(old_cwd)

def test_0301_connectivity_ok_but_exit_code_1():
    """Test that dCodRes=0301 has connectivity_ok=true but exit code 1"""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Change to temp directory
        old_cwd = os.getcwd()
        os.chdir(tmpdir)
        
        try:
            # Create artifacts directory
            Path("artifacts").mkdir()
            
            # Mock the necessary functions to simulate dCodRes=0301
            mock_metadata = {
                "response_dCodRes": "0301",
                "response_dMsgRes": "Lote no encolado",
                "post_url": "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl",
                "http_status": 200,
                "ok": True
            }
            
            mock_response = b"<soap:Envelope>...</soap:Envelope>"
            mock_request = b"<soap:Envelope>...</soap:Envelope>"
            mock_zip = b"dummy_zip_content"
            
            def mock_send_lote(env, zip_bytes):
                return mock_metadata, mock_response, mock_request
            
            def mock_diagnose_0301(*args):
                pass  # Do nothing for test
            
            with patch('tools.test_smoke_recibe_lote.create_minimal_lote', return_value=mock_zip), \
                 patch('tools.test_smoke_recibe_lote.send_lote_to_sifen', side_effect=mock_send_lote), \
                 patch('tools.test_smoke_recibe_lote.save_artifacts'), \
                 patch('tools.test_smoke_recibe_lote.diagnose_0301', side_effect=mock_diagnose_0301), \
                 patch('sys.argv', ['test_smoke_recibe_lote.py', '--env', 'test', 
                                   '--sign-p12-path', 'dummy.p12', 
                                   '--sign-p12-password', 'dummy']):
                
                # Run the test
                exit_code = main()
                
                # Verify exit code is 1 (error)
                assert exit_code == 1, f"Expected exit code 1, got {exit_code}"
                
                # Check metadata
                metadata_files = list(Path("artifacts").glob("smoke_test_metadata_test_*.json"))
                with open(metadata_files[0]) as f:
                    saved_metadata = json.load(f)
                
                # Verify connectivity_ok is true
                assert saved_metadata.get("connectivity_ok") == True, \
                    f"Expected connectivity_ok=true, got {saved_metadata.get('connectivity_ok')}"
                
                # Verify biz_blocker is None
                assert saved_metadata.get("biz_blocker") is None, \
                    f"Expected biz_blocker=None, got {saved_metadata.get('biz_blocker')}"
                
                print("✅ Test passed: dCodRes=0301 has connectivity_ok=true but exit code 1")
                return True
                
        finally:
            os.chdir(old_cwd)

if __name__ == "__main__":
    print("Testing dCodRes classification...")
    
    try:
        test_1264_connectivity_ok()
        test_0301_connectivity_ok_but_exit_code_1()
        print("\n✅ All tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
