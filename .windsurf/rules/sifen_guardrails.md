---
trigger: always_on
---

# Guardrails SIFEN (Always On)
- Antes de proponer un cambio: abrir y leer `docs/SIFEN_LEARNINGS.md`.
- Si el síntoma coincide con una entrada existente: aplicar ese fix primero.
- Después de resolver algo y verificarlo: agregar una nueva entrada al final de `docs/SIFEN_LEARNINGS.md` usando el formato estándar.
- Siempre incluir comandos reproducibles (ej: xmlsec1 verify, unzip -p, grep de Id/Reference URI) y paths reales generados por el run.
- No sugerir placeholders como rde_signed_<Id>.xml: siempre resolver el filename real (ls -t / grep Id) y escribir el comando con ese archivo real.

## XMLSEC – Cómo extraer el PreDigest real (no dejar predigest vacío)

- Si `predigest.xml` queda en 0 bytes, el extractor no encontró los marcadores en la salida de `xmlsec1`.
- En nuestras pruebas, los marcadores `== PreDigest data - start buffer:` y `== PreDigest data - end buffer` aparecen con `xmlsec1 --verify ... --verbose` (no hace falta `--print-debug`).
- Comando recomendado (guardar log y predigest):
  - `xmlsec1 --verify --insecure --id-attr:Id DE --verbose lote_from_zip.xml 2>&1 | tee xmlsec-debug.log | awk '...marcadores...' > predigest.xml` 
- Siempre hacer sanity-check:
  - `wc -c predigest.xml` debe ser > 0
  - `grep -n "PreDigest data" xmlsec-debug.log` debe mostrar los marcadores

## XMLSEC – Si predigest.xml queda vacío

- Si `predigest.xml` queda en 0 bytes, no asumir que awk está mal: primero verificar si `xmlsec-debug.log` contiene o no los marcadores.
- Comandos de sanity-check obligatorios:
  - `wc -c xmlsec-debug.log predigest.xml` 
  - `sed -n '1,80p' xmlsec-debug.log` 
  - `grep -niE "predigest|start buffer|end buffer" xmlsec-debug.log` 
- Si el log NO contiene "PreDigest…", entonces esa versión/flags de `xmlsec1` no está imprimiendo el buffer y hay que usar otro método (ej: extraer el nodo referenciado y canonicalizarlo nosotros).

## XMLSEC – Predigest vacío por falta de flags

- Si `predigest.xml` queda en 0 bytes, casi siempre es porque `xmlsec1` NO imprimió "== PreDigest data …".
- Para obtener "PreDigest data" hay que correr con flags de debug, no solo `--verbose`:
  - `--print-debug --print-xml-debug` (y idealmente `--store-references`)
- Guardar siempre el output completo en un log (ej: `xmlsec-debug-full.log`) sin `grep` en el medio antes de extraer.
- Sanity checks:
  - `wc -c xmlsec-debug-full.log predigest.xml` 
  - `grep -n "PreDigest data" xmlsec-debug-full.log | head`

## XMLDSIG – Para extraer PreDigest real de xmlsec

- `--verbose` NO alcanza: el log puede quedar de ~300 bytes y no incluye PreDigest.
- Para obtener el bloque "== PreDigest data …" hay que correr:
  - `--print-debug --print-xml-debug --verbose` (opcional `--store-references`)
- Validación rápida:
  - `wc -c xmlsec-debug-full.log predigest.xml` 
  - `grep -n "PreDigest data" xmlsec-debug-full.log | head`

## XMLDSIG – "predigest" impreso vs bytes reales

- El bloque "== PreDigest data …" de `--print-xml-debug` puede NO ser byte-exacto (es debug impreso).
- Para comparar en serio, preferir `xmlsec1 --store-references` y ubicar los archivos `xmlsec*ref*` generados: contienen el octet-stream real post-transforms.
- Cuando haya mismatch:
  1) localizar dumps de `--store-references` 
  2) hashear esos bytes (sha256 base64)
  3) recién ahí concluir si el `DigestValue` fue calculado con otros transforms o si el XML cambió después de firmar.

## SIFEN — Error 0160 "XML Mal Formado" con xmlsec OK

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


## [2026-01-17] Fix definitivo error 0160 + regla RUC sin DV + validaciones XML v150

### 1) Bugfix 0160 (XML mal formado)
- Se resolvió el error 0160 restaurando un commit estable de `tools/send_sirecepde.py` y re-aplicando correctamente el fix de "rebuilt ZIP".
- Regla anti-regresión: ante cambios de empaquetado/zip/envelope, correr un "smoke send" que verifique que SIFEN ya no devuelve 0160.

### 2) Bugfix 0160 en consulta_ruc por manejo de RUC
- Causa: si el usuario provee un RUC sin DV (ej: "4554737"), el código NO debe truncar dígitos (no convertirlo en 6 dígitos).
- Regla: aceptar ambos formatos:
  - "4554737" (sin DV) → usar tal cual como RUC (sin DV)
  - "4554737-8" (con DV) → extraer DV correctamente, y derivar RUC sin DV cuando el WS lo requiera.
- Nota de dominio: guías DNIT/Marangatu y formularios indican "RUC sin dígito verificador (DV)" para estos trámites.

### 3) Checklist XML correcto (v150)
- `<rLoteDE>` sin prefijos
- `<rDE>` sin prefijos
- `<dVerFor>150</dVerFor>` como primer hijo de `<rDE>` 
- `<Signature>` sin prefijos
- Regla anti-regresión: añadir un test/validador que falle si aparece un namespace/prefijo inesperado en esos nodos.

### 4) Estado actual esperado
- `consulta_ruc` devuelve 0502 "RUC encontrado" cuando el request está bien.
- Si `dRUCFactElec='N'`, el bloqueo ya no es técnico: requiere habilitar el RUC como facturador electrónico en Marangatu/SIFEN.

### Cómo detectar rápido si es técnico vs administrativo
- 0160 → casi siempre estructura XML/namespace/firma/envelope
- 0502 + dRUCFactElec=N → habilitación administrativa pendiente



### INVARIANTS (anti-regresión)
- INVARIANT-0160-XML: si aparece 0160, revisar namespaces/prefijos y orden de `<dVerFor>` antes de tocar lógica de negocio.
- INVARIANT-RUC: RUC sin DV nunca se trunca; si viene con DV, extraer DV; si viene sin DV, usar tal cual.
- INVARIANT-V150-NO-PREFIX: `<rLoteDE>`, `<rDE>`, `<Signature>` deben ir sin prefijos.
