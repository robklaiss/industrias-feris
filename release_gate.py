#!/usr/bin/env python3
"""
Release Gate - Pipeline Validation

Ejecuta todas las validaciones críticas antes de permitir un release.
Es el punto único de entrada para validar que todo está listo.
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def run_command(cmd: List[str], cwd: str = None) -> Tuple[int, str, str]:
    """Ejecuta un comando y retorna (exit_code, stdout, stderr)."""
    print(f"🔧 Running: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or "."
    )
    if result.returncode != 0:
        print(f"❌ Failed with exit code {result.returncode}")
        if result.stderr:
            print(f"Stderr: {result.stderr[:500]}")
    else:
        print("✅ Passed")
    return result.returncode, result.stdout, result.stderr


def main():
    print("=" * 60)
    print("RELEASE GATE - PIPELINE VALIDATION")
    print("=" * 60)
    
    checks = [
        {
            "name": "Pipeline Compliance",
            "cmd": [".venv/bin/python", "validate_pipeline_compliance.py", "--score-only"],
            "expected_exit": 0,
            "description": "Verifica archivos críticos y flags requeridos"
        },
        {
            "name": "Anti-regression Tests",
            "cmd": [".venv/bin/python", "-m", "pytest", "tests/test_antiregression_xml_rules.py", "-q"],
            "expected_exit": 0,
            "description": "Valida reglas críticas anti-regresión"
        },
        {
            "name": "All Tests",
            "cmd": [".venv/bin/python", "-m", "pytest", "-q", "--tb=short"],
            "expected_exit": 0,
            "description": "Ejecuta todos los tests del pipeline"
        },
        {
            "name": "Preflight Tool Exists",
            "cmd": ["test", "-f", "tesaka-cv/tools/preflight_validate_xml.py"],
            "expected_exit": 0,
            "description": "Verifica que el preflight esté disponible"
        },
        {
            "name": "Auto-fix Loop Exists",
            "cmd": ["test", "-f", "tesaka-cv/tools/auto_fix_0160_loop.py"],
            "expected_exit": 0,
            "description": "Verifica que el loop de auto-fix esté disponible"
        },
        {
            "name": "Documentation Exists",
            "cmd": ["test", "-f", "tesaka-cv/docs/TROUBLESHOOTING_0160.md"],
            "expected_exit": 0,
            "description": "Verifica que la documentación esté presente"
        }
    ]
    
    passed = 0
    failed = 0
    
    for check in checks:
        print(f"\n📋 {check['name']}")
        print(f"   {check['description']}")
        
        exit_code, _, _ = run_command(check["cmd"])
        
        if exit_code == check["expected_exit"]:
            passed += 1
        else:
            failed += 1
            print(f"❌ CHECK FAILED: {check['name']}")
            
    print("\n" + "=" * 60)
    print("RELEASE GATE SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📊 Total:  {passed + failed}")
    
    if failed > 0:
        print("\n❌ RELEASE GATE FAILED")
        print("Fix the failed checks before proceeding with release")
        sys.exit(1)
    else:
        print("\n✅ RELEASE GATE PASSED")
        print("Pipeline is ready for release!")
        sys.exit(0)


if __name__ == "__main__":
    main()
