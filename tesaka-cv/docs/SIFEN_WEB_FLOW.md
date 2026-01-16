# Flujo Web SIFEN - Guía de Uso

Este documento describe cómo usar la integración SIFEN desde la aplicación web.

## Configuración

### Variables de Entorno

Crear archivo `.env` basado en `.env.example`:

```bash
cp tesaka-cv/.env.example tesaka-cv/.env
```

Editar `.env` con valores reales:

```bash
# Ambiente SIFEN
SIFEN_ENV=test  # o "prod"

# Certificado P12 (mTLS y firma)
SIFEN_P12_PATH=/path/to/your/certificate.p12
# O alternativamente, usar PEM directo:
# SIFEN_CERT_PEM=/path/to/cert.pem
# SIFEN_KEY_PEM=/path/to/key.pem

# Password del P12 (opcional, se pedirá interactivo en CLI si falta)
# REQUERIDO en modo web si usa P12
SIFEN_P12_PASS=your_password_here

# Gate consultaRUC (saltable con "1")
SIFEN_SKIP_RUC_GATE=0  # 0=validar RUC antes de enviar, 1=skip (WARNING)

# Timeout HTTP para requests SIFEN
SIFEN_HTTP_TIMEOUT=30  # segundos

# Ambiente de la aplicación
ENV=development  # o "test", "production"
```

**IMPORTANTE:**
- El archivo `.env` NO debe committearse al repo
- La password del P12 NO debe estar en logs ni en código
- Los archivos PEM temporales se crean en `/tmp` con permisos 600 y se limpian automáticamente

## Endpoints Disponibles

### 1. Consulta RUC (Interno, solo dev/test)

**GET** `/internal/sifen/consulta-ruc?value=4554737-8`

Consulta el estado y habilitación de un RUC en SIFEN.

**Parámetros:**
- `value` (query, requerido): RUC a consultar (puede venir con guión, ej: "4554737-8" o "45547378")

**Respuesta exitosa (200):**
```json
{
  "ok": true,
  "normalized": "45547378",
  "http_code": 200,
  "dCodRes": "0502",
  "dMsgRes": "RUC encontrado",
  "xContRUC": {
    "dRUCCons": "45547378",
    "dRazCons": "EMPRESA EJEMPLO S.A.",
    "dCodEstCons": "01",
    "dDesEstCons": "Habilitado"
  }
}
```

**Respuesta con error de formato (400):**
```json
{
  "ok": false,
  "error": "Formato de RUC inválido: RUC tiene longitud inválida: 4 (debe ser 7 u 8 dígitos)",
  "normalized": null
}
```

**Respuesta con error SIFEN (500):**
```json
{
  "ok": false,
  "error": "Error en consultaRUC: Error de conexión: ...",
  "normalized": "45547378"
}
```

**Restricciones:**
- Solo disponible si `ENV != "production"`
- Requiere `SIFEN_P12_PATH` configurado en `.env`
- Si `SIFEN_P12_PASS` no está configurado, fallará (no se puede pedir interactivo en web)

**Ejemplo de uso desde la terminal:**
```bash
curl "http://localhost:8000/internal/sifen/consulta-ruc?value=4554737-8"
```

### 2. Enviar Factura a SIFEN

**POST** `/api/facturas/{id}/enviar-sifen`

Envía una factura a SIFEN para su aprobación.

**Parámetros:**
- `id` (path): ID de la factura en la base de datos

**Gate consultaRUC:**
- Antes de enviar, valida el RUC del comprador
- Saltable con `SIFEN_SKIP_RUC_GATE=1` (se loguea WARNING)
- Reglas robustas:
  - Si `xContRUC.dRUCFactElec` existe: debe ser `"S"` (habilitado)
  - Si no: exigir `dCodRes == "0502"` (RUC encontrado)

**Respuesta exitosa (200):**
```json
{
  "ok": true,
  "http_code": 200,
  "dCodRes": "0200",
  "dMsgRes": "DE recibido con éxito",
  "sifen_env": "test",
  "endpoint": "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl",
  "signed_xml_sha256": "abc123...",
  "ruc_validated": true,
  "ruc_validation": {
    "normalized": "45547378",
    "http_code": 200,
    "dCodRes": "0502",
    "dMsgRes": "RUC encontrado",
    "xContRUC": {
      "dRUCCons": "45547378",
      "dRazCons": "EMPRESA EJEMPLO S.A.",
      "dRUCFactElec": "S"
    }
  },
  "extra": {
    "cdc": "01045547378001001000000112025123011234567892",
    "estado": "aprobado"
  }
}
```

**Respuesta con error de RUC (400):**
```json
{
  "ok": false,
  "error": "RUC no habilitado para facturación electrónica: dRUCFactElec=N, dCodRes=0502, dMsgRes=RUC encontrado",
  "ruc_validation": {
    "normalized": "45547378",
    "http_code": 200,
    "dCodRes": "0502",
    "dMsgRes": "RUC encontrado",
    "xContRUC": {
      "dRUCFactElec": "N"
    }
  }
}
```

**Respuesta con error SIFEN (500):**
```json
{
  "ok": false,
  "error": "Error en envío SOAP a SIFEN: ...",
  "ruc_validated": true,
  "ruc_validation": {...}
}
```

**Flujo interno:**
1. Carga factura por ID
2. **Gate consultaRUC** (saltable con `SIFEN_SKIP_RUC_GATE=1`)
3. Genera XML DE crudo usando `tools.build_de.build_de_xml()`
4. Firma XML usando `app.sifen_client.xml_signer.XmlSigner`
5. Wrappea en siRecepDE (`rEnviDe` con `xDE`)
6. Envía a SIFEN vía SOAP + mTLS usando `app.sifen_client.soap_client.SoapClient.recepcion_de()`
7. Persiste resultado en tabla `sifen_submissions`
8. Actualiza campos `sifen_*` en tabla `invoices` (compatibilidad)

## Normalización de RUC

El módulo `app/sifen/ruc.py` proporciona la función `normalize_truc()` que normaliza RUCs según la especificación SIFEN:

**Reglas:**
- Si viene con guión "BASE-DV":
  - BASE debe ser 6 o 7 dígitos
  - DV debe ser 1 dígito
  - Resultado: BASE+DV (7 u 8 dígitos total)
- Si NO tiene guión:
  - Debe ser solo dígitos
  - Longitud: 7 u 8 dígitos
  - Resultado: tal cual (sin cambios)

**Validación estricta:**
- Regex final: `^[0-9]{7,8}$`
- No acepta letras (el RUC paraguayo solo tiene dígitos)

**Ejemplos:**
```python
from app.sifen.ruc import normalize_truc

normalize_truc("4554737-8")  # → "45547378"
normalize_truc("45547378")   # → "45547378"
normalize_truc("80012345-7") # → "80012345" (BASE 8 dígitos, se ignora DV)
normalize_truc("12345")      # → Error: longitud inválida
normalize_truc("ABC12345")   # → Error: contiene letras
```

## Códigos de Respuesta SIFEN

### Consulta RUC (`dCodRes`)

| Código | Significado | Acción |
|--------|-------------|--------|
| `0500` | RUC inexistente | Verificar RUC ingresado |
| `0501` | Sin permiso para consultar | Verificar certificado mTLS |
| `0502` | RUC encontrado (éxito) | Continuar con el flujo |
| `0183` | RUC del certificado no activo | Verificar certificado P12 |

### Envío de Factura (`dCodRes`)

| Código | Significado | Acción |
|--------|-------------|--------|
| `0160` | XML Mal Formado | Revisar estructura XML del DE (prolog, namespace, prefijos) |
| `0200` | DE recibido con éxito | DE aprobado, CDC disponible en `extra.cdc` |
| `0300` | Lote recibido con éxito (lotes) | Consultar estado después de 10 minutos |
| `0301` | Lote no encolado (lotes) | Verificar motivos de rechazo/bloqueo |

## Errores Comunes

### 1. `0160 (XML Mal Formado)`

**Causas posibles:**
- Endpoint POST incorrecto (usar `/de/ws/consultas/consulta-ruc.wsdl` sin `?wsdl`, igual que Roshka)
- XML tiene prefijos `xsd:` cuando debería usar namespace default
- XML tiene espacios o BOM antes de `<?xml ...?>`

**Solución:**
- Verificar que se use `https://sifen-*.set.gov.py/de/ws/consultas/consulta-ruc.wsdl` (sin `?wsdl`)
- Asegurar `SIFEN_CONSULTA_RUC_BODY_NS_MODE=default` (default) y namespace SIFEN en `rEnviConsRUC`
- Validar que el XML empiece exactamente con `<?xml version="1.0" encoding="UTF-8"?>`

### 2. `0500 (RUC inexistente)`

**Causas posibles:**
- RUC ingresado es incorrecto
- RUC no está registrado en SIFEN

**Solución:**
- Verificar que el RUC ingresado sea correcto
- Consultar manualmente en https://ekuatia.set.gov.py

### 3. `Falta password del certificado P12`

**Causa:**
- `SIFEN_P12_PASS` no está configurado en `.env`
- En modo web, no se puede pedir interactivo

**Solución:**
- Agregar `SIFEN_P12_PASS=...` en `.env`
- O usar modo CLI donde se puede pedir interactivo

### 4. `Certificado P12 no encontrado`

**Causa:**
- `SIFEN_P12_PATH` no apunta a un archivo válido
- No existe certificado en `~/.sifen/certs/*.p12`

**Solución:**
- Verificar que `SIFEN_P12_PATH` sea una ruta absoluta válida
- O colocar el certificado en `~/.sifen/certs/` con nombre `*.p12`

## Flujo Completo de Envío

1. **Validar RUC del comprador** (gate consultaRUC)
   - Normalizar RUC con `app.sifen.ruc.normalize_truc()`
   - Consultar estado con `app.sifen.consulta_ruc.consulta_ruc_client()`
   - **Reglas robustas:**
     - Si `xContRUC.dRUCFactElec` existe: debe ser `"S"` (habilitado)
     - Si no: exigir `dCodRes == "0502"` (RUC encontrado)
   - Si `SIFEN_SKIP_RUC_GATE=1`, loguear WARNING y continuar

2. **Generar XML del DE**
   - Usar `tools.build_de.build_de_xml()` o `app.sifen_client.xml_generator_v150.create_rde_xml_v150()`
   - Extraer datos de `invoice_data` (buyer, transaction, items, etc.)
   - Limpiar XML con `app.sifen_client.xml_utils.clean_xml()`

3. **Firmar XML**
   - Usar `app.sifen_client.xml_signer.XmlSigner`
   - Certificado desde P12 (materializado a PEM temporal con permisos 600)
   - Cleanup automático de archivos PEM temporales

4. **Wrappear en siRecepDE**
   - Usar `tools.build_sirecepde.build_sirecepde_xml()` o construir manualmente
   - Generar `dId` único (YYYYMMDDHHMMSS + 1 dígito = 15 dígitos)
   - Remover declaración XML del DE firmado antes de wrappear

5. **Enviar a SIFEN**
   - Enviar vía SOAP usando `app.sifen_client.soap_client.SoapClient.recepcion_de()`
   - Usar mTLS con certificado P12 (materializado a PEM temporal)
   - Parsear `dCodRes`/`dMsgRes` robustamente (sin depender de prefijos ns)

6. **Persistir Resultado**
   - Guardar en tabla `sifen_submissions`:
     - `invoice_id`, `sifen_env`, `http_code`, `dCodRes`, `dMsgRes`
     - `signed_xml_sha256`, `endpoint`
     - `request_xml`, `response_xml` (truncados a 50KB)
     - `ruc_validated`, `ruc_validation_result` (JSON)
   - Actualizar tabla `invoices`:
     - `sifen_status`, `sifen_last_cod`, `sifen_last_msg`, `sifen_last_sent_at`

7. **Consultar Estado** (si es necesario)
   - Para lotes: esperar mínimo 10 minutos, consultar usando `dProtConsLote`
   - Para DE individual: CDC disponible en `extra.cdc` si `dCodRes=0200`

## Desarrollo y Testing

### Probar Consulta RUC

```bash
# Terminal 1: Iniciar servidor
cd tesaka-cv
uvicorn app.main:app --reload --port 8000

# Terminal 2: Probar endpoint
curl "http://localhost:8000/internal/sifen/consulta-ruc?value=4554737-8"
```

### Probar Normalización de RUC

```python
from app.sifen.ruc import normalize_truc

# Probar casos válidos
assert normalize_truc("4554737-8") == "45547378"
assert normalize_truc("45547378") == "45547378"

# Probar casos inválidos (deben lanzar RucFormatError)
try:
    normalize_truc("12345")
    assert False, "Debe lanzar error"
except RucFormatError:
    pass
```

### Modo CLI vs Web

**CLI:**
- Permite entrada interactiva para password del P12
- Útil para scripts y herramientas de línea de comandos

**Web:**
- NO permite entrada interactiva
- Requiere `SIFEN_P12_PASS` en `.env`
- Útil para endpoints HTTP desde frontend

## Seguridad

- **Nunca commitee** archivos `.env` con valores reales
- **Nunca loguee** passwords del P12
- **Nunca commitee** archivos PEM (están en `.gitignore`)
- Los archivos PEM temporales se crean con permisos 600 y se limpian automáticamente
- El endpoint `/internal/sifen/consulta-ruc` está protegido: solo disponible si `ENV != "production"`

## Referencias

- [Especificación SIFEN V150](https://ekuatia.set.gov.py)
- [Guía de Mejores Prácticas SIFEN](docs/SIFEN_BEST_PRACTICES.md)
- [Estado Actual SIFEN](docs/ESTADO_ACTUAL_SIFEN.md)
