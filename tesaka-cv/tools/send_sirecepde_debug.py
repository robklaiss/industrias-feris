#!/usr/bin/env python3
"""
Instrumentación para detectar dónde cambia el XML en el pipeline de send_sirecepde
"""
import hashlib
import os
from pathlib import Path
from typing import Optional

def dump_stage(tag: str, xml_bytes: bytes, artifacts_dir: Optional[Path] = None) -> str:
    """
    Guarda XML en una etapa del pipeline y calcula su SHA256
    Returns: SHA256 hash
    """
    sha256 = hashlib.sha256(xml_bytes).hexdigest()
    
    if artifacts_dir:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        stage_file = artifacts_dir / f"_stage_{tag}.xml"
        stage_file.write_bytes(xml_bytes)
        print(f"🔍 STAGE {tag}: {len(xml_bytes)} bytes, SHA256: {sha256}")
        print(f"   💾 Guardado: {stage_file}")
    else:
        print(f"🔍 STAGE {tag}: {len(xml_bytes)} bytes, SHA256: {sha256}")
    
    return sha256

def compare_hashes(hash1: str, hash2: str, stage1: str, stage2: str) -> None:
    """Compara dos hashes y reporta si son diferentes"""
    if hash1 != hash2:
        print(f"⚠️  ¡CAMBIO DETECTADO! {stage1} -> {stage2}")
        print(f"   {stage1}: {hash1}")
        print(f"   {stage2}: {hash2}")
    else:
        print(f"✅ Sin cambios: {stage1} -> {stage2}")
