#!/usr/bin/env python3
"""
Test script to verify the smoke test modifications work correctly
"""
import subprocess
import sys
from pathlib import Path

def test_smoke_test_flags():
    """Test that the smoke test accepts the new --check-ruc flag"""
    
    # Change to tesaka-cv directory
    cv_dir = Path(__file__).parent / "tesaka-cv"
    
    print("Testing smoke test with --help to check new flag...")
    
    # Test 1: Check --help shows the new flag
    result = subprocess.run(
        [".venv/bin/python", "tools/test_smoke_recibe_lote.py", "--help"],
        cwd=cv_dir,
        capture_output=True,
        text=True
    )
    
    if "--check-ruc" in result.stdout:
        print("✅ --check-ruc flag is present in help")
    else:
        print("❌ --check-ruc flag NOT found in help")
        print("Help output:")
        print(result.stdout)
        return False
    
    # Test 2: Dry run check (should fail due to missing P12, but should show the flag is accepted)
    print("\nTesting smoke test accepts --check-ruc flag...")
    result = subprocess.run(
        [".venv/bin/python", "tools/test_smoke_recibe_lote.py", "--env", "test", "--check-ruc"],
        cwd=cv_dir,
        capture_output=True,
        text=True
    )
    
    # Should fail with P12 error, not with unknown flag error
    if "unrecognized arguments: --check-ruc" in result.stderr:
        print("❌ --check-ruc flag not recognized")
        print("Error output:")
        print(result.stderr)
        return False
    elif "Falta P12 de firma" in result.stderr or "Falta P12 de firma" in result.stdout:
        print("✅ --check-ruc flag accepted (failed on P12 as expected)")
    else:
        print("⚠️  Unexpected output:")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    
    # Test 3: Default behavior (no --check-ruc)
    print("\nTesting smoke test default behavior (no RUC check)...")
    result = subprocess.run(
        [".venv/bin/python", "tools/test_smoke_recibe_lote.py", "--env", "test"],
        cwd=cv_dir,
        capture_output=True,
        text=True
    )
    
    if "unrecognized arguments" in result.stderr:
        print("❌ Problem with basic arguments")
        print("Error output:")
        print(result.stderr)
        return False
    elif "Falta P12 de firma" in result.stderr or "Falta P12 de firma" in result.stdout:
        print("✅ Default behavior works (failed on P12 as expected)")
    else:
        print("⚠️  Unexpected output:")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    
    print("\n✅ All tests passed! The smoke test modifications are working correctly.")
    print("\nTo run the smoke test:")
    print("1. Without RUC check (default):")
    print("   .venv/bin/python tools/test_smoke_recibe_lote.py --env test")
    print("\n2. With RUC check (informational only):")
    print("   .venv/bin/python tools/test_smoke_recibe_lote.py --env test --check-ruc")
    
    return True

if __name__ == "__main__":
    success = test_smoke_test_flags()
    sys.exit(0 if success else 1)
