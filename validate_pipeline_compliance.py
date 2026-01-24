#!/usr/bin/env python3
"""
PIPELINE_CONTRACT v2.0 Compliance Validator

This script validates that the SIFEN pipeline implementation
complies with all PIPELINE_CONTRACT v2.0 requirements.

Usage:
    python validate_pipeline_compliance.py [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import subprocess


class PipelineValidator:
    """Validates PIPELINE_CONTRACT compliance"""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.tesaka_dir = repo_root / "tesaka-cv"
        self.tools_dir = self.tesaka_dir / "tools"
        self.tests_dir = repo_root / "tests"
        self.results = []
        
    def log(self, section: str, status: str, message: str):
        """Log validation result"""
        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        self.results.append({
            "section": section,
            "status": status,
            "message": message
        })
        print(f"{icon} [{section}] {message}")
    
    def validate_contract_version(self):
        """Validate PIPELINE_CONTRACT has version tracking"""
        contract = self.repo_root / "PIPELINE_CONTRACT.md"
        if not contract.exists():
            self.log("Contract", "FAIL", "PIPELINE_CONTRACT.md not found")
            return False
        
        content = contract.read_text(encoding="utf-8")
        
        if "Version: 2.0" not in content:
            self.log("Contract", "FAIL", "Contract not updated to v2.0")
            return False
        
        if "Changelog:" not in content:
            self.log("Contract", "WARN", "Missing changelog in contract")
        else:
            self.log("Contract", "PASS", "Contract v2.0 with changelog")
        
        return True
    
    def validate_required_tools(self):
        """Check all required tools exist"""
        required_tools = [
            "send_sirecepde.py",
            "follow_lote.py", 
            "auto_fix_0160_loop.py",
            "soap_picker.py",
            "validate_xde_zip_contains_dcodseg.py",
            "validate_success_criteria.py"
        ]
        
        all_exist = True
        for tool in required_tools:
            tool_path = self.tools_dir / tool
            if not tool_path.exists():
                self.log("Tools", "FAIL", f"Missing {tool}")
                all_exist = False
            elif tool_path.stat().st_size == 0:
                self.log("Tools", "FAIL", f"Empty {tool}")
                all_exist = False
            else:
                self.log("Tools", "PASS", f"Found {tool}")
        
        return all_exist
    
    def validate_canonical_commands(self):
        """Validate send_sirecepde.py has all required flags"""
        send_script = self.tools_dir / "send_sirecepde.py"
        if not send_script.exists():
            self.log("Commands", "FAIL", "send_sirecepde.py not found")
            return False
        
        content = send_script.read_text(encoding="utf-8")
        
        required_args = [
            "--env",
            "--xml", 
            "--bump-doc",
            "--dump-http",
            "--artifacts-dir"
        ]
        
        all_present = True
        for arg in required_args:
            if f'"{arg}"' not in content and f"'{arg}'" not in content:
                self.log("Commands", "FAIL", f"Missing argument {arg}")
                all_present = False
            else:
                self.log("Commands", "PASS", f"Found argument {arg}")
        
        # Check for iteration parameter (v2.0 addition)
        if "--iteration" in content:
            self.log("Commands", "PASS", "Found --iteration parameter (v2.0)")
        else:
            self.log("Commands", "WARN", "Missing --iteration parameter (v2.0)")
        
        return all_present
    
    def validate_polling_behavior(self):
        """Validate follow_lote.py handles 0361/0362 correctly"""
        follow_script = self.tools_dir / "follow_lote.py"
        if not follow_script.exists():
            self.log("Polling", "FAIL", "follow_lote.py not found")
            return False
        
        content = follow_script.read_text(encoding="utf-8")
        
        checks = [
            ("0361", "Processing state handling"),
            ("0362", "Concluded state handling"),
            ("processing", "Processing keyword"),
            ("en procesamiento", "Spanish processing keyword")
        ]
        
        all_present = True
        for check, desc in checks:
            if check not in content:
                self.log("Polling", "FAIL", f"Missing {desc}")
                all_present = False
            else:
                self.log("Polling", "PASS", f"Found {desc}")
        
        return all_present
    
    def validate_auto_fix_structure(self):
        """Validate auto_fix_0160_loop.py structure"""
        loop_script = self.tools_dir / "auto_fix_0160_loop.py"
        if not loop_script.exists():
            self.log("Auto-fix", "FAIL", "auto_fix_0160_loop.py not found")
            return False
        
        content = loop_script.read_text(encoding="utf-8")
        
        required_elements = [
            ("--max-iter", "Max iterations"),
            ("--poll-every", "Poll interval"),
            ("--max-poll", "Max poll attempts"),
            ("is_processing_status", "Processing status check"),
            ("canonical_gTotSub_order", "gTotSub ordering"),
            ("fix_summary_", "Fix summary generation")
        ]
        
        all_present = True
        for element, desc in required_elements:
            if element not in content:
                self.log("Auto-fix", "FAIL" if element != "fix_summary_" else "WARN", 
                        f"Missing {desc}")
                if element != "fix_summary_":
                    all_present = False
            else:
                self.log("Auto-fix", "PASS", f"Found {desc}")
        
        return all_present
    
    def validate_exit_codes(self):
        """Validate exit codes follow standard"""
        validate_script = self.tools_dir / "validate_success_criteria.py"
        if not validate_script.exists():
            self.log("Exit Codes", "FAIL", "validate_success_criteria.py not found")
            return False
        
        # Test the tool with sample data
        test_cases = [
            ({"dCodRes": "0001"}, 0, "Success code"),
            ({"dCodRes": "1264"}, 0, "Business error"),
            ({"dCodRes": "0160"}, 1, "Technical error"),
            ({"dCodRes": "0361"}, 1, "Processing state")
        ]
        
        import tempfile
        import os
        
        all_correct = True
        for test_data, expected_exit, desc in test_cases:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(test_data, f)
                temp_file = f.name
            
            try:
                result = subprocess.run(
                    [sys.executable, str(validate_script), temp_file],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == expected_exit:
                    self.log("Exit Codes", "PASS", f"{desc} returns {expected_exit}")
                else:
                    self.log("Exit Codes", "FAIL", 
                            f"{desc} returns {result.returncode}, expected {expected_exit}")
                    all_correct = False
            finally:
                os.unlink(temp_file)
        
        return all_correct
    
    def validate_artifact_naming(self):
        """Validate artifact naming convention"""
        # Check send_sirecepde.py
        send_content = (self.tools_dir / "send_sirecepde.py").read_text(encoding="utf-8")
        
        patterns = [
            ("response_recepcion_", "Response artifacts"),
            ("timestamp", "Timestamped names"),
            ("artifacts_dir", "Artifact directory")
        ]
        
        for pattern, desc in patterns:
            if pattern in send_content:
                self.log("Artifacts", "PASS", f"Found {desc}")
            else:
                self.log("Artifacts", "FAIL", f"Missing {desc}")
        
        # Check for iteration support
        if "_iter" in send_content:
            self.log("Artifacts", "PASS", "Found iteration naming (v2.0)")
        else:
            self.log("Artifacts", "WARN", "Missing iteration naming (v2.0)")
    
    def validate_test_suite(self):
        """Check test suite exists and runs"""
        test_file = self.tests_dir / "test_pipeline_contract.py"
        if not test_file.exists():
            self.log("Tests", "FAIL", "test_pipeline_contract.py not found")
            return False
        
        # Try to run tests
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", str(test_file), "--tb=no"],
                capture_output=True,
                text=True,
                cwd=str(self.repo_root)
            )
            
            if result.returncode == 0:
                # Count passed tests
                output = result.stdout
                if "passed" in output:
                    import re
                    match = re.search(r'(\d+) passed', output)
                    if match:
                        count = match.group(1)
                        self.log("Tests", "PASS", f"All {count} tests pass")
                else:
                    self.log("Tests", "PASS", "All tests pass")
            else:
                self.log("Tests", "FAIL", f"Tests failed with exit code {result.returncode}")
                return False
        except Exception as e:
            self.log("Tests", "WARN", f"Could not run tests: {e}")
        
        return True
    
    def validate_anti_regression(self):
        """Check anti-regression documentation"""
        anti_reg = self.tesaka_dir / "docs" / "aprendizajes" / "anti-regresion.md"
        if not anti_reg.exists():
            self.log("Anti-regression", "FAIL", "anti-regresion.md not found")
            return False
        
        content = anti_reg.read_text(encoding="utf-8")
        
        key_rules = [
            "rDE Id",
            "dVerFor",
            "gCamFuFD", 
            "0160",
            "schemaLocation",
            "CSC"
        ]
        
        for rule in key_rules:
            if rule in content:
                self.log("Anti-regression", "PASS", f"Found rule for {rule}")
            else:
                self.log("Anti-regression", "WARN", f"Missing rule for {rule}")
        
        return True
    
    def run_validation(self, verbose: bool = False):
        """Run all validation checks"""
        print("=" * 70)
        print("PIPELINE_CONTRACT v2.0 Compliance Validation")
        print("=" * 70)
        
        # Run all checks
        self.validate_contract_version()
        self.validate_required_tools()
        self.validate_canonical_commands()
        self.validate_polling_behavior()
        self.validate_auto_fix_structure()
        self.validate_exit_codes()
        self.validate_artifact_naming()
        self.validate_test_suite()
        self.validate_anti_regression()
        
        # Calculate results
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        warned = sum(1 for r in self.results if r["status"] == "WARN")
        total = len(self.results)
        
        print("\n" + "=" * 70)
        print("VALIDATION SUMMARY")
        print("=" * 70)
        print(f"Total checks: {total}")
        print(f"✅ Passed: {passed}")
        print(f"❌ Failed: {failed}")
        print(f"⚠️  Warnings: {warned}")
        
        if failed == 0:
            print("\n🎉 PIPELINE_CONTRACT v2.0 COMPLIANT!")
            if warned > 0:
                print(f"\n⚠️  {warned} warning(s) to review for full compliance")
        else:
            print(f"\n❌ NOT COMPLIANT - {failed} failure(s) must be fixed")
            print("\nFailed items:")
            for r in self.results:
                if r["status"] == "FAIL":
                    print(f"  - [{r['section']}] {r['message']}")
        
        if verbose:
            print("\n" + "=" * 70)
            print("DETAILED RESULTS")
            print("=" * 70)
            for r in self.results:
                print(f"[{r['status']}] {r['section']}: {r['message']}")
        
        return failed == 0


def main():
    parser = argparse.ArgumentParser(
        description="Validate PIPELINE_CONTRACT v2.0 compliance"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed results"
    )
    parser.add_argument(
        "--repo-root",
        default=None,
        help="Repository root path (default: auto-detect)"
    )
    
    args = parser.parse_args()
    
    # Detect repo root if not provided
    if args.repo_root:
        repo_root = Path(args.repo_root)
    else:
        # Assume script is in repo root
        repo_root = Path(__file__).parent
    
    # Run validation
    validator = PipelineValidator(repo_root)
    success = validator.run_validation(verbose=args.verbose)
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
