#!/usr/bin/env python3
"""
Tests para validar que el XML exportado para el Prevalidador SIFEN
tenga la estructura correcta en rDE (Id, schemaLocation).
"""
import re
from pathlib import Path

import pytest

UPLOAD_PATH = Path.home() / "Desktop" / "SIFEN_PREVALIDADOR_UPLOAD.xml"
EXPECTED_SCHEMA_LOCATION = "http://ekuatia.set.gov.py/sifen/xsd http://ekuatia.set.gov.py/sifen/xsd/siRecepRDE_v150.xsd"


@pytest.fixture
def upload_xml_bytes():
    """Load the exported XML bytes if it exists."""
    if not UPLOAD_PATH.exists():
        pytest.skip(f"Upload file not found: {UPLOAD_PATH}")
    return UPLOAD_PATH.read_bytes()


def test_rde_has_id_attribute(upload_xml_bytes: bytes):
    """rDE root element must have Id attribute (CDC)."""
    # Match <rDE ... Id="..." ...>
    rde_id_pat = re.compile(rb'<rDE\b[^>]*\sId=(["\'])([^"\']+)\1')
    m = rde_id_pat.search(upload_xml_bytes)
    assert m is not None, "rDE does not have Id attribute"
    rde_id = m.group(2).decode("utf-8")
    assert len(rde_id) >= 40, f"rDE@Id too short (expected CDC of ~44 chars): {rde_id}"
    print(f"rDE@Id: {rde_id}")


def test_schema_location_correct(upload_xml_bytes: bytes):
    """xsi:schemaLocation must point to siRecepRDE_v150.xsd with correct format."""
    schema_loc_pat = re.compile(rb'xsi:schemaLocation=(["\'])([^"\']+)\1')
    m = schema_loc_pat.search(upload_xml_bytes)
    assert m is not None, "xsi:schemaLocation not found in rDE"
    
    schema_loc = m.group(2).decode("utf-8")
    print(f"schemaLocation: {schema_loc}")
    
    # Must have exactly 2 tokens (namespace + location)
    tokens = schema_loc.split()
    assert len(tokens) == 2, f"schemaLocation must have 2 tokens (namespace + location), got {len(tokens)}: {tokens}"
    
    # First token is namespace
    assert tokens[0] == "http://ekuatia.set.gov.py/sifen/xsd", f"Wrong namespace: {tokens[0]}"
    
    # Second token must end with siRecepRDE_v150.xsd (NOT siRecepDE_v150.xsd)
    assert tokens[1].endswith("siRecepRDE_v150.xsd"), f"schemaLocation must point to siRecepRDE_v150.xsd, got: {tokens[1]}"
    
    # Full match
    assert schema_loc == EXPECTED_SCHEMA_LOCATION, f"schemaLocation mismatch: expected '{EXPECTED_SCHEMA_LOCATION}', got '{schema_loc}'"


def test_de_has_id_attribute(upload_xml_bytes: bytes):
    """DE element must have Id attribute (referenced by signature)."""
    de_id_pat = re.compile(rb'<DE\b[^>]*\sId=(["\'])([^"\']+)\1')
    m = de_id_pat.search(upload_xml_bytes)
    assert m is not None, "DE does not have Id attribute"
    de_id = m.group(2).decode("utf-8")
    assert len(de_id) >= 40, f"DE@Id too short: {de_id}"
    print(f"DE@Id: {de_id}")


def test_rde_id_matches_de_id(upload_xml_bytes: bytes):
    """rDE@Id should match DE@Id (both are CDC)."""
    rde_id_pat = re.compile(rb'<rDE\b[^>]*\sId=(["\'])([^"\']+)\1')
    de_id_pat = re.compile(rb'<DE\b[^>]*\sId=(["\'])([^"\']+)\1')
    
    m_rde = rde_id_pat.search(upload_xml_bytes)
    m_de = de_id_pat.search(upload_xml_bytes)
    
    if m_rde is None:
        pytest.skip("rDE@Id not found")
    if m_de is None:
        pytest.skip("DE@Id not found")
    
    rde_id = m_rde.group(2).decode("utf-8")
    de_id = m_de.group(2).decode("utf-8")
    
    assert rde_id == de_id, f"rDE@Id ({rde_id}) does not match DE@Id ({de_id})"


def test_signature_present(upload_xml_bytes: bytes):
    """Signature element must be present with default xmlns."""
    sig_pat = re.compile(rb'<Signature\b[^>]*xmlns=(["\'])http://www\.w3\.org/2000/09/xmldsig#\1')
    m = sig_pat.search(upload_xml_bytes)
    assert m is not None, "Signature with default xmlns not found"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
