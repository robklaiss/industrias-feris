# SIFEN Runbook (Tesaka-CV) — Debug, Fixes y Checklist

> Objetivo: que TODO lo que descubrimos en estos días quede documentado y no se rompa de nuevo.
> Este documento es la guía oficial de operación, debugging, QA y salida a producción.

## 0) Glosario rápido
- **DE**: Documento Electrónico (XML firmado).
- **CDC (44 dígitos)**: identificador del DE (va en `DE@Id`).
- **DV (CDC)**: dígito verificador del CDC.
- **siRecepLoteDE**: recepción asíncrona (envío de lote).
- **rEnviConsLoteDe**: consulta de lote (resultado final por documento).
- **dProtConsLote**: protocolo para consultar el lote.

---

## 1) Lo que se arregló (hallazgos y fixes)

### 1.1 Guardado correcto de SOAP (artifacts)
**Problema:** se estaban guardando artifacts como `repr()` de objetos (`<Element ...>`), imposible de parsear como XML.  
**Fix:** convertir envelope/request a bytes XML reales antes de guardar.

**Resultado esperado:**
- `artifacts/consulta_lote_response_<ts>.xml` empieza con `<?xml version='1.0' encoding='UTF-8'?>`
- `parse_consulta_lote.py` encuentra `dFecProc`, `dCodResLot`, `dMsgResLot` y documentos.

---

### 1.2 Parser robusto de consulta-lote (SOAP/XML)
**Problema:** namespaces / basura / artifacts "sucios".  
**Fix:** parser con `recover=True`, `huge_tree=True` + XPath usando `local-name()` y limpieza del inicio real del XML.

Script: `artifacts/parse_consulta_lote.py`

---

### 1.3 CDC/DV correcto (Mod 11)
**Problema crítico:** DV calculado mal (pesos incompletos) → SIFEN rechaza con `1003 TEST - DV del CDC inválido`.  
**Fix:** DV módulo 11 con pesos **[2..9]** (ciclo).

Componentes:
- `app/sifen_client/cdc_utils.py`
  - `calc_dv_mod11(num_str)`
  - `validate_cdc(cdc44)`
  - `fix_cdc(cdc44)`
- `xml_generator_v150.py` usa DV correcto
- `tools/check_cdc.py` verifica y puede corregir

**Comando útil:**
- `python -m tools.check_cdc <CDC> --fix`

---

### 1.4 Validación defensiva del CDC antes de generar/enviar
**Problemas vistos:**
- `DE@Id` con letra (ej: contiene `A`) → no es CDC válido.
- CDC no numérico → debe fallar claro.

**Fix:** validar que CDC sea:
- longitud 44
- solo dígitos 0-9
- DV correcto (autocorregible si corresponde)

---

### 1.5 Estructura real del JSON de consulta lote (gResProc "puede ser lista")
**Problema:** a veces en `consulta_lote_*.json` el campo:
- `gResProc` no es dict sino **LISTA** (ej: `gResProc[0].dCodRes`, `gResProc[0].dMsgRes`)
y por eso el script mostraba `dCodRes/dMsgRes = None`.

**Fix:** scripts de inspección y parse deben contemplar:
- `gResProc` dict
- `gResProc` list y leer el primer elemento (y/o todos)

Scripts:
- `tools/inspect_response_recepcion.py` (recibe-lote)
- `tools/inspect_consulta_lote_json.py` (consulta-lote)

---

### 1.6 Errores intermitentes de red (Connection reset by peer)
**Observación real:** `ConnectionResetError(54, 'Connection reset by peer')` puede ocurrir en consulta lote.  
**Recomendación:** retry con backoff / reintento manual (no asumir fallo lógico).

---

### 1.7 XMLDSIG/Digest mismatch – Confirmación de predigest vs DE final
**Aprendizaje clave:** Confirmación de que `predigest.xml` extraído desde xmlsec (`== PreDigest data`) es idéntico al `<DE>` presente en el XML final (`diff` vacío cuando se exporta el DE sin XML declaration). Esto confirma que el problema NO es "XML modificado después de firmar" por declaración XML u otras diferencias de serialización simple; el mismatch viene de que el `DigestValue` embebido fue calculado con otro pipeline/representación (p.ej. transforms diferentes).

**Comandos de verificación:**
```bash
# Extraer predigest desde xmlsec
xmlsec1 --verify --insecure --id-attr:Id DE \
  --store-references \
  --print-debug \
  --print-xml-debug \
  --verbose lote_from_zip.xml 2>&1 \
  | awk '/== PreDigest data - start buffer:/{flag=1; next}
         /== PreDigest data - end buffer/{flag=0}
         flag{print}' > predigest.xml

# Extraer DE del XML final (sin XML declaration)
xmllint --xpath "//DE" lote_from_zip.xml > de_final.xml

# Comparar
diff predigest.xml de_final.xml
# Si diff está vacío: el DE no fue modificado post-firma
```

---

## 2) Flujo de punta a punta (lo que debe pasar)
1) Generar DE (XML) con CDC válido y DV correcto.
2) Firmar DE y normalizar orden de nodos del `rDE` (si aplica).
3) Enviar lote con `send_sirecepde` → obtener `dProtConsLote (0300 "Lote recibido con éxito")`.
4) Consultar lote con `follow_lote` o `consulta_lote_de` hasta que concluya (`dCodResLot=0362`).
5) Ver resultado por DE:
   - `dEstRes` (Aceptado/Rechazado)
   - `dCodRes / dMsgRes` (pueden venir dentro de `gResProc` list)

---

## 3) Comandos operativos (QA / debug)

### 3.1 Envío (siRecepLoteDE)
- `SIFEN_DEBUG_SOAP=1 SIFEN_VALIDATE_XSD=1 python -m tools.send_sirecepde --env test --xml <archivo.xml> --artifacts-dir artifacts`

### 3.2 Inspeccionar respuesta de recepción (protocolo)
- `python -m tools.inspect_response_recepcion --all`

### 3.3 Seguir lote (consulta)
- `python -m tools.follow_lote --env test --wsdl-file artifacts/consulta-lote.wsdl.xml --wsdl-cache-dir artifacts --once`

### 3.4 Inspeccionar JSON de consulta-lote
- `python -m tools.inspect_consulta_lote_json`
- `python -m tools.inspect_consulta_lote_json artifacts/consulta_lote_<ts>.json --dump-paths`

### 3.5 Validaciones
- `python -m tools.check_cdc <CDC>`
- `python -m tools.validate_xsd --schema de <archivo.xml>` (si aplica)

---

## 4) Checklist de "no se rompe más" (reglas)
- ✅ Guardar SOAP artifacts como XML real, no `repr()`.
- ✅ CDC siempre 44 dígitos numéricos.
- ✅ DV con pesos 2-9 (mod11).
- ✅ Scripts contemplan `gResProc` dict **y** list.
- ✅ Manejo de resets de conexión como transitorio (retry).
- ✅ Logs + artifacts siempre guardados por timestamp.

---

## 5) Checklist de pruebas finales (antes de PROD)
- [ ] Generar DE con datos reales del emisor (RUC/DV/timbrado/establecimiento/punto/numero).
- [ ] Validar XSD local (configurar `SIFEN_XSD_DIR` si corresponde).
- [ ] Firmar y verificar que el XML final tenga `ds:Signature`.
- [ ] Enviar lote en TEST y recibir `0300`.
- [ ] Consultar lote y confirmar `0362` y resultado por DE.
- [ ] Confirmar que el error anterior "DV inválido" ya no aparece.
- [ ] Probar al menos 3 casos:
  - 1 factura simple (1 ítem, IVA 10)
  - 1 factura con IVA 5 (si aplica)
  - 1 caso con 2 ítems / totales
- [ ] Confirmar persistencia (BD guarda lote, protocolo, timestamps).
- [ ] Confirmar que errores se reportan con mensaje claro (sin "None" ambiguo).
- [ ] Confirmar que artifacts generados son legibles y parseables.

---

## 6) Plan de salida a producción (Go/No-Go)
**GO si:**
- TEST: 3 casos pasan punta a punta.
- Consulta-lote devuelve estados esperados por DE.
- CDC/DV correcto en todos los casos.
- Logs y artifacts se generan bien.
- Variables PROD listas (certificado, contraseñas, endpoints, WSDL prod).

**NO-GO si:**
- Aún aparecen errores de CDC/DV / "no correspondiente con el XML".
- No hay validación XSD consistente.
- No se puede reproducir y entender cada rechazo con dCodRes/dMsgRes.
- No hay trazabilidad (protocolo → lote → resultado).

---

## 7) Variables de entorno (referencia)
- `SIFEN_ENV` (test/prod)
- `SIFEN_CERT_PATH` / `SIFEN_CERT_PASSWORD`
- `SIFEN_MTLS_P12_PATH` / `SIFEN_MTLS_P12_PASSWORD`
- `SIFEN_SIGN_P12_PATH` / `SIFEN_SIGN_P12_PASSWORD`
- `SIFEN_DEBUG_SOAP=1`
- `SIFEN_VALIDATE_XSD=1`
- `SIFEN_XSD_DIR=<path>` (si se usa)

---

## 8) Historial de incidentes (resumen)
- Rechazo por DV inválido → fix mod11 pesos 2-9.
- CDC alfanumérico (contiene letra) → validar y fallar claro.
- `gResProc` en JSON como lista → contemplar list/dict.
- Artifacts SOAP guardados como repr → serializar XML real.
- Resets de conexión en consulta → tratar como transitorio.

---

# Fin del documento


---

## Aprendizaje / Anti-regresión — Error 0160 "XML Mal Formado"

**Síntoma**
- SIFEN devuelve 0160 "XML Mal Formado" pero `xmlsec1 --verify ...` da OK.

**Causa real encontrada**
- Faltaba `dVerFor` dentro de `rDE` (debe ser el primer hijo, valor 150 para v150), por lo que el XSD falla aunque la firma sea correcta.

**Checklist anti-regresión**
1) Siempre extraer y revisar el lote REAL enviado (desde soap_last_request_SENT → xDE → zip → lote.xml)
2) Verificar firma con xmlsec
3) Verificar estructura mínima: `rDE children` debe comenzar con `dVerFor`, y `gCamFuFD` NO debe estar dentro de `DE`.

**Comandos de verificación**
```bash
# Extraer lote del SOAP enviado
unzip -p artifacts/soap_last_request_SENT.xml xDE > xDE.zip
unzip -p xDE.zip lote.xml > lote_from_SENT.xml

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_from_SENT.xml

# Verificar estructura
python - <<'PY'
from lxml import etree
doc = etree.parse("lote_from_SENT.xml")
NS="http://ekuatia.set.gov.py/sifen/xsd"
ns={"s":NS}
rde = doc.xpath("//s:rDE", namespaces=ns)[0]
children = [c.tag.split("}")[-1] for c in rde]
print("rDE children:", children)
dver = rde.find(f"{{{NS}}}dVerFor")
print("dVerFor:", None if dver is None else dver.text)
PY
```
