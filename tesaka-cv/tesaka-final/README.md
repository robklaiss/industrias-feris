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

## Dependencias
- Usa el .venv existente de tesaka-cv
- Requiere: zeep, requests, lxml, cryptography

## Notas
- No usa git. Solo copia de archivos.
- Los XSDs incluyen referencias locales para evitar dependencias de red.
- El script `run_test_follow.sh` configura todo automáticamente.
