"""
Pytest configuration y helpers para tests SIFEN
"""
import pytest
import sys
from typing import Callable, Any

# Registrar markers personalizados para evitar warnings
def pytest_configure(config):
    """Registra markers personalizados"""
    config.addinivalue_line(
        "markers", "requires_jsonschema: marca test que requiere jsonschema"
    )
    config.addinivalue_line(
        "markers", "requires_signxml: marca test que requiere signxml"
    )
    config.addinivalue_line(
        "markers", "requires_xmlsec: marca test que requiere xmlsec"
    )
    config.addinivalue_line(
        "markers", "requires_lxml: marca test que requiere lxml"
    )


def has_pkg(pkg_name: str) -> bool:
    """Verifica si un paquete está instalado"""
    try:
        __import__(pkg_name)
        return True
    except ImportError:
        return False


@pytest.fixture(scope="session", autouse=True)
def check_optional_deps(request: pytest.FixtureRequest):
    """
    Fixture autouse que verifica markers de dependencias opcionales
    y skippea tests si falta el paquete requerido
    """
    markers = request.node.own_markers
    skip_reasons = []
    
    # Mapeo de markers a nombres de paquetes
    marker_to_pkg = {
        "requires_jsonschema": "jsonschema",
        "requires_signxml": "signxml",
        "requires_xmlsec": "xmlsec",
        "requires_lxml": "lxml",
    }
    
    # Verificar cada marker
    for marker in markers:
        marker_name = marker.name
        if marker_name in marker_to_pkg:
            pkg_name = marker_to_pkg[marker_name]
            if not has_pkg(pkg_name):
                skip_reasons.append(
                    f"{pkg_name} no está instalado (requerido por {marker_name})"
                )
    
    if skip_reasons:
        pytest.skip(
            "; ".join(skip_reasons) + ". Instale con: pip install " + " ".join(
                marker_to_pkg.get(m.name, "") for m in markers 
                if m.name in marker_to_pkg
            )
        )
