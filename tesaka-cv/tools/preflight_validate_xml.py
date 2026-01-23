#!/usr/bin/env python3
"""
Preflight XML Validation Tool

Performs comprehensive validation of SIFEN XML files before submission.
Validates anti-regression rules, canonical order, and XSD compliance.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple, Optional
import re


class PreflightValidator:
    """Validates XML files for SIFEN compliance."""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.errors = []
        self.warnings = []
        
        # SIFEN namespace
        self.NS = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
        
    def log_error(self, message: str):
        """Log an error message."""
        self.errors.append(message)
        if self.verbose:
            print(f"❌ ERROR: {message}")
            
    def log_warning(self, message: str):
        """Log a warning message."""
        self.warnings.append(message)
        if self.verbose:
            print(f"⚠️  WARNING: {message}")
            
    def log_info(self, message: str):
        """Log an info message if verbose."""
        if self.verbose:
            print(f"ℹ️  INFO: {message}")
            
    def validate_rde_no_id(self, root: ET.Element) -> bool:
        """Validate that rDE element does not have Id attribute."""
        self.log_info("Checking rDE for Id attribute...")
        
        rde = root.find('.//sifen:rDE', self.NS)
        if rde is None:
            self.log_error("rDE element not found")
            return False
            
        if 'Id' in rde.attrib:
            self.log_error(f"rDE has Id attribute (forbidden): {rde.attrib['Id']}")
            return False
            
        self.log_info("✓ rDE correctly has no Id attribute")
        return True
        
    def validate_dverfor_first(self, root: ET.Element) -> bool:
        """Validate that dVerFor is the first child of rDE."""
        self.log_info("Checking dVerFor position...")
        
        rde = root.find('.//sifen:rDE', self.NS)
        if rde is None:
            self.log_error("rDE element not found")
            return False
            
        if len(rde) == 0:
            self.log_error("rDE has no children")
            return False
            
        first_child = rde[0]
        tag_name = first_child.tag.split('}')[-1] if '}' in first_child.tag else first_child.tag
        
        if tag_name != 'dVerFor':
            self.log_error(f"First child of rDE should be dVerFor, but is: {tag_name}")
            return False
            
        if first_child.text != '150':
            self.log_error(f"dVerFor should be '150', but is: {first_child.text}")
            return False
            
        self.log_info("✓ dVerFor correctly positioned as first child with value '150'")
        return True
        
    def validate_signature_namespace(self, root: ET.Element) -> bool:
        """Validate that Signature uses XMLDSig namespace."""
        self.log_info("Checking Signature namespace...")
        
        signature = root.find('.//{http://www.w3.org/2000/09/xmldsig#}Signature')
        if signature is None:
            self.log_error("Signature element not found")
            return False
            
        if 'http://www.w3.org/2000/09/xmldsig#' not in signature.tag:
            self.log_error(f"Signature should use XMLDSig namespace, but has: {signature.tag}")
            return False
            
        self.log_info("✓ Signature uses correct XMLDSig namespace")
        return True
        
    def validate_dcodseg_format(self, root: ET.Element) -> bool:
        """Validate dCodSeg format if present."""
        self.log_info("Checking dCodSeg format...")
        
        dCodSeg = root.find('.//sifen:dCodSeg', self.NS)
        if dCodSeg is None:
            self.log_warning("dCodSeg not found in XML (may be in ZIP)")
            return True
            
        if dCodSeg.text is None:
            self.log_error("dCodSeg element has no text")
            return False
            
        if not re.match(r'^\d{9}$', dCodSeg.text):
            self.log_error(f"dCodSeg must be exactly 9 digits, but is: '{dCodSeg.text}'")
            return False
            
        self.log_info(f"✓ dCodSeg has correct format: {dCodSeg.text}")
        return True
        
    def validate_qr_format(self, root: ET.Element) -> bool:
        """Validate QR URL format if present."""
        self.log_info("Checking QR format...")
        
        qr = root.find('.//sifen:dCarQR', self.NS)
        if qr is None:
            self.log_warning("QR (dCarQR) not found in XML")
            return True
            
        qr_text = qr.text or ''
        
        if '?nVersion=' not in qr_text:
            self.log_error(f"QR must contain '?nVersion=', but has: {qr_text}")
            return False
            
        if '/qrnVersion=' in qr_text:
            self.log_error(f"QR has malformed '/qrnVersion=' (missing '?'): {qr_text}")
            return False
            
        self.log_info("✓ QR has correct format with '?nVersion='")
        return True
        
    def validate_gtotsub_order(self, root: ET.Element) -> bool:
        """Validate canonical order of gTotSub elements without rewriting."""
        self.log_info("Checking gTotSub canonical order...")
        
        gTotSub = root.find('.//sifen:gTotSub', self.NS)
        if gTotSub is None:
            self.log_error("gTotSub element not found")
            return False
            
        # Expected order according to anti-regression rules
        expected_order = [
            'dTotGralOpe', 'dTotGravadas', 'dTotIVA', 'dTotSubExe', 'dTotSubExo',
            'dTotSubNS', 'dTotSubIVA', 'dTotOtrosTrib', 'dTotVtaOper', 'dTotDesc',
            'dTotDescGlob', 'dTotAnticipo', 'dTotReteIVA', 'dTotReteRenta',
            'dTotPerceps', 'dTotCompraTotal', 'dTotVtaNGrav', 'dTotVtaExe',
            'dTotVtaExo', 'dTotVtaNS', 'dTotIVAComp', 'dTotRetenido',
            'dTotReembolso', 'dTotDescItem', 'dTotAntItem'
        ]
        
        actual_order = []
        for child in gTotSub:
            tag_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
            actual_order.append(tag_name)
            
        # Check if all expected elements are present in order
        missing = []
        out_of_order = []
        
        expected_idx = 0
        for actual in actual_order:
            if actual in expected_order:
                expected_idx = expected_order.index(actual, expected_idx)
                if expected_idx != len(expected_order):
                    expected_idx += 1
            else:
                # Unexpected element
                pass
                
        # Check for missing required elements
        for expected in expected_order:
            if expected not in actual_order:
                missing.append(expected)
                
        if missing:
            self.log_warning(f"Missing gTotSub elements: {', '.join(missing)}")
            
        # Check order of present elements
        present_expected = [e for e in expected_order if e in actual_order]
        actual_filtered = [a for a in actual_order if a in expected_order]
        
        if present_expected != actual_filtered:
            self.log_warning("gTotSub elements are not in canonical order")
            if self.verbose:
                print(f"  Expected: {present_expected}")
                print(f"  Actual:   {actual_filtered}")
        else:
            self.log_info("✓ gTotSub elements are in canonical order")
            
        return True  # Warning only, not failure
        
    def validate_xsd_compliance(self, xml_path: Path) -> bool:
        """Validate XML against XSD if available (best-effort)."""
        self.log_info("Checking XSD validation (best-effort)...")
        
        # Try to find XSD schema
        xsd_paths = [
            Path("schemas_sifen/rLoteDE_v150.xsd"),
            Path("../schemas_sifen/rLoteDE_v150.xsd"),
            Path("tesaka-cv/schemas_sifen/rLoteDE_v150.xsd"),
        ]
        
        xsd_path = None
        for path in xsd_paths:
            if path.exists():
                xsd_path = path
                break
                
        if xsd_path is None:
            self.log_warning("XSD schema not found, skipping XSD validation")
            return True
            
        try:
            from lxml import etree
            
            # Load XSD
            xml_schema_doc = etree.parse(str(xsd_path))
            xml_schema = etree.XMLSchema(xml_schema_doc)
            
            # Load XML
            xml_doc = etree.parse(str(xml_path))
            
            # Validate
            if xml_schema.validate(xml_doc):
                self.log_info("✓ XML is valid against XSD")
                return True
            else:
                self.log_error("XML is not valid against XSD")
                if self.verbose:
                    for error in xml_schema.error_log:
                        print(f"  XSD Error: {error}")
                return False
                
        except ImportError:
            self.log_warning("lxml not installed, skipping XSD validation")
            return True
        except Exception as e:
            self.log_warning(f"XSD validation failed: {e}")
            return True
            
    def validate_xml_file(self, xml_path: Path) -> bool:
        """Perform all validations on an XML file."""
        self.log_info(f"Validating XML file: {xml_path}")
        
        if not xml_path.exists():
            self.log_error(f"XML file not found: {xml_path}")
            return False
            
        try:
            # Parse XML
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Run all validations
            all_valid = True
            
            all_valid &= self.validate_rde_no_id(root)
            all_valid &= self.validate_dverfor_first(root)
            all_valid &= self.validate_signature_namespace(root)
            all_valid &= self.validate_dcodseg_format(root)
            all_valid &= self.validate_qr_format(root)
            all_valid &= self.validate_gtotsub_order(root)
            all_valid &= self.validate_xsd_compliance(xml_path)
            
            return all_valid
            
        except ET.ParseError as e:
            self.log_error(f"XML parsing error: {e}")
            return False
        except Exception as e:
            self.log_error(f"Unexpected error: {e}")
            return False
            
    def print_summary(self):
        """Print validation summary."""
        print("\n" + "="*60)
        print("PREFLIGHT VALIDATION SUMMARY")
        print("="*60)
        
        if not self.errors and not self.warnings:
            print("✅ All validations passed!")
            return True
            
        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"  - {error}")
                
        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"  - {warning}")
                
        if self.errors:
            print("\n❌ VALIDATION FAILED - Fix errors before proceeding")
            return False
        else:
            print("\n⚠️  VALIDATION PASSED WITH WARNINGS")
            return True


def main():
    parser = argparse.ArgumentParser(
        description="Validate SIFEN XML files before submission",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --xml artifacts/last_lote.xml
  %(prog)s --xml lote.xml --verbose
  %(prog)s --xml /path/to/lote.xml --check-only
        """
    )
    
    parser.add_argument(
        '--xml', '-x',
        required=True,
        help="Path to XML file to validate"
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help="Verbose output"
    )
    
    parser.add_argument(
        '--check-only',
        action='store_true',
        help="Only check, don't print summary (useful for scripts)"
    )
    
    args = parser.parse_args()
    
    # Create validator
    validator = PreflightValidator(verbose=args.verbose)
    
    # Validate XML
    xml_path = Path(args.xml)
    success = validator.validate_xml_file(xml_path)
    
    # Print summary unless check-only
    if not args.check_only:
        validator.print_summary()
        
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
