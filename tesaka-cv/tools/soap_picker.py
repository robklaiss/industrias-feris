#!/usr/bin/env python3
"""
SOAP Picker - Unified SOAP file selector

Single source of truth for selecting the "real" SOAP file
that was actually sent to SIFEN.
"""

import argparse
import re
from pathlib import Path
from typing import Optional, List
from datetime import datetime


def pick_real_soap(artifacts_dir: Optional[Path] = None) -> Optional[Path]:
    """
    Pick the real SOAP file following these rules:
    1. If soap_last_request_REAL.xml exists, use it
    2. Otherwise, find the newest file containing <xDE> tag
    """
    if artifacts_dir is None:
        # Default to common artifacts directories
        for possible_dir in ["artifacts", "tesaka-cv/artifacts", "."]:
            if Path(possible_dir).exists():
                artifacts_dir = Path(possible_dir)
                break
                
    if not artifacts_dir or not artifacts_dir.exists():
        return None
        
    # Rule 1: Look for soap_last_request_REAL.xml
    real_soap = artifacts_dir / "soap_last_request_REAL.xml"
    if real_soap.exists():
        return real_soap
        
    # Rule 2: Find newest file with <xDE> tag
    soap_files = []
    for soap_file in artifacts_dir.glob("*.xml"):
        if "soap" in soap_file.name.lower():
            # Check if contains <xDE> tag (avoid false positives like <abcxDE>)
            try:
                content = soap_file.read_text(encoding='utf-8')
                if re.search(r'<xDE[^>]*>', content):
                    soap_files.append((soap_file, soap_file.stat().st_mtime))
            except:
                pass
                
    # Sort by modification time, newest first
    soap_files.sort(key=lambda x: x[1], reverse=True)
    
    if soap_files:
        return soap_files[0][0]
        
    return None
    
    
def pick_real_soap_path(artifacts_dir: Optional[Path] = None) -> Optional[str]:
    """Return the path as string, or None if not found."""
    soap_path = pick_real_soap(artifacts_dir)
    return str(soap_path) if soap_path else None
    
    
def list_soap_files(artifacts_dir: Path) -> List[Path]:
    """List all SOAP files in the directory with their info."""
    soap_files = []
    
    for soap_file in artifacts_dir.glob("*.xml"):
        if "soap" in soap_file.name.lower():
            try:
                stat = soap_file.stat()
                has_xde = False
                try:
                    content = soap_file.read_text(encoding='utf-8')
                    has_xde = bool(re.search(r'<xDE[^>]*>', content))
                except:
                    pass
                    
                soap_files.append({
                    'path': soap_file,
                    'size': stat.st_size,
                    'mtime': datetime.fromtimestamp(stat.st_mtime),
                    'has_xde': has_xde
                })
            except:
                pass
                
    return soap_files


def main():
    parser = argparse.ArgumentParser(description="Pick the real SOAP file")
    parser.add_argument("--artifacts-dir", help="Artifacts directory path")
    parser.add_argument("--list", action="store_true", help="List all SOAP files")
    parser.add_argument("--bash", action="store_true", help="Output bash-friendly path")
    args = parser.parse_args()
    
    artifacts_dir = None
    if args.artifacts_dir:
        artifacts_dir = Path(args.artifacts_dir)
        
    if args.list:
        if not artifacts_dir or not artifacts_dir.exists():
            print("Error: artifacts directory not found")
            return 1
            
        files = list_soap_files(artifacts_dir)
        if not files:
            print("No SOAP files found")
            return 1
            
        print("\nSOAP files in", artifacts_dir)
        print("-" * 60)
        for f in files:
            marker = "★" if f['has_xde'] else " "
            print(f"{marker} {f['path'].name:40} {f['mtime']} {f['size']:>8} bytes")
            
        # Show which one would be picked
        picked = pick_real_soap(artifacts_dir)
        if picked:
            print(f"\nPicked: {picked.name}")
        return 0
        
    # Pick and return the real SOAP
    soap_path = pick_real_soap_path(artifacts_dir)
    
    if not soap_path:
        print("Error: No suitable SOAP file found")
        return 1
        
    if args.bash:
        # Output just the path for bash scripts
        print(soap_path)
    else:
        print(f"Real SOAP file: {soap_path}")
        
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
