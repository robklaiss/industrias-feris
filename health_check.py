#!/usr/bin/env python3
"""
Health Check - SIFEN Pipeline Environment Diagnosis

Verifica rápidamente que el ambiente está configurado correctamente
para operar el pipeline de SIFEN.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple
import importlib.util


class HealthChecker:
    """Checks the health of the SIFEN pipeline environment."""
    
    def __init__(self):
        self.results = {}
        self.warnings = []
        self.errors = []
        
    def check_python_version(self) -> bool:
        """Check Python version >= 3.9."""
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 9):
            self.errors.append(f"Python {version.major}.{version.minor} is too old (need >= 3.9)")
            return False
        self.results["python_version"] = f"{version.major}.{version.minor}.{version.micro}"
        return True
        
    def check_venv(self) -> bool:
        """Check we're in a virtual environment."""
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            venv_path = sys.prefix
            self.results["venv_path"] = venv_path
            return True
        else:
            self.warnings.append("Not running in a virtual environment")
            return False
            
    def check_required_packages(self) -> bool:
        """Check required packages are installed."""
        required = [
            "requests", "lxml", "zeep", "click", 
            "pytest", "cryptography", "xmlsec"
        ]
        missing = []
        installed = {}
        
        for package in required:
            spec = importlib.util.find_spec(package)
            if spec is None:
                missing.append(package)
            else:
                # Try to get version
                try:
                    module = importlib.import_module(package)
                    version = getattr(module, '__version__', 'unknown')
                    installed[package] = version
                except:
                    installed[package] = 'installed'
                    
        if missing:
            self.errors.append(f"Missing packages: {', '.join(missing)}")
            
        self.results["packages"] = installed
        return len(missing) == 0
        
    def check_sifen_environment(self) -> bool:
        """Check SIFEN environment variables."""
        required_vars = {
            "prod": ["SIFEN_PROD_CSC", "SIFEN_PROD_CSC_ID"],
            "test": ["SIFEN_TEST_CSC", "SIFEN_TEST_CSC_ID"]
        }
        
        env_status = {}
        has_errors = False
        
        for env, vars_list in required_vars.items():
            env_status[env] = {}
            for var in vars_list:
                value = os.environ.get(var)
                if value:
                    env_status[env][var] = f"✓ Set (len={len(value)})"
                else:
                    env_status[env][var] = "✗ Not set"
                    if env == "prod":
                        has_errors = True
                        
        if has_errors:
            self.errors.append("Production SIFEN variables not set")
            
        self.results["sifen_env"] = env_status
        return not has_errors
        
    def check_certificates(self) -> bool:
        """Check certificate files exist."""
        cert_paths = [
            "tesaka-cv/certs/test_cert.pem",
            "tesaka-cv/certs/test_key.pem",
            "tesaka-cv/certs/prod_cert.p12",
        ]
        
        cert_status = {}
        has_missing = False
        
        for cert_path in cert_paths:
            path = Path(cert_path)
            if path.exists():
                cert_status[cert_path] = f"✓ Exists ({path.stat().st_size} bytes)"
            else:
                cert_status[cert_path] = "✗ Missing"
                if "prod" in cert_path:
                    self.warnings.append(f"Production certificate missing: {cert_path}")
                else:
                    has_missing = True
                    
        if has_missing:
            self.errors.append("Test certificates missing")
            
        self.results["certificates"] = cert_status
        return not has_missing
        
    def check_tools_exist(self) -> bool:
        """Check required tool scripts exist."""
        tools = [
            "tesaka-cv/tools/send_sirecepde.py",
            "tesaka-cv/tools/follow_lote.py",
            "tesaka-cv/tools/auto_fix_0160_loop.py",
            "tesaka-cv/tools/preflight_validate_xml.py",
            "tesaka-cv/tools/soap_picker.py",
        ]
        
        tool_status = {}
        has_missing = False
        
        for tool in tools:
            path = Path(tool)
            if path.exists():
                tool_status[tool] = "✓ Exists"
            else:
                tool_status[tool] = "✗ Missing"
                has_missing = True
                
        if has_missing:
            self.errors.append("Required tools missing")
            
        self.results["tools"] = tool_status
        return not has_missing
        
    def check_schemas(self) -> bool:
        """Check XSD schemas are available."""
        schema_paths = [
            "tesaka-cv/schemas_sifen/rLoteDE_v150.xsd",
            "schemas_sifen/rLoteDE_v150.xsd",
        ]
        
        for schema_path in schema_paths:
            if Path(schema_path).exists():
                self.results["schema"] = f"✓ Found at {schema_path}"
                return True
                
        self.warnings.append("XSD schemas not found - XSD validation will be skipped")
        return False
        
    def check_connectivity(self) -> bool:
        """Check basic connectivity to SIFEN endpoints."""
        endpoints = {
            "prod": "https://sifen.set.gov.py/recibe-lote",
            "test": "https://test.sifen.set.gov.py/recibe-lote",
        }
        
        import requests
        from requests.exceptions import RequestException
        
        conn_status = {}
        
        for env, url in endpoints.items():
            try:
                # Just check if we can reach the host
                response = requests.head(url, timeout=5)
                if response.status_code < 500:
                    conn_status[env] = f"✓ Reachable (HTTP {response.status_code})"
                else:
                    conn_status[env] = f"⚠ Server error (HTTP {response.status_code})"
            except RequestException as e:
                conn_status[env] = f"✗ Unreachable: {str(e)[:50]}"
                
        self.results["connectivity"] = conn_status
        return True  # Don't fail the check for connectivity
        
    def run_all_checks(self) -> bool:
        """Run all health checks."""
        print("🏥 SIFEN Pipeline Health Check")
        print("=" * 50)
        
        checks = [
            ("Python Version", self.check_python_version),
            ("Virtual Environment", self.check_venv),
            ("Required Packages", self.check_required_packages),
            ("SIFEN Environment", self.check_sifen_environment),
            ("Certificates", self.check_certificates),
            ("Tools", self.check_tools_exist),
            ("Schemas", self.check_schemas),
            ("Connectivity", self.check_connectivity),
        ]
        
        all_passed = True
        
        for name, check_func in checks:
            print(f"\n🔍 Checking {name}...")
            try:
                passed = check_func()
                if not passed:
                    all_passed = False
            except Exception as e:
                print(f"❌ Error checking {name}: {e}")
                all_passed = False
                
        return all_passed
        
    def print_summary(self):
        """Print health check summary."""
        print("\n" + "=" * 50)
        print("HEALTH CHECK SUMMARY")
        print("=" * 50)
        
        # Print results
        for category, data in self.results.items():
            print(f"\n📊 {category.upper()}:")
            if isinstance(data, dict):
                for key, value in data.items():
                    print(f"  {key}: {value}")
            else:
                print(f"  {data}")
                
        # Print warnings
        if self.warnings:
            print("\n⚠️  WARNINGS:")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        # Print errors
        if self.errors:
            print("\n❌ ERRORS:")
            for error in self.errors:
                print(f"  - {error}")
                
        # Overall status
        print("\n" + "=" * 50)
        if self.errors:
            print("❌ ENVIRONMENT NOT HEALTHY")
            print("Fix the errors above before using the pipeline")
        else:
            print("✅ ENVIRONMENT HEALTHY")
            if self.warnings:
                print("(Some warnings detected, but pipeline should work)")
            else:
                print("(All checks passed)")
                
                
def main():
    """Run health check."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Check SIFEN pipeline environment health")
    parser.add_argument("--fix", action="store_true", help="Show suggestions for fixing issues")
    args = parser.parse_args()
    
    checker = HealthChecker()
    healthy = checker.run_all_checks()
    
    checker.print_summary()
    
    if args.fix and checker.errors:
        print("\n" + "=" * 50)
        print("SUGGESTED FIXES")
        print("=" * 50)
        
        # Suggest fixes for common issues
        if "Missing packages" in str(checker.errors):
            print("\n📦 Install missing packages:")
            print("  .venv/bin/pip install -r requirements.txt")
            
        if "Production SIFEN variables not set" in str(checker.errors):
            print("\n🔐 Set production variables:")
            print("  export SIFEN_PROD_CSC='your_32_char_csc'")
            print("  export SIFEN_PROD_CSC_ID='your_4_char_id'")
            
        if "Test certificates missing" in str(checker.errors):
            print("\n📜 Generate test certificates:")
            print("  # Follow the documentation in tesaka-cv/certs/")
            
        if "Required tools missing" in str(checker.errors):
            print("\n🛠️  Ensure you're in the correct directory:")
            print("  cd /path/to/industrias-feris-facturacion-electronica-simplificado")
            
    sys.exit(0 if healthy else 1)


if __name__ == "__main__":
    main()
