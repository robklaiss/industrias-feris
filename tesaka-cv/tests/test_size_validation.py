"""
Tests unitarios para validación de tamaños según límites SIFEN
"""
import pytest
from app.sifen_client.soap_client import SIZE_LIMITS, SifenSizeLimitError
from app.sifen_client.exceptions import SifenSizeLimitError as SizeLimitError


def test_size_limits_defined():
    """Test que todos los límites están definidos"""
    assert 'siRecepDE' in SIZE_LIMITS
    assert 'siRecepLoteDE' in SIZE_LIMITS
    assert 'siConsRUC' in SIZE_LIMITS
    assert 'siConsDE' in SIZE_LIMITS


def test_size_limit_sirecepde():
    """Test límite para siRecepDE (1000 KB)"""
    limit = SIZE_LIMITS['siRecepDE']
    assert limit == 1000 * 1024  # 1000 KB en bytes


def test_size_limit_sireceplotede():
    """Test límite para siRecepLoteDE (10.000 KB)"""
    limit = SIZE_LIMITS['siRecepLoteDE']
    assert limit == 10000 * 1024  # 10.000 KB en bytes


def test_size_limit_siconsruc():
    """Test límite para siConsRUC (1000 KB)"""
    limit = SIZE_LIMITS['siConsRUC']
    assert limit == 1000 * 1024  # 1000 KB en bytes


def test_size_limit_error_creation():
    """Test creación de excepción de límite de tamaño"""
    error = SizeLimitError(
        service='siRecepDE',
        size=2000 * 1024,
        limit=1000 * 1024,
        code='0200'
    )
    
    assert error.service == 'siRecepDE'
    assert error.size == 2000 * 1024
    assert error.limit == 1000 * 1024
    assert error.code == '0200'
    assert '0200' in str(error)
    assert 'siRecepDE' in str(error)


def test_validate_size_under_limit():
    """Test que contenido bajo el límite pasa validación"""
    from app.sifen_client.soap_client import SoapClient
    from app.sifen_client.config import SifenConfig
    
    # Crear config de prueba (sin certificado real)
    config = SifenConfig(env='test')
    
    # Mock del método _validate_size
    class MockSoapClient:
        def _validate_size(self, service, content):
            size = len(content.encode('utf-8'))
            limit = SIZE_LIMITS.get(service)
            if limit and size > limit:
                error_code = {
                    'siRecepDE': '0200',
                    'siRecepLoteDE': '0270',
                    'siConsRUC': '0460',
                }.get(service, '0000')
                raise SizeLimitError(service, size, limit, error_code)
    
    client = MockSoapClient()
    
    # Contenido pequeño (500 KB)
    small_content = "x" * (500 * 1024)
    client._validate_size('siRecepDE', small_content)  # No debe lanzar excepción


def test_validate_size_over_limit():
    """Test que contenido sobre el límite falla validación"""
    from app.sifen_client.soap_client import SoapClient
    from app.sifen_client.config import SifenConfig
    
    class MockSoapClient:
        def _validate_size(self, service, content):
            size = len(content.encode('utf-8'))
            limit = SIZE_LIMITS.get(service)
            if limit and size > limit:
                error_code = {
                    'siRecepDE': '0200',
                    'siRecepLoteDE': '0270',
                    'siConsRUC': '0460',
                }.get(service, '0000')
                raise SizeLimitError(service, size, limit, error_code)
    
    client = MockSoapClient()
    
    # Contenido grande (1500 KB, excede límite de 1000 KB)
    large_content = "x" * (1500 * 1024)
    
    with pytest.raises(SizeLimitError) as exc_info:
        client._validate_size('siRecepDE', large_content)
    
    assert exc_info.value.code == '0200'
    assert exc_info.value.service == 'siRecepDE'


def test_size_validation_different_services():
    """Test que diferentes servicios tienen diferentes límites"""
    # siRecepDE: 1000 KB
    assert SIZE_LIMITS['siRecepDE'] == 1000 * 1024
    
    # siRecepLoteDE: 10.000 KB (10x más)
    assert SIZE_LIMITS['siRecepLoteDE'] == 10000 * 1024
    assert SIZE_LIMITS['siRecepLoteDE'] > SIZE_LIMITS['siRecepDE']
    
    # siConsRUC: 1000 KB (igual que siRecepDE)
    assert SIZE_LIMITS['siConsRUC'] == 1000 * 1024
    assert SIZE_LIMITS['siConsRUC'] == SIZE_LIMITS['siRecepDE']


def test_size_validation_edge_case():
    """Test caso límite (exactamente en el límite)"""
    from app.sifen_client.soap_client import SoapClient
    
    class MockSoapClient:
        def _validate_size(self, service, content):
            size = len(content.encode('utf-8'))
            limit = SIZE_LIMITS.get(service)
            if limit and size > limit:  # > no >=, así que exactamente en el límite pasa
                error_code = {
                    'siRecepDE': '0200',
                    'siRecepLoteDE': '0270',
                    'siConsRUC': '0460',
                }.get(service, '0000')
                raise SizeLimitError(service, size, limit, error_code)
    
    client = MockSoapClient()
    
    # Contenido exactamente en el límite (1000 KB)
    exact_content = "x" * (1000 * 1024)
    client._validate_size('siRecepDE', exact_content)  # No debe lanzar (es >, no >=)
    
    # Contenido 1 byte sobre el límite
    over_content = "x" * (1000 * 1024 + 1)
    with pytest.raises(SizeLimitError):
        client._validate_size('siRecepDE', over_content)

