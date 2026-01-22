#!/usr/bin/env python3
"""Tests para validate_xde_zip_contains_dcodseg.py"""

import base64
import zipfile
from io import BytesIO
from pathlib import Path
import sys
import tempfile

# Agregar el directorio tools al path para importar el módulo
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv" / "tools"))

from validate_xde_zip_contains_dcodseg import extract_and_validate_dcodseg


def create_soap_with_zip(lote_xml_content: str, namespace_prefix: str = "xsd") -> str:
    """
    Crea un SOAP XML con un ZIP base64 conteniendo el lote_xml.
    """
    # Crear ZIP en memoria con lote.xml
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('lote.xml', lote_xml_content)
    zip_bytes = zip_buffer.getvalue()
    
    # Codificar en base64
    b64_content = base64.b64encode(zip_bytes).decode('ascii')
    
    # Construir SOAP con el namespace solicitado
    soap_template = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
               xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
    <soap:Header/>
    <soap:Body>
        <{namespace_prefix}:rEnvioLote xmlns:{namespace_prefix}="http://ekuatia.set.gov.py/sifen/xsd">
            <{namespace_prefix}:dId>123</{namespace_prefix}:dId>
            <{namespace_prefix}:xDE>{b64_content}</{namespace_prefix}:xDE>
        </{namespace_prefix}:rEnvioLote>
    </soap:Body>
</soap:Envelope>"""
    
    return soap_template


def test_valid_dcodseg():
    """Test con dCodSeg válido."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>123456789</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path)
        assert exit_code == 0, f"Expected exit_code 0, got {exit_code}, message: {message}"
        assert value == "123456789", f"Expected value '123456789', got '{value}'"
        assert "✅" in message, f"Expected success message, got: {message}"
    finally:
        temp_path.unlink()


def test_missing_dcodseg():
    """Test sin dCodSeg."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path)
        assert exit_code == 2, f"Expected exit_code 2, got {exit_code}"
        assert "❌" in message, f"Expected error message, got: {message}"
        assert "no se encontró" in message.lower(), f"Expected 'no se encontró' in message, got: {message}"
    finally:
        temp_path.unlink()


def test_invalid_format_dcodseg():
    """Test con dCodSeg de formato inválido."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>ABC123456</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path)
        assert exit_code == 2, f"Expected exit_code 2, got {exit_code}"
        assert "❌" in message, f"Expected error message, got: {message}"
        assert "no numéricos" in message, f"Expected 'no numéricos' in message, got: {message}"
    finally:
        temp_path.unlink()


def test_all_zeros_dcodseg():
    """Test con dCodSeg todo ceros."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>000000000</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path)
        assert exit_code == 2, f"Expected exit_code 2, got {exit_code}"
        assert "❌" in message, f"Expected error message, got: {message}"
        assert "todo ceros" in message, f"Expected 'todo ceros' in message, got: {message}"
    finally:
        temp_path.unlink()


def test_wrong_length_dcodseg():
    """Test con dCodSeg de largo incorrecto."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>12345</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path)
        assert exit_code == 2, f"Expected exit_code 2, got {exit_code}"
        assert "❌" in message, f"Expected error message, got: {message}"
        assert "exactamente 9 dígitos" in message, f"Expected 'exactamente 9 dígitos' in message, got: {message}"
    finally:
        temp_path.unlink()


def test_expected_value_match():
    """Test con valor esperado que coincide."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>987654321</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path, expected_value="987654321")
        assert exit_code == 0, f"Expected exit_code 0, got {exit_code}, message: {message}"
        assert value == "987654321", f"Expected value '987654321', got '{value}'"
    finally:
        temp_path.unlink()


def test_expected_value_mismatch():
    """Test con valor esperado que no coincide."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>123456789</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    soap_xml = create_soap_with_zip(lote_xml)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path, expected_value="999999999")
        assert exit_code == 2, f"Expected exit_code 2, got {exit_code}"
        assert "❌" in message, f"Expected error message, got: {message}"
        assert "no coincide" in message, f"Expected 'no coincide' in message, got: {message}"
    finally:
        temp_path.unlink()


def test_different_namespace_prefix():
    """Test con prefijo de namespace diferente."""
    lote_xml = """<?xml version="1.0" encoding="utf-8"?>
<rLoteDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">
    <rDE Id="rDE123">
        <dVerFor>150</dVerFor>
        <DE Id="DE123">
            <gOpeDE>
                <iTipEmi>1</iTipEmi>
                <dDesTipEmi>Normal</dDesTipEmi>
                <dCodSeg>555666777</dCodSeg>
            </gOpeDE>
        </DE>
    </rDE>
</rLoteDE>"""
    
    # Usar prefijo 'sifen' en lugar de 'xsd'
    soap_xml = create_soap_with_zip(lote_xml, namespace_prefix="sifen")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
        f.write(soap_xml)
        temp_path = Path(f.name)
    
    try:
        exit_code, message, value = extract_and_validate_dcodseg(temp_path)
        assert exit_code == 0, f"Expected exit_code 0, got {exit_code}, message: {message}"
        assert value == "555666777", f"Expected value '555666777', got '{value}'"
    finally:
        temp_path.unlink()


if __name__ == "__main__":
    # Ejecutar todos los tests
    test_valid_dcodseg()
    test_missing_dcodseg()
    test_invalid_format_dcodseg()
    test_all_zeros_dcodseg()
    test_wrong_length_dcodseg()
    test_expected_value_match()
    test_expected_value_mismatch()
    test_different_namespace_prefix()
    
    print("✅ Todos los tests pasaron")
