"""
Validador de coherencia de ambiente SIFEN.
Asegura que TODO el flujo use TEST cuando SIFEN_ENV=test (QR, endpoints, modo).
"""

import os
from typing import Optional, Dict, Any
from .qr_inspector import extract_dcar_qr, detect_qr_env


def get_current_env() -> str:
    """
    Obtiene el ambiente actual desde SIFEN_ENV.
    
    Returns:
        "test" o "prod"
    """
    env = os.getenv("SIFEN_ENV", "test").lower()
    if env not in ["test", "prod"]:
        raise ValueError(f"SIFEN_ENV inválido: '{env}'. Debe ser 'test' o 'prod'")
    return env


def env_to_modo(env: str) -> int:
    """
    Convierte ambiente a modo de prevalidador.
    
    Args:
        env: "test" o "prod"
        
    Returns:
        1 para TEST, 0 para PROD
    """
    return 1 if env == "test" else 0


def modo_to_env(modo: int) -> str:
    """
    Convierte modo de prevalidador a ambiente.
    
    Args:
        modo: 0 (PROD) o 1 (TEST)
        
    Returns:
        "prod" o "test"
    """
    return "test" if modo == 1 else "prod"


def get_expected_qr_base(env: str) -> str:
    """
    Obtiene la base URL esperada del QR según ambiente.
    
    Args:
        env: "test" o "prod"
        
    Returns:
        URL base del QR
    """
    if env == "test":
        return "https://ekuatia.set.gov.py/consultas-test/qr"
    else:
        return "https://ekuatia.set.gov.py/consultas/qr"


def get_expected_validator_endpoint(env: str) -> str:
    """
    Obtiene el endpoint del prevalidador según ambiente.
    
    Args:
        env: "test" o "prod"
        
    Returns:
        URL del endpoint de validación
    """
    return "https://ekuatia.set.gov.py/validar/validar"


def assert_test_env(xml_content: str, modo: Optional[int] = None) -> Dict[str, Any]:
    """
    Verifica que el XML y parámetros sean coherentes con SIFEN_ENV=test.
    
    Args:
        xml_content: Contenido del XML a validar
        modo: Modo de prevalidador (opcional)
        
    Returns:
        Dict con resultado de validación:
        {
            "valid": bool,
            "env": str,
            "qr_env": str,
            "modo": int,
            "errors": list,
            "warnings": list
        }
    """
    current_env = get_current_env()
    expected_modo = env_to_modo(current_env)
    
    result = {
        "valid": True,
        "env": current_env,
        "qr_env": None,
        "modo": modo if modo is not None else expected_modo,
        "errors": [],
        "warnings": []
    }
    
    # Verificar QR
    qr_url = extract_dcar_qr(xml_content)
    if qr_url:
        qr_env_detected = detect_qr_env(qr_url)
        result["qr_env"] = qr_env_detected
        
        # Error crítico: QR no coincide con SIFEN_ENV
        if current_env == "test" and qr_env_detected == "PROD":
            result["valid"] = False
            result["errors"].append(
                f"❌ SIFEN_ENV={current_env} pero QR apunta a PROD (consultas/qr). "
                f"Regenerar XML con SIFEN_ENV=test."
            )
        elif current_env == "prod" and qr_env_detected == "TEST":
            result["valid"] = False
            result["errors"].append(
                f"❌ SIFEN_ENV={current_env} pero QR apunta a TEST (consultas-test/qr). "
                f"Regenerar XML con SIFEN_ENV=prod."
            )
    else:
        result["warnings"].append("⚠️  No se encontró dCarQR en el XML")
    
    # Verificar modo si se especificó
    if modo is not None:
        modo_env = modo_to_env(modo)
        
        if current_env != modo_env:
            result["valid"] = False
            result["errors"].append(
                f"❌ SIFEN_ENV={current_env} pero modo={modo} ({modo_env.upper()}). "
                f"Usar modo={expected_modo} para {current_env.upper()}."
            )
        
        # Verificar coherencia modo vs QR
        if qr_url and result["qr_env"]:
            qr_env_lower = result["qr_env"].lower()
            if modo == 0 and qr_env_lower == "test":
                result["valid"] = False
                result["errors"].append(
                    f"❌ modo=0 (PROD) pero QR es TEST. Causará error 2502."
                )
            elif modo == 1 and qr_env_lower == "prod":
                result["valid"] = False
                result["errors"].append(
                    f"❌ modo=1 (TEST) pero QR es PROD. Causará error 2502."
                )
    
    return result


def enforce_test_env():
    """
    Fuerza SIFEN_ENV=test si no está configurado.
    Útil para scripts que deben correr en TEST por defecto.
    """
    if "SIFEN_ENV" not in os.environ:
        os.environ["SIFEN_ENV"] = "test"
        return True
    return False


def validate_qr_base_url(qr_base: str) -> Dict[str, Any]:
    """
    Valida que la base URL del QR sea coherente con SIFEN_ENV.
    
    Args:
        qr_base: Base URL del QR que se va a usar
        
    Returns:
        Dict con resultado de validación
    """
    current_env = get_current_env()
    expected_base = get_expected_qr_base(current_env)
    
    result = {
        "valid": qr_base == expected_base,
        "env": current_env,
        "qr_base": qr_base,
        "expected_base": expected_base,
        "error": None
    }
    
    if not result["valid"]:
        # Detectar si está usando base de PROD cuando debería ser TEST
        if current_env == "test" and "consultas-test" not in qr_base:
            result["error"] = (
                f"❌ SIFEN_ENV=test pero QR base es '{qr_base}' (PROD). "
                f"Debe usar: {expected_base}"
            )
        elif current_env == "prod" and "consultas-test" in qr_base:
            result["error"] = (
                f"❌ SIFEN_ENV=prod pero QR base es '{qr_base}' (TEST). "
                f"Debe usar: {expected_base}"
            )
        else:
            result["error"] = f"❌ QR base '{qr_base}' no coincide con esperado: {expected_base}"
    
    return result
