#!/usr/bin/env python3
"""
Diagnostic script for SIFEN access issues.
Tests RUC status and WSDL availability, protecting against BIG-IP logout/hangup.
"""

import os
ENV = (os.getenv('SIFEN_ENV') or 'test').strip().lower()
if ENV not in ('test', 'prod'):
    raise SystemExit(f"SIFEN_ENV inválido: {ENV!r} (usar 'test' o 'prod')")
BASE_HOST = 'sifen.set.gov.py' if ENV == 'prod' else 'sifen-test.set.gov.py'
import sys
import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sifen_client.soap_client import SoapClient, SifenConfig
from app.sifen_client.config import get_artifacts_dir


def is_valid_wsdl(content: bytes) -> bool:
    """Check if content is a valid WSDL (not HTML/redirect)."""
    if not content:
        return False
    
    content_str = content.decode('utf-8', errors='ignore').lower()
    
    # Check for HTML indicators (BIG-IP logout page)
    if '<html' in content_str or 'big-ip' in content_str:
        return False
    
    # Check for WSDL indicators
    if 'definitions' in content_str or 'wsdl:definitions' in content_str:
        return True
    
    return False


def test_consulta_ruc() -> Dict[str, Any]:
    """Test RUC consultation in TEST environment."""
    print(f"\n=== Testing RUC Consultation ({ENV.upper()}) ===")
    
    result = {
        "test": "consulta_ruc",
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "endpoint": None,
        "http_status": None,
        "dCodRes": None,
        "dMsgRes": None,
        "dRUCFactElec": None,
        "error": None
    }
    
    try:
        # Get RUC from environment
        ruc_input = os.getenv("SIFEN_EMISOR_RUC", "4554737")
        
        # Remove DV if present for display
        ruc_display = ruc_input.split("-")[0] if "-" in ruc_input else ruc_input
        
        print(f"Testing RUC: {ruc_display}")
        
        # Initialize client for TEST environment
        cfg = SifenConfig(env=ENV)
        client = SoapClient(config=cfg)
        
        # Call consulta_ruc_raw
        response = client.consulta_ruc_raw(ruc_display, dump_http=True)
        
        # Extract endpoint from client
        result["endpoint"] = client._resolve_endpoint_with_fallback("consulta_ruc")
        
        # Parse response
        result["dCodRes"] = response.get("dCodRes")
        result["dMsgRes"] = response.get("dMsgRes")
        
        # Extract dRUCFactElec if available
        if "xContRUC" in response and response["xContRUC"]:
            result["dRUCFactElec"] = response["xContRUC"].get("dRUCFactElec")
        
        result["success"] = True
        print(f"✓ dCodRes: {result['dCodRes']}")
        print(f"✓ dMsgRes: {result['dMsgRes']}")
        if result["dRUCFactElec"]:
            print(f"✓ dRUCFactElec: {result['dRUCFactElec']}")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"✗ Error: {e}")
    
    return result


def test_wsdl_availability() -> Dict[str, Any]:
    """Test WSDL download without following redirects."""
    print("\n=== Testing WSDL Availability (recibe-lote) ===")
    
    result = {
        "test": "wsdl_recibe_lote",
        "timestamp": datetime.now().isoformat(),
        "url": f"https://{BASE_HOST}/de/ws/async/recibe-lote.wsdl?wsdl",
        "success": False,
        "status_code": None,
        "content_type": None,
        "is_redirect": False,
        "is_html": False,
        "is_valid_wsdl": False,
        "content_length": None,
        "error": None
    }
    
    try:
        # Make request without following redirects
        resp = requests.get(
            result["url"],
            allow_redirects=False,
            timeout=20
        )
        
        result["status_code"] = resp.status_code
        result["content_type"] = resp.headers.get("content-type", "")
        result["content_length"] = len(resp.content)
        
        # Check for redirects
        if resp.status_code in (301, 302, 303, 307, 308):
            result["is_redirect"] = True
            result["error"] = f"Redirect detected (status {resp.status_code}) - likely BIG-IP hangup"
            print(f"✗ Redirect detected: {resp.status_code}")
            if "location" in resp.headers:
                print(f"  Location: {resp.headers['location']}")
            return result
        
        # Check content
        content_str = resp.content.decode('utf-8', errors='ignore').lower()
        if '<html' in content_str:
            result["is_html"] = True
            result["error"] = "Received HTML instead of WSDL - BIG-IP logout page"
            print(f"✗ Received HTML (BIG-IP logout page)")
            return result
        
        # Validate WSDL
        result["is_valid_wsdl"] = is_valid_wsdl(resp.content)
        if result["is_valid_wsdl"]:
            result["success"] = True
            print(f"✓ Valid WSDL received ({len(resp.content)} bytes)")
            
            # Save WSDL to artifacts
            artifacts_dir = get_artifacts_dir()
            wsdl_path = artifacts_dir / "wsdl_recibe-lote_test.wsdl"
            wsdl_path.write_bytes(resp.content)
            print(f"✓ WSDL saved to: {wsdl_path}")
        else:
            result["error"] = "Content is not a valid WSDL"
            print(f"✗ Invalid WSDL content")
        
    except Exception as e:
        result["error"] = str(e)
        print(f"✗ Error: {e}")
    
    return result


def save_diagnostic_results(results: list):
    """Save diagnostic results to JSON file."""
    artifacts_dir = get_artifacts_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Save full results
    results_file = artifacts_dir / f"diag_sifen_access_{timestamp}.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Full results saved to: {results_file}")
    
    # Save individual RUC result if available
    for result in results:
        if result["test"] == "consulta_ruc":
            ruc_file = artifacts_dir / f"diag_consulta_ruc_{timestamp}.json"
            with open(ruc_file, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"✓ RUC result saved to: {ruc_file}")
        
        elif result["test"] == "wsdl_recibe_lote":
            wsdl_file = artifacts_dir / f"diag_wsdl_{timestamp}.json"
            # Save summary with first 300 chars
            summary = {
                "status_code": result["status_code"],
                "headers": dict(result.get("headers", {})),
                "content_preview": result.get("content_preview", "")
            }
            with open(wsdl_file, "w") as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            print(f"✓ WSDL summary saved to: {wsdl_file}")


def main():
    """Main diagnostic routine."""
    print("SIFEN Access Diagnostic Tool")
    print("=" * 50)
    
    results = []
    
    # Test 1: RUC Consultation
    ruc_result = test_consulta_ruc()
    results.append(ruc_result)
    
    # Test 2: WSDL Availability
    wsdl_result = test_wsdl_availability()
    results.append(wsdl_result)
    
    # Save results
    save_diagnostic_results(results)
    
    # Determine exit code
    exit_code = 0
    
    # Check RUC result
    if ruc_result.get("dRUCFactElec") != "S" and ruc_result.get("dRUCFactElec") is not None:
        print(f"\n⚠️  RUC not enabled for electronic invoicing (dRUCFactElec={ruc_result.get('dRUCFactElec')})")
        exit_code = 2
    
    # Check WSDL result
    if not wsdl_result.get("success", False):
        print(f"\n⚠️  WSDL validation failed - BIG-IP issues detected")
        exit_code = 3 if exit_code == 0 else exit_code
    
    if exit_code == 0:
        print("\n✅ All tests passed!")
    
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
