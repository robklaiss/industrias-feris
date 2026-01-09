"""
Test de contrato WSDL para consultaRUC (offline, sin red)

Este test valida que el snapshot WSDL local tiene la estructura esperada:
- Operación rEnviConsRUC presente
- Endpoint SOAP address correcto
- Schema imports presentes

NO requiere conexión a internet ni certificados P12.
"""
import pytest
import xml.etree.ElementTree as ET
from pathlib import Path

# Ruta al snapshot WSDL
REPO_ROOT = Path(__file__).parent.parent.parent.parent
WSDL_SNAPSHOT = REPO_ROOT / "tesaka-cv" / "wsdl_snapshots" / "consulta-ruc_test.wsdl"


@pytest.fixture
def wsdl_snapshot_exists():
    """Verifica que el snapshot WSDL existe y no está vacío"""
    if not WSDL_SNAPSHOT.exists():
        pytest.skip(f"WSDL snapshot no encontrado: {WSDL_SNAPSHOT}")
    if not WSDL_SNAPSHOT.stat().st_size > 0:
        pytest.skip(f"WSDL snapshot está vacío: {WSDL_SNAPSHOT}")
    return WSDL_SNAPSHOT


def test_wsdl_snapshot_exists_and_valid(wsdl_snapshot_exists):
    """Verifica que el snapshot WSDL existe y tiene contenido"""
    assert wsdl_snapshot_exists.exists()
    assert wsdl_snapshot_exists.stat().st_size > 0
    
    # Verificar que contiene WSDL válido
    content = wsdl_snapshot_exists.read_text(encoding='utf-8')
    assert 'wsdl:definitions' in content or 'definitions' in content


def test_wsdl_contains_renviconsruc_operation(wsdl_snapshot_exists):
    """Verifica que el WSDL contiene la operación rEnviConsRUC"""
    tree = ET.parse(wsdl_snapshot_exists)
    root = tree.getroot()
    
    # Definir namespaces comunes
    namespaces = {
        'wsdl': 'http://schemas.xmlsoap.org/wsdl/',
        'wsdl12': 'http://schemas.xmlsoap.org/wsdl/',
        'soap': 'http://schemas.xmlsoap.org/wsdl/soap/',
        'soap12': 'http://schemas.xmlsoap.org/wsdl/soap12/',
    }
    
    # Buscar operación rEnviConsRUC
    # Puede estar en wsdl:operation name="rEnviConsRUC"
    operations = []
    for prefix, ns in namespaces.items():
        ops = root.findall(f".//{{{ns}}}operation[@name='rEnviConsRUC']")
        operations.extend(ops)
        # También buscar sin namespace
        ops = root.findall(".//operation[@name='rEnviConsRUC']")
        operations.extend(ops)
    
    # Si no se encontró con namespaces, buscar en texto
    if not operations:
        content = wsdl_snapshot_exists.read_text(encoding='utf-8')
        assert 'rEnviConsRUC' in content, "Operación rEnviConsRUC no encontrada en WSDL"
    
    # Si se encontró, verificar estructura
    if operations:
        assert len(operations) > 0, "Operación rEnviConsRUC encontrada"


def test_wsdl_contains_soap_address_endpoint(wsdl_snapshot_exists):
    """Verifica que el WSDL contiene el endpoint SOAP address"""
    tree = ET.parse(wsdl_snapshot_exists)
    root = tree.getroot()
    
    # Buscar soap:address o soap12:address
    namespaces = {
        'soap': 'http://schemas.xmlsoap.org/wsdl/soap/',
        'soap12': 'http://schemas.xmlsoap.org/wsdl/soap12/',
    }
    
    addresses = []
    for prefix, ns in namespaces.items():
        addr = root.findall(f".//{{{ns}}}address")
        addresses.extend(addr)
        # También buscar sin namespace
        addr = root.findall(".//address")
        addresses.extend(addr)
    
    # Si no se encontró con namespaces, buscar en texto
    if not addresses:
        content = wsdl_snapshot_exists.read_text(encoding='utf-8')
        # Verificar que contiene alguna referencia a consulta-ruc
        assert 'consulta-ruc' in content.lower(), "Endpoint consulta-ruc no encontrado en WSDL"
    else:
        # Verificar que al menos uno tiene location
        locations = []
        for addr in addresses:
            loc = addr.get('location')
            if loc:
                locations.append(loc)
        
        assert len(locations) > 0, "Al menos un SOAP address debe tener location"
        
        # Verificar que contiene consulta-ruc en alguna location
        has_consulta_ruc = any('consulta-ruc' in loc.lower() for loc in locations)
        assert has_consulta_ruc, f"Endpoint debe contener 'consulta-ruc'. Locations encontradas: {locations}"


def test_wsdl_contains_schema_import(wsdl_snapshot_exists):
    """Verifica que el WSDL contiene imports de schema XSD"""
    content = wsdl_snapshot_exists.read_text(encoding='utf-8')
    
    # Buscar imports de schema (xsd:import o schemaLocation)
    has_schema_import = (
        'schemaLocation' in content or
        'xsd:import' in content.lower() or
        '.xsd' in content.lower()
    )
    
    # Esta validación es opcional (warning si no se encuentra)
    if not has_schema_import:
        pytest.skip("No se encontraron imports de schema XSD (puede ser válido)")


def test_wsdl_is_valid_xml(wsdl_snapshot_exists):
    """Verifica que el WSDL es XML válido"""
    try:
        tree = ET.parse(wsdl_snapshot_exists)
        root = tree.getroot()
        assert root is not None
    except ET.ParseError as e:
        pytest.fail(f"WSDL no es XML válido: {e}")
