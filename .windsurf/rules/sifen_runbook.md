# SIFEN Runbook (anti-regresión)

## 1) Regla de oro: siempre depurar el XML REAL ENVIADO
- Extraer el xDE desde artifacts/soap_last_request_SENT.xml
- Decodificar base64 -> ZIP -> extraer lote.xml
- Validar contra ese lote.xml, no contra archivos "intermedios".

## 2) LOTE AS-IS
- Si `--xml` apunta a un lote (root `rLoteDE`), se envía AS-IS:
  - No reconstruir
  - No re-firmar
  - No normalizar CDC
  - No fallback a artifacts/last_lote.xml
- Si el parse/detección falla, abortar con error explícito (prohibido enviar otro archivo silenciosamente).

## 3) Diferenciar firma vs XSD
- `xmlsec1 --verify OK` NO garantiza que SIFEN acepte.
- Para error 0160 ("XML Mal Formado"), la acción obligatoria es:
  - Validar `lote_from_SENT.zip.xml` contra el XSD correcto de LOTE (v150).
  - El mensaje exacto del validador define el fix (orden de elementos / ubicación / namespace).

## 4) Check rápido recomendado antes de enviar
- xmlsec verify del lote real
- XSD validate del lote real
- Comparar SHA256 del lote real vs archivo que se quiso enviar
## Validación XSD v150 (xmllint)
Para validar un lote/DE con xmllint, entrar al directorio donde está el XSD para que funcionen los imports/includes:
- `cd tesaka-cv/xsd`
- `xmllint --noout --schema siRecepDE_v150.xsd ../<ruta-al-xml>`
Si `exit=0`, el XML pasa XSD localmente; si SIFEN devuelve 0160 igual, investigar reglas adicionales server-side (estructura, namespaces, valores, etc.).



## Validación XSD: NO validar rLoteDE con siRecepDE_v150.xsd
- Error típico al validar lote: "Element 'rLoteDE': No matching global declaration available for the validation root."
- Causa: siRecepDE_v150.xsd no tiene como root a rLoteDE; es para DE/rDE, no para el lote.
- Acción correcta:
  1) Buscar qué XSD declara rLoteDE con: grep -R "rLoteDE" en xsd/ y schemas_sifen/
  2) Usar ese XSD como entrypoint para xmllint.
- Nota: includes tipo rde/150/RDE_Group.xsd pueden no existir como URL pública; preferir resolver desde XSD locales del repo (rshk-jsifenlib/docs/… o tmp/roshka-sifen/…) antes de intentar curl.

## Validación XSD offline: Lote vs rDE
- NO intentar validar un XML de lote con `siRecepDE_v150.xsd` si el root es `<rLoteDE>`: ese XSD no declara `rLoteDE` y `xmllint` falla con:
  "Element 'rLoteDE': No matching global declaration…".
- Para validar offline:
  1) Crear `xsd_local/` como copia de `xsd/` y reemplazar URLs absolutas:
     `https://ekuatia.set.gov.py/sifen/xsd/` -> path relativo (ej: `Paises_v100.xsd`).
  2) Extraer el nodo `<rDE>` del lote a `rde_only.xml`.
  3) Validar `rde_only.xml` con `xsd_local/siRecepRDE_v150.xsd` (o `rDE_prevalidador_v150.xsd` si aplica).
- Confirmación: el repo ya contiene diccionarios requeridos como `Paises_v100.xsd`, `Monedas_v150.xsd`, `Departamentos_v141.xsd`, etc; el problema era el root equivocado, no la ausencia de XSD.

## XSD: no asumir ruta fija


## Aprendizaje: rEnvioLote vs rEnvioLoteDe (siRecepLoteDE)

## Async recibe-lote (siRecepLoteDE) – wrapper correcto

## Aprendizaje: ZIP contenido en siRecepLoteDE (rLoteDE vs rDE)

## SIFEN recibe-lote (TEST) — WSDL y endpoint

## Aprendizaje: eliminar xsi:schemaLocation para evitar 0160

## Aprendizaje: validar helpers después de parches regex

## Aprendizaje: ZIP debe contener lote.xml (no de_*.xml)

## 2026-01-16 — siRecepLoteDE: ZIP debe contener `lote.xml` (no `de_1.xml`)
- **Síntoma**: SIFEN devuelve `dCodRes=0160` ("XML Mal Formado") y/o preflight local falla porque el ZIP trae `de_1.xml`.
- **Causa**: función `_zip_lote_xml_bytes()` empaquetaba cada DE como `de_{n}.xml` cuando el root era `rDE` o se estaba normalizando mal; SIFEN espera SIEMPRE un ZIP con un único archivo llamado `lote.xml`.
- **Fix**: asegurar `_zip_lote_xml_bytes(lote_xml_bytes)` => crea ZIP en memoria con `zf.writestr("lote.xml", lote_xml_bytes)` únicamente.
- **Check**: inspector debe mostrar `zip files=["lote.xml"]` y `root=rLoteDE ns=http://ekuatia.set.gov.py/sifen/xsd rDE>=1 xDE>=1`.

## 2026-01-16 — Lote interno NO debe incluir `<xDE>` dentro de `lote.xml`

## 2026-01-16 — curl: opción --key con argumento vacío

## 2026-01-16 — Estructura XSD: rLoteDE debe contener rDE directo (no xDE)
- **Síntoma**: SIFEN responde 0160 "XML Mal Formado" aunque lote.xml sea well-formed.
- **Causa real**: el lote.xml dentro del ZIP no cumple el XSD: root rLoteDE contiene xDE (wrapper) en vez de rDE directo; además el orden de hijos de rDE es sensible.
- **Fix**: al construir lote.xml, asegurar rLoteDE -> rDE* directo (sin xDE). Reordenar hijos de rDE según XSD si aplica. Validar extrayendo xDE base64 desde soap_last_request_SENT.xml, decodificando a ZIP y verificando la estructura con namespaces.
- **Verificación reproducible**:
  1) Extraer xDE (base64) -> _debug_xde.zip y descomprimir
  2) Chequear: rLoteDE tiene rDE directos (xDE=0) y el orden de hijos de rDE.

## 2026-01-16 — Error 0160 puede persistir si se reutiliza xDE (ZIP base64) existente
**Síntoma:** logs muestran "zip_base64 al inicio = presente" y "Usando ZIP existente…", pero cambios de namespace/wrapper/estructura no se reflejan en el envío real.
**Causa:** el script reusa el ZIP base64 ya construido, por lo que cualquier corrección previa al build no impacta el payload final.
**Fix anti-regresión:** agregar ENV `SIFEN_NO_REUSE_ZIP=1` (o flag CLI) para **ignorar zip_base64 existente** y **reconstruir el ZIP siempre desde `lote_xml_bytes`**.
**Verificación:** extraer `xDE` desde `artifacts/soap_last_request_SENT.xml`, descomprimir `lote.xml`, y confirmar estructura esperada.


## CLI: forzar wrapper SOAP (rEnvioLote vs rEnvioLoteDe)
- **Problema**: el wrapper real del Body se decidía por WSDL guess / ENV (SIFEN_ENVIOLOTE_ROOT), pero el CLI no exponía `--wrapper`, causando `unrecognized arguments`.
- **Fix**: agregar `--wrapper {rEnvioLote,rEnvioLoteDe}` al argparse.
- **Conexión mínima y segura**: si `args.wrapper` está presente, setear `os.environ["SIFEN_ENVIOLOTE_ROOT"]=args.wrapper` antes de construir el payload.
- **Resultado**: permite probar rápidamente rEnvioLote vs rEnvioLoteDe sin tocar código ni depender de artifacts de WSDL.


## Learning (SIFEN 0160): revisar capa SOAP/HTTP antes de volver a tocar ZIP
Aunque lote.xml esté correcto (solo rLoteDE con rDE directos, sin xDE, con dVerFor como primer hijo), SIFEN puede seguir devolviendo 0160 si el problema está en la capa SOAP/HTTP. Verificar siempre el request real en artifacts/soap_last_request_SENT.xml: debe coincidir con SOAP 1.2 (Envelope/Body) y el Content-Type esperado (a menudo application/soap+xml para SOAP 1.2). Si persiste 0160, priorizar revisión de Envelope, wrapper root y headers antes de volver a tocar el ZIP.

## Learning: asegurar dump SOAP en cada run (independientemente del modo)
**Problema**: artifacts/soap_raw_sent.xml y soap_raw_sent_nonamespace.xml eran dumps viejos (Dec 29) y no reflejan el envío actual. Los envíos recientes se registran en soap_raw_sent_lote_*.xml, pero algunas ramas (modo AS-IS / requests) pueden NO generar soap_last_request_SENT.xml aunque se pase --dump-http.
**Acción anti-regresión**: asegurar que el código escriba SIEMPRE un dump del SOAP real posteado (y hash del ZIP base64) para cada run, con timestamp, independientemente del modo/branch.

- **Síntoma**: `curl: option --key: blank argument` al probar WSDL con `--key "$SIFEN_KEY_PATH"`.

## Learning: soap_raw_sent_lote_*.xml viene de DIAGNOSTICO_0301 (no de send_sirecepde.py)
**Problema**: tools/send_sirecepde.py no escribe soap_raw_sent_lote_*.xml; esos artifacts están definidos por el flujo de DIAGNOSTICO_0301 y/o el SOAP client. No usar soap_raw_sent_lote_*.xml como "fuente de verdad" del envío sin ubicar el writer real y asegurarse de que se genera en el mismo run.
**Acción**: centralizar el dump del SOAP request final (y el ZIP/base64 exacto) en un único lugar, con timestamp + SHA256, y que preflight_check_zip_lote.py consuma ese artifact único.
**Problema**: artifacts/soap_raw_sent.xml y soap_raw_sent_nonamespace.xml eran dumps viejos (Dec 29) y no reflejan el envío actual. Los envíos recientes se registran en soap_raw_sent_lote_*.xml, pero algunas ramas (modo AS-IS / requests) pueden NO generar soap_last_request_SENT.xml aunque se pase --dump-http.
**Acción anti-regresión**: asegurar que el código escriba SIEMPRE un dump del SOAP real posteado (y hash del ZIP base64) para cada run, con timestamp, independientemente del modo/branch.

- **Síntoma**: `curl: option --key: blank argument` al probar WSDL con `--key "$SIFEN_KEY_PATH"`.
- **Causa**: `SIFEN_KEY_PATH` vacío/no exportado (o ruta inválida), por lo que curl recibe `--key ""`.
- **Fix**: verificar env vars con `printf %q`, y si solo hay .p12/.pfx convertir a PEM (cert.pem + key.pem) y exportar `SIFEN_CERT_PATH`/`SIFEN_KEY_PATH`.
- **Verificación**:
  ```bash
  printf "SIFEN_CERT_PATH=%q SIFEN_KEY_PATH=%q\n" "$SIFEN_CERT_PATH" "$SIFEN_KEY_PATH"
  ls -lah "$SIFEN_CERT_PATH" "$SIFEN_KEY_PATH"
  curl -vk --cert "$SIFEN_CERT_PATH" --key "$SIFEN_KEY_PATH" "<WSDL_URL>" -o /tmp/wsdl && head -n 5 /tmp/wsdl
  ```

- **Síntoma**: siRecepLoteDE responde `dCodRes=0160` ("XML Mal Formado") aunque:
  - el ZIP tiene `lote.xml`
  - `xmllint --noout lote.xml` pasa
- **Causa probable**: `lote.xml` estaba estructurado como `rLoteDE -> xDE -> rDE ...`
  - `xDE` es un wrapper del SOAP (base64 del ZIP), no pertenece al lote interno.
- **Regla**: Dentro del ZIP, `lote.xml` debe ser `rLoteDE` conteniendo `rDE` directos (repetibles), sin `<xDE>`.
- **Test rápido**: si `head lote.xml` muestra `<rLoteDE> <xDE> ...` => unwrap antes de zippear/enviar.


- No confiar en parches por regex que "mueven bloques" dentro de tools/send_sirecepde.py sin validar que no borren helpers.
- Regla: antes de tocar preflight/ZIP, correr `rg -n "def _zip_lote_xml_bytes|_zip_lote_xml_bytes(" tools/send_sirecepde.py` y asegurar que el helper existe + py_compile pasa.
- Síntoma típico: NameError: _zip_lote_xml_bytes is not defined en send_sirecepde.py durante construcción del lote (antes del POST a SIFEN).

- Si aparece 0160 "XML Mal Formado" al enviar siRecepLoteDE / recibe-lote, revisar y eliminar xsi:schemaLocation del XML que va dentro del ZIP.
- Especialmente importante en el root `<rDE>` o `<rLoteDE>`.
- Mantener el XML "limpio" (namespace OK, sin schemaLocation) antes de comprimir y base64.

- El WSDL recibe-lote.wsdl?wsdl define operación rEnvioLote (no siRecepLoteDE).
- El soap12:address location declara el endpoint https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl.
- No "normalizar" el endpoint removiendo .wsdl/?wsdl a mano: usar el soap12:address location del WSDL.
  Stripping incorrecto puede causar HTTP 400 + dCodRes=0160 (XML Mal Formado).


- El schema importado desde el WSDL (recibe-lote.wsdl.xsd1.xsd) declara el request root como rEnvioLote (sin "De").
- Si se envía rEnvioLoteDe, SIFEN puede responder 0160 "XML Mal Formado".
- Checklist de verificación:
  - grep en /tmp/recibe-lote.wsdl.xsd1.xsd para <xs:element name="rEnvioLote">
  - grep en artifacts/soap_last_request_SENT.xml para confirmar que el Body usa <rEnvioLote ...>
- Fecha: 2026-01-16, caso real: RUC 4554737-8, endpoint test async recibe-lote.

## P12 / Password / curl
- Si `openssl pkcs12 -info -in "$SIFEN_CERT_PATH" -noout` devuelve `exit=0`, el .p12 es válido y contiene cert + key.
- Si curl da: `LibreSSL error ... PKCS12 ... mac verify failure`, casi siempre es password incorrecta (o caracteres/espacios invisibles).
- Para bajar recursos protegidos (WSDL/XSD) usar:
  `curl --cert-type P12 --cert "$SIFEN_CERT_PATH:$P12PASS" "<URL>" -o "<OUT>"`
- Evitar pegar líneas sueltas que empiecen con `#` en zsh (puede intentar ejecutarlas y ensuciar la sesión); pegar bloques completos o eliminar esas líneas.
## XSD v150 trae includes con URLs absolutas (cadena completa)
xmllint puede fallar (exit=5) porque los XSD usan xsd:include con URLs tipo:
https://ekuatia.set.gov.py/sifen/xsd/<archivo>.xsd
No solo en siRecepDE_v150.xsd, también dentro de DE_v150.xsd y otros (ej: Paises_v100.xsd).

Solución local/offline:
1) Copiar carpeta de XSD a un workspace local:
   rm -rf xsd_local && cp -R xsd xsd_local
2) Reescribir URLs absolutas a paths relativos en TODOS los XSD:
   perl -pi -e 's#https://ekuatia.set.gov.py/sifen/xsd/##g' xsd_local/*.xsd
3) Validar con el entrypoint:
   ( cd xsd_local && xmllint --noout --schema siRecepDE_v150.xsd ../<xml> )



## Validación XSD: NO validar rLoteDE con siRecepDE_v150.xsd
- Error típico al validar lote: "Element 'rLoteDE': No matching global declaration available for the validation root."
- Causa: siRecepDE_v150.xsd no tiene como root a rLoteDE; es para DE/rDE, no para el lote.
- Acción correcta:
  1) Buscar qué XSD declara rLoteDE con: grep -R "rLoteDE" en xsd/ y schemas_sifen/
  2) Usar ese XSD como entrypoint para xmllint.
- Nota: includes tipo rde/150/RDE_Group.xsd pueden no existir como URL pública; preferir resolver desde XSD locales del repo (rshk-jsifenlib/docs/… o tmp/roshka-sifen/…) antes de intentar curl.

## Validación XSD offline: Lote vs rDE
- NO intentar validar un XML de lote con `siRecepDE_v150.xsd` si el root es `<rLoteDE>`: ese XSD no declara `rLoteDE` y `xmllint` falla con:
  "Element 'rLoteDE': No matching global declaration…".
- Para validar offline:
  1) Crear `xsd_local/` como copia de `xsd/` y reemplazar URLs absolutas:
     `https://ekuatia.set.gov.py/sifen/xsd/` -> path relativo (ej: `Paises_v100.xsd`).
  2) Extraer el nodo `<rDE>` del lote a `rde_only.xml`.
  3) Validar `rde_only.xml` con `xsd_local/siRecepRDE_v150.xsd` (o `rDE_prevalidador_v150.xsd` si aplica).
- Confirmación: el repo ya contiene diccionarios requeridos como `Paises_v100.xsd`, `Monedas_v150.xsd`, `Departamentos_v141.xsd`, etc; el problema era el root equivocado, no la ausencia de XSD.

## XSD: no asumir ruta fija


## Aprendizaje: rEnvioLote vs rEnvioLoteDe (siRecepLoteDE)

## Async recibe-lote (siRecepLoteDE) – wrapper correcto


## SIFEN recibe-lote (TEST) — WSDL y endpoint


- El WSDL recibe-lote.wsdl?wsdl define operación rEnvioLote (no siRecepLoteDE).
- El soap12:address location declara el endpoint https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl.
- No "normalizar" el endpoint removiendo .wsdl/?wsdl a mano: usar el soap12:address location del WSDL.
  Stripping incorrecto puede causar HTTP 400 + dCodRes=0160 (XML Mal Formado).


- El schema importado desde el WSDL (recibe-lote.wsdl.xsd1.xsd) declara el request root como rEnvioLote (sin "De").
- Si se envía rEnvioLoteDe, SIFEN puede responder 0160 "XML Mal Formado".
- Checklist de verificación:
  - grep en /tmp/recibe-lote.wsdl.xsd1.xsd para <xs:element name="rEnvioLote">
  - grep en artifacts/soap_last_request_SENT.xml para confirmar que el Body usa <rEnvioLote ...>
- Fecha: 2026-01-16, caso real: RUC 4554737-8, endpoint test async recibe-lote.

## P12 / Password / curl
- Si `openssl pkcs12 -info -in "$SIFEN_CERT_PATH" -noout` devuelve `exit=0`, el .p12 es válido y contiene cert + key.
- Si curl da: `LibreSSL error ... PKCS12 ... mac verify failure`, casi siempre es password incorrecta (o caracteres/espacios invisibles).
- Para bajar recursos protegidos (WSDL/XSD) usar:
  `curl --cert-type P12 --cert "$SIFEN_CERT_PATH:$P12PASS" "<URL>" -o "<OUT>"`
- Evitar pegar líneas sueltas que empiecen con `#` en zsh (puede intentar ejecutarlas y ensuciar la sesión); pegar bloques completos o eliminar esas líneas.- El XML puede declarar `xsi:schemaLocation` con un nombre como `siRecepDE_v150.xsd`.
- Antes de validar, localizar el XSD real en el repo:
  - `find .. -maxdepth 8 -type f \( -iname "siRecepDE_v150.xsd" -o -iname "*v150*.xsd" \)`
- Si no existe en el repo, se debe descargar/instalar el paquete XSD v150 correspondiente y guardar su ruta para validaciones futuras.

