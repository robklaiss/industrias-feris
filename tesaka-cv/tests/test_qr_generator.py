"""
Tests unitarios para qr_generator
"""
import pytest
import hashlib
from app.sifen_client.qr_generator import QRGenerator, QRGeneratorError


@pytest.fixture
def qr_generator_test():
    """Generador de QR para ambiente TEST"""
    return QRGenerator(
        csc="ABCD1234567890123456789012345678",  # 32 caracteres
        csc_id="0001",
        environment="TEST"
    )


@pytest.fixture
def qr_generator_prod():
    """Generador de QR para ambiente PROD"""
    return QRGenerator(
        csc="ABCD1234567890123456789012345678",
        csc_id="0001",
        environment="PROD"
    )


def test_qr_generator_init_missing_csc():
    """Test que falla si no se proporciona CSC"""
    with pytest.raises(QRGeneratorError, match="CSC no especificado"):
        QRGenerator()


def test_qr_generator_init_invalid_environment():
    """Test que falla con ambiente inválido"""
    with pytest.raises(QRGeneratorError, match="Ambiente inválido"):
        QRGenerator(csc="ABCD1234567890123456789012345678", environment="INVALID")


def test_qr_generator_init_test(qr_generator_test):
    """Test inicialización en ambiente TEST"""
    assert qr_generator_test.environment == "TEST"
    assert qr_generator_test.qr_url_base == "https://www.ekuatia.set.gov.py/consultas-test/qr?"
    assert qr_generator_test.csc == "ABCD1234567890123456789012345678"
    assert qr_generator_test.csc_id == "0001"


def test_qr_generator_init_prod(qr_generator_prod):
    """Test inicialización en ambiente PROD"""
    assert qr_generator_prod.environment == "PROD"
    assert qr_generator_prod.qr_url_base == "https://www.ekuatia.set.gov.py/consultas/qr?"


def test_qr_generator_generate_basic(qr_generator_test):
    """Test generación básica de QR"""
    result = qr_generator_test.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1"
    )
    
    assert 'url' in result
    assert 'url_xml' in result
    assert 'hash' in result
    assert 'datos' in result
    assert 'csc_id' in result
    
    # Verificar que la URL contiene la base correcta
    assert result['url'].startswith("https://www.ekuatia.set.gov.py/consultas-test/qr?")
    
    # Verificar que contiene el hash
    assert 'cHashQR=' in result['url']
    assert result['hash'] in result['url']
    
    # Verificar que NO contiene el CSC
    assert qr_generator_test.csc not in result['url']
    assert qr_generator_test.csc not in result['url_xml']
    
    # Verificar que url_xml tiene &amp; en lugar de &
    assert '&amp;' in result['url_xml'] or '&' not in result['url_xml'].replace('&amp;', '')
    
    # Verificar que el hash tiene 64 caracteres (SHA-256 en hex)
    assert len(result['hash']) == 64
    assert result['hash'].isupper()  # Debe estar en mayúsculas


def test_qr_generator_hash_verification(qr_generator_test):
    """Test que el hash generado es correcto"""
    result = qr_generator_test.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1"
    )
    
    # Recalcular hash manualmente
    datos = result['datos']
    datos_con_csc = datos + qr_generator_test.csc
    hash_manual = hashlib.sha256(datos_con_csc.encode('utf-8')).hexdigest().upper()
    
    assert result['hash'] == hash_manual


def test_qr_generator_escape_xml(qr_generator_test):
    """Test que el escape XML funciona correctamente"""
    result = qr_generator_test.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1"
    )
    
    # url_xml debe tener &amp; en lugar de &
    assert '&amp;' in result['url_xml']
    
    # Verificar que el escape es correcto
    unescaped = QRGenerator.unescape_xml(result['url_xml'])
    assert unescaped == result['url']


def test_qr_generator_sanitize_for_logging(qr_generator_test):
    """Test que la sanitización para logging funciona"""
    result = qr_generator_test.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1"
    )
    
    # La URL no debe contener CSC (ya está protegido)
    sanitized = qr_generator_test.sanitize_for_logging(result['url'])
    assert qr_generator_test.csc not in sanitized


def test_qr_generator_prod_vs_test(qr_generator_test, qr_generator_prod):
    """Test que las URLs difieren entre TEST y PROD"""
    result_test = qr_generator_test.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1"
    )
    
    result_prod = qr_generator_prod.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1"
    )
    
    # Las URLs base deben ser diferentes
    assert "consultas-test" in result_test['url']
    assert "consultas-test" not in result_prod['url']
    assert "consultas/qr" in result_prod['url']
    
    # Pero los hashes deben ser iguales (mismos datos y CSC)
    assert result_test['hash'] == result_prod['hash']


def test_qr_generator_with_optional_fields(qr_generator_test):
    """Test generación con campos opcionales"""
    result = qr_generator_test.generate(
        d_id="1",
        d_fe_emi="20250129",
        d_ruc_em="4554737",
        d_est="001",
        d_pun_exp="001",
        d_num_doc="0000001",
        d_tipo_doc="01",
        d_tipo_cont="1",
        d_tipo_emi="1",
        d_cod_gen="12345",
        d_den_suc="Sucursal Central",
        d_dv_emi="8"
    )
    
    assert 'url' in result
    assert 'hash' in result
    # Los campos opcionales deben estar en los datos
    assert "12345" in result['datos']
    assert "Sucursal Central" in result['datos']
    assert "8" in result['datos']

