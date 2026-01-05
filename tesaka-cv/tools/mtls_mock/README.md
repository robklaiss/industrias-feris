# Mock Server mTLS para Pruebas Locales

Este directorio contiene un mock server mTLS para probar la integración SIFEN **sin conectarse a SIFEN real**.

## Quick Start

```bash
# 1. Generar certificados DEV
make mtls-mock-certs

# 2. Levantar servidor
make mtls-mock-server

# 3. En otra terminal, probar
make mtls-mock-test
```

## Archivos

- `generate_dev_certs.sh` - Genera certificados DEV (CA, server, client)
- `mock_server.py` - Servidor Flask que requiere mTLS
- `test_mtls_mock.py` - Test automático completo
- `certs/` - Certificados DEV (NO commitear `.key`, `.p12`)
- `artifacts/` - Artifacts de requests (sanitizados)

## Documentación Completa

Ver [docs/MTLS_MOCK.md](../../docs/MTLS_MOCK.md) para documentación completa.

## Seguridad

⚠️ **NO commitear** certificados privados (`.key`, `.p12`, `.pfx`) al repositorio.

