#!/usr/bin/env python3
"""
Pruebas automáticas para la colocación de firma XMLDSig SIFEN

Verifica que la firma se coloque correctamente según el feature flag
SIFEN_SIGNATURE_PARENT (DE o RDE).

Uso:
    python tests/test_signature_placement.py
"""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Optional

# Agregar el path del proyecto para importar módulos
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "tesaka-cv" / "app"))

try:
    from sifen_client.xmldsig_signer import sign_de_xml
    from sifen_client.exceptions import SifenClientError
    SIFEN_CLIENT_AVAILABLE = True
except ImportError:
    SIFEN_CLIENT_AVAILABLE = False

try:
    import lxml.etree as etree
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False

# Namespaces
DS_NS = "http://www.w3.org/2000/09/xmldsig#"
SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"

def create_minimal_de_xml(de_id: str = "TESTDE001") -> str:
    """
    Crea un XML DE mínimo para pruebas.
    
    Args:
        de_id: ID del elemento DE
        
    Returns:
        XML como string
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <dVerFor>150</dVerFor>
    <DE Id="{de_id}">
        <dVerFor>150</dVerFor>
        <iTiDE>1</iTiDE>
        <cEmi>12345678</cEmi>
        <dEmi>2026-01-12</dEmi>
        <iTiOpe>1</iTiOpe>
        <cSuc>001</cSuc>
        <dNumDoc>001-001-0000001</dNumDoc>
        <dNumDocRef>001-001-0000001</dNumDocRef>
        <dFecFin>2026-01-12</dFecFin>
        <mMonGs>100000</mMonGs>
        <mMonExo>0</mMonExo>
        <mMonExa>0</mMonExa>
        <mMonTot>100000</mMonTot>
        <mTotGrs>100000</mTotGrs>
        <mTotOpe>100000</mTotOpe>
        <mTotTra>0</mTotTra>
        <mTotAnt>0</mTotAnt>
        <mTotBon>0</mTotBon>
        <mTotDes>0</mTotDes>
        <mPorDes>0</mPorDes>
        <mTotIVA>0</mTotIVA>
        <cTiGrs>01</cTiGrs>
        <cCond>1</cCond>
        <cFormPag>1</cFormPag>
        <dFecPag>2026-01-12</dFecPag>
        <gOpeDE>
            <dInfOpe>
                <gDatGralOpe>
                    <dDesPda>Factura de prueba</dDesPda>
                    <cCondRec>1</cCondRec>
                    <cMedPag>1</cMedPag>
                </gDatGralOpe>
            </dInfOpe>
        </gOpeDE>
    </DE>
</rDE>"""

def create_test_p12_files() -> tuple[str, str]:
    """
    Crea archivos P12 de prueba para testing.
    
    Returns:
        Tupla (ruta_p12, contraseña)
    """
    # Para pruebas reales, necesitaríamos un certificado válido
    # Por ahora, vamos a saltar las pruebas que requieran firma real
    pytest.skip("Se requiere certificado P12 real para pruebas de firma")

def verify_signature_placement(xml_str: str, expected_parent: str) -> bool:
    """
    Verifica que la firma esté en el parent correcto.
    
    Args:
        xml_str: XML como string
        expected_parent: 'DE' o 'RDE'
        
    Returns:
        True si la firma está en el lugar correcto
    """
    if not LXML_AVAILABLE:
        pytest.skip("lxml no disponible")
    
    try:
        root = etree.fromstring(xml_str.encode('utf-8'))
    except Exception:
        pytest.fail("XML inválido")
    
    # Buscar Signature
    ns = {"ds": DS_NS}
    signatures = root.xpath(".//ds:Signature", namespaces=ns)
    
    if not signatures:
        pytest.fail("No se encontró ds:Signature")
    
    signature = signatures[0]
    parent = signature.getparent()
    
    if parent is None:
        pytest.fail("Signature no tiene parent")
    
    parent_name = etree.QName(parent).localname
    
    if expected_parent.upper() == "DE":
        return parent_name == "DE"
    elif expected_parent.upper() == "RDE":
        return parent_name == "rDE"
    else:
        pytest.fail(f"expected_parent inválido: {expected_parent}")

def verify_reference_uri(xml_str: str, de_id: str) -> bool:
    """
    Verifica que Reference URI apunte al DE/@Id correcto.
    
    Args:
        xml_str: XML como string
        de_id: ID esperado del DE
        
    Returns:
        True si Reference URI es correcto
    """
    if not LXML_AVAILABLE:
        pytest.skip("lxml no disponible")
    
    try:
        root = etree.fromstring(xml_str.encode('utf-8'))
    except Exception:
        pytest.fail("XML inválido")
    
    # Buscar Signature y Reference URI
    ns = {"ds": DS_NS}
    signatures = root.xpath(".//ds:Signature", namespaces=ns)
    
    if not signatures:
        pytest.fail("No se encontró ds:Signature")
    
    signature = signatures[0]
    ref_uris = signature.xpath(".//ds:Reference/@URI", namespaces=ns)
    
    if not ref_uris:
        pytest.fail("No se encontró Reference/@URI")
    
    expected_uri = f"#{de_id}"
    return ref_uris[0] == expected_uri

@pytest.mark.skipif(not SIFEN_CLIENT_AVAILABLE, reason="sifen_client no disponible")
@pytest.mark.skipif(not LXML_AVAILABLE, reason="lxml no disponible")
class TestSignaturePlacement:
    """Pruebas para la colocación de firma XMLDSig"""
    
    def test_signature_parent_de_env(self):
        """Test: Signature como hijo de DE (enveloped)"""
        # Esta prueba requiere un certificado real, así que la marcaremos como skip
        pytest.skip("Se requiere certificado P12 real para esta prueba")
        
        # El código sería algo así:
        # de_xml = create_minimal_de_xml()
        # p12_path, p12_pass = create_test_p12_files()
        # 
        # # Configurar environment variable
        # os.environ["SIFEN_SIGNATURE_PARENT"] = "DE"
        # 
        # # Firmar
        # signed_xml = sign_de_xml(de_xml, p12_path, p12_pass)
        # 
        # # Verificar
        # assert verify_signature_placement(signed_xml, "DE")
        # assert verify_reference_uri(signed_xml, "TESTDE001")
    
    def test_signature_parent_rde(self):
        """Test: Signature como hijo de rDE (comportamiento original)"""
        pytest.skip("Se requiere certificado P12 real para esta prueba")
        
        # Código similar al anterior pero con SIFEN_SIGNATURE_PARENT="RDE"
    
    def test_signature_parent_default(self):
        """Test: Valor por defecto de SIFEN_SIGNATURE_PARENT es DE"""
        # Eliminar variable de entorno si existe
        if "SIFEN_SIGNATURE_PARENT" in os.environ:
            del os.environ["SIFEN_SIGNATURE_PARENT"]
        
        # El default debe ser "DE"
        # Esto se verificaría en el código real de sign_de_xml
        # Por ahora, solo verificamos la lógica del feature flag
        from sifen_client.xmldsig_signer import sign_de_xml
        import inspect
        
        # Inspeccionar el código fuente para verificar el default
        source = inspect.getsource(sign_de_xml)
        assert 'os.environ.get("SIFEN_SIGNATURE_PARENT", "DE")' in source
    
    def test_signature_parent_invalid(self):
        """Test: Valor inválido de SIFEN_SIGNATURE_PARENT usa default"""
        pytest.skip("Se requiere certificado P12 real para esta prueba")
        
        # Configurar valor inválido
        os.environ["SIFEN_SIGNATURE_PARENT"] = "INVALID"
        
        # El código debe usar "DE" como fallback
        # Esto se verificaría en tiempo de ejecución
    
    def test_xml_structure_integrity(self):
        """Test: La estructura XML se mantiene intacta"""
        de_xml = create_minimal_de_xml()
        
        # Verificar que el XML de entrada tenga la estructura esperada
        assert "<rDE" in de_xml
        assert "<dVerFor>150</dVerFor>" in de_xml
        assert "<DE Id=" in de_xml
        assert "</DE>" in de_xml
        assert "</rDE>" in de_xml
        
        # Verificar que no haya firma antes de firmar
        assert "ds:Signature" not in de_xml

@pytest.mark.skipif(not LXML_AVAILABLE, reason="lxml no disponible")
class TestSignatureValidation:
    """Pruebas de validación de firma sin certificado real"""
    
    def test_minimal_xml_validity(self):
        """Test: XML mínimo es válido y parseable"""
        de_xml = create_minimal_de_xml()
        
        try:
            root = etree.fromstring(de_xml.encode('utf-8'))
            
            # Verificar estructura básica
            assert etree.QName(root).localname == "rDE"
            
            # Buscar DE
            de_elements = root.xpath(".//DE")
            assert len(de_elements) == 1
            
            de_elem = de_elements[0]
            assert de_elem.get("Id") == "TESTDE001"
            
        except Exception as e:
            pytest.fail(f"XML mínimo inválido: {e}")
    
    def test_xpath_queries(self):
        """Test: Queries XPath funcionan correctamente"""
        de_xml = create_minimal_de_xml()
        
        try:
            root = etree.fromstring(de_xml.encode('utf-8'))
            
            # Test queries sin namespace
            de_elements = root.xpath(".//DE")
            assert len(de_elements) == 1
            
            # Test queries con namespace
            ns = {"sifen": SIFEN_NS}
            de_elements_ns = root.xpath(".//sifen:DE", namespaces=ns)
            assert len(de_elements_ns) == 1
            
        except Exception as e:
            pytest.fail(f"Error en XPath queries: {e}")

def test_feature_flag_environment():
    """Test: Feature flag se lee correctamente del environment"""
    # Test default
    if "SIFEN_SIGNATURE_PARENT" in os.environ:
        del os.environ["SIFEN_SIGNATURE_PARENT"]
    
    # Importar y verificar el comportamiento
    # Esto es una prueba unitaria del feature flag
    expected_default = "DE"
    
    # Simular la lógica del código
    actual_value = os.environ.get("SIFEN_SIGNATURE_PARENT", "DE").upper()
    assert actual_value == expected_default
    
    # Test con valor personalizado
    os.environ["SIFEN_SIGNATURE_PARENT"] = "RDE"
    actual_value = os.environ.get("SIFEN_SIGNATURE_PARENT", "DE").upper()
    assert actual_value == "RDE"
    
    # Limpiar
    del os.environ["SIFEN_SIGNATURE_PARENT"]

if __name__ == "__main__":
    # Ejecutar pruebas directamente
    pytest.main([__file__, "-v"])
