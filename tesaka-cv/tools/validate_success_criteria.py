#!/usr/bin/env python3
"""
Validate SIFEN response against PIPELINE_CONTRACT success criteria (Section 9)

This tool helps determine if a SIFEN response represents success, business error,
or technical error according to the contract.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Any, Tuple

# Success codes from PIPELINE_CONTRACT section 9
SUCCESS_CODES = {
    "0001", "0002", "0003",  # Sin observaciones
    "0101", "0102", "0103",  # Aprobado
    "0201", "0202"          # Aprobado con observaciones
}

BUSINESS_ERROR_CODES = {
    "1264",  # RUC no habilitado
    "0301"   # No encolado
}

TECHNICAL_ERROR_CODES = {
    "0160",  # XML mal formado
    "0500", "0501", "0502", "0503", "0504", "0505",  # Errores varios
    "0900", "0901", "0902",  # Errores internos
}

PROCESSING_CODES = {
    "0361",  # En procesamiento
    "0300"   # Encolado
}

def classify_response(dCodRes: str, dMsgRes: str = "") -> Tuple[str, str]:
    """
    Classify SIFEN response according to PIPELINE_CONTRACT
    
    Returns: (category, description)
    """
    if not dCodRes:
        return ("unknown", "No response code")
    
    # Check success
    if dCodRes in SUCCESS_CODES:
        return ("success", f"✅ Success - {dCodRes}")
    
    # Check business errors (still exit code 0 but should be reported)
    if dCodRes in BUSINESS_ERROR_CODES:
        desc = {
            "1264": "RUC not enabled for service",
            "0301": "Lote not enqueued"
        }.get(dCodRes, "Business error")
        return ("business_error", f"⚠️  Business error - {desc}")
    
    # Check processing states
    if dCodRes in PROCESSING_CODES:
        desc = {
            "0361": "Processing - continue polling",
            "0300": "Encolado - wait for processing"
        }.get(dCodRes, "Processing")
        return ("processing", f"🔄 Processing - {desc}")
    
    # Check technical errors
    if dCodRes in TECHNICAL_ERROR_CODES:
        desc = {
            "0160": "XML mal formado"
        }.get(dCodRes, "Technical error")
        return ("technical_error", f"❌ Technical error - {desc}")
    
    # Unknown code
    return ("unknown", f"❓ Unknown response code - {dCodRes}")

def get_exit_code(category: str) -> int:
    """Return exit code according to PIPELINE_CONTRACT section 7"""
    exit_codes = {
        "success": 0,
        "business_error": 0,  # Exit 0 but should be reported
        "processing": 1,      # Should not happen at final check
        "technical_error": 1,
        "unknown": 1
    }
    return exit_codes.get(category, 1)

def load_json_file(path: str) -> Dict[str, Any]:
    """Load JSON file and return parsed data"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading {path}: {e}")
        sys.exit(2)

def extract_response_code(data: Dict[str, Any]) -> Tuple[str, str]:
    """Extract dCodRes and dMsgRes from response JSON"""
    # Try various possible paths
    paths = [
        ("dCodRes", "dMsgRes"),
        ("dCodResLot", "dMsgResLot"),
        ("response.dCodRes", "response.dMsgRes"),
        ("lote.dCodRes", "lote.dMsgRes"),
    ]
    
    def get_nested(data: Dict[str, Any], path: str):
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current
    
    for cod_path, msg_path in paths:
        cod = get_nested(data, cod_path)
        msg = get_nested(data, msg_path)
        if cod:
            return (str(cod), str(msg) if msg else "")
    
    return ("", "")

def main():
    parser = argparse.ArgumentParser(
        description="Validate SIFEN response against PIPELINE_CONTRACT success criteria"
    )
    parser.add_argument(
        "json_file",
        help="Path to response JSON (response_recepcion_*.json or consulta_lote_*.json)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed classification"
    )
    
    args = parser.parse_args()
    
    # Load and parse JSON
    data = load_json_file(args.json_file)
    dCodRes, dMsgRes = extract_response_code(data)
    
    if not dCodRes:
        print(f"❌ Could not extract response code from {args.json_file}")
        sys.exit(2)
    
    # Classify response
    category, description = classify_response(dCodRes, dMsgRes)
    exit_code = get_exit_code(category)
    
    # Print results
    print(f"\n📊 Response Classification:")
    print(f"   Code: {dCodRes}")
    print(f"   Message: {dMsgRes[:100] + '...' if len(dMsgRes) > 100 else dMsgRes}")
    print(f"   Category: {category}")
    print(f"   Description: {description}")
    print(f"   Exit code: {exit_code}")
    
    if args.verbose:
        print(f"\n📋 PIPELINE_CONTRACT Reference:")
        if category == "success":
            print("   → DE concluido exitosamente (STOP)")
        elif category == "business_error":
            print("   → Error de negocio, pero conectividad OK (STOP)")
        elif category == "processing":
            print("   → Continuar polling (NO STOP)")
        elif category == "technical_error":
            print("   → Error técnico requiere intervención (STOP)")
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()
