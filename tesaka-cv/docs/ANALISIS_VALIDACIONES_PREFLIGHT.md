# Análisis: Validaciones Preflight Antes de Enviar a SIFEN

## Resumen Ejecutivo

Este documento identifica todas las validaciones "preflight" realizadas antes de enviar a SIFEN, compara con el caso actual (CDC nuevo, firma OK), e identifica qué validaciones faltan que podrían causar que SIFEN no encolé el lote.

---

## 1. VALIDACIONES PREFLIGHT ACTUALES

### 1.1 Función Principal: `preflight_soap_request()`

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 3313-3672  
**Contexto**: Se ejecuta ANTES de enviar el SOAP request a SIFEN

**Validaciones implementadas**:

#### ✅ 1. SOAP Request Parseable
- **Validación**: `etree.fromstring(payload_xml)` con `recover=False`
- **Error si**: XML mal formado
- **Artifact**: `artifacts/preflight_soap.xml`

#### ✅ 2. xDE Existe y es Base64 Válido
- **Validación**: Busca `<xDE>` en `rEnvioLote`, verifica que tenga texto, decodifica Base64
- **Error si**: `xDE` no encontrado, vacío, o Base64 inválido
- **Artifact**: `artifacts/preflight_soap.xml`

#### ✅ 3. ZIP Válido y Contiene lote.xml
- **Validación**: Abre ZIP, verifica que contenga `lote.xml` y solo ese archivo
- **Error si**: ZIP inválido, no contiene `lote.xml`, o contiene otros archivos
- **Artifact**: `artifacts/preflight_zip.zip`

#### ✅ 4. lote.xml Estructura Correcta
- **Validación**:
  - Root es `rLoteDE` (localname)
  - Namespace es `http://ekuatia.set.gov.py/sifen/xsd`
  - NO contiene `<dId>` (pertenece al SOAP)
  - NO contiene `<xDE>` (pertenece al SOAP)
  - Contiene al menos 1 `<rDE>` hijo directo
- **Error si**: Estructura incorrecta
- **Artifact**: `artifacts/preflight_lote.xml`, `artifacts/preflight_report.txt`

#### ✅ 5. DE Existe con Id
- **Validación**: Busca `<DE>` dentro de `<rDE>`, verifica atributo `Id`
- **Error si**: No se encuentra `<DE>` o no tiene `Id`
- **Artifact**: `artifacts/preflight_lote.xml`

#### ✅ 6. ds:Signature Dentro de DE
- **Validación**: Busca `<ds:Signature>` dentro de `<DE>` (namespace `http://www.w3.org/2000/09/xmldsig#`)
- **Error si**: No se encuentra `Signature` o no está dentro de `DE`
- **Artifact**: `artifacts/preflight_lote.xml`

#### ✅ 7. Algoritmos de Firma SHA256
- **Validación**:
  - `SignatureMethod.Algorithm == "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"`
  - `DigestMethod.Algorithm == "http://www.w3.org/2001/04/xmlenc#sha256"`
- **Error si**: Algoritmos incorrectos
- **Artifact**: `artifacts/preflight_lote.xml`

#### ✅ 8. Reference URI Correcto
- **Validación**: `Reference.URI == "#<DE@Id>"`
- **Error si**: URI no coincide con el `Id` del `DE`
- **Artifact**: `artifacts/preflight_lote.xml`

#### ✅ 9. X509Certificate Existe y No Vacío
- **Validación**: Busca `<X509Certificate>`, verifica que tenga texto no vacío
- **Error si**: No existe o está vacío (firma dummy)
- **Artifact**: `artifacts/preflight_lote.xml`

#### ✅ 10. SignatureValue Existe y No es Dummy
- **Validación**: Busca `<SignatureValue>`, verifica que tenga texto no vacío y no contenga "dummy" o "test"
- **Error si**: No existe, está vacío, o contiene texto dummy
- **Artifact**: `artifacts/preflight_lote.xml`

---

### 1.2 Validaciones Adicionales en el Pipeline

#### ✅ Guard-rail de Dependencias
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `_check_signing_dependencies()` (línea 2305)

- **Validación**: Verifica que `lxml` y `xmlsec` estén disponibles
- **Error si**: Faltan dependencias
- **Artifact**: `artifacts/sign_blocked_reason.txt`, `artifacts/sign_blocked_input.xml`

#### ✅ Validación de Tamaño
**Archivo**: `app/sifen_client/soap_client.py`  
**Función**: `_validate_size()` (línea 546)

- **Validación**: Verifica que el tamaño del XML no exceda límites (configurado por servicio)
- **Error si**: XML demasiado grande
- **Límites**: Configurados por servicio (ej: `siRecepLoteDE` tiene límite específico)

#### ✅ Sanity Gate: Caracteres Inválidos
**Archivo**: `tools/send_sirecepde.py`  
**Función**: `_scan_xml_bytes_for_common_malformed()` (línea 84)

- **Validación**: Detecta BOM UTF-8, caracteres de control inválidos, entidades `&` mal escapadas
- **Error si**: Caracteres inválidos detectados
- **Artifact**: `artifacts/prevalidator_raw.xml`, `artifacts/prevalidator_sanity_report.txt`

---

### 1.3 Validación XSD (Opcional)

**Archivo**: `tools/send_sirecepde.py`  
**Línea**: 4141-4150

- **Activación**: `SIFEN_VALIDATE_XSD=1` o `SIFEN_DEBUG_SOAP=1`
- **Validación**: Valida XML contra XSD locales (si están disponibles)
- **Nota**: No siempre está activado por defecto

---

## 2. VALIDADOR LOCAL (SifenValidator)

**Archivo**: `app/sifen_client/validator.py`  
**Clase**: `SifenValidator`

### 2.1 Validaciones Disponibles

#### ✅ `validate_xml_structure()`
- **Validación**: Verifica que el XML sea well-formed (parsea con `lxml`)
- **Retorna**: `{"valid": bool, "errors": [...]}`

#### ✅ `validate_against_xsd()`
- **Validación**: Valida XML contra XSD locales (si están disponibles)
- **Retorna**: `{"valid": bool, "errors": [...], "xsd_used": str}`
- **Nota**: Requiere XSD descargados en `schemas_sifen/`

#### ✅ `prevalidate_with_service()`
- **Validación**: Envía XML al Prevalidador SIFEN público
- **URL**: `https://ekuatia.set.gov.py/prevalidador/validacion`
- **Retorna**: `{"valid": bool, "error": str, "suggestion": str}`
- **Nota**: Requiere conexión a internet

---

## 3. COMPARACIÓN CON CASO ACTUAL (CDC Nuevo, Firma OK)

### 3.1 Caso Actual: CDC Nuevo, Firma OK

**Escenario**:
- ✅ CDC generado correctamente (44 dígitos)
- ✅ Firma digital correcta (SHA256, Reference URI correcto)
- ✅ Estructura XML correcta (rLoteDE, rDE, DE)
- ✅ Preflight pasa todas las validaciones

**Resultado**: `dCodRes=0301 "Lote no encolado para procesamiento"` con `dProtConsLote=0`

---

### 3.2 Validaciones que PASAN en Preflight

| Validación | Estado | Nota |
|------------|--------|------|
| SOAP parseable | ✅ Pasa | XML bien formado |
| xDE Base64 válido | ✅ Pasa | ZIP decodificable |
| ZIP válido | ✅ Pasa | Contiene lote.xml |
| lote.xml estructura | ✅ Pasa | Root rLoteDE, contiene rDE |
| DE con Id | ✅ Pasa | CDC presente |
| ds:Signature dentro DE | ✅ Pasa | Firma correcta |
| Algoritmos SHA256 | ✅ Pasa | SignatureMethod y DigestMethod correctos |
| Reference URI | ✅ Pasa | Coincide con DE@Id |
| X509Certificate | ✅ Pasa | Certificado real |
| SignatureValue | ✅ Pasa | No es dummy |

---

## 4. VALIDACIONES FALTANTES (Que Podrían Causar dCodRes=0301)

### 4.1 Validaciones de Campos Obligatorios del DE

#### ❌ Timbrado (dNumTim)
- **Campo**: `<gTimb><dNumTim>`
- **Validación faltante**: 
  - ¿Timbrado existe y es válido?
  - ¿Timbrado está habilitado en SIFEN?
  - ¿Timbrado corresponde al RUC?
- **Riesgo**: SIFEN puede rechazar si timbrado no existe o no está habilitado

#### ❌ Fecha de Emisión (dFeEmi)
- **Campo**: `<gDatGralOpe><dFeEmi>`
- **Validación faltante**:
  - ¿Fecha está en formato correcto (YYYY-MM-DD)?
  - ¿Fecha no es futura?
  - ¿Fecha no es muy antigua (ej: > 1 año)?
  - ¿Fecha está dentro de la vigencia del timbrado?
- **Riesgo**: SIFEN puede rechazar si fecha es inválida o fuera de vigencia

#### ❌ Totales (dTotGralOpe)
- **Campo**: `<gTotOpe><dTotGralOpe>`
- **Validación faltante**:
  - ¿Total general existe y es > 0?
  - ¿Total general coincide con suma de items?
  - ¿Totales de IVA son correctos?
- **Riesgo**: SIFEN puede rechazar si totales son incorrectos o no coinciden

#### ❌ Tipo de Documento (dTipDoc)
- **Campo**: `<gDtipDE><dTipDoc>`
- **Validación faltante**:
  - ¿Tipo de documento es válido (1=Factura, 2=Nota de Crédito, etc.)?
  - ¿Tipo de documento corresponde al timbrado?
- **Riesgo**: SIFEN puede rechazar si tipo de documento no es válido

#### ❌ RUC Emisor (dRucEm, dDVEmi)
- **Campo**: `<gEmis><dRucEm>`, `<gEmis><dDVEmi>`
- **Validación faltante**:
  - ¿RUC existe y es válido?
  - ¿RUC está habilitado en SIFEN?
  - ¿DV del RUC es correcto?
  - ¿RUC corresponde al certificado de firma?
- **Riesgo**: SIFEN puede rechazar si RUC no existe o no está habilitado

#### ❌ Establecimiento y Punto de Expedición (dEst, dPunExp)
- **Campo**: `<gTimb><dEst>`, `<gTimb><dPunExp>`
- **Validación faltante**:
  - ¿Establecimiento existe para el timbrado?
  - ¿Punto de expedición existe para el establecimiento?
  - ¿Establecimiento/punto están habilitados?
- **Riesgo**: SIFEN puede rechazar si establecimiento/punto no existen

#### ❌ Número de Documento (dNumDoc)
- **Campo**: `<gTimb><dNumDoc>`
- **Validación faltante**:
  - ¿Número de documento es válido (7 dígitos)?
  - ¿Número de documento no está duplicado (mismo timbrado/est/punto)?
- **Riesgo**: SIFEN puede rechazar si número está duplicado

---

### 4.2 Validaciones de CDC

#### ❌ CDC Válido
- **Campo**: `<DE Id="...">`
- **Validación faltante**:
  - ¿CDC tiene 44 dígitos?
  - ¿CDC es numérico?
  - ¿DV del CDC es correcto (módulo 11)?
  - ¿CDC no está duplicado (ya enviado a SIFEN)?
- **Riesgo**: SIFEN puede rechazar si CDC es inválido o duplicado

#### ❌ CDC Coincide con Campos
- **Validación faltante**:
  - ¿CDC fue generado con los mismos campos (RUC, timbrado, est, punto, num, tipo, fecha, monto)?
  - ¿CDC no fue modificado manualmente?
- **Riesgo**: SIFEN puede rechazar si CDC no coincide con campos

---

### 4.3 Validaciones de Ambiente

#### ❌ Ambiente Correcto
- **Validación faltante**:
  - ¿RUC corresponde al ambiente (test/prod)?
  - ¿Certificado corresponde al ambiente?
  - ¿Timbrado corresponde al ambiente?
- **Riesgo**: SIFEN puede rechazar si hay mismatch de ambiente

---

### 4.4 Validaciones de Estructura XML (Campos Obligatorios)

#### ❌ Campos Obligatorios Presentes
- **Validación faltante**: Verificar que todos los campos obligatorios según XSD estén presentes:
  - `dDVId` (DV del CDC)
  - `dFecFirma` (Fecha de firma)
  - `dSisFact` (Sistema de facturación)
  - `gOpeDE` (Operación)
  - `gTimb` (Timbrado)
  - `gDatGralOpe` (Datos generales)
  - `gDtipDE` (Tipo de documento)
  - `gEmis` (Emisor)
  - `gTotOpe` (Totales)
- **Riesgo**: SIFEN puede rechazar si faltan campos obligatorios

---

### 4.5 Validaciones de Negocio

#### ❌ Items con Totales Correctos
- **Validación faltante**:
  - ¿Cada item tiene precio, cantidad, subtotal?
  - ¿Subtotal de items coincide con total general?
  - ¿IVA calculado correctamente?
- **Riesgo**: SIFEN puede rechazar si totales no coinciden

#### ❌ Cliente Válido
- **Validación faltante**:
  - ¿Cliente tiene RUC válido (si es contribuyente)?
  - ¿Cliente tiene DV correcto?
  - ¿Cliente tiene razón social?
- **Riesgo**: SIFEN puede rechazar si datos de cliente son inválidos

#### ❌ Moneda Válida
- **Validación faltante**:
  - ¿Moneda es válida (PYG, USD, etc.)?
  - ¿Moneda corresponde al ambiente?
- **Riesgo**: SIFEN puede rechazar si moneda no es válida

---

## 5. RESUMEN: Validaciones Faltantes

### 5.1 Validaciones Críticas (Alto Riesgo de dCodRes=0301)

| Validación | Campo | Riesgo | Prioridad |
|------------|-------|--------|-----------|
| Timbrado válido y habilitado | `dNumTim` | Alto | 🔴 Alta |
| Fecha dentro de vigencia | `dFeEmi` | Alto | 🔴 Alta |
| RUC válido y habilitado | `dRucEm`, `dDVEmi` | Alto | 🔴 Alta |
| CDC no duplicado | `DE@Id` | Alto | 🔴 Alta |
| CDC válido (DV correcto) | `DE@Id` | Alto | 🔴 Alta |
| Establecimiento/punto válidos | `dEst`, `dPunExp` | Medio | 🟡 Media |
| Número de documento no duplicado | `dNumDoc` | Medio | 🟡 Media |
| Totales correctos | `dTotGralOpe` | Medio | 🟡 Media |
| Tipo de documento válido | `dTipDoc` | Medio | 🟡 Media |
| Ambiente correcto | Config | Medio | 🟡 Media |

---

### 5.2 Validaciones Recomendadas (Bajo Riesgo, pero Útiles)

| Validación | Campo | Riesgo | Prioridad |
|------------|-------|--------|-----------|
| Campos obligatorios presentes | Varios | Bajo | 🟢 Baja |
| Items con totales correctos | `gItemDE` | Bajo | 🟢 Baja |
| Cliente válido | `gCamDE` | Bajo | 🟢 Baja |
| Moneda válida | `dMonId` | Bajo | 🟢 Baja |

---

## 6. PROPUESTA: Validaciones Adicionales para Preflight

### 6.1 Función: `validate_de_business_rules()`

**Archivo**: `tools/send_sirecepde.py` (nueva función)

```python
def validate_de_business_rules(
    de_elem: etree._Element,
    env: str,
    artifacts_dir: Optional[Path] = None
) -> Tuple[bool, Optional[str]]:
    """
    Valida reglas de negocio del DE que podrían causar dCodRes=0301.
    
    Validaciones:
    1. Timbrado existe y es válido (consultar SIFEN si es posible)
    2. Fecha dentro de vigencia del timbrado
    3. RUC válido y habilitado
    4. CDC válido (DV correcto)
    5. CDC no duplicado (consultar BD)
    6. Establecimiento/punto válidos
    7. Número de documento no duplicado
    8. Totales correctos
    9. Tipo de documento válido
    10. Ambiente correcto (RUC/certificado corresponden al ambiente)
    
    Returns:
        Tupla (success, error_message)
    """
    errors = []
    
    # 1. Validar timbrado
    d_num_tim = de_elem.find(f".//{{{SIFEN_NS}}}dNumTim")
    if d_num_tim is None or not d_num_tim.text:
        errors.append("Falta <dNumTim> (timbrado)")
    else:
        timbrado = d_num_tim.text.strip()
        # TODO: Consultar SIFEN si timbrado existe y está habilitado
    
    # 2. Validar fecha
    d_fe_emi = de_elem.find(f".//{{{SIFEN_NS}}}dFeEmi")
    if d_fe_emi is None or not d_fe_emi.text:
        errors.append("Falta <dFeEmi> (fecha de emisión)")
    else:
        fecha_str = d_fe_emi.text.strip()
        # Validar formato YYYY-MM-DD
        # Validar que no sea futura
        # Validar que no sea muy antigua
    
    # 3. Validar RUC
    d_ruc_em = de_elem.find(f".//{{{SIFEN_NS}}}dRucEm")
    d_dv_emi = de_elem.find(f".//{{{SIFEN_NS}}}dDVEmi")
    if d_ruc_em is None or not d_ruc_em.text:
        errors.append("Falta <dRucEm> (RUC emisor)")
    if d_dv_emi is None or not d_dv_emi.text:
        errors.append("Falta <dDVEmi> (DV RUC)")
    # TODO: Validar DV del RUC
    # TODO: Consultar SIFEN si RUC está habilitado
    
    # 4. Validar CDC
    de_id = de_elem.get("Id")
    if not de_id:
        errors.append("Falta atributo Id en <DE> (CDC)")
    else:
        # Validar longitud (44 dígitos)
        if len(de_id) != 44 or not de_id.isdigit():
            errors.append(f"CDC inválido: debe ser 44 dígitos, encontrado: {len(de_id)}")
        else:
            # Validar DV del CDC
            from app.sifen_client.cdc_utils import validate_cdc
            is_valid, pos, expected = validate_cdc(de_id)
            if not is_valid:
                errors.append(f"CDC inválido: DV incorrecto en posición {pos} (esperado: {expected})")
            
            # Verificar si CDC ya fue usado
            from web.db import get_conn
            conn = get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM de_documents WHERE cdc = ?", (de_id,))
            if cursor.fetchone():
                errors.append(f"CDC duplicado: ya existe en BD (puede causar dCodRes=0301)")
            conn.close()
    
    # 5. Validar establecimiento y punto
    d_est = de_elem.find(f".//{{{SIFEN_NS}}}dEst")
    d_pun_exp = de_elem.find(f".//{{{SIFEN_NS}}}dPunExp")
    if d_est is None or not d_est.text:
        errors.append("Falta <dEst> (establecimiento)")
    if d_pun_exp is None or not d_pun_exp.text:
        errors.append("Falta <dPunExp> (punto de expedición)")
    # TODO: Consultar SIFEN si establecimiento/punto existen
    
    # 6. Validar número de documento
    d_num_doc = de_elem.find(f".//{{{SIFEN_NS}}}dNumDoc")
    if d_num_doc is None or not d_num_doc.text:
        errors.append("Falta <dNumDoc> (número de documento)")
    # TODO: Verificar si número está duplicado
    
    # 7. Validar totales
    d_tot_gral_ope = de_elem.find(f".//{{{SIFEN_NS}}}dTotGralOpe")
    if d_tot_gral_ope is None or not d_tot_gral_ope.text:
        errors.append("Falta <dTotGralOpe> (total general)")
    else:
        try:
            total = float(d_tot_gral_ope.text.strip())
            if total <= 0:
                errors.append(f"Total general debe ser > 0, encontrado: {total}")
        except ValueError:
            errors.append(f"Total general inválido: {d_tot_gral_ope.text}")
        # TODO: Validar que total coincide con suma de items
    
    # 8. Validar tipo de documento
    d_tip_doc = de_elem.find(f".//{{{SIFEN_NS}}}dTipDoc")
    if d_tip_doc is None or not d_tip_doc.text:
        errors.append("Falta <dTipDoc> (tipo de documento)")
    else:
        tipo_doc = d_tip_doc.text.strip()
        valid_types = ["1", "2", "3", "4", "5", "6", "7", "8"]  # Verificar con documentación
        if tipo_doc not in valid_types:
            errors.append(f"Tipo de documento inválido: {tipo_doc} (válidos: {valid_types})")
    
    # 9. Validar ambiente
    # TODO: Verificar que RUC corresponde al ambiente (test/prod)
    # TODO: Verificar que certificado corresponde al ambiente
    
    if errors:
        error_msg = "Validaciones de negocio fallaron:\n" + "\n".join(f"  - {e}" for e in errors)
        if artifacts_dir:
            artifacts_dir.joinpath("preflight_business_rules_errors.txt").write_text(
                error_msg, encoding="utf-8"
            )
        return (False, error_msg)
    
    return (True, None)
```

---

### 6.2 Integración en Preflight

**Archivo**: `tools/send_sirecepde.py`  
**Función**: `preflight_soap_request()` (línea 3313)

**Agregar después de validación de firma** (línea ~3660):

```python
# 11. Validar reglas de negocio del DE
business_valid, business_error = validate_de_business_rules(
    de_elem, env=env, artifacts_dir=artifacts_dir
)
if not business_valid:
    return (False, business_error)
```

---

## 7. RECOMENDACIONES

### 7.1 Validaciones Inmediatas (Alta Prioridad)

1. **Validar CDC no duplicado**: Consultar BD antes de enviar
2. **Validar CDC válido**: Verificar DV del CDC (módulo 11)
3. **Validar fecha no futura**: Rechazar si fecha es futura
4. **Validar totales > 0**: Rechazar si total general es 0 o negativo

### 7.2 Validaciones Futuras (Media Prioridad)

1. **Consultar SIFEN si timbrado existe**: Usar servicio de consulta de timbrado
2. **Consultar SIFEN si RUC está habilitado**: Usar servicio de consulta de RUC
3. **Validar fecha dentro de vigencia**: Consultar vigencia del timbrado
4. **Validar número de documento no duplicado**: Consultar BD de documentos enviados

### 7.3 Validaciones Opcionales (Baja Prioridad)

1. **Validar totales coinciden con items**: Sumar items y comparar con total general
2. **Validar cliente válido**: Verificar RUC y DV del cliente
3. **Validar moneda válida**: Verificar que moneda es válida según SIFEN

---

## 8. CONCLUSIÓN

### 8.1 Validaciones Actuales

✅ **Preflight actual valida**:
- Estructura XML (SOAP, ZIP, lote.xml)
- Firma digital (algoritmos, Reference URI, certificado)
- Campos básicos (DE Id, Signature)

❌ **Preflight actual NO valida**:
- Campos obligatorios del DE (timbrado, fecha, totales, tipo documento)
- Reglas de negocio (CDC duplicado, fecha válida, totales correctos)
- Ambiente (RUC/certificado corresponden al ambiente)
- Habilitación en SIFEN (timbrado, RUC, establecimiento/punto)

### 8.2 Impacto en dCodRes=0301

**Causas probables de `dCodRes=0301` que NO se detectan en preflight**:
1. CDC duplicado (ya enviado anteriormente)
2. Timbrado no existe o no está habilitado
3. RUC no existe o no está habilitado
4. Fecha fuera de vigencia del timbrado
5. Establecimiento/punto no existen
6. Número de documento duplicado
7. Ambiente incorrecto (test vs prod)

**Recomendación**: Agregar validaciones de negocio en preflight para detectar estos casos ANTES de enviar a SIFEN.

---

**Última actualización**: 2025-01-XX  
**Versión**: 1.0

