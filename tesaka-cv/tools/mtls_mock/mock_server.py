#!/usr/bin/env python3
"""
Mock server mTLS para pruebas locales de SIFEN (dev-only)

Este servidor:
- Requiere certificado de cliente (mTLS)
- Escucha en https://127.0.0.1:9443
- Responde a SOAP 1.2 requests
- Guarda artifacts sanitizados

Uso:
    python tools/mtls_mock/mock_server.py
"""

import os
import sys
import logging
import ssl
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from flask import Flask, request, Response
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

# Agregar el directorio raíz al path para imports
ROOT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT_DIR / "app"))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Directorios
CERT_DIR = Path(__file__).parent / "certs"
ARTIFACTS_DIR = Path(__file__).parent / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Configuración
SERVER_HOST = os.getenv("MTLS_MOCK_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("MTLS_MOCK_PORT", "9443"))
SERVER_CERT = CERT_DIR / "server-dev.crt"
SERVER_KEY = CERT_DIR / "server-dev.key"
CA_CERT = CERT_DIR / "ca-dev.crt"

if not FLASK_AVAILABLE:
    logger.error("Flask no está instalado. Instale con: pip install flask")
    sys.exit(1)

app = Flask(__name__)


def sanitize_xml_for_logging(xml_bytes: bytes, max_size: int = 10000) -> str:
    """Sanitiza XML removiendo contenido sensible antes de guardar."""
    try:
        xml_str = xml_bytes.decode('utf-8', errors='replace')
        # Redactar xDE (puede contener base64 largo)
        import re
        # Buscar <xDE>...</xDE> y reemplazar contenido
        xml_str = re.sub(
            r'(<xDE[^>]*>)([^<]+)(</xDE>)',
            r'\1[REDACTED: base64 content]\3',
            xml_str,
            flags=re.IGNORECASE | re.DOTALL
        )
        # Limitar tamaño
        if len(xml_str) > max_size:
            xml_str = xml_str[:max_size] + "\n... [TRUNCATED]"
        return xml_str
    except Exception as e:
        logger.warning(f"Error al sanitizar XML: {e}")
        return f"[ERROR sanitizing: {e}]"


def extract_client_cert_info(request) -> dict:
    """Extrae información del certificado del cliente (sin datos sensibles)."""
    info = {
        "has_cert": False,
        "subject": None,
        "issuer": None,
        "serial": None,
    }
    
    if hasattr(request, 'environ') and 'SSL_CLIENT_CERT' in request.environ:
        # Flask con mTLS configurado
        cert_pem = request.environ.get('SSL_CLIENT_CERT')
        if cert_pem:
            try:
                import cryptography.x509
                from cryptography import x509
                from cryptography.hazmat.backends import default_backend
                
                cert = x509.load_pem_x509_certificate(
                    cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
                    default_backend()
                )
                info["has_cert"] = True
                info["subject"] = str(cert.subject)
                info["issuer"] = str(cert.issuer)
                info["serial"] = str(cert.serial_number)
            except Exception as e:
                logger.debug(f"Error al parsear cert del cliente: {e}")
    elif hasattr(request, 'client_cert'):
        # Fallback si está disponible
        info["has_cert"] = True
        info["subject"] = str(request.client_cert.get('subject', 'Unknown'))
    
    return info


@app.route('/de/ws/async/recibe-lote', methods=['POST'])
@app.route('/soap', methods=['POST'])
def soap_endpoint():
    """Endpoint SOAP que simula siRecepLoteDE."""
    # Extraer info del certificado del cliente
    client_cert_info = extract_client_cert_info(request)
    
    if not client_cert_info["has_cert"]:
        logger.warning("Request sin certificado de cliente (mTLS requerido)")
        return Response(
            '{"error": "mTLS required: client certificate not provided"}',
            status=403,
            mimetype='application/json'
        )
    
    logger.info(
        f"SOAP request recibido - Client cert subject: {client_cert_info.get('subject', 'Unknown')}"
    )
    
    # Validar Content-Type
    content_type = request.headers.get('Content-Type', '')
    if 'application/soap+xml' not in content_type and 'text/xml' not in content_type:
        logger.warning(f"Content-Type no es SOAP: {content_type}")
        # No rechazar, solo loguear
    
    # Leer body
    try:
        body_bytes = request.data
        logger.info(f"Request body size: {len(body_bytes)} bytes")
    except Exception as e:
        logger.error(f"Error al leer body: {e}")
        return Response(
            '{"error": "Failed to read request body"}',
            status=400,
            mimetype='application/json'
        )
    
    # Guardar artifact sanitizado
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifact_path = ARTIFACTS_DIR / f"last_request_{timestamp}.xml"
    try:
        sanitized_xml = sanitize_xml_for_logging(body_bytes)
        artifact_path.write_text(sanitized_xml, encoding='utf-8')
        logger.info(f"Artifact guardado: {artifact_path}")
    except Exception as e:
        logger.warning(f"Error al guardar artifact: {e}")
    
    # Generar respuesta SOAP dummy
    # Simular respuesta de siRecepLoteDE con dCodRes=0300 y dProtConsLote ficticio
    soap_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
  <soap:Body>
    <rResEnviLoteDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
      <dId>123456789012345</dId>
      <dCodRes>0300</dCodRes>
      <dMsgRes>Lote recibido correctamente (MOCK)</dMsgRes>
      <dProtConsLote>999999999</dProtConsLote>
      <dTpoProces>1</dTpoProces>
    </rResEnviLoteDe>
  </soap:Body>
</soap:Envelope>'''
    
    return Response(
        soap_response,
        status=200,
        mimetype='application/soap+xml; charset=utf-8'
    )


@app.route('/health', methods=['GET'])
def health():
    """Endpoint de health check (sin mTLS requerido)."""
    return Response(
        '{"status": "ok", "service": "mtls-mock-server"}',
        status=200,
        mimetype='application/json'
    )


def create_ssl_context() -> ssl.SSLContext:
    """Crea SSLContext para el servidor con mTLS requerido."""
    if not SERVER_CERT.exists() or not SERVER_KEY.exists():
        raise FileNotFoundError(
            f"Certificados del servidor no encontrados. "
            f"Ejecute: tools/mtls_mock/generate_dev_certs.sh"
        )
    
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(str(SERVER_CERT), str(SERVER_KEY))
    
    # Requerir certificado de cliente (mTLS)
    context.verify_mode = ssl.CERT_REQUIRED
    
    # Cargar CA para verificar certificados de cliente
    if CA_CERT.exists():
        context.load_verify_locations(str(CA_CERT))
    else:
        logger.warning(f"CA cert no encontrado: {CA_CERT}. mTLS puede fallar.")
    
    return context


def main():
    """Inicia el servidor mock mTLS."""
    logger.info("=== Iniciando Mock Server mTLS ===")
    logger.info(f"Host: {SERVER_HOST}")
    logger.info(f"Port: {SERVER_PORT}")
    logger.info(f"Server cert: {SERVER_CERT}")
    logger.info(f"Server key: {SERVER_KEY}")
    logger.info(f"CA cert: {CA_CERT}")
    
    # Verificar certificados
    if not SERVER_CERT.exists() or not SERVER_KEY.exists():
        logger.error(
            f"Certificados del servidor no encontrados.\n"
            f"Ejecute: tools/mtls_mock/generate_dev_certs.sh"
        )
        sys.exit(1)
    
    # Crear SSL context
    try:
        ssl_context = create_ssl_context()
        logger.info("SSL context creado (mTLS requerido)")
    except Exception as e:
        logger.error(f"Error al crear SSL context: {e}")
        sys.exit(1)
    
    logger.info(f"Servidor escuchando en https://{SERVER_HOST}:{SERVER_PORT}")
    logger.info("Endpoints:")
    logger.info("  POST /de/ws/async/recibe-lote (SOAP)")
    logger.info("  POST /soap (SOAP)")
    logger.info("  GET  /health (sin mTLS)")
    
    # Iniciar servidor Flask con SSL
    try:
        app.run(
            host=SERVER_HOST,
            port=SERVER_PORT,
            ssl_context=ssl_context,
            debug=False,
            threaded=True
        )
    except KeyboardInterrupt:
        logger.info("\nServidor detenido por el usuario")
    except Exception as e:
        logger.error(f"Error al iniciar servidor: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

