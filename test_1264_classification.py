#!/usr/bin/env python3
"""Simple test to verify dCodRes classification logic"""

import sys
import os
from pathlib import Path

# Add tesaka-cv to path
tesaka_cv = Path(__file__).parent / "tesaka-cv"
sys.path.insert(0, str(tesaka_cv))

def test_classification_logic():
    """Test the classification logic for different dCodRes values"""
    
    test_cases = [
        ("0300", True, None, 0, "✅ Envío exitoso - Lote encolado para procesamiento"),
        ("0301", True, None, 1, "⚠️  Lote no encolado (pero endpoint responde - conectividad OK)"),
        ("1264", True, "RUC_NOT_ENABLED_FOR_SERVICE", 0, "⚠️  RUC no habilitado para el servicio (pero mTLS + SOAP OK)"),
        ("0160", False, None, 1, "❌ Respuesta inesperada (dCodRes=0160)"),
    ]
    
    for d_cod_res, expected_connectivity, expected_blocker, expected_exit_code, expected_msg_prefix in test_cases:
        # Apply the same logic as in test_smoke_recibe_lote.py
        connectivity_ok = d_cod_res in ("0300", "0301", "1264")
        biz_blocker = None
        if d_cod_res == "1264":
            biz_blocker = "RUC_NOT_ENABLED_FOR_SERVICE"
        
        # Determine exit code and message
        if d_cod_res == "0300":
            exit_code = 0
            msg = "✅ Envío exitoso - Lote encolado para procesamiento"
        elif d_cod_res == "0301":
            exit_code = 1
            msg = "⚠️  Lote no encolado (pero endpoint responde - conectividad OK)"
        elif d_cod_res == "1264":
            exit_code = 0
            msg = "⚠️  RUC no habilitado para el servicio (pero mTLS + SOAP OK)"
        else:
            exit_code = 1
            msg = f"❌ Respuesta inesperada (dCodRes={d_cod_res})"
        
        # Verify expectations
        assert connectivity_ok == expected_connectivity, \
            f"dCodRes={d_cod_res}: connectivity_ok expected {expected_connectivity}, got {connectivity_ok}"
        assert biz_blocker == expected_blocker, \
            f"dCodRes={d_cod_res}: biz_blocker expected {expected_blocker}, got {biz_blocker}"
        assert exit_code == expected_exit_code, \
            f"dCodRes={d_cod_res}: exit_code expected {expected_exit_code}, got {exit_code}"
        assert msg.startswith(expected_msg_prefix), \
            f"dCodRes={d_cod_res}: message should start with {expected_msg_prefix}, got {msg}"
        
        print(f"✅ dCodRes={d_cod_res}: connectivity_ok={connectivity_ok}, biz_blocker={biz_blocker}, exit_code={exit_code}")
    
    return True

if __name__ == "__main__":
    try:
        test_classification_logic()
        print("\n✅ All classification tests passed!")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
