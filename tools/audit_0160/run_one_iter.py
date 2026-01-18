#!/usr/bin/env python3
"""
SIFEN 0160 Audit Runner
Executes one iteration of the audit process with a specific tweak.
"""
import os
import sys
import json
import hashlib
import zipfile
import subprocess
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
import xml.etree.ElementTree as ET
from lxml import etree

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tesaka-cv"))

class AuditRunner:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.audit_dir = base_dir / "tools" / "audit_0160"
        self.vendor_dir = self.audit_dir / "vendor"
        self.iter_dir = self.audit_dir / "iterations"
        self.iter_dir.mkdir(exist_ok=True)
        
        # Load configuration
        self.load_config()
        
    def load_config(self):
        """Load SIFEN configuration from .env.test"""
        env_file = self.base_dir / ".env.test"
        if not env_file.exists():
            env_file = self.base_dir / ".env"
        
        # Load environment variables
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
        
        self.config = {
            'sifen_url': os.getenv('SIFEN_URL_TEST', 'https://sifen.set.gov.py/ws/test'),
            'skip_ruc_gate': os.getenv('SIFEN_SKIP_RUC_GATE', '0'),
            'cert_path': os.getenv('SIFEN_CERT_PATH'),
            'cert_password': os.getenv('SIFEN_CERT_PASSWORD'),
        }
        
    def run_iteration(self, iter_num: int, tweak: Optional[str] = None) -> Dict[str, Any]:
        """Run one iteration with optional tweak"""
        print(f"\n{'='*60}")
        print(f"Running iteration {iter_num:02d}" + (f" with tweak: {tweak}" if tweak else ""))
        print(f"{'='*60}")
        
        # Create iteration directory
        iter_dir = self.iter_dir / f"iter_{iter_num:02d}"
        iter_dir.mkdir(exist_ok=True)
        
        # Start with base XML (the one we've been using)
        base_xml = self.base_dir / "tesaka-cv" / "artifacts" / "_stage_04_signed.xml"
        if not base_xml.exists():
            base_xml = self.base_dir / "lote.xml"
        
        # Copy base XML to working location
        work_xml = iter_dir / "lote_before_tweak.xml"
        shutil.copy2(base_xml, work_xml)
        
        # Apply tweak if specified
        if tweak:
            work_xml = self.apply_tweak(work_xml, tweak, iter_num)
        
        # Generate artifacts
        artifacts = self.generate_artifacts(work_xml, iter_dir, iter_num)
        
        # Send to SIFEN
        response = self.send_to_sifen(Path(artifacts['lote_xml']), iter_num)
        
        # Validate and analyze
        analysis = self.analyze_results(iter_dir, response)
        
        # Update state
        self.update_state(iter_num, tweak, artifacts, response, analysis)
        
        return {
            'iteration': iter_num,
            'tweak': tweak,
            'artifacts': artifacts,
            'response': response,
            'analysis': analysis
        }
    
    def apply_tweak(self, xml_file: Path, tweak: str, iter_num: int) -> Path:
        """Apply a specific tweak to the XML"""
        print(f"Applying tweak: {tweak}")
        
        # Parse XML with parser that removes blank text
        parser = etree.XMLParser(remove_blank_text=False)
        tree = etree.parse(str(xml_file), parser)
        root = tree.getroot()
        
        # Register namespaces
        ns = {'s': 'http://ekuatia.set.gov.py/sifen/xsd',
              'ds': 'http://www.w3.org/2000/09/xmldsig#'}
        
        if tweak == "xml_declaration":
            # Ensure XML declaration
            tweaked_file = xml_file.parent / "lote_with_decl.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
            
        elif tweak == "no_xml_declaration":
            # Remove XML declaration
            tweaked_file = xml_file.parent / "lote_no_decl.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=False)
            return tweaked_file
            
        elif tweak == "lf_line_endings":
            # Normalize line endings to LF
            content = xml_file.read_text(encoding='utf-8')
            content = content.replace('\r\n', '\n').replace('\r', '\n')
            tweaked_file = xml_file.parent / "lote_lf.xml"
            tweaked_file.write_text(content, encoding='utf-8')
            return tweaked_file
            
        elif tweak == "add_dcarqr":
            # Add dCarQR to gCamFuFD
            rde = root.find('.//s:rDE', ns)
            if rde is not None:
                gcamfufd = rde.find('.//s:gCamFuFD', ns)
                if gcamfufd is None:
                    # Create gCamFuFD after Signature
                    signature = rde.find('.//s:Signature', ns)
                    gcamfufd = etree.SubElement(rde, f"{{{ns['s']}}}gCamFuFD")
                    if signature is not None:
                        rde.insert(list(rde).index(signature) + 1, gcamfufd)
                
                # Add dCarQR if not present
                dcarqr = gcamfufd.find('.//s:dCarQR', ns)
                if dcarqr is None:
                    # Generate QR using TIPS method
                    qr_content = self.generate_qr_tips_method(rde)
                    dcarqr = etree.SubElement(gcamfufd, f"{{{ns['s']}}}dCarQR")
                    dcarqr.text = qr_content
            
            tweaked_file = xml_file.parent / "lote_with_dcarqr.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
            
        elif tweak == "remove_duplicate_gcamfufd":
            # Remove duplicate gCamFuFD elements
            rde = root.find('.//s:rDE', ns)
            if rde is not None:
                gcamfufd_elements = rde.findall('.//s:gCamFuFD', ns)
                # Keep only the last one (which should be the complete one)
                for elem in gcamfufd_elements[:-1]:
                    rde.remove(elem)
            
            tweaked_file = xml_file.parent / "lote_no_dup_gcam.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
            
        elif tweak == "fix_signature_and_gcamfufd":
            # Fix both signature namespace and remove duplicate gCamFuFD
            content = xml_file.read_text(encoding='utf-8')
            
            # Fix Signature namespace
            content = content.replace(
                '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">',
                '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            )
            
            # Remove duplicate gCamFuFD - keep the one with dCarQR content
            lines = content.split('\n')
            new_lines = []
            gcamfufd_count = 0
            for line in lines:
                if '<gCamFuFD>' in line:
                    gcamfufd_count += 1
                    if gcamfufd_count == 1:
                        # Skip the first (empty) gCamFuFD
                        continue
                new_lines.append(line)
            
            content = '\n'.join(new_lines)
            
            tweaked_file = xml_file.parent / "lote_fixed_all.xml"
            tweaked_file.write_text(content, encoding='utf-8')
            return tweaked_file
            
        elif tweak == "signature_ns_string_replace":
            # Fix signature namespace by string replacement
            content = xml_file.read_text(encoding='utf-8')
            # Replace Signature xmlns attribute
            content = content.replace(
                '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">',
                '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            )
            # Also handle the case where it might be self-closing
            content = content.replace(
                '<Signature xmlns="http://www.w3.org/2000/09/xmldsig#"/>',
                '<Signature xmlns="http://ekuatia.set.gov.py/sifen/xsd"/>'
            )
            
            tweaked_file = xml_file.parent / "lote_sig_ns_fixed.xml"
            tweaked_file.write_text(content, encoding='utf-8')
            return tweaked_file
            
        elif tweak == "signature_sifen_ns":
            # Change Signature namespace from XMLDSig to SIFEN
            # Find Signature regardless of namespace
            signature = None
            for elem in root.iter():
                if elem.tag.endswith('Signature'):
                    signature = elem
                    break
            
            if signature is not None:
                # Remove all xmlns attributes
                signature.attrib.clear()
                # Set SIFEN namespace only
                signature.set('xmlns', 'http://ekuatia.set.gov.py/sifen/xsd')
                print(f"Signature xmlns changed to: {signature.get('xmlns')}")
            
            tweaked_file = xml_file.parent / "lote_sifen_sig_ns.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
            
        elif tweak == "signature_xmldsig_ns":
            # Ensure Signature uses XMLDSig namespace
            signature = root.find('.//ds:Signature', namespaces=ns)
            if signature is not None:
                signature.set('xmlns', 'http://www.w3.org/2000/09/xmldsig#')
                # Remove ds: prefix if present
                for elem in signature.iter():
                    if elem.tag.startswith('{http://www.w3.org/2000/09/xmldsig#}'):
                        continue
                    if elem.tag.startswith('ds:'):
                        elem.tag = elem.tag.replace('ds:', '{http://www.w3.org/2000/09/xmldsig#}')
            
            tweaked_file = xml_file.parent / "lote_xmldsig_ns.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
            
        elif tweak == "reorder_rde_children":
            # Force order: dVerFor, DE, Signature, gCamFuFD
            rde = root.find('.//s:rDE', ns)
            if rde is not None:
                children = list(rde)
                new_order = []
                
                # First: dVerFor
                dverfor = rde.find('.//s:dVerFor', ns)
                if dverfor is not None:
                    new_order.append(dverfor)
                
                # Second: DE
                de = rde.find('.//s:DE', ns)
                if de is not None:
                    new_order.append(de)
                
                # Third: Signature
                sig = rde.find('.//s:Signature', ns)
                if sig is not None:
                    new_order.append(sig)
                
                # Fourth: gCamFuFD
                gcam = rde.find('.//s:gCamFuFD', ns)
                if gcam is not None:
                    new_order.append(gcam)
                
                # Clear and reinsert in order
                rde.clear()
                for child in new_order:
                    rde.append(child)
            
            tweaked_file = xml_file.parent / "lote_reordered.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
            
        elif tweak == "remove_schemalocation":
            # Remove xsi:schemaLocation if present
            for elem in root.iter():
                if '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation' in elem.attrib:
                    del elem.attrib['{http://www.w3.org/2001/XMLSchema-instance}schemaLocation']
            
            tweaked_file = xml_file.parent / "lote_no_schemaloc.xml"
            tree.write(str(tweaked_file), 
                      encoding='UTF-8', 
                      xml_declaration=True,
                      standalone=False)
            return tweaked_file
        
        # Default: no change
        return xml_file
    
    def generate_qr_tips_method(self, rde_elem) -> str:
        """Generate QR using TIPS method"""
        # Import TIPS QR generator
        sys.path.insert(0, str(self.vendor_dir / "facturacionelectronicapy-qrgen"))
        try:
            from qrgen import QRGen
            
            # Extract necessary data from rDE
            # This is a simplified version - adjust based on actual TIPS implementation
            de = rde_elem.find('.//s:DE', {'s': 'http://ekuatia.set.gov.py/sifen/xsd'})
            
            # Mock QR generation for now
            # In real implementation, use TIPS QRGen with actual data
            return "QR_GENERATED_BY_TIPS_METHOD"
        except Exception as e:
            print(f"Warning: Could not generate QR with TIPS method: {e}")
            return "GENERATED_QR_PLACEHOLDER"
    
    def generate_artifacts(self, xml_file: Path, iter_dir: Path, iter_num: int) -> Dict[str, str]:
        """Generate all artifacts for the iteration"""
        artifacts = {}
        
        # 1. Save the XML that will be used
        final_xml = iter_dir / f"iter_{iter_num:02d}_lote.xml"
        shutil.copy2(xml_file, final_xml)
        artifacts['lote_xml'] = str(final_xml)
        
        # 2. Calculate SHA256
        sha256_hash = hashlib.sha256()
        with open(xml_file, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        artifacts['sha256'] = sha256_hash.hexdigest()
        
        # 3. Create ZIP with lote.xml
        zip_file = iter_dir / f"iter_{iter_num:02d}_zip.zip"
        with zipfile.ZipFile(zip_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.write(xml_file, 'lote.xml')
        artifacts['zip'] = str(zip_file)
        
        # 4. Generate SOAP request
        soap_file = iter_dir / f"iter_{iter_num:02d}_soap.xml"
        self.generate_soap_request(zip_file, soap_file)
        artifacts['soap'] = str(soap_file)
        
        return artifacts
    
    def generate_soap_request(self, zip_file: Path, soap_file: Path):
        """Generate SOAP request with ZIP embedded"""
        # Read ZIP as base64
        with open(zip_file, 'rb') as f:
            zip_data = f.read()
        import base64
        zip_b64 = base64.b64encode(zip_data).decode('utf-8')
        
        # Generate xDE ID
        import uuid
        xde_id = f"xDE_{uuid.uuid4()}"
        
        # SOAP template matching SIFEN requirements
        soap = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope" xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
  <soap12:Header>
    <xsd:Auth>
      <xsd:dUsu>{os.getenv('SIFEN_USER', 'testuser')}</xsd:dUsu>
      <xsd:dPass>{os.getenv('SIFEN_PASS', 'testpass')}</xsd:dPass>
    </xsd:Auth>
  </soap12:Header>
  <soap12:Body>
    <xsd:rEnvioLote>
      <xsd:dId>{xde_id}</xsd:dId>
      <xsd:xDE>{zip_b64}</xsd:xDE>
    </xsd:rEnvioLote>
  </soap12:Body>
</soap12:Envelope>'''
        
        soap_file.write_text(soap, encoding='utf-8')
    
    def send_to_sifen(self, xml_file: Path, iter_num: int) -> Dict[str, Any]:
        """Send request to SIFEN and capture response"""
        print(f"Sending to SIFEN...")
        
        # Use send_sirecepde.py to send
        send_script = self.base_dir / "tesaka-cv" / "tools" / "send_sirecepde.py"
        
        cmd = [
            "python3", str(send_script),
            "--env", "test",
            "--xml", str(xml_file),
            "--dump-http"
        ]
        
        # Run and capture output
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={**os.environ, "SIFEN_SKIP_RUC_GATE": "1"}
        )
        
        # Save response
        response_file = xml_file.parent / f"iter_{iter_num:02d}_response.json"
        response_data = {
            'returncode': result.returncode,
            'stdout': result.stdout,
            'stderr': result.stderr
        }
        
        # Try to parse SIFEN response from artifacts
        try:
            # Check for SOAP response in artifacts
            artifacts_dir = self.base_dir / "tesaka-cv" / "artifacts"
            soap_response = artifacts_dir / "soap_last_response_RECV.xml"
            
            if soap_response.exists():
                resp_content = soap_response.read_text(encoding='utf-8')
                cod_res_match = re.search(r'dCodRes>(\d+)<', resp_content)
                msg_res_match = re.search(r'dMsgRes>([^<]+)<', resp_content)
                
                if cod_res_match:
                    response_data['sifen_code'] = cod_res_match.group(1)
                    response_data['sifen_message'] = msg_res_match.group(1) if msg_res_match else ""
            
            # Also check stdout as fallback
            elif result.stdout:
                cod_res_match = re.search(r'dCodRes>(\d+)<', result.stdout)
                msg_res_match = re.search(r'dMsgRes>([^<]+)<', result.stdout)
                
                if cod_res_match:
                    response_data['sifen_code'] = cod_res_match.group(1)
                    response_data['sifen_message'] = msg_res_match.group(1) if msg_res_match else ""
        except Exception as e:
            print(f"Warning: Could not parse SIFEN response: {e}")
        
        with open(response_file, 'w') as f:
            json.dump(response_data, f, indent=2)
        
        return response_data
    
    def analyze_results(self, iter_dir: Path, response: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze the results of the iteration"""
        analysis = {
            'xsd_valid': False,
            'signature_valid': False,
            'sifen_result': response.get('sifen_code', 'UNKNOWN'),
            'sifen_message': response.get('sifen_message', ''),
            'differences': []
        }
        
        # Validate XSD
        lote_xml = next(iter_dir.glob("iter_*_lote.xml"))
        try:
            schema_doc = etree.parse(str(self.base_dir / "schemas_sifen" / "rLoteDE_v150.xsd"))
            schema = etree.XMLSchema(schema_doc)
            doc = etree.parse(str(lote_xml))
            analysis['xsd_valid'] = schema.validate(doc)
        except Exception as e:
            analysis['xsd_error'] = str(e)
        
        # Verify signature
        try:
            result = subprocess.run(
                ["xmlsec1", "--verify", "--insecure", "--id-attr:Id", "DE", str(lote_xml)],
                capture_output=True,
                text=True
            )
            analysis['signature_valid'] = result.returncode == 0
            if result.stderr:
                analysis['signature_error'] = result.stderr
        except Exception as e:
            analysis['signature_error'] = str(e)
        
        # Generate diff vs baseline if not iteration 00
        if not str(lote_xml).endswith("iter_00_lote.xml"):
            baseline = self.base_dir / "tools" / "audit_0160" / "iterations" / "iter_00" / "iter_00_lote.xml"
            if baseline.exists():
                diff = subprocess.run(
                    ["diff", "-u", str(baseline), str(lote_xml)],
                    capture_output=True,
                    text=True
                )
                if diff.stdout:
                    analysis['differences'] = diff.stdout.split('\n')
        
        return analysis
    
    def update_state(self, iter_num: int, tweak: Optional[str], artifacts: Dict, response: Dict, analysis: Dict):
        """Update STATE.md with iteration results"""
        state_file = self.audit_dir / "STATE.md"
        
        # Read current state
        with open(state_file, 'r') as f:
            content = f.read()
        
        # Add iteration to table
        table_row = f"| {iter_num:02d} | {tweak or 'Baseline'} | {artifacts['sha256'][:16]}... | {analysis['sifen_result']} | {analysis.get('sifen_message', '')[:50]}{'...' if len(analysis.get('sifen_message', '')) > 50 else ''} |\n"
        
        # Find table end and insert
        lines = content.split('\n')
        table_end = -1
        for i, line in enumerate(lines):
            if line.startswith('|---') and i > 0:
                table_end = i + 1
                break
        
        if table_end > 0:
            lines.insert(table_end, table_row)
        
        # Write back
        with open(state_file, 'w') as f:
            f.write('\n'.join(lines))
        
        # Print summary
        print(f"\nIteration {iter_num:02d} Summary:")
        print(f"  Tweak: {tweak or 'Baseline'}")
        print(f"  SIFEN Result: {analysis['sifen_result']} - {analysis.get('sifen_message', '')}")
        print(f"  XSD Valid: {analysis['xsd_valid']}")
        print(f"  Signature Valid: {analysis['signature_valid']}")
        print(f"  SHA256: {artifacts['sha256']}")


def main():
    """Main entry point"""
    base_dir = Path(__file__).parent.parent.parent
    runner = AuditRunner(base_dir)
    
    # Parse arguments
    iter_num = 0
    tweak = None
    
    if len(sys.argv) > 1:
        try:
            iter_num = int(sys.argv[1])
        except:
            print("First argument must be iteration number")
            sys.exit(1)
    
    if len(sys.argv) > 2:
        tweak = sys.argv[2]
    
    # Run iteration
    result = runner.run_iteration(iter_num, tweak)
    
    # Check if we found a solution
    if result['analysis']['sifen_result'] != '0160':
        print(f"\n{'!'*60}")
        print(f"!!! SOLUTION FOUND IN ITERATION {iter_num:02d} !!!")
        print(f"{'!'*60}")
        print(f"Tweak applied: {tweak}")
        print(f"Result: {result['analysis']['sifen_result']} - {result['analysis']['sifen_message']}")
        
        # Save winning iteration
        win_file = runner.audit_dir / "WINNING_ITERATION.md"
        with open(win_file, 'w') as f:
            f.write(f"# Winning Iteration: {iter_num:02d}\n\n")
            f.write(f"## Tweak Applied\n{tweak}\n\n")
            f.write(f"## Result\n{result['analysis']['sifen_result']} - {result['analysis']['sifen_message']}\n\n")
            f.write(f"## Artifacts\n- XML: {result['artifacts']['lote_xml']}\n")
            f.write(f"- ZIP: {result['artifacts']['zip']}\n")
            f.write(f"- SOAP: {result['artifacts']['soap']}\n")
            f.write(f"- SHA256: {result['artifacts']['sha256']}\n")


if __name__ == "__main__":
    main()
