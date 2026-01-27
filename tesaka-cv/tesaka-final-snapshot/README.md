# Tesaka Final - Ambiente Limpio para Depuración de Error 0160

## Propósito
Carpeta limpia con lo mínimo necesario para reproducir y depurar el error 0160 en consulta-lote.

## Estructura
```
tesaka-final/
├── tools/                     # Scripts principales
│   ├── sifen_run.sh          # Wrapper principal
│   ├── follow_lote.py        # Polling de lotes
│   └── consulta_lote_de.py   # Consulta de lote SIFEN
├── app/sifen_client/         # Módulos SIFEN críticos
│   ├── config.py             # Configuración de endpoints
│   ├── exceptions.py         # Excepciones
│   ├── pkcs12_utils.py       # Manejo de certificados
│   └── soap_client.py        # Cliente SOAP
├── config/
│   └── sifen_test.env        # Variables de entorno TEST
├── schemas_sifen/            # XSDs locales para validación
├── .venv/                    # Python virtual environment
└── run_test_follow.sh        # Script de ejecución
```

## Uso

### 1. Ejecutar el caso de prueba
```bash
cd tesaka-cv
bash tesaka-final/run_test_follow.sh
```

### 2. Ver los resultados
Los archivos de depuración se guardan en:
```
/Users/robinklaiss/Desktop/SIFEN_ARTIFACTS_TEST_20260123/
├── zeep_consulta_lote_sent_try*.xml    # Request SOAP enviado
├── zeep_consulta_lote_headers_*.txt    # Headers HTTP enviados
└── response_consulta_*.json            # Respuesta SIFEN
```

### 3. Analizar el error 0160
El XML de interés está en `zeep_consulta_lote_sent_try*.xml`:
```xml
<ns0:rEnviConsLoteDe xmlns:ns0="http://ekuatia.set.gov.py/sifen/xsd">
    <ns0:dId>...</ns0:dId>
    <ns0:dProtConsLote>...</ns0:dProtConsLote>
</ns0:rEnviConsLoteDe>
```

## Variables de Ambiente
- `SIFEN_ENV=test` - Ambiente de prueba
- `SIFEN_XSD_DIR` - Apunta a schemas_sifen local

## Firma P12 (XMLDSig) - variables requeridas

- `SIFEN_SIGN_P12_PATH` (fallback: `SIFEN_MTLS_P12_PATH`)
- `SIFEN_SIGN_P12_PASSWORD` (fallback: `SIFEN_MTLS_P12_PASSWORD`)

Alternativa para servidor (sin interacción):
- `SIFEN_SIGN_P12_PASSWORD_FILE` (fallback: `SIFEN_MTLS_P12_PASSWORD_FILE`)

Opcional:
- `OPENSSL_BIN` para forzar el binario `openssl` a usar en el fallback `-legacy`.

## Deploy servidor (systemd)

Ejemplo de unit:

```
[Service]
EnvironmentFile=/etc/tesaka/tesaka.env
ExecStart=/usr/bin/python -m uvicorn web.main:app --host 127.0.0.1 --port 8001
WorkingDirectory=/opt/tesaka/tesaka-cv/tesaka-final
User=tesaka
Group=tesaka
```

En `/etc/tesaka/tesaka.env` (ejemplo):

```
SIFEN_ENV=prod
SIFEN_SIGN_P12_PATH=/etc/tesaka/F1T_65478.p12
SIFEN_SIGN_P12_PASSWORD_FILE=/etc/tesaka/sifen_sign_p12_password.txt
```

Permisos recomendados para el archivo secreto:

```
chmod 600 /etc/tesaka/sifen_sign_p12_password.txt
chown root:tesaka /etc/tesaka/sifen_sign_p12_password.txt
```

No commitear esos archivos en el repo.

### Smoke test local (con cleanup)

```bash
cd tesaka-cv/tesaka-final
python3 -c "import os; from app.sifen_client.pkcs12_utils import p12_to_temp_pem_files, cleanup_pem_files; p=os.environ.get('SIFEN_SIGN_P12_PATH') or os.environ.get('SIFEN_MTLS_P12_PATH'); w=os.environ.get('SIFEN_SIGN_P12_PASSWORD') or os.environ.get('SIFEN_MTLS_P12_PASSWORD'); c,k=p12_to_temp_pem_files(p,w); print('cert_pem=',c,'key_pem=',k); cleanup_pem_files(c,k); print('OK')"
```

## Dependencias
- Usa el .venv existente de tesaka-cv
- Requiere: zeep, requests, lxml, cryptography

## Notas
- No usa git. Solo copia de archivos.
- Los XSDs incluyen referencias locales para evitar dependencias de red.
- El script `run_test_follow.sh` configura todo automáticamente.
