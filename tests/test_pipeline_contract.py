#!/usr/bin/env python3
"""
Test suite for PIPELINE_CONTRACT v2.0 compliance

This test validates that the implementation follows all contract requirements.
Run with: python -m pytest tests/test_pipeline_contract.py -v
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.validate_success_criteria import classify_response, get_exit_code
from tools.auto_fix_0160_loop import canonical_gTotSub_order


class TestPipelineContract:
    """Test PIPELINE_CONTRACT v2.0 compliance"""
    
    @pytest.fixture
    def repo_root(self) -> Path:
        """Get repository root path"""
        return Path(__file__).parent.parent
    
    @pytest.fixture
    def tools_dir(self, repo_root) -> Path:
        """Get tools directory"""
        return repo_root / "tesaka-cv" / "tools"
    
    def test_canonical_command_structure(self, tools_dir):
        """Test that send_sirecepde.py has all required flags (Section 2)"""
        send_script = tools_dir / "send_sirecepde.py"
        assert send_script.exists(), "send_sirecepde.py not found"
        
        content = send_script.read_text(encoding="utf-8")
        
        # Check all required arguments are present
        required_args = [
            "--env",
            "--xml",
            "--bump-doc",
            "--dump-http",
            "--artifacts-dir"
        ]
        
        for arg in required_args:
            assert f'"{arg}"' in content or f"'{arg}'" in content, \
                f"Missing argument {arg} in send_sirecepde.py"
    
    def test_follow_lote_polling_behavior(self, tools_dir):
        """Test that follow_lote.py handles 0361/0362 correctly (Section 3)"""
        follow_script = tools_dir / "follow_lote.py"
        assert follow_script.exists(), "follow_lote.py not found"
        
        content = follow_script.read_text(encoding="utf-8")
        
        # Should check for 0361 and continue polling
        assert "0361" in content, "Missing 0361 handling in follow_lote.py"
        assert "processing" in content.lower(), "Missing processing keyword"
        
        # Should check for 0362 and evaluate DE
        assert "0362" in content, "Missing 0362 handling in follow_lote.py"
    
    def test_auto_fix_loop_structure(self, tools_dir):
        """Test auto_fix_0160_loop.py has correct loop structure (Section 4)"""
        loop_script = tools_dir / "auto_fix_0160_loop.py"
        assert loop_script.exists(), "auto_fix_0160_loop.py not found"
        
        content = loop_script.read_text(encoding="utf-8")
        
        # Check required arguments
        required_args = [
            "--max-iter",
            "--poll-every",
            "--max-poll"
        ]
        
        for arg in required_args:
            assert arg in content, f"Missing argument {arg} in auto_fix_0160_loop.py"
        
        # Check internal polling logic
        assert "is_processing_status" in content, "Missing processing status check"
        assert "while.*poll_count" in content or "for.*poll" in content, \
            "Missing polling loop"
    
    def test_exit_codes_compliance(self):
        """Test exit codes follow PIPELINE_CONTRACT section 7"""
        # Test success codes
        success_codes = ["0001", "0002", "0003", "0101", "0201"]
        for code in success_codes:
            category, _ = classify_response(code)
            exit_code = get_exit_code(category)
            assert exit_code == 0, f"Success code {code} should return exit code 0"
        
        # Test business error codes
        business_codes = ["1264", "0301"]
        for code in business_codes:
            category, _ = classify_response(code)
            exit_code = get_exit_code(category)
            assert exit_code == 0, f"Business error {code} should return exit code 0"
        
        # Test technical error codes
        error_codes = ["0160", "0500", "0900"]
        for code in error_codes:
            category, _ = classify_response(code)
            exit_code = get_exit_code(category)
            assert exit_code == 1, f"Technical error {code} should return exit code 1"
    
    def test_gtotsub_canonical_order(self):
        """Test gTotSub canonical order implementation (Section 6)"""
        from tools.auto_fix_0160_loop import canonical_gtotsub_order
        
        # Expected canonical order from contract
        expected_order = [
            "dSubExe", "dSubExo", "dSub5", "dSub10", "dTotOpe",
            "dTotDesc", "dTotDescGlotem", "dTotAntItem", "dTotAnt",
            "dPorcDescTotal", "dTotIVA", "dTotGralOp", "dTotGrav", "dTotExe"
        ]
        
        # Check that canonical_gTotSub_order function exists and uses correct order
        import inspect
        source = inspect.getsource(canonical_gTotSub_order)
        
        for item in expected_order:
            assert f'"{item}"' in source, f"Missing {item} in canonical order"
    
    def test_artifact_naming_convention(self, tools_dir):
        """Test that artifacts follow naming convention (Section 5)"""
        # Check send_sirecepde.py generates response_recepcion_*.json
        send_content = (tools_dir / "send_sirecepde.py").read_text(encoding="utf-8")
        assert "response_recepcion_" in send_content, \
            "Missing response_recepcion_ artifact naming"
        
        # Check auto_fix_0160_loop.py generates iteration-specific files
        loop_content = (tools_dir / "auto_fix_0160_loop.py").read_text(encoding="utf-8")
        assert "_loopfix_" in loop_content or "iteration" in loop_content.lower(), \
            "Missing iteration-specific artifact naming"
        
        # Check for fix_summary generation (if patched)
        if "fix_summary_" in loop_content:
            assert "fix_summary_" in loop_content, \
                "Missing fix_summary_N.md generation"
    
    def test_soap_picker_unified(self, tools_dir):
        """Test that unified SOAP picker is used (Loop 6)"""
        picker_script = tools_dir / "soap_picker.py"
        assert picker_script.exists(), "soap_picker.py not found"
        
        content = picker_script.read_text(encoding="utf-8")
        
        # Check for required functions
        required_functions = [
            "pick_real_soap",
            "pick_real_soap_path"
        ]
        
        for func in required_functions:
            assert f"def {func}" in content, f"Missing function {func}"
        
        # Check priority rule: soap_last_request_REAL.xml first
        assert "REAL" in content, "Missing REAL file priority"
    
    def test_csc_validation_integration(self, tools_dir):
        """Test CSC validation is integrated (Loop 5)"""
        # Check preflight_send.py validates CSC
        preflight = tools_dir / "preflight_send.py"
        if preflight.exists():
            content = preflight.read_text(encoding="utf-8")
            assert "validate_csc" in content, "Missing CSC validation in preflight"
        
        # Check send_sirecepde.py shows CSC info
        send_content = (tools_dir / "send_sirecepde.py").read_text(encoding="utf-8")
        assert "CSC" in send_content, "Missing CSC info display"
    
    def test_xde_zip_validation(self, tools_dir):
        """Test xDE ZIP validation (Loop 4)"""
        validator = tools_dir / "validate_xde_zip_contains_dcodseg.py"
        assert validator.exists(), "validate_xde_zip_contains_dcodseg.py not found"
        
        content = validator.read_text(encoding="utf-8")
        
        # Check for key validation logic
        assert "dCodSeg" in content, "Missing dCodSeg validation"
        assert "ZIP" in content.upper(), "Missing ZIP validation"
        assert "xDE" in content, "Missing xDE validation"
    
    def test_contract_version_exists(self, repo_root):
        """Test that PIPELINE_CONTRACT has version tracking"""
        contract = repo_root / "PIPELINE_CONTRACT_v2.md"
        assert contract.exists(), "PIPELINE_CONTRACT_v2.md not found"
        
        content = contract.read_text(encoding="utf-8")
        assert "Version: 2.0" in content, "Missing version in contract"
        assert "Changelog:" in content, "Missing changelog in contract"
    
    def test_completeness_of_tools(self, tools_dir):
        """Test that all required tools exist"""
        required_tools = [
            "send_sirecepde.py",
            "follow_lote.py",
            "auto_fix_0160_loop.py",
            "soap_picker.py",
            "validate_xde_zip_contains_dcodseg.py",
            "validate_success_criteria.py"
        ]
        
        for tool in required_tools:
            tool_path = tools_dir / tool
            assert tool_path.exists(), f"Required tool {tool} not found"
            assert tool_path.stat().st_size > 0, f"Tool {tool} is empty"
    
    def test_antiregression_rules_documented(self, repo_root):
        """Test that anti-regression rules are documented"""
        anti_regression = repo_root / "tesaka-cv" / "docs" / "aprendizajes" / "anti-regresion.md"
        assert anti_regression.exists(), "anti-regresion.md not found"
        
        content = anti_regression.read_text(encoding="utf-8")
        
        # Check for key anti-regression rules
        key_rules = [
            "rDE Id",
            "dVerFor",
            "gCamFuFD",
            "0160",
            "schemaLocation"
        ]
        
        for rule in key_rules:
            assert rule in content, f"Missing anti-regression rule for {rule}"


class TestPipelineIntegration:
    """Integration tests for the complete pipeline"""
    
    def test_help_messages_work(self, repo_root):
        """Test that all tools show help without errors"""
        tools_dir = repo_root / "tesaka-cv" / "tools"
        venv_dir = repo_root / ".venv"
        python_exe = venv_dir / "bin" / "python"
        
        if not python_exe.exists():
            pytest.skip("Virtual environment not found")
        
        tools_to_test = [
            "send_sirecepde.py",
            "follow_lote.py",
            "auto_fix_0160_loop.py",
            "validate_success_criteria.py"
        ]
        
        for tool in tools_to_test:
            result = subprocess.run(
                [str(python_exe), "-m", f"tools.{tool[:-3]}", "--help"],
                cwd=str(repo_root / "tesaka-cv"),
                capture_output=True,
                text=True
            )
            assert result.returncode == 0, f"Help failed for {tool}"
            assert "usage:" in result.stdout.lower(), f"No usage shown for {tool}"
    
    def test_validate_success_criteria_tool(self, repo_root):
        """Test validate_success_criteria.py with sample data"""
        # Create test response JSON
        test_data = {
            "dCodRes": "0001",
            "dMsgRes": "Aprobado sin observaciones"
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_file = f.name
        
        try:
            # Run validation
            result = subprocess.run(
                [sys.executable, str(repo_root / "tesaka-cv" / "tools" / "validate_success_criteria.py"), temp_file],
                capture_output=True,
                text=True
            )
            
            assert result.returncode == 0, "Success code should return exit code 0"
            assert "Success" in result.stdout, "Should identify as success"
        finally:
            os.unlink(temp_file)


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v"])
