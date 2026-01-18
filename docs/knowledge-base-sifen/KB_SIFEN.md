# SIFEN — Base de Conocimiento del Proyecto

> **Última actualización:** 2026-01-17  
> **Propósito:** punto único de consulta (manual + mejores prácticas) para integrar en el codebase.

## Fuentes incluidas

- **Manual Técnico SIFEN v150 (10/09/2019)** — texto extraído del PDF provisto por el usuario.

- **Guía de Mejores Prácticas para la Gestión del Envío de DE (Oct 2024)** — texto extraído del PDF provisto por el usuario.

## Cómo usar este documento

- Buscá por términos clave: `CDC`, `dCodRes`, `siRecepLoteDE`, `consulta-lote`, `0300`, `0361`, `0422`.

- La parte de arriba es una **guía operativa** (lo que hacemos en el proyecto).

- Al final están los **apéndices con el texto completo** de ambos documentos para auditoría/consulta.

---

## Glosario mínimo

- **SIFEN**: Sistema Integrado de Facturación Electrónica Nacional.

- **DE / DTE**: Documento Electrónico / Documento Tributario Electrónico.

- **CDC**: Código de Control del DE (identificador/clave de control).

- **RUC**: Registro Único de Contribuyentes (emisor).

- **Lote**: envío agrupado de DE (hasta 50) para procesamiento asíncrono.

- **WSDL**: contrato del servicio SOAP.

- **TLS mutuo**: autenticación cliente+servidor con certificado digital.

---

## Resumen operativo para el proyecto (lo que implementamos)

### 1) Pre-requisitos técnicos obligatorios

- XML + SOAP 1.2 + HTTP.

- **TLS 1.2 con autenticación mutua** usando certificado emitido por PSC habilitada.

- Firma: **XML Digital Signature (Enveloped)** con RSA 2048 y SHA-2; canonización C14N/exclusive.



### 2) Reglas de oro al generar un `rDE` (evita rechazos sutiles)

Basado en la guía de mejores prácticas:

- No agregar espacios al inicio/fin en campos numéricos/alfanuméricos.

- No incluir `annotation` / `documentation` ni comentarios.

- Evitar caracteres de formato (LF/CR/TAB/espacios) “de más” entre etiquetas.

- No usar prefijos en el namespace de las etiquetas del DE.

- No enviar etiquetas sin valor (salvo campos obligatorios del XSD).

- No usar valores negativos o no numéricos en campos numéricos.

- Respetar mayúsculas/minúsculas exactas de nombres de grupos/campos (case sensitive).



Namespace típico (ej MT 150):

```xml
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd">
```

### 3) Envío por lotes (asíncrono) — flujo recomendado

1. Generar y **firmar** cada `rDE`.

2. Armar `rLoteDE` e insertar los `rDE` firmados.

3. Comprimir `rLoteDE` y convertir el comprimido a **Base64**.

4. Invocar `siRecepLoteDE` (`/de/ws/async/recibe-lote.wsdl`) enviando el Base64 dentro de `xDE`.

5. Si la respuesta trae `dCodRes=0300`, guardar `dProtConsLote` (número/protocolo del lote).

6. Consultar `consulta-lote` con `dProtConsLote` hasta obtener `dCodResLot=0362` (concluido).

7. Para DE aprobados, usar `consulta` por `dCDC` y obtener `xContenDE` (XML aprobado).

### 4) Reglas de composición del lote

- Máximo **50 DE por lote**.

- Un lote debe contener **un solo RUC emisor**.

- Un lote debe contener **un solo tipo de documento** (solo FE, solo NC, etc.).

- Tamaño del mensaje de entrada del WS: **no debe superar 1000 KB** (según guía de mejores prácticas).

### 5) Tiempos de consulta y reintentos

- SIFEN procesa en cola; recomendación: **consultar el lote luego de ~10 minutos** y repetir a intervalos **>= 10 min**.

- No reenviar un mismo **CDC** sin tener resultado definitivo (Aprobado / Aprobado c/Obs / Rechazado).

- Si no recibiste respuesta al enviar lote (corte), podés ubicar el lote consultando por un CDC incluido (solo para ese caso).

### 6) Códigos de respuesta que usamos como “semaforización”

**Recepción lote (`recibe-lote`)**

- `0300`: Lote recibido con éxito (se procesará).

- `0301`: Lote no encolado (no se procesará).


**Consulta lote (`consulta-lote`)**

- `0360`: Número de lote inexistente.

- `0361`: Lote en procesamiento.

- `0362`: Procesamiento concluido (leer `gResProcLote` por CDC).

- `0364`: Consulta extemporánea (hasta 48h); luego consultar cada CDC con `consulta`.


**Consulta DE por CDC (`consulta`)**

- `0420`: DE no existe o no está aprobado (o fue rechazado).

- `0422`: CDC encontrado y aprobado; viene `xContenDE` con el XML.

---

## Extractos de referencia rápida (del material fuente)

### Direcciones (URLs) de servicios (test vs prod)

> Extracto del Manual Técnico v150 (tabla de resumen de URLs).


```text
Resumen de las Direcciones Electrónicas de los Servicios Web para Ambientes de Pruebas y
Producción ..................................................................................................................................................... 41
```

### CDC — ubicación del capítulo relevante

> El Manual Técnico v150 dedica una sección específica a la estructura y verificación del CDC.


```text
10.1. Estructura del código de control (CDC) de los DE ......................................................................... 56
```

### Recomendaciones de envío (guía Oct 2024)

```text
Recomendaciones
1. Enviar la máxima cantidad posible de documentos en un lote (hasta 50 documentos).
2. Verificar la respuesta de la recepción del lote, considerando los siguientes códigos
de respuesta:
5


--- PAGE 6 ---

a. Lote recibido con éxito (0300), el lote será procesado, se debe consultar el
estado, a través del número de lote retornado, para obtener el detalle de los
documentos enviados.
b.
```

### Motivos típicos de rechazo del lote (no encolado)

```text
Motivos de rechazo 6
```

### Motivos típicos de bloqueo temporal por RUC (10–60 min)

```text
Motivos de bloqueo 6
```

---

## Plantillas SOAP (copy/paste) — guía Oct 2024

> **Nota:** ajustar `xmlns` según WSDL y entorno (test/prod).


### `recibe-lote` (siRecepLoteDE)

```text
recibe-lote 8
```

### `consulta-lote` (siConsLoteDE)

```text
consulta-lote 10
consulta 12
2


--- PAGE 3 ---

Introducción
Este documento está orientado al usuario desarrollador de servicios web de integración con
SIFEN, es una aplicación práctica de lo especificado en el Manual Técnico de Sistema de
Facturación Electrónica Nacional referente a la recepción de documentos electrónicos (DE)
por lotes. Se da por entendido que el usuario tiene los conocimientos necesarios y
suficientes de las siguientes normas y estándares:
● XML
● SOAP, versión 1.2
● HTTP
● Protocolo de seguridad TLS versión 1.2, con autenticación mutua
● Estándar de certificado y firma digital
○ Estándar de Firma: XML Digital Signature, formato Enveloped W3C
○ Certificado Digital: Expedido por una de las PSC habilitados en la República
del Paraguay, estándar http://www.w3.org/2000/09/xmldsig#X509Data
○ Tamaño de la Clave Criptográfica: RSA 2048, para cifrado por software.
○ Función Criptográfica Asimétrica: RSA conforme a
https://www.w3.org/TR/2002/REC-xmlenc-core20021210/Overview.html#rsa-
1_5 .
○ Función de “message digest”: SHA-2
https://www.w3.org/TR/2002/REC-xmlenc-core-20021210/Overview.html#sha
256
○ Codificación: Base64 https://www.w3.org/TR/xmldsig-core1/#sec-Base-64
○ Transformaciones exigidas: Útil para canonizar el XML enviado, con el
propósito de realizar la validación correcta de la firma digital: Enveloped,
https://www.w3.org/TR/xmldsig-core1/#sec-EnvelopedSignature C14N,
http://www.w3.org/2001/10/xml-exc-c14n#
3


--- PAGE 4 ---

Generación de los Documentos Electrónicos
Para mayor información se debe consultar el Manual Técnico en la versión que se está
utilizando, por ejemplo para el MT 150
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd">
Tener precaución de NO incorporar:
1. Espacios en blanco en el inicio o en el final de campos numéricos y alfanuméricos.
2. Comentarios, anotaciones y documentaciones, léase las etiquetas annotation y
documentation.
3. Caracteres de formato de archivo, como line-feed, carriage return, tab, espacios
entre etiquetas.
4. Prefijos en el namespace de las etiquetas.
5. Etiquetas de campos que no contengan valor, sean estas numéricas, que contienen
ceros, vacíos o blancos para campos del tipo alfanumérico. Están excluidos de esta
regla todos aquellos campos identificados como obligatorios en los distintos formatos
de archivo XML, la obligatoriedad de los mismos se encuentra plenamente detallada
en el manual técnico.
6. Valores negativos o caracteres no numéricos en campos numéricos.
7. El nombre de los campos es sensible a minúsculas y mayúsculas, por lo que deben
ser comunicados de la misma forma en la que se visualiza en el manual técnico.
Ejemplo: el grupo gOpeDE, es diferente a GopeDE, a gopede y a cualquier otra
combinación distinta a la inicial.
La DNIT disponibiliza una herramienta para pre validación del DE en tiempo de
desarrollo, utilidad para detectar campos incorrectos en el XML.
Prevalidador SIFEN: https://ekuatia.set.gov.py/prevalidador/
4


--- PAGE 5 ---

Generación de Lotes de Documentos Electrónicos
Los documentos electrónicos se envían a SIFEN en lotes, el procesamiento de los lotes se
realiza a través de la recepción de varios DE en un archivo comprimido para procesarlos de
forma asíncrona. El resultado del procesamiento de un lote se debe consultar en un
segundo momento, separado del envío.
Servicios Web Asíncronos:
Tener en cuenta los dominios para cada ambiente:
1. Ambiente de Producción: sifen.set.gov.py
2. Ambiente de Test (pruebas) : sifen-test.set.gov.py
● Recepción lote DE
Recibe el lote de DE (hasta 50 DE) para procesarlos en una cola de espera.
https://{ambiente}/de/ws/async/recibe-lote.wsdl
● Consulta resultado lote
Consulta el estado de un lote recibido previamente.
https://{ambiente}/de/ws/consultas/consulta-lote.wsdl
● Consulta por CDC
Consulta un DE, si está aprobado retorna el XML del DE.
https://{ambiente}/de/ws/consultas/consulta.wsdl
Para obtener el WSDL de cada servicio, agregar al final de cada url ?wsdl, por ejemplo para
la consulta de resultado lote el wsdl se obtiene con la siguiente url:
https://{ambiente}/de/ws/consultas/consulta-lote.wsdl?wsdl
La descripción de estructuras y las restricciones de los contenidos de los documentos XML
se encuentran especificados en el Manual Técnico, correspondiente a la versión, y en los
schemas XSD de SIFEN que están publicados en http://ekuatia.set.gov.py/sifen/xsd
Recomendaciones
1. Enviar la máxima cantidad posible de documentos en un lote (hasta 50 documentos).
2. Verificar la respuesta de la recepción del lote, considerando los siguientes códigos
de respuesta:
5


--- PAGE 6 ---

a. Lote recibido con éxito (0300), el lote será procesado, se debe consultar el
estado, a través del número de lote retornado, para obtener el detalle de los
documentos enviados.
b. Lote no encolado para procesamiento (0301), el lote NO será procesado,
verificar la sección "Lote no encolado para procesamiento".
3. Cuando se envía un lote y no se recibe respuesta del SIFEN por algún corte en la
comunicación, se puede consultar el lote con un CDC que fue enviado en el lote
respectivo. De esta manera obtendrá el resultado del estado del lote y el número de
lote correspondiente. Utilizar esta opción solo en caso de no recibir el Número de
Lote como respuesta al envío.
4. La consulta de un lote recibido se debe realizar luego de pasado un periodo de
tiempo no muy corto de la recepción, teniendo en cuenta que SIFEN tiene una cola
de procesamiento que puede variar de acuerdo a la fecha y horas pico de las
actividades comerciales. Si bien el procesamiento por cada DE está definido cercano
a los 1 segundo, se recomienda comenzar a realizar la consulta pasados los 10
minutos de la recepción y luego a intervalos regulares no menores a 10 minutos.
5. Nunca se debe enviar un mismo CDC sin haber tenido la respuesta definitiva de
SIFEN (Aprobado, Aprobado con Observación o Rechazado), es decir, consultar el
resultado del procesamiento del lote con el WS de consulta de lote. Así también
tener en cuenta las reglas de bloqueo de RUC por envíos duplicados de DE.
Lote no encolado para procesamiento
Motivos de rechazo
La recepción de un lote se puede rechazar por los siguientes motivos:
a. Haber envíado DE con distintos RUC emisores.
Se debe enviar documentos de un solo RUC emisor por lote.
b. Haber envíado DE de distintos tipos.
Se debe enviar documentos de un solo tipo de documento por lote (solo
Factura Electrónica, solo Nota de Crédito, etc).
c. Haber enviado más de 50 DE en un mismo lote
d. Estar bloqueado por envío duplicado, ver Motivos de bloqueo
e. El tamaño del archivo comprimido enviado supera el tamaño permitido.
El mensaje de datos de entrada del WS no debe superar 1000 KB.
Motivos de bloqueo
Las siguientes operaciones generan bloqueo de recepción de documentos por RUC
Emisor de 10 a 60 minutos, según la cantidad de reincidencia. Esto puede generar
6


--- PAGE 7 ---

algún esquema de penalización en el futuro. Los motivos del bloqueo temporal de
recepción por RUC son:
f. Enviar lotes vacíos o con contenido no válido.
g. Enviar el mismo CDC varias veces en un mismo lote.
h. Enviar el mismo CDC varias veces en lotes distintos y que aún se encuentren
en procesamiento.
Antes de volver a enviar un DE (mismo CDC enviado) se debe verificar que
no esté aún en procesamiento, con la consulta de lote.
i. Enviar varias veces un mismo lote.
Invocación de Web Service Asíncronos
1. Se debe prestar mucha atención a los namespace especificados para cada servicio
web.
2. Se realiza una autenticación mutua con SIFEN a través de un certificado digital
emitido por una PSC habilitada. El medio para establecer esta comunicación es la
Internet, apoyado en la utilización del protocolo de seguridad TLS versión 1.2, con
autenticación mutua.
Configuracióndeconexiónparaautenticaciónmutua(enPostman)
7


--- PAGE 8 ---

recibe-lote
Recepción de DE por lotes, para consumir este servicio, el cliente deberá construir la
estructura en XML, según el schema WS_SiRecepLoteDE.xsd y comprimir dicho archivo.
Cabe aclarar que el lote podrá contener hasta 50 DE del mismo tipo (ejemplo: Facturas
Electrónicas), cada uno de ellos debe estar firmado.
InvocaciónPOST(enPostman)
Request Body
Pasos para crear el Body para la invocación del servicio:
1. Crear la estructura del lote
<rLoteDE>
…
</rLoteDE>
2. Insertar los DE firmados en la estructura del lote
<rLoteDE>
<rDE>...</rDE>
<rDE>...</rDE>
…
</rLoteDE>
3. Comprimir el contenido de la estructura del lote “rLoteDE”
4. Convertir el contenido comprimido a Base64
5. Crear el envelope soap, teniendo en cuenta los namespace especificados
8


--- PAGE 9 ---

<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body<
<xsd:rEnvioLote>
<xsd:dId>20240926</xsd:dId>
<xsd:xDE>{Aquí va el Base64 del punto 4}</xsd:xDE>
</xsd:rEnvioLote>
</soap:Body>
</soap:Envelope>
6. Verificar la respuesta de la invocación “rResEnviLoteDe”
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rResEnviLoteDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-08T14:51:21-03:00</ns2:dFecProc>
<ns2:dCodRes>0300</ns2:dCodRes>
<ns2:dMsgRes>Lote recibido con &#233;xito</ns2:dMsgRes>
<ns2:dProtConsLote>11158097383597290</ns2:dProtConsLote>
<ns2:dTpoProces>0</ns2:dTpoProces>
</ns2:rResEnviLoteDe>
</env:Body>
</env:Envelope>
Response
La respuesta, se debe analizar el campo “dCodRes”, puede indicar una de las situaciones
siguientes
1. Lote recibido con éxito (0300), el lote será procesado, se debe consultar el estado
para obtener el detalle de los documentos enviados. Se sugiere comenzar a
consultar un lote enviado pasado 10 minutos desde el envío.
2. Lote no encolado para procesamiento (0301), el lote NO será procesado, verificar la
sección "Lote no encolado para procesamiento".
9


--- PAGE 10 ---

consulta-lote
Devuelve el resultado del procesamiento de cada uno de los DE contenidos en un lote.
Según el schema WS_SiConsLote.xsd.
Request Body
La consulta se realiza por el valor del campo “dProtConsLote” que forma parte del
response de la recepción del lote.
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body>
<xsd:rEnviConsLoteDe>
<xsd:dId>1</xsd:dId>
<xsd:dProtConsLote>11158097383597290</xsd:dProtConsLote>
</xsd:rEnviConsLoteDe>
</soap:Body>
</soap:Envelope>
Response
La respuesta, se debe analizar el campo “dCodResLot”, puede indicar una de las cuatro
situaciones siguientes:
1. No existe número de lote consultado. 0360 Número del Lote inexistente
2. No se ha culminado el procesamiento de los DE. 0361 Lote en procesamiento. Debe
consultar nuevamente el lote, se sugiere consultar a intervalos mínimos de 10
minutos. En momentos de alta carga el procesamiento puede ocurrir entre 1 a 24
horas posteriores a la recepción.
3. Consulta extemporánea de Lote. 0364 La consulta del lote contempla un plazo de
hasta 48 horas posteriores al envío del mismo. Una vez superado el tiempo, deberá
consultar cada CDC del lote mediante la WS Consulta DE
4. Éxito en la consulta. 0362 Procesamiento de lote concluido.
La respuesta también contiene el contenedor del DE, definido en el Schema.
A. En procesamiento
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
10


--- PAGE 11 ---

<env:Body>
<ns2:rResEnviConsLoteDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-08T14:53:53-03:00</ns2:dFecProc>
<ns2:dCodResLot>0361</ns2:dCodResLot>
<ns2:dMsgResLot>Lote {11158097383597290} en procesamiento
</ns2:dMsgResLot>
</ns2:rResEnviConsLoteDe>
</env:Body>
</env:Envelope>
B. Procesamiento concluido
Se indica el detalle del procesamiento CDC en el elemento “gResProcLote”
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rResEnviConsLoteDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-08T03:58:16-03:00</ns2:dFecProc>
<ns2:dCodResLot>0362</ns2:dCodResLot>
<ns2:dMsgResLot>Procesamiento de lote {11444651783497640} concluido
</ns2:dMsgResLot>
<ns2:gResProcLote>
<ns2:id>07800252985001001000311822024021016361562161</ns2:id>
<ns2:dEstRes>Rechazado</ns2:dEstRes>
<ns2:gResProc>
<ns2:dCodRes>0160</ns2:dCodRes>
<ns2:dMsgRes>XML malformado: [El valor del elemento: dDirRec es
invalido, El valor del elemento: dDirLocEnt es invalido]
</ns2:dMsgRes>
</ns2:gResProc>
</ns2:gResProcLote>
</ns2:rResEnviConsLoteDe>
</env:Body>
</env:Envelope>
11


--- PAGE 12 ---
```

### `consulta` por CDC (siConsDE)

```text
consulta
Devuelve el XML de un DE que está en estado aprobado. Según el schema
WS_SiConsDE.xsd
Request Body
La consulta se realiza por el valor del campo “dCDC”.
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:si="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body>
<xsd:rEnviConsDeRequest>
<xsd:dId>12</xsd:dId>
<xsd:dCDC>01028052080001001000013622023100111644108186</xsd:dCDC>
</xsd:rEnviConsDeRequest>
</soap:Body>
</soap:Envelope>
Response
La respuesta, se debe analizar el campo “dCodRes”, puede indicar una de las dos situaciones
siguientes:
1. 0420 El DE no existe o no está aprobado, se debe volver a enviar el DE para su
procesamiento, tener en cuenta el resultado de la consulta por lote antes de enviar
nuevamente.
2. 0422 Existe como DTE, está aprobado, se responde el contenido XML del DE en
“xContenDE”
A. No existe
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rEnviConsDeResponse xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-09T09:28:39-03:00</ns2:dFecProc>
<ns2:dCodRes>0420</ns2:dCodRes>
<ns2:dMsgRes>Documento No Existe en SIFEN o ha sido Rechazado
</ns2:dMsgRes>
12


--- PAGE 13 ---

</ns2:rEnviConsDeResponse>
</env:Body>
</env:Envelope>
B. Existe
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rEnviConsDeResponse xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2023-10-02T15:13:52-03:00</ns2:dFecProc>
<ns2:dCodRes>0422</ns2:dCodRes>
<ns2:dMsgRes>CDC encontrado</ns2:dMsgRes>
<ns2:xContenDE>{contenido XML del DE}</ns2:xContenDE>
</ns2:rEnviConsDeResponse>
</env:Body>
</env:Envelope>
13
```

---

## Checklist anti-regresión (para CI / QA)

- [ ] El XML de `rDE` valida contra el XSD de la versión objetivo (ej. v150).

- [ ] El `CDC` calculado corresponde con los datos del XML (no hay divergencias por padding/zeros/fechas).

- [ ] No hay tags vacíos ni whitespace/prefixes no permitidos.

- [ ] Firma XMLDSig `enveloped` válida (C14N correcto) y certificado no revocado.

- [ ] Lotes: misma `dRUCEm` + mismo `iTiDE` + <= 50 DE + payload <= 1000 KB.

- [ ] No se reenvía el mismo CDC hasta tener estado definitivo (evitar bloqueos).

- [ ] Polling de `consulta-lote` con backoff >= 10 min; manejo de `0364` (48h).

---

## Errores frecuentes / Diagnósticos de conectividad

### BIG-IP /vdesk/hangup.php3 (WSDL 302 en PROD)

**Síntoma**
- En PROD, al intentar obtener WSDL (ej: `https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl`) puede responder **302** con `Location: /vdesk/hangup.php3`.

**Contexto técnico**
- La guía oficial recalca **TLS 1.2 con autenticación mutua (mTLS)** para consumir SIFEN.
- El GET del WSDL puede requerir presentar **certificado cliente** también (no solo el POST SOAP).

**Acción recomendada**
1) Probar GET del WSDL con mTLS:
   `curl -vk --cert $SIFEN_CERT_PATH --key $SIFEN_KEY_PATH "https://sifen.set.gov.py/...?.wsdl?wsdl"` 
2) Si con mTLS funciona: asegurar que el código que hace `GET wsdl_url` incluya `cert=(cert_path,key_path)`.
3) Si sigue el 302: habilitar fallback/caché de WSDL (evitar depender de `?wsdl` en PROD).

**Nota de ambientes**
- Producción: `sifen.set.gov.py` 
- Test: `sifen-test.set.gov.py`

---

# Apéndice A — Texto completo: Guía de Mejores Prácticas (Oct 2024)

<!-- SOURCE: Guía de Mejores Prácticas para la Gestión del Envío de DE (Octubre 2024) -->


```text
--- PAGE 1 ---

Recomendaciones y mejores prácticas
para SIFEN
Guía para el desarrollador
Octubre 2024
1


--- PAGE 2 ---

Índice
Introducción 3
Generación de los Documentos Electrónicos 4
Generación de Lotes de Documentos Electrónicos 5
Servicios Web Asíncronos: 5
Recomendaciones 5
Lote no encolado para procesamiento 6
Motivos de rechazo 6
Motivos de bloqueo 6
Invocación de Web Service Asíncronos 7
recibe-lote 8
consulta-lote 10
consulta 12
2


--- PAGE 3 ---

Introducción
Este documento está orientado al usuario desarrollador de servicios web de integración con
SIFEN, es una aplicación práctica de lo especificado en el Manual Técnico de Sistema de
Facturación Electrónica Nacional referente a la recepción de documentos electrónicos (DE)
por lotes. Se da por entendido que el usuario tiene los conocimientos necesarios y
suficientes de las siguientes normas y estándares:
● XML
● SOAP, versión 1.2
● HTTP
● Protocolo de seguridad TLS versión 1.2, con autenticación mutua
● Estándar de certificado y firma digital
○ Estándar de Firma: XML Digital Signature, formato Enveloped W3C
○ Certificado Digital: Expedido por una de las PSC habilitados en la República
del Paraguay, estándar http://www.w3.org/2000/09/xmldsig#X509Data
○ Tamaño de la Clave Criptográfica: RSA 2048, para cifrado por software.
○ Función Criptográfica Asimétrica: RSA conforme a
https://www.w3.org/TR/2002/REC-xmlenc-core20021210/Overview.html#rsa-
1_5 .
○ Función de “message digest”: SHA-2
https://www.w3.org/TR/2002/REC-xmlenc-core-20021210/Overview.html#sha
256
○ Codificación: Base64 https://www.w3.org/TR/xmldsig-core1/#sec-Base-64
○ Transformaciones exigidas: Útil para canonizar el XML enviado, con el
propósito de realizar la validación correcta de la firma digital: Enveloped,
https://www.w3.org/TR/xmldsig-core1/#sec-EnvelopedSignature C14N,
http://www.w3.org/2001/10/xml-exc-c14n#
3


--- PAGE 4 ---

Generación de los Documentos Electrónicos
Para mayor información se debe consultar el Manual Técnico en la versión que se está
utilizando, por ejemplo para el MT 150
<rDE xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd">
Tener precaución de NO incorporar:
1. Espacios en blanco en el inicio o en el final de campos numéricos y alfanuméricos.
2. Comentarios, anotaciones y documentaciones, léase las etiquetas annotation y
documentation.
3. Caracteres de formato de archivo, como line-feed, carriage return, tab, espacios
entre etiquetas.
4. Prefijos en el namespace de las etiquetas.
5. Etiquetas de campos que no contengan valor, sean estas numéricas, que contienen
ceros, vacíos o blancos para campos del tipo alfanumérico. Están excluidos de esta
regla todos aquellos campos identificados como obligatorios en los distintos formatos
de archivo XML, la obligatoriedad de los mismos se encuentra plenamente detallada
en el manual técnico.
6. Valores negativos o caracteres no numéricos en campos numéricos.
7. El nombre de los campos es sensible a minúsculas y mayúsculas, por lo que deben
ser comunicados de la misma forma en la que se visualiza en el manual técnico.
Ejemplo: el grupo gOpeDE, es diferente a GopeDE, a gopede y a cualquier otra
combinación distinta a la inicial.
La DNIT disponibiliza una herramienta para pre validación del DE en tiempo de
desarrollo, utilidad para detectar campos incorrectos en el XML.
Prevalidador SIFEN: https://ekuatia.set.gov.py/prevalidador/
4


--- PAGE 5 ---

Generación de Lotes de Documentos Electrónicos
Los documentos electrónicos se envían a SIFEN en lotes, el procesamiento de los lotes se
realiza a través de la recepción de varios DE en un archivo comprimido para procesarlos de
forma asíncrona. El resultado del procesamiento de un lote se debe consultar en un
segundo momento, separado del envío.
Servicios Web Asíncronos:
Tener en cuenta los dominios para cada ambiente:
1. Ambiente de Producción: sifen.set.gov.py
2. Ambiente de Test (pruebas) : sifen-test.set.gov.py
● Recepción lote DE
Recibe el lote de DE (hasta 50 DE) para procesarlos en una cola de espera.
https://{ambiente}/de/ws/async/recibe-lote.wsdl
● Consulta resultado lote
Consulta el estado de un lote recibido previamente.
https://{ambiente}/de/ws/consultas/consulta-lote.wsdl
● Consulta por CDC
Consulta un DE, si está aprobado retorna el XML del DE.
https://{ambiente}/de/ws/consultas/consulta.wsdl
Para obtener el WSDL de cada servicio, agregar al final de cada url ?wsdl, por ejemplo para
la consulta de resultado lote el wsdl se obtiene con la siguiente url:
https://{ambiente}/de/ws/consultas/consulta-lote.wsdl?wsdl
La descripción de estructuras y las restricciones de los contenidos de los documentos XML
se encuentran especificados en el Manual Técnico, correspondiente a la versión, y en los
schemas XSD de SIFEN que están publicados en http://ekuatia.set.gov.py/sifen/xsd
Recomendaciones
1. Enviar la máxima cantidad posible de documentos en un lote (hasta 50 documentos).
2. Verificar la respuesta de la recepción del lote, considerando los siguientes códigos
de respuesta:
5


--- PAGE 6 ---

a. Lote recibido con éxito (0300), el lote será procesado, se debe consultar el
estado, a través del número de lote retornado, para obtener el detalle de los
documentos enviados.
b. Lote no encolado para procesamiento (0301), el lote NO será procesado,
verificar la sección "Lote no encolado para procesamiento".
3. Cuando se envía un lote y no se recibe respuesta del SIFEN por algún corte en la
comunicación, se puede consultar el lote con un CDC que fue enviado en el lote
respectivo. De esta manera obtendrá el resultado del estado del lote y el número de
lote correspondiente. Utilizar esta opción solo en caso de no recibir el Número de
Lote como respuesta al envío.
4. La consulta de un lote recibido se debe realizar luego de pasado un periodo de
tiempo no muy corto de la recepción, teniendo en cuenta que SIFEN tiene una cola
de procesamiento que puede variar de acuerdo a la fecha y horas pico de las
actividades comerciales. Si bien el procesamiento por cada DE está definido cercano
a los 1 segundo, se recomienda comenzar a realizar la consulta pasados los 10
minutos de la recepción y luego a intervalos regulares no menores a 10 minutos.
5. Nunca se debe enviar un mismo CDC sin haber tenido la respuesta definitiva de
SIFEN (Aprobado, Aprobado con Observación o Rechazado), es decir, consultar el
resultado del procesamiento del lote con el WS de consulta de lote. Así también
tener en cuenta las reglas de bloqueo de RUC por envíos duplicados de DE.
Lote no encolado para procesamiento
Motivos de rechazo
La recepción de un lote se puede rechazar por los siguientes motivos:
a. Haber envíado DE con distintos RUC emisores.
Se debe enviar documentos de un solo RUC emisor por lote.
b. Haber envíado DE de distintos tipos.
Se debe enviar documentos de un solo tipo de documento por lote (solo
Factura Electrónica, solo Nota de Crédito, etc).
c. Haber enviado más de 50 DE en un mismo lote
d. Estar bloqueado por envío duplicado, ver Motivos de bloqueo
e. El tamaño del archivo comprimido enviado supera el tamaño permitido.
El mensaje de datos de entrada del WS no debe superar 1000 KB.
Motivos de bloqueo
Las siguientes operaciones generan bloqueo de recepción de documentos por RUC
Emisor de 10 a 60 minutos, según la cantidad de reincidencia. Esto puede generar
6


--- PAGE 7 ---

algún esquema de penalización en el futuro. Los motivos del bloqueo temporal de
recepción por RUC son:
f. Enviar lotes vacíos o con contenido no válido.
g. Enviar el mismo CDC varias veces en un mismo lote.
h. Enviar el mismo CDC varias veces en lotes distintos y que aún se encuentren
en procesamiento.
Antes de volver a enviar un DE (mismo CDC enviado) se debe verificar que
no esté aún en procesamiento, con la consulta de lote.
i. Enviar varias veces un mismo lote.
Invocación de Web Service Asíncronos
1. Se debe prestar mucha atención a los namespace especificados para cada servicio
web.
2. Se realiza una autenticación mutua con SIFEN a través de un certificado digital
emitido por una PSC habilitada. El medio para establecer esta comunicación es la
Internet, apoyado en la utilización del protocolo de seguridad TLS versión 1.2, con
autenticación mutua.
Configuracióndeconexiónparaautenticaciónmutua(enPostman)
7


--- PAGE 8 ---

recibe-lote
Recepción de DE por lotes, para consumir este servicio, el cliente deberá construir la
estructura en XML, según el schema WS_SiRecepLoteDE.xsd y comprimir dicho archivo.
Cabe aclarar que el lote podrá contener hasta 50 DE del mismo tipo (ejemplo: Facturas
Electrónicas), cada uno de ellos debe estar firmado.
InvocaciónPOST(enPostman)
Request Body
Pasos para crear el Body para la invocación del servicio:
1. Crear la estructura del lote
<rLoteDE>
…
</rLoteDE>
2. Insertar los DE firmados en la estructura del lote
<rLoteDE>
<rDE>...</rDE>
<rDE>...</rDE>
…
</rLoteDE>
3. Comprimir el contenido de la estructura del lote “rLoteDE”
4. Convertir el contenido comprimido a Base64
5. Crear el envelope soap, teniendo en cuenta los namespace especificados
8


--- PAGE 9 ---

<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body<
<xsd:rEnvioLote>
<xsd:dId>20240926</xsd:dId>
<xsd:xDE>{Aquí va el Base64 del punto 4}</xsd:xDE>
</xsd:rEnvioLote>
</soap:Body>
</soap:Envelope>
6. Verificar la respuesta de la invocación “rResEnviLoteDe”
<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rResEnviLoteDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-08T14:51:21-03:00</ns2:dFecProc>
<ns2:dCodRes>0300</ns2:dCodRes>
<ns2:dMsgRes>Lote recibido con &#233;xito</ns2:dMsgRes>
<ns2:dProtConsLote>11158097383597290</ns2:dProtConsLote>
<ns2:dTpoProces>0</ns2:dTpoProces>
</ns2:rResEnviLoteDe>
</env:Body>
</env:Envelope>
Response
La respuesta, se debe analizar el campo “dCodRes”, puede indicar una de las situaciones
siguientes
1. Lote recibido con éxito (0300), el lote será procesado, se debe consultar el estado
para obtener el detalle de los documentos enviados. Se sugiere comenzar a
consultar un lote enviado pasado 10 minutos desde el envío.
2. Lote no encolado para procesamiento (0301), el lote NO será procesado, verificar la
sección "Lote no encolado para procesamiento".
9


--- PAGE 10 ---

consulta-lote
Devuelve el resultado del procesamiento de cada uno de los DE contenidos en un lote.
Según el schema WS_SiConsLote.xsd.
Request Body
La consulta se realiza por el valor del campo “dProtConsLote” que forma parte del
response de la recepción del lote.
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body>
<xsd:rEnviConsLoteDe>
<xsd:dId>1</xsd:dId>
<xsd:dProtConsLote>11158097383597290</xsd:dProtConsLote>
</xsd:rEnviConsLoteDe>
</soap:Body>
</soap:Envelope>
Response
La respuesta, se debe analizar el campo “dCodResLot”, puede indicar una de las cuatro
situaciones siguientes:
1. No existe número de lote consultado. 0360 Número del Lote inexistente
2. No se ha culminado el procesamiento de los DE. 0361 Lote en procesamiento. Debe
consultar nuevamente el lote, se sugiere consultar a intervalos mínimos de 10
minutos. En momentos de alta carga el procesamiento puede ocurrir entre 1 a 24
horas posteriores a la recepción.
3. Consulta extemporánea de Lote. 0364 La consulta del lote contempla un plazo de
hasta 48 horas posteriores al envío del mismo. Una vez superado el tiempo, deberá
consultar cada CDC del lote mediante la WS Consulta DE
4. Éxito en la consulta. 0362 Procesamiento de lote concluido.
La respuesta también contiene el contenedor del DE, definido en el Schema.
A. En procesamiento
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
10


--- PAGE 11 ---

<env:Body>
<ns2:rResEnviConsLoteDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-08T14:53:53-03:00</ns2:dFecProc>
<ns2:dCodResLot>0361</ns2:dCodResLot>
<ns2:dMsgResLot>Lote {11158097383597290} en procesamiento
</ns2:dMsgResLot>
</ns2:rResEnviConsLoteDe>
</env:Body>
</env:Envelope>
B. Procesamiento concluido
Se indica el detalle del procesamiento CDC en el elemento “gResProcLote”
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rResEnviConsLoteDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-08T03:58:16-03:00</ns2:dFecProc>
<ns2:dCodResLot>0362</ns2:dCodResLot>
<ns2:dMsgResLot>Procesamiento de lote {11444651783497640} concluido
</ns2:dMsgResLot>
<ns2:gResProcLote>
<ns2:id>07800252985001001000311822024021016361562161</ns2:id>
<ns2:dEstRes>Rechazado</ns2:dEstRes>
<ns2:gResProc>
<ns2:dCodRes>0160</ns2:dCodRes>
<ns2:dMsgRes>XML malformado: [El valor del elemento: dDirRec es
invalido, El valor del elemento: dDirLocEnt es invalido]
</ns2:dMsgRes>
</ns2:gResProc>
</ns2:gResProcLote>
</ns2:rResEnviConsLoteDe>
</env:Body>
</env:Envelope>
11


--- PAGE 12 ---

consulta
Devuelve el XML de un DE que está en estado aprobado. Según el schema
WS_SiConsDE.xsd
Request Body
La consulta se realiza por el valor del campo “dCDC”.
<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"
xmlns:xsd="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:si="http://ekuatia.set.gov.py/sifen/xsd">
<soap:Header/>
<soap:Body>
<xsd:rEnviConsDeRequest>
<xsd:dId>12</xsd:dId>
<xsd:dCDC>01028052080001001000013622023100111644108186</xsd:dCDC>
</xsd:rEnviConsDeRequest>
</soap:Body>
</soap:Envelope>
Response
La respuesta, se debe analizar el campo “dCodRes”, puede indicar una de las dos situaciones
siguientes:
1. 0420 El DE no existe o no está aprobado, se debe volver a enviar el DE para su
procesamiento, tener en cuenta el resultado de la consulta por lote antes de enviar
nuevamente.
2. 0422 Existe como DTE, está aprobado, se responde el contenido XML del DE en
“xContenDE”
A. No existe
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rEnviConsDeResponse xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2024-10-09T09:28:39-03:00</ns2:dFecProc>
<ns2:dCodRes>0420</ns2:dCodRes>
<ns2:dMsgRes>Documento No Existe en SIFEN o ha sido Rechazado
</ns2:dMsgRes>
12


--- PAGE 13 ---

</ns2:rEnviConsDeResponse>
</env:Body>
</env:Envelope>
B. Existe
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:Body>
<ns2:rEnviConsDeResponse xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:dFecProc>2023-10-02T15:13:52-03:00</ns2:dFecProc>
<ns2:dCodRes>0422</ns2:dCodRes>
<ns2:dMsgRes>CDC encontrado</ns2:dMsgRes>
<ns2:xContenDE>{contenido XML del DE}</ns2:xContenDE>
</ns2:rEnviConsDeResponse>
</env:Body>
</env:Envelope>
13
```

---

# Apéndice B — Texto completo: Manual Técnico SIFEN v150 (10/09/2019)

<!-- SOURCE: Manual Técnico SIFEN v150 (Versión 150) -->


```text
--- PAGE 1 / 217 ---

MANUAL TÉCNICO
SISTEMA INTEGRADO
DE FACTURACIÓN
ELECTRÓNICA
NACIONAL (SIFEN)
Versión 150
10/09/2019
El presente docume nto puede sufrir
modificaciones hasta la i mplementación total
del proyecto SIFEN.

--- PAGE 2 / 217 ---

Contenido
INDICE DE GRÁFICAS ..................................................................................................... 7
INDICE DE TABLAS .......................................................................................................... 8
INDICE DE SCHEMAS ...................................................................................................... 9
Control de versiones ........................................................................................................ 10
Versión: 120 ................................................................................................................................................... 10
Versión: 130 ................................................................................................................................................... 10
Versión: 140 ................................................................................................................................................... 11
Versión: 141 ................................................................................................................................................... 12
Versión: 150 ................................................................................................................................................... 12
1. INTRODUCCIÓN .................................................................................................. 15
2. OBJETIVOS .......................................................................................................... 16
3. ALCANCE ............................................................................................................. 17
4. Sistema Integrado de Facturación Electrónica Nacional SIFEN ............................ 18
4.1. Estructura y subsistemas SIFEN ......................................................................................................... 18
4.2. Fundamento legal .............................................................................................................................. 20
4.3. Validez jurídica e incidencia tributaria de los documentos tributarios electrónicos ........................ 21
5. Documentos Tributarios Electrónicos .................................................................... 22
5.1. Comprobantes de ventas electrónicos: ............................................................................................. 22
5.2. Documentos complementarios electrónicos: ................................................................................... 22
5.3. Nota de Remisión Electrónica ........................................................................................................... 22
6. Modelo Operativo .................................................................................................. 23
6.1. Descriptores del modelo operativo de SIFEN .................................................................................... 23
6.1.1. Archivo electrónico .................................................................................................................... 23
6.1.2. Aprobación del DTE ................................................................................................................... 23
6.2. Plazo de transmisión del DE a la SET ................................................................................................. 24
6.2.1. Plazos SIFEN ............................................................................................................................... 24
6.3. Relación directa con los contribuyentes ........................................................................................... 26
6.4. Entrega del DE al receptor ................................................................................................................. 26
6.5. Rechazo del DE en el modelo de aprobación posterior .................................................................... 26
6.6. Verificación de la existencia del DTE por parte del receptor ............................................................ 27
7. Características tecnológicas del formato ............................................................... 28
7.1. Modelo conceptual de comunicación ............................................................................................... 28
7.2. Estándar del formato XML ................................................................................................................. 30
7.2.1. Estándar de codificación ............................................................................................................ 30
7.2.2. Declaración namespace ............................................................................................................. 30
septiembre de 2019 1

--- PAGE 3 / 217 ---

7.2.2.1. Particularidad de la firma digital ........................................................................................... 31
7.2.2.2. Particularidad del envío de lote............................................................................................. 31
7.2.3. Convenciones referenciadas en tablas ...................................................................................... 32
7.2.4. Recomendaciones mejores prácticas de generación del archivo ............................................. 34
7.3. Contenedor de documento electrónico ............................................................................................ 35
7.4. Estándar de comunicación ................................................................................................................ 35
7.5. Estándar de certificado digital ........................................................................................................... 36
7.6. Estándar de firma digital ................................................................................................................... 37
7.7. Especificaciones técnicas del estándar de certificado y firma digital ............................................... 39
7.8. Procedimiento para la validación de la firma digital: ........................................................................ 40
7.9. Síntesis de definiciones tecnológicas ................................................................................................ 40
7.10. Resumen de las Direcciones Electrónicas de los Servicios Web para Ambientes de Pruebas y
Producción ..................................................................................................................................................... 41
7.11. Servidor para sincronización externa de horario .......................................................................... 41
8. Aspectos Tecnológicos de los Servicios Web del SIFEN ...................................... 42
8.1. Servicio síncrono................................................................................................................................ 42
8.1.1. Flujo funcional: .......................................................................................................................... 42
8.2. Servicio asíncrono .............................................................................................................................. 43
8.2.1. Secuencia del servicio asíncrono: .............................................................................................. 43
8.2.2. Tiempo promedio de procesamiento de un lote: ..................................................................... 43
8.3. Estándar de mensajes de los servicios del SIFEN .............................................................................. 44
8.4. Versión de los Schemas XML ............................................................................................................. 44
8.4.1. Identificación de la versión de los Schemas XML ...................................................................... 44
8.4.2. Liberación de versiones de los Schemas XML ........................................................................... 44
8.4.3. Paquete inicial de Schemas ....................................................................................................... 44
9. Descripción de los Servicios Web del SIFEN ........................................................ 45
9.1. WS recepción documento electrónico – siRecepDE .......................................................................... 45
9.1.1. Definición del protocolo que consume este servicio ................................................................ 45
9.1.2. Descripción del procesamiento ................................................................................................. 45
9.1.3. Protocolo de respuesta ............................................................................................................. 46
9.2. WS recepción lote DE – siRecepLoteDE ............................................................................................. 47
9.2.1. Definición del protocolo que consume este servicio ................................................................ 47
9.2.2. Descripción del procesamiento ................................................................................................. 47
9.2.3. Protocolo de respuesta ............................................................................................................. 48
septiembre de 2019 2

--- PAGE 4 / 217 ---

9.3. WS consulta resultado de lote DE – siResultLoteDE ......................................................................... 48
9.3.1. Definición del protocolo que consume este servicio ................................................................ 48
9.3.2. Descripción del procesamiento ................................................................................................. 49
9.3.3. Protocolo de respuesta ............................................................................................................. 49
9.4. WS consulta DE – siConsDE ............................................................................................................... 50
9.4.1. Definición del protocolo que consume este servicio ................................................................ 50
9.4.2. Descripción del procesamiento ................................................................................................. 51
9.4.3. Protocolo de respuesta ............................................................................................................. 51
9.5. WS recepción evento – siRecepEvento ............................................................................................. 52
9.5.1. Definición del protocolo que consume este Servicio ................................................................ 52
9.5.2. Descripción del procesamiento ................................................................................................. 53
9.5.3. Protocolo de respuesta ............................................................................................................. 53
9.6. WS consulta RUC – siConsRUC .......................................................................................................... 53
9.6.1. Definición del protocolo que consume este servicio ................................................................ 54
9.6.2. Descripción del procesamiento ................................................................................................. 54
9.6.3. Protocolo de respuesta ............................................................................................................. 54
9.7. WS consulta DE de entidades u organismos externos autorizados – siConsDEST (a futuro) ............ 55
10. Formato de los Documentos Electrónicos ............................................................. 56
10.1. Estructura del código de control (CDC) de los DE ......................................................................... 56
10.2. Dígito verificador del CDC .............................................................................................................. 57
10.3. Generación del código de seguridad ............................................................................................. 57
10.4. Datos que se deben informar en los documentos electrónicos (DE) ............................................ 58
10.5. Manejo del timbrado y Numeración ............................................................................................. 59
11. Gestión de eventos ............................................................................................. 112
11.1. Eventos realizados por el emisor ................................................................................................. 112
11.1.1. Inutilización de número de DE ................................................................................................ 112
11.1.2. Cancelación .............................................................................................................................. 113
11.1.3. Devolución y Ajuste de precios ............................................................................................... 113
11.1.4. Endoso de FE (evento futuro) .................................................................................................. 114
11.2. Eventos registrados por el receptor ............................................................................................ 114
11.2.1. Conformidad con el DTE .......................................................................................................... 114
11.2.2. Disconformidad con el DTE...................................................................................................... 114
11.2.3. Desconocimiento con el DE o DTE ........................................................................................... 114
11.2.4. Notificación de recepción de un DE o DTE .............................................................................. 115
septiembre de 2019 3

--- PAGE 5 / 217 ---

11.2.5. Tipología de los eventos del receptor ......................................................................................... 115
11.4. Eventos registrados por la SET (evento futuro) ........................................................................... 116
11.4.1. Impugnación de DTE ................................................................................................................ 116
11.5. Estructura de los Eventos ............................................................................................................ 120
11.5.1. FORMATO DE EVENTOS EMISOR ............................................................................................. 121
11.5.2. FORMATO DE EVENTOS RECEPTOR ......................................................................................... 123
11.6. REGLAS DE VALIDACIÓN DE GESTIÓN DE EVENTOS .................................................................... 133
11.6.1. REGLAS DE VALIDACIÓN PARA CANCELACIÓN ........................................................................ 134
11.6.2. REGLAS DE VALIDACIÓN PARA INUTILIZACIÓN ....................................................................... 135
11.6.3. REGLAS DE VALIDACIÓN PARA NOTIFICACIÓN – RECEPCIÓN DE/DTE .................................... 136
11.6.4. REGLAS DE VALIDACIÓN PARA EL EVENTO CONFORMIDAD ................................................... 137
11.6.5. REGLAS DE VALIDACIÓN PARA EL EVENTO DISCONFORMIDAD .............................................. 138
11.6.6. REGLAS DE VALIDACIÓN PARA EL EVENTO DESCONOCIMIENTO DE/DTE ............................... 139
11.6.7. REGLAS DE VALIDACIÓN PARA EL EVENTO POR ACTUALIZACIÓN DE DATOS: DATOS DEL
TRANSPORTE ........................................................................................................................................... 141
12. Validaciones ........................................................................................................ 145
12.1. Estructura de los códigos de validación ...................................................................................... 146
12.1.1. Códigos de respuestas de las validaciones de los Servicios Web ............................................ 147
12.1.2. Códigos de respuestas de las validaciones de los DE .............................................................. 148
12.1.3. Códigos de respuestas de las validaciones de los eventos ...................................................... 150
12.2. Codificación de respuestas de los Servicios WEB del SIFEN ........................................................ 150
12.2.1. Validaciones del certificado de transmisión. Protocolo TLS .................................................... 150
12.2.2. Validación de la estructura XML de los WS ............................................................................. 151
12.2.3. Validación de forma del área de datos del Request ................................................................ 152
12.2.4. Validación del certificado de firma .......................................................................................... 152
12.2.5. Validación de la firma digital ................................................................................................... 153
12.2.6. Validaciones genéricas a los mensajes de entrada de los WS ................................................. 153
12.2.7. Validaciones genéricas a los mensajes de control de llamada de los WS ............................... 154
12.3. Validaciones de cada Web Service .............................................................................................. 154
12.3.1. WS recepción documento electrónico – siRecepDE ................................................................ 154
12.3.1.1. Mensaje de entrada del WS ................................................................................................ 154
12.3.1.2. Información de control de la llamada al WS ....................................................................... 154
12.3.1.3. Área de datos del WS .......................................................................................................... 154
12.3.2. WS recepción lote DE – siRecepLoteDE ................................................................................... 155
septiembre de 2019 4

--- PAGE 6 / 217 ---

12.3.2.1. Mensaje de entrada del WS ................................................................................................ 155
12.3.2.2. Información de control de la llamada al WS ....................................................................... 155
12.3.2.3. Área de datos del WS .......................................................................................................... 155
12.3.3. WS consulta resultado de lote DE – siResultLoteDE ............................................................... 155
12.3.3.1. Mensaje de entrada del WS ................................................................................................ 155
12.3.3.2. Información de control de la llamada al WS ....................................................................... 156
12.3.3.3. Área de datos del WS .......................................................................................................... 156
12.3.4. WS consulta de DE – siConsDE ................................................................................................ 156
12.3.4.1. Mensaje de entrada del WS ................................................................................................ 156
12.3.4.2. Información de control de la llamada al WS ....................................................................... 157
12.3.4.3. Área de datos del WS .......................................................................................................... 157
12.3.5. WS consulta de RUC – siConsRUC ........................................................................................... 157
12.3.5.1. Mensaje de entrada del WS ................................................................................................ 157
12.3.5.2. Información de control de la llamada al WS ....................................................................... 157
12.3.5.3. Área de datos del WS .......................................................................................................... 157
12.3.6. WS recepción de evento – siRecepEvento .............................................................................. 158
12.3.6.1. Mensaje de entrada del WS ................................................................................................ 158
12.3.6.2. Información de control de la llamada al WS ....................................................................... 158
12.3.6.3. Área de datos del WS .......................................................................................................... 158
12.4. Validaciones del formato ............................................................................................................. 159
13. Gráfica (KUDE) ................................................................................................... 193
13.1. Definición y alcance del KuDE: .................................................................................................... 193
13.2. Características y funcionalidades ................................................................................................ 193
13.3. Denominación de los KuDE .......................................................................................................... 193
13.4. Estructura del KuDE ..................................................................................................................... 194
13.4.1. Campos del encabezado del KuDE .......................................................................................... 195
13.4.2. Campos que describen los ítems de la operación del KuDE .................................................... 196
13.4.3. Campos que describen los subtotales y totales de la transacción documentada y liquidación de
IVA 196
13.4.4. Campos de información propia de la consulta en SIFEN de la SET ......................................... 196
13.4.5. Información adicional de interés para el emisor ..................................................................... 197
13.5. KuDE ............................................................................................................................................ 197
13.6. KuDE (cinta de papel) .................................................................................................................. 203
13.7. Cinta papel resumen del KuDE .................................................................................................... 204
septiembre de 2019 5

--- PAGE 7 / 217 ---

13.8. Código bidimensional (QR) .......................................................................................................... 205
13.8.1. Delineamientos del QR Code ................................................................................................... 205
13.8.2. Conformación del Código QR .................................................................................................. 205
13.8.3. Metodología para la generación del Código QR ...................................................................... 206
13.8.4. Ejemplo de generación del Código QR .................................................................................... 207
13.8.5. Mensajes desplegados en consulta del QR ............................................................................. 209
14. Operación de Contingencia (Futuro) ................................................................... 210
15. CODIFICACIONES ............................................................................................. 210
16. GLOSARIO TÉCNICO ........................................................................................ 214
septiembre de 2019 6

--- PAGE 8 / 217 ---

INDICE DE GRÁFICAS
Gráfica Nº 01 Sistema Integrado de Facturación Electrónica Nacional (SIFEN) .............. 18
Gráfica Nº 02 Subsistema de Validación de Uso ............................................................. 19
Gráfica Nº 03 Subsistema Electrónico Solución Gratuita E-kuatia’i .................................. 20
Gráfica Nº 04: Secuencia de acciones tecnológicas SIFEN ............................................. 23
Gráfica Nº 05: Flujo de comunicación .............................................................................. 28
Gráfica Nº 06: WS Sincrónico .......................................................................................... 29
Gráfica Nº 07: WS Asincrónico ........................................................................................ 29
Gráfica N° 08: Relación elementos XML .......................................................................... 32
Gráfica Nº 09 – KuDE FE Formato 1 (Papel Carta o similar) ......................................... 198
Gráfica Nº 10 – KuDE NCE Formato 1 (Papel Carta o similar) ...................................... 199
Gráfica Nº 11 – KuDE NDE Formato 1 (Papel Carta o similar) ...................................... 200
Gráfica Nº 12 – KuDE AFE Formato 1 (Papel Carta o similar) ....................................... 201
Gráfica Nº 13 – KuDE NRE Formato 1 (Papel Carta o similar) ...................................... 202
Gráfica Nº 14 – KuDE FE Formato 2 (cinta de papel) .................................................... 203
Gráfica Nº 15 – Cinta papel resumen del KuDE ............................................................. 204
septiembre de 2019 7

--- PAGE 9 / 217 ---

INDICE DE TABLAS
Tabla A – Convenciones Utilizadas en la Tablas de Definición de los Formatos XML ..... 32
Tabla B – Tipos de Datos en los Archivos XML ............................................................... 33
Tabla C: Tamaños de campos ......................................................................................... 34
Tabla D: Formatos numéricos .......................................................................................... 34
Tabla E: Estándares de tecnología utilizados .................................................................. 40
Tabla F – Resultados de Procesamiento del WS Consulta Resultado de Lote ................ 49
Tabla G – Resultados de Procesamiento del WS Consulta DE ........................................ 51
Tabla H – Resultados de Procesamiento del WS Consulta RUC ..................................... 54
Tabla I – Grupos de campos del Archivo XML ................................................................. 58
Tabla J: Resumen de los eventos de SIFEN según los actores ..................................... 117
Tabla K: Correcciones de los eventos del Receptor en el SIFEN ................................... 119
TABLA 1 – TIPO DE REGIMEN ..................................................................................... 210
TABLA 2.1 – DEPARTAMENTOS, DISTRITOS Y CIUDADES ...................................... 210
TABLA 2.2 - CIUDADES ................................................................................................ 210
TABLA 3 – ACTIVIDADES ECONÓMICAS .................................................................... 211
TABLA 4 – CODIFICACION DE PAISES ....................................................................... 211
TABLA 5 – CODIFICACION DE UNIDADES DE MEDIDA ............................................. 211
TABLA 6 – CODIGOS DE AFECTACION ...................................................................... 212
TABLA 7 – CATEGORIAS DEL ISC .............................................................................. 212
TABLA 8 – TASAS DEL ISC .......................................................................................... 212
TABLA 9 – TIPOS DE VEHÍCULOS .............................................................................. 212
TABLA 10 – CONDICIONES DE NEGOCIACION - INCOTERMS ................................. 213
TABLA 11 – REGÍMENES ADUANEROS ...................................................................... 213
septiembre de 2019 8

--- PAGE 10 / 217 ---

INDICE DE SCHEMAS
Schema XML 1: xmldsig-core-schema- v150.xsd (Estándar de la Firma Digital).............. 38
Schema XML 2: siRecepDE_v150.xsd (WS Recepción DE) ............................................ 45
Schema XML 3: resRecepDE_v150.xsd (Respuesta del “WS Recepción DE”) ................ 46
Schema XML 4: ProtProcesDE_v150.xsd (Protocolo de Procesamiento de DE) ............. 46
Schema XML 5: SiRecepLoteDE_v150.xsd (WS Recepción DE Lote) ............................. 47
Schema XML 5A: ProtProcesLoteDE_v150.xsd (Protocolo de procesamiento del Lote) .. 47
Schema XML 6: resRecepLoteDE_v150.xsd (Respuesta del WS Recepción Lote) ......... 48
Schema XML 7: SiResultLoteDE_v150.xsd (WS Consulta Resultado de Lote) ................ 48
Schema XML 8: resResultLoteDE_v150.xsd (Respuesta del WS Consulta Resultado Lote)49
Schema XML 9: siConsDE_v150.xsd (WS Consulta DE) ................................................. 50
Schema XML 10: resConsDE_v150.xsd (Respuesta del WS Consulta DE) ..................... 51
Schema XML 11: ContenedorDE_v150.xsd (Contenedor de DE) .................................... 51
Schema XML 12: ContenedorEvento_v150.xsd (Contenedor de Evento) ........................ 52
Schema XML 13: siRecepEvento_v150.xsd (WS Recepción Evento) .............................. 52
Schema XML 14: resRecepEvento_v150.xsd (Respuesta del WS Recepción Evento) .... 53
Schema XML 15: siConsRUC_v150.xsd (WS Consulta RUC) ......................................... 54
Schema XML 16: resConsRUC_v150.xsd (Respuesta del WS Consulta RUC) ............... 54
Schema XML 17: ContenedorRUC_v150.xsd (Contenedor de RUC) ............................... 55
Schema XML 18: DE_v150.xsd (Documento Electrónico) ............................................... 61
Schema XML 19: Evento_v150.xsd (Formato de evento emisor) ................................... 120
septiembre de 2019 9

--- PAGE 11 / 217 ---

Control de versiones
Versión: 120
Fecha de modificación: 03/05/2018
Ubicación - capítulo Descripción de las modificaciones
Por la cual se crea el Manual Técnico que establece los requisitos y condiciones tecnológicos para
constituirse como Facturador Electrónico del Sistema Integrado de Facturación Electrónica Nacional
(SIFEN)
Versión: 130
Fecha de modificación: 29/06/2018
Ubicación - capítulo Descripción de las modificaciones
6 Modelo operativo Eliminación de Ambiente de habilitación y/o pruebas.
Creación y Reestructuración del apartado 6.2.1 Plazo de transmisión del
DE a la SET.
Cambios en Rechazo del DE en el modelo de validación posterior
6.2.1. Plazos SIFEN Se crea esta sección, se introducen cambios en la tabla de plazos
7. Características Se agrega las etiquetas <rDE> <dVerfor> en 7.2.2.1 Particularidad de la
tecnológicas del formato Firma digital y 7.2.2.2 Particularidad de envío de lote
Cambios en el 7.4. Estándar de comunicación, se modificó Request de
ejemplo utilizando SOAP
8.3. Estándar de mensajes Se elimina la versión
de los servicios del SIFEN y
8.4 Información de control y
área de datos de los
mensajes
9 Descripción de los Desde el Schema XML 2 al Schema XML 14 (Se eliminó versión)
servicios web del SIFEN
10.3. Generación del código Se agregó esta sección
de seguridad
TABLA DE FORMATO DE El antiguo grupo A se divide en grupo AA y A.
CAMPOS DE UN Se eliminó el grupo Campos que identifican a los terceros autorizados.
DOCUMENTO Reestructuración en el grupo E
ELECTRÓNICO Se agregaron campos en el grupo D3. Datos que identifican al receptor
del Documento Electrónico DE (D200-D299)
11 Gestión de eventos Modificaciones en 11.1.3 Anulación o Ajuste y 11.2.1 Disconformidad
con el DTE
Se agrega 11.1.4 Endoso de FE
13.7 Código bidimensional Cambios en 13.7.2. Conformación del Código QR se agregaron.
(QR) Se agregan las siguientes secciones: 13.7.3 Metodología para la
generación del código QR, 13.7.4 Ejemplo de datos de generación del
código QR, 13.7.5 Ejemplo URL de la imagen del QR y 13.7.6 Mensajes
desplegados en consulta del QR
septiembre de 2019 10

--- PAGE 12 / 217 ---

Versión: 140
Fecha de modificación: 23/08/2018
Ubicación - capítulo Descripción de las modificaciones
Se detallan los cambios de la versión actual y la anterior en el control de versiones.
6.2.1. Plazos SIFEN Se introducen cambios en la tabla de plazos
6.5 Rechazo del DE en el Se aclara el procedimiento
modelo de validación
posterior
7.2.3 Tabla A Tipos de Datos * Del tipo de dato Fecha (F) se elimina la zona horaria.
y en todas las secciones en * En el tipo de dato Numérico (N) no se mantiene una longitud
donde se utilizan fechas. invariante.
7.5 Estándar de certificado Se agrega un ejemplo de uso del dato RUC
digital
8.2.2 Tiempo promedio de Aclaraciones en tiempos de procesamiento
procesamiento de un lote
8.4.5. Paquete de Schemas Se elimina esta sección, debido a que ya no se utiliza el ambiente
para el ambiente de (prueba o producción)
pruebas
9. DESCRIPCIÓN DE LOS * Se eliminó el ambiente y la versión del formato de los Web Services.
SERVICIOS WEB DEL SIFEN * Se modifica la versión de los Schemas de 100 a 140.
* El proceso síncrono ahora devuelve un número de transacción.
El proceso asíncrono en su respuesta contiene un número de lote
(denominado Número del protocolo de autorización anteriormente)
* Se agrega el Web service de consulta de RUC siConsRUC y el Web
service consulta DE destinadas siConsDEST
10.1. Estructura del código Se modifica la estructura del CDC, ahora se diferencian el RUC del
de control (CDC) de los DE emisor y su Dígito verificador.
TABLA DE FORMATO DE Se introdujeron varios cambios en los grupos, no entramos a detallarlos
CAMPOS DE UN en esta sección para contribuir a la legibilidad, sin embargo, esos
DOCUMENTO cambios se reflejan en esta versión del Manual Técnico mediante los
ELECTRONICO (DE) siguientes colores.
Amarillo = modificaciones
Verde = adición de campos
11 Gestión de eventos Se agrega una tabla resumen de tipo de evento según el actor.
Se agrega las estructuras correspondientes a los eventos de
Cancelación e Inutilización.
Se agregan las validaciones a realizarse sobre los eventos de
Cancelación e Inutilización
13.7 Código bidimensional Se elimina el ambiente de generación
(QR)
septiembre de 2019 11

--- PAGE 13 / 217 ---

Versión: 141
Fecha de modificación: 21/09/2018
Ubicación - capítulo Descripción de las modificaciones
6.2.1 Plazos SIFEN Se introducen cambios en la tabla de plazos
7.2 Estándar del formato 7.2.2 Declaración namespace, se cambia la url del namespace
XML
7.2.2.1 Particularidad de la firma digital, cambio del ejemplo
7.2.2.2 Particularidad del envío de lote, cambio del ejemplo
7.2.3 Convenciones referenciadas en tablas, mejor especificación del
tipo de dato fecha y se agregó el tipo de dato Binario
7.4 Estándar de Se modificaron el Request y el Response de ejemplo
comunicación
7.6 Estándar de firma digital Modificaciones en el Schema XML 1.
7.10 Resumen de las Se agregó la tabla resumen con las urls.
Direcciones Electrónicas de
los Servicios Web para
Ambientes de Pruebas y
Producción
8 ASPECTOS Se elimina la sección 8.4 Información de control y área de datos de los
TECNOLÓGICOS DE LOS mensajes
SERVICIOS WEB DEL SIFEN
9 DESCRIPCIÓN de los * Modificaciones en los siguientes schemas: Schema XML 4, Schema
Servicios Web del SIFEN XML 5, Schema XML 6, Schema XML 7, Schema XML 8, Schema XML 16,
Schema XML 17
* Se agregó el Schema XML 5A
TABLA DE FORMATO DE Se introdujeron varios cambios en los grupos, no entramos a detallarlos
CAMPOS DE UN en esta sección para contribuir a la legibilidad, sin embargo, esos
DOCUMENTO cambios se reflejan en esta versión del Manual Técnico mediante los
ELECTRONICO (DE) siguientes colores.
Amarillo = modificaciones
Verde = adición de campos
11 Gestión de eventos Modificaciones en las validaciones a realizarse sobre los eventos de
Cancelación e Inutilización
13.8 Código bidimensional Se modifica el Código de Seguridad (CSC) a 32 dígitos alfanuméricos.
(QR)
Versión: 150
Fecha de modificación: 10/09/2019
Ubicación - capítulo Descripción de las modificaciones
Se realizó la actualización de la numeración de los capítulos, estilos y formatos para mejor
organización de los índices.
4.1. Estructura y Actualización de la gráfica Nº 2
subsistemas SIFEN
4.2. Fundamento Legal Se agregó la resolución general reglamentaria
6.2.1 Plazos SIFEN Se introducen plazos para eventos en la tabla
septiembre de 2019 12

--- PAGE 14 / 217 ---

7.10 Resumen de las Se actualizan las URLs para los ambientes de Producción y Test
Direcciones Electrónicas de
los Servicios Web para
Ambientes de Pruebas y
Producción
7.4. Estándar de Se corrige el campo donde se incluye el mensaje XML a cualquiera de
comunicación los Servicios Web del SIFEN. El campo actualizado es soap:Body
9 DESCRIPCIÓN de los * Modificaciones en los siguientes schemas: Schema XML 4, Schema
Servicios Web del SIFEN XML 6, Schema XML 8, Schema XML 14, Schema XML 17
TABLA DE FORMATO DE Se introdujeron varios cambios, ya que desde esta versión del sistema
CAMPOS DE UN se puede recibir y gestionar los siguientes DEs: Autofactura electrónica
DOCUMENTO y Nota de Remisión electrónica. Los cambios se reflejan en esta versión
ELECTRONICO (DE) del Manual Técnico mediante los siguientes colores.
Amarillo = modificaciones
Verde = adición de campos
Rojo = eliminación
Además, se eliminaron las citas que se hacían hacia los tipos de
documentos: Factura electrónica de exportación, Factura electrónica
de importación y Comprobante de retención electrónico.
Se eliminó la estructura relacionada a ISC
10.5 Manejo del timbrado y Explicación del uso de serie
Numeración
11 Gestión de eventos El evento de anulación ahora se denomina Devolución y Ajuste de
precios
Se introdujeron eventos que realizarán los receptores: Conformidad y
Disconformidad con el DTE, Desconocimiento con el DE o DTE y
Notificación de recepción de un DE o DTE
Cambios en la Tabla J: Resumen de los eventos de SIFEN según los
actores
Se agrega la Tabla K: Correcciones de los eventos del Receptor en el
SIFEN
Se agregan las estructuras que se utilizarán para los servicios de
eventos del receptor
Se agregan los esquemas para los nuevos eventos automáticos y para
el evento de actualización de datos del transporte
12.2.2. Validación de la La versión del DE se informa en el campo de versión dentro del grupo
estructura XML de los WS rDE
Se elimina el ejemplo del elemento soap12:Header
12.2.3 Validación de forma Se eliminan los mensajes con código desde 0100 hasta el 0107
del área de datos del
Request
12.2.4 Validación del Se eliminan los mensajes con código desde el 0123 hasta el 0126
certificado de firma
12.2.5 Validación de la La validación con código 0141 se encarga de controlar los casos que se
firma contemplaban en las validaciones con código 0123 al 0126
12.4 Validaciones del Se introdujeron cambios en las validaciones sobre el formato, puesto
formato que se han agregado los siguientes DE: Autofactura electrónica y
Notificación de recepción electrónica.
Se eliminaron las validaciones correspondientes al ISC, así como las
validaciones que se estimaban se realizarían en el futuro.
13. Gráfica KuDE Actualización de las URLs de consulta en los distintos ambientes
Se agregan ejemplos de cada uno de los KuDEs
septiembre de 2019 13

--- PAGE 15 / 217 ---

13.8.3. Metodología para la Modificaciones en los datos del cuadro de ejemplo
generación del Código QR
13.8.4. Ejemplo datos QR Se modifica para especificar por pasos la generación de código QR.
13.8.5. Ejemplo del QR con Se elimina como 13.8.5 y se inserta como un paso más en el punto
el Código Secreto del 13.8.4.
Contribuyente
13.8.6. Ejemplo URL de la Se elimina como 13.8.6 y se inserta como un paso más en el punto
imagen del QR 13.8.4
13.8.7 Mensajes Se actualiza la numeración a 13.8.5
desplegados en consulta
del QR
14. Operación de Se elimina el contenido de esta sección, ya que sigue en etapa de
Contingencia definición
15. Codificaciones Se elimina tabla de Ciudades (Tabla 2.2) y se reemplaza por el link que
lleva al archivo de Departamentos, Distritos y Ciudades (Tabla 2.1)
Se agrega el link para la tabla de Regímenes Aduaneros (Tabla 11)
Observación: en esta versión del Manual técnico están resaltados la mayor parte de los cambios que se
introdujeron siguiendo el siguiente patrón:
Amarillo = modificaciones
Verde = adición de contenido
Rojo = eliminación de contenido
No se respetó este esquema de control de versiones a color en la eliminación de contenido relacionado a ISC,
y a los tipos de documentos: Factura electrónica de exportación, Factura electrónica de importación y
Comprobante de retenciones electrónico.
septiembre de 2019 14

--- PAGE 16 / 217 ---

1. INTRODUCCIÓN
El presente Manual Técnico (MT) tiene como propósito constituirse en el documento maestro que establece
el conjunto de requisitos, condiciones y procedimientos tecnológicos que deben cumplir los contribuyentes
de IVA que se adhieran de manera voluntaria, o aquellos que hayan sido seleccionados por parte de la SET
para ser facturadores electrónicos, en el Sistema Integrado de Facturación Electrónica Nacional (SIFEN).
En tal sentido, el MT es una guía tecnológica en la cual los contribuyentes, potenciales facturadores
electrónicos, pueden encontrar los objetivos y alcance pretendidos en los capítulos 2 y 3; identificar en el
capítulo 4, en las secciones 4.1 a 4.3, la estructura y subsistemas de SIFEN, el fundamento legal que lo soporta,
la validez jurídica de los Documentos Tributarios Electrónicos (DTE) que se verán alcanzados con la operación
electrónica.
En el capítulo 5 se detallan los documentos tributarios electrónicos previstos para la versión actual del MT. En
el capítulo 6 se describe el Modelo Operativo.
En el capítulo 7, uno de los más determinantes del MT, se establecen las características tecnológicas del
formato, abarcando el modelo conceptual de comunicación, los estándares del formato XML, de
comunicación, del certificado y firma digital y las especificaciones técnicas respectivas.
Seguidamente, en los capítulos 8 y 9, se describen los Servicios Web previstos para SIFEN. El formato de los
Documentos Electrónicos, la gestión de eventos y las validaciones, son abordados en los capítulos 10, 11 y 12
respectivamente.
Los capítulos 13 al 17 abarcan lo concerniente a la representación gráfica (KuDE), la operación de contingencia,
la conservación de los DTE, las codificaciones utilizadas por SIFEN y glosario técnico.
Finalmente, es importante mencionar que este documento forma parte integral de la Resolución (futura) para
la etapa de Voluntariedad, que establece el marco jurídico procedimental y reglamenta a su vez el Decreto No
7.795/2017, mediante el cual se crea el SIFEN; constituyéndose en el pilar que regula y orienta la operación
del Sistema Integrado de Facturación Electrónica Nacional (SIFEN) del Paraguay.
septiembre de 2019 15

--- PAGE 17 / 217 ---

2. OBJETIVOS
Definir los requisitos y condiciones, así como los procedimientos tecnológicos y operacionales para realizar los
ajustes informáticos, la parametrización y adaptación de los sistemas de facturación, que deben cumplir los
contribuyentes de IVA, sean estos voluntarios y/o elegidos por la SET, para constituirse como facturadores
electrónicos.
Establecer el paso a paso a seguir para realizar la solicitud de autorización y timbrado, y en consecuencia
obtener la habilitación correspondiente.
Determinar las condiciones de estructuración del formato electrónico que deben observar los emisores al
momento de enviar y transmitir los Documentos Electrónicos a los receptores y a la SET respectivamente, a
este último actor, mediante el consumo de los servicios web dispuestos (estándar, tipos y descripción); así
como, aquellas referentes a la validación y/o rechazo por parte de la SET.
Precisar las condiciones, acciones y procedimientos que deban observar los contribuyentes facturadores
electrónicos para gestionar la contingencia que se presenta en el proceso de facturación electrónica, con el
objeto de generar y entregar la representación gráfica (KuDE) a los receptores y para el uso de las
codificaciones requeridas en el SIFEN.
Definir las condiciones, acciones y procedimientos que deban observar los contribuyentes facturadores
electrónicos para gestionar los eventos que se sucedan sobre los documentos electrónicos previamente
validados por la SET; así como, las condiciones y requisitos para consumir los servicios de consulta de los
mismos y sus eventos asociados.
septiembre de 2019 16

--- PAGE 18 / 217 ---

3. ALCANCE
Este documento tiene como alcance definir el conjunto de requisitos, condiciones y procedimientos
tecnológicos que deben cumplir los contribuyentes de IVA que se adhieran de manera voluntaria, o aquellos
que hayan sido seleccionados por la SET para ser facturadores electrónicos, en el Sistema Integrado de
Facturación Electrónica Nacional (SIFEN) del Paraguay.
septiembre de 2019 17

--- PAGE 19 / 217 ---

4. Sistema Integrado de Facturación Electrónica Nacional SIFEN
4.1. Estructura y subsistemas SIFEN
El Sistema Integrado de Facturación Electrónica Nacional (SIFEN) se encuentra estructurado en dos
subsistemas (subsistema de validación, y subsistema solución gratuita de facturación electrónica) que agrupan
funcionalidades específicas y servicios orientados a diferentes segmentos del universo de contribuyentes de
la SET, diferenciadas en su alcance, modelo operativo y tecnológico, volumen transaccional; así como, en su
desarrollo y construcción en el horizonte de tiempo de ejecución. Ver Gráfica Nº 01.
Gráfica Nº 01 Sistema Integrado de Facturación Electrónica Nacional (SIFEN)
Subsistema de Aprobación: se encuentra orientado en especial a grandes y medianos contribuyentes, los
cuales se podrán adherir de manera voluntaria o podrán ser seleccionados por la SET de manera obligatoria a
facturar electrónicamente. Los facturadores electrónicos comprendidos en este subsistema tendrán que
observar los requisitos, condiciones y plazos establecidos en el Decreto, su Resolución Reglamentaria y en el
presente Manual Técnico.
Este subsistema contempla dos momentos en su operación:
Primer momento – Operación comercial con documentos electrónicos (DE)
Como resultado de la operación comercial, el facturador electrónico emite el documento electrónico (DE)
firmado digitalmente y lo envía al comprador o receptor, en formato XML. Si el comprador o receptor no es
facturador electrónico, el emisor deberá enviar o disponibilizar una representación gráfica del documento
(KuDE) que soporta la transacción en formato físico o digital.
Segundo momento – Transmisión de los documentos electrónicos (DE) a la SET
Los contribuyentes facturadores electrónicos, envían el formato XML firmado digitalmente de los DE a la SET
para su proceso de validación (Ver Gráfica Nº 02).
septiembre de 2019 18

--- PAGE 20 / 217 ---

Gráfica Nº 02 Subsistema de Validación de Uso
Este subsistema contemplará, en las fases de piloto y voluntariedad del plan de masificación de la factura
electrónica, el control sobre aquellos segmentos de contribuyentes que tendrán que enviar el formato de los
DE al Sistema Integrado de Facturación Electrónica Nacional en un plazo de hasta 72 horas para su
correspondiente validación y aprobación como DTE, entiéndase horas corridas desde el momento de la firma
digital del DE.
Del mismo modo, y de manera controlada en las diferentes fases del plan de masificación podrá establecer o
habilitar a determinados contribuyentes bajo la modalidad de la validación previa; es decir, aquella en la cual
se exige al facturador electrónico (en condición de emisor) que previamente transmita el documento
electrónico (DE) a la SET (SIFEN) para su validación antes de su envío al receptor. Obviamente con la obtención
de la validación positiva (aprobación) por parte de SIFEN.
Subsistema Solución Gratuita de Facturación Electrónica Ekuatia’i: se encuentra orientado a contribuyentes
con una cantidad de emisión de documentos electrónicos baja, el cual será provisto por la SET de manera
gratuita, y comprenderá como productos y servicios básicos la emisión, transmisión y almacenamiento de
documentos electrónicos, estando soportados en los servicios web desarrollados en el subsistema de
aprobación, lo que permitirá mantener la integridad transaccional del SIFEN. Contempla para determinados
contribuyentes de este segmento el uso de firma digital. Las transacciones que se realicen en este subsistema
son en tiempo real. Ver Gráfica Nº 03.
septiembre de 2019 19

--- PAGE 21 / 217 ---

Portal SIFEN
Solución Gratuita Consulta
SIFEN SET F o ir C m o a n D tr i i g b i u ta y l ente DTE
Generación
KuDE
Multiplataforma Posib.import.
Web Responsive Archivo TXT/XML
Generación
DTE W Sin e c b r ó S n er ic v a ic ( e 1 FE/vez) WS WS Sincrónico/ W As e i b n c S r e ó r n v i i c c o e Act C o o re m s u c n o ic m a e c r i c ó i n a les
DTE: FE, NCE, NDE,
Pequeños contribuyentes NRE, AFE Validaciones previas
Volumen bajo de DTE
Solución Gratuita
E-Kuatia’i
Reportes
APP Móvil Básicos
MARANGATU 2.0 (ConsultaQR)
Acceso y Autenticación
• Usuario y Clave Gestión de Codificación e importación
Eventos de productos y catálogos
Timbrado -RUC
Gráfica Nº 03 Subsistema Electrónico Solución Gratuita E-kuatia’i
Los anteriores subsistemas mencionados de SIFEN tendrán una interoperabilidad con Marangatu, en particular
con el RUC y el módulo de Autorización y Timbrado, al igual que con los prestadores de servicios de
certificación de Paraguay a efectos de validar la vigencia del certificado digital.
SIFEN proveerá todos los servicios web y de internet de consulta referente a los Documentos Tributarios
Electrónicos (DTE), así como aquellos servicios orientados a indicar las novedades, afectaciones y eventos
sobre los mismos.
4.2. Fundamento legal
El SIFEN tiene su base legal en el siguiente marco normativo:
• La Ley N° 125/1991 "Que Establece el Nuevo Régimen Tributario" y sus modificaciones;
• La Ley Nº 4.017/2010 “De validez jurídica de la firma electrónica, la firma digital, los mensajes de datos
y el expediente electrónico”, y sus modificaciones.
• La Ley Nº 4.679/2012 “De Trámites Administrativos”.
• La Ley Nº 4.868/2013 “Comercio Electrónico”.
• El Decreto N° 6.539/2005 “Por el cual se dicta el reglamento general de Timbrado y uso de
Comprobantes de Venta, Documentos Complementarios, Notas de Remisión y Comprobantes de
Retención” y sus modificaciones.
• El Decreto Nº 7.369/2011” Por el cual se aprueba el Reglamento General de la Ley Nº 4.017/2010 de
validez jurídica de la firma electrónica, la firma digital, los mensajes de datos y el expediente
electrónico”.
• El Decreto Nº 1.165/2014 “Por el cual se aprueba el reglamento de la Ley Nº 4.868 del 26 de febrero
de 2013 de Comercio Electrónico”.
• El Decreto Nº 7.795/2017 “Por el cual se crea el Sistema Integrado de Facturación Electrónica
Nacional”.
septiembre de 2019 20

--- PAGE 22 / 217 ---

• La Resolución Nº 124/2018 “Por la cual se designa a las empresas participantes del plan piloto de
implementación del sistema integrado de facturación electrónica nacional (SIFEN)”.
• La Resolución General Reglamentaria Nº 05/2018 “Por la cual se reglamenta el Sistema de Facturación
Electrónica Nacional”.
• La Resolución General Reglamentaria Futura, para la etapa de voluntariedad.
4.3. Validez jurídica e incidencia tributaria de los documentos tributarios electrónicos
Para efectos del MT se debe considerar lo manifestado el artículo 32 de La Ley N° 4.868/2013 “Comercio
Electrónico”, el cual define a la factura electrónica como el comprobante de pago que deberán emitir los
proveedores de bienes y servicios por vía electrónica a distancia a quienes realicen transacciones comerciales
con ellos.
Por otra parte, la referida Ley en su artículo 33, dispone que la factura electrónica emitida por los proveedores
de bienes y servicios tendrá la misma validez contable y tributaria que la factura convencional, siempre que
cumplan con las normas tributarias y sus disposiciones reglamentarias.
En ese sentido, el Decreto N° 7.795/2017, por el cual se crea el SIFEN, en su artículo 2° define al documento
tributario electrónico como el documento emitido por el facturador electrónico con firma digital que ha sido
validado formalmente por la Administración Tributaria y que sirve para respaldar el débito y el crédito fiscal
del Impuesto al Valor Agregado, así como las ventas de bienes y servicios, los costos y los gastos en los
Impuestos a la renta.
Lo anterior significa en el contexto del presente MT, que los Documentos Electrónicos (DE) definidos en el
glosario y condicionados por el estándar del formato electrónico XML descripto en la sección 7.2, una vez
firmados digitalmente conforme lo mencionado en la sección 7.7, y efectuado el proceso de validación por
parte de la Administración Tributaria, adquieren naturaleza Documentos Tributarios Electrónicos (DTE) con
validez jurídica, fuerza probatoria e incidencia tributaria en las mismas condiciones que los comprobantes
físicos o convencionales autorizados por la Subsecretaría de Estado de Tributación.
El proceso se encuentra soportado en el conjunto de validaciones definidas en el capítulo 12; en tal sentido,
si un formato electrónico XML reúne las condiciones y requisitos formales y tecnológicos establecidos, se da
por superado el proceso de validación y se otorga la aprobación de uso del DTE.
Esto no implica que la Administración Tributaria se pronuncie sobre la veracidad de la operación comercial
documentada en el DTE, ni limita o excluye las facultades de fiscalización que posea sobre la misma.
septiembre de 2019 21

--- PAGE 23 / 217 ---

5. Documentos Tributarios Electrónicos
Los documentos electrónicos previstos por SIFEN para la presente versión, son los siguientes:
5.1. Comprobantes de ventas electrónicos:
• Factura Electrónica
• Autofactura Electrónica
5.2. Documentos complementarios electrónicos:
• Nota de Crédito Electrónica.
• Nota de Débito Electrónica.
5.3. Nota de Remisión Electrónica
Conforme lo establecido en el Decreto 7.795/2017 y sus reglamentaciones, lo anterior no implica que la
Administración Tributaria pueda implementar de manera gradual la utilización de otros DE, que por su
naturaleza requieran un tratamiento similar de operación electrónica, los cuales se introducirán en versiones
posteriores del presente MT.
septiembre de 2019 22

--- PAGE 24 / 217 ---

6. Modelo Operativo
6.1. Descriptores del modelo operativo de SIFEN
6.1.1. Archivo electrónico
El SIFEN define el archivo electrónico basado en el lenguaje XML como la representación electrónica de una
factura o los documentos establecidos en el capítulo 5 del presente MT. Del mismo modo, el archivo
electrónico en el contexto de la Ley 4.017/2010 tiene naturaleza de mensaje de datos y como tal, si contiene
una firma digital válida tiene admisibilidad y fuerza probatoria.
6.1.2. Aprobación del DTE
Para efectos de que el receptor, de un DE firmado digitalmente por un facturador electrónico, pueda asegurar
que el mismo tiene validez, el modelo operativo de SIFEN ha definido que este documento debe ser objeto de
unas validaciones (de conexión, técnicas, y de negocio) sobre el formato electrónico de cada uno de los DE
transmitidos, cuya aprobación de uso tendrá efectos tributarios sobre los contribuyentes involucrados en la
operación comercial al establecer su ingreso o no al SIFEN.
En un archivo XML estructurado conforme el Schema XML 4: ProtProcesDE_v150.xsd (protocolo de
procesamiento del DE), existen campos que definen que ha superado satisfactoriamente las validaciones
definidas para el efecto en el presente MT y, por tanto, ha sido aprobado como DTE. Ver gráfica Nº 04.
Gráfica Nº 04: Secuencia de acciones tecnológicas SIFEN
La obtención del resultado satisfactorio de las validaciones y en consecuencia la naturaleza de DTE
(Aprobación) no implican que la SET, como Administración Tributaria, pueda establecer la veracidad de la
operación comercial documentada en el DTE, en consecuencia, no limita ni excluye las facultades de
fiscalización de esta.
septiembre de 2019 23

--- PAGE 25 / 217 ---

6.2. Plazo de transmisión del DE a la SET
La transmisión del DE firmado digitalmente contempla un plazo de hasta 72 horas posteriores a la firma digital
del DE de la operación comercial. El modelo operativo tiene previsto para el futuro, dependiendo de la
naturaleza de las operaciones, empresas, sectores y/o gremios en particular, y con base en unos criterios
propios de la SET, determinados contribuyentes transmitan estos DE en plazos menores a las 72 horas.
El plazo de transmisión del DE de hasta 72 hs es un beneficio del modelo operativo para el contribuyente
emisor, para que pueda tener tranquilidad en su operación comercial y disminuir la necesidad del uso de
contingencia por problemas de infraestructura de Internet, de energía eléctrica o de disponibilidad de SIFEN.
Para la SET, en SIFEN, el tiempo de respuesta de validación de un DTE está establecido, como máximo de 1
(un) minuto, con objetivo de llegar, en el futuro, en tiempo de procesamiento menor a 2 (dos) segundos por
DTE.
Por lo tanto, por decisión de las empresas o industrias se podrá optar por la validación y aprobación previa, la
cual implica que SIFEN realice las validaciones y se obtenga el protocolo de aprobación del DTE, de manera
previa o posterior, a la entrega del documento al receptor por parte del emisor.
Adicionalmente, como un descriptor diferenciador entre el modelo operativo de validación posterior y previa,
se encuentra que para el primero se permite la generación de la representación gráfica (KuDE) antes que se
obtenga la correspondiente aprobación de uso. La misma puede ser utilizada en caso de venta a un receptor
no electrónico contribuyente de IVA o renta (este se obliga a realizar la consulta conforme a lo mencionado
en la sección 6.6 del presente MT), al consumidor final y para las mercaderías en su traslado físico.
Es importante mencionar, que el KuDE es un documento tributario auxiliar que expresa de manera simplificada
una transacción que ha sido respaldada por un DE, y como tal no es íntegramente el Documento Tributario
Electrónico, por cuanto su naturaleza es simplificada (contiene sólo algunos campos representativos del DTE)
y su validez jurídica se encuentra condicionada a la aprobación por parte de la SET. Situación en la cual el
receptor se obliga a consultar y/o comprobar la existencia del DTE en el SIFEN, tomando en consideración
algunos campos presentes en el cuerpo del KuDE como criterios de consulta.
6.2.1. Plazos SIFEN
Conforme a las bases y condiciones estructurales del Modelo del Sistema Integrado de Facturación Electrónica
Nacional (SIFEN), para el correcto cumplimiento tributario conforme a la potestad otorgada mediante el
Decreto N° 7.795/2017 y sus reglamentaciones, partiendo de la regla general, se han establecido plazos
diferenciados, de cara a las situaciones de contingencias, eventos, emisión de determinados DE y
comunicaciones, presentes en el proceso de transmisión, de la siguiente manera:
CASOS PLAZOS OBSERVACION
Regla general: se considera transmisión
normal de los DE al envío de aquellos
Transmisión normal de los DE Hasta 72 horas (regla general) documentos cuya fecha y hora de
transmisión no supera las 72 horas en
relación con la fecha y hora de la firma
digital de los mismos. Y que adicionalmente
septiembre de 2019 24

--- PAGE 26 / 217 ---

CASOS PLAZOS OBSERVACION
cumpla con una de las siguientes
condiciones:
• Que la diferencia entre la fecha y
hora de emisión (anterior) y la fecha y hora
de transmisión al SIFEN no sea superior a
120 horas (5 días).
• Que la diferencia entre la fecha y
hora de emisión (posterior) y la fecha y
hora de transmisión al SIFEN no sea
superior a 120 horas (5 días)
Se considera como transmisión
extemporánea de los DE al envío de
Transmisión extemporánea de Según situación de aquellos documentos que se encuentren en
los DE extemporaneidad situación contraria a la Transmisión normal
de los DE, a los cuales se les aplicará las
sanciones que correspondan
Se considera situación de rechazo de los
DE por transmisión extemporánea en las
siguientes situaciones:
* Cuando la diferencia entre la fecha de
Rechazo de los DE por transmisión y la fecha de emisión del DE,
720 horas (30 días)
transmisión extemporánea sea mayor a 720 horas (30 días)
*Cuando la diferencia entre la fecha de
emisión y la fecha de transmisión del DE
sea mayor a 120 horas (5 días)
En caso de rechazo de los DE por
transmisión extemporánea y para efectos
Trámite administrativo para de obtener su normalización (aprobación
extemporánea) en el SIFEN, los
normalizar DE rechazados por Mayor a 720 horas (30 días)
facturadores electrónicos, deberán iniciar
extemporaneidad
un trámite administrativo sin perjuicio de la
aplicación de las sanciones que
correspondan
Para efectos del registro del evento de
cancelación, necesariamente el DTE debe
Evento de cancelación de una existir en el SIFEN.
Hasta 48 horas (2 días)
FE El cómputo del plazo será contado a partir
de la aprobación del DE por parte de la SET
(fecha y hora SIFEN)
Para efectos del registro del evento de
cancelación, necesariamente el DTE
Eventos de cancelación de DTE Hasta 168 horas (distinto a FE) debe existir en el SIFEN.
distintos a FE (7 días) El cómputo del plazo será contado a partir
de la aprobación del DE por parte de la SET
(fecha y hora SIFEN)
Plazo que empieza a correr a partir del
Inutilización de la numeración
Hasta 360 horas (15 días) siguiente mes del consumo de la
de un DE
numeración del timbrado
Eventos del Receptor:
Notificación de Recepción
El plazo se computa desde la fecha de
DE/DTE, Conformidad, Hasta 1080 horas (45 días)
emisión del DE/DTE
Disconformidad,
Desconocimiento DE/DTE
septiembre de 2019 25

--- PAGE 27 / 217 ---

CASOS PLAZOS OBSERVACION
Corrección Evento del
El plazo se computa desde la fecha de
Receptor: Notificación de
registro del primer evento sobre un DTE
Recepción DE/DTE, Hasta 360 horas (15 días)
(Conformidad o Disconformidad o
Conformidad, Disconformidad,
Desconocimiento)
Desconocimiento DE/DTE
Obs: El cómputo de los plazos fue establecido en horas corridas.
6.3. Relación directa con los contribuyentes
El modelo operativo de SIFEN entiende que la interacción de la SET con los facturadores electrónicos es de
manera directa y sin necesidad de intermediación obligatoria de actor diferente. Quiere decir esto que, a
discreción y decisión de los contribuyentes, estos podrán acudir a servicios de proveedores tecnológicos,
reiterando que en todo caso la relación es directamente con los contribuyentes.
6.4. Entrega del DE al receptor
Como regla general, la entrega del DE por parte del emisor al receptor, en el modelo de validación y aprobación
del DE, se da de manera previa, y este último se obliga a consultar a posteriori, en los servicios de consulta
disponibles por SIFEN, que el DTE (luego de aprobado el DE) se encuentre conforme la operación comercial
realizada.
“Es importante remarcar que, al momento de la generación, emisión y antes de la entrega de un Documento
Electrónico (DE) al receptor, el referido documento debe estar firmado digitalmente. Carecerán de total
validez aquellos documentos electrónicos que no lleven la firma digital y que no fueron validados y
aprobados por la Administración Tributaria”.
Entre posibles alternativas de envío del DE del emisor al receptor, propio del ámbito comercial entre las partes,
se tienen las siguientes:
• Descarga por el receptor en página web expuesta por el emisor.
• Archivo adjunto transmitido por correo electrónico o aplicaciones.
• Archivo adjunto transmitido por aplicativo de mensajería electrónica de datos.
6.5. Rechazo del DE en el modelo de aprobación posterior
En el caso de que el DE enviado a SIFEN no supere las validaciones previstas para otorgar su aprobación, y su
ajuste para ser validado, no implique cambios que alteren la construcción del Código de Control (CDC), se
podrá reutilizar el mismo CDC, descrito en la sección 10.1, del DE rechazado (esto con el objeto de permitir
que el DE con aprobado (DTE) pueda ser consultado por medio del QR generado en el KuDE entregado al
receptor en el momento de la operación comercial), y someter nuevamente a validación. El emisor debe
realizar el mismo procedimiento hasta lograr la aprobación, cuantas veces sea necesario. Esto sin prejuicio del
incumplimiento de los términos y condiciones en la transmisión de los DE y la consecuente aplicación del
régimen sancionatorio por la entrega extemporánea de los mismos.
septiembre de 2019 26

--- PAGE 28 / 217 ---

Para aquellos casos en los que se introduzcan cambios que alteren la conformación del CDC, el emisor deberá
inutilizar el número de comprobante previamente generado y emitir uno nuevo, lo cual igualmente supone su
envío al receptor o comprador.
6.6. Verificación de la existencia del DTE por parte del receptor
En el modelo de aprobación posterior, el receptor de los DE, con el objeto de ejercer sus derechos tributarios
(como respaldo documental de sus Declaraciones Juradas), se obliga a verificar la existencia y coincidencia de
la Representación Gráfica del DTE (KuDE) con el DTE almacenado en el SIFEN.
La verificación podrá realizarse por servicio web de consulta CDC, o mediante consulta en la página web que
para sus efectos disponga la SET a través de SIFEN, a partir del código QR existente incorporado en el KuDE o
por el llenado del CDC en la página. Al respecto, debe verificar en específico que:
• El DE fue transmitido y obtuvo la aprobación como DTE, y
• Que la información presente en el KuDE coincide plenamente con la información del DTE consultado.
septiembre de 2019 27

--- PAGE 29 / 217 ---

7. Características tecnológicas del formato
En este capítulo se abordan las características tecnológicas de la facturación electrónica, que involucran la
utilización de certificados digitales, el lenguaje utilizado para el intercambio de información, XML o lenguaje
de marcado o extensible1, juntamente con los Servicios Web, esenciales para el intercambio seguro de los DE.
También se identifican los Servicios Web contemplados en el modelo conceptual de comunicación, se
establecen las definiciones acerca de la utilización del XML, así como los estándares de comunicación entre el
SIFEN y los sistemas de los contribuyentes.
7.1. Modelo conceptual de comunicación
El SIFEN, disponibilizará los siguientes Servicios Web:
• Recepción de DE
• Recepción lotes de DE
• Consulta resultado lote
• Recepción evento
• Consulta DE
• Consulta RUC (por demanda)
• Consulta DE a entidades u organismos externos autorizados (a futuro)
Cada servicio se encuentra respaldado por un Servicio Web específico. El modelo de comunicación e
interoperabilidad siempre iniciará en el sistema del contribuyente (sea de manera directa o prestado por un
tercero), por medio del consumo del servicio correspondiente. Ver gráfica Nº 05
FLUJO DE COMUNICACIÓN
Contribuyente SET
https
Cliente Sistema de FE
Flujo de la Servicios
Comunicación Sincrónicos
SIFEN
Servicios
Transacciones
Asincrónicos
Facturas
Sistema de FE
Facturas
Electrónicas
Gráfica Nº 05: Flujo de comunicación
1 https://es.wikipedia.org/wiki/Extensible_Markup_Language
septiembre de 2019 28

--- PAGE 30 / 217 ---

Existen dos tipos de procesamiento de Servicios Web:
Síncronos: Se consideran a aquellos en los cuales el procesamiento y respuesta del servicio se realizan en la
misma conexión de consumo. Ver gráfica Nº 06.
Sincrónico
Establececonexión Recibemensajedesolicitud
1 Envía mensaje de 2 Direcciona al sistema de
solicitud recepciónyprocesamiento
Sistema de Web Service SIFEN
Información FE 1 a 1 Sistema de Recepción y
Contribuyente Procesamiento
5
R Te e r c m ib in e a R c e o s n p e u x e ió st n a R D C e i o re c n i t c b r c i e b io u m n y a e e n n s te a a j l ec S on ist r e e m su a ltad d o el 4 Dev R ue e l a ve liz a m p s r j o re ce su s l a ta m d ie o n a to l WS 3
Gráfica Nº 06: WS Sincrónico
Asíncronos: Son aquellos en los cuales el resultado del procesamiento del servicio requerido no es entregado
en la misma conexión de la solicitud de consumo (Ver gráfica Nº 07). Consta de un mensaje y un número de
lote descriptos a continuación:
• Un mensaje con un recibo (ticket) que confirma que el archivo remitido ha superado las primeras
validaciones y se ha recepcionado el lote, y
• El número de lote, incluido en esta respuesta, con el cual el cliente (sistema del contribuyente) podrá
consultar el resultado del procesamiento, consumiendo el Web Service correspondiente, en otra
conexión.
Gráfica Nº 07: WS Asincrónico
septiembre de 2019 29

--- PAGE 31 / 217 ---

7.2. Estándar del formato XML
El formato de documentos y protocolos de servicios, utilizan el lenguaje de marcas expansible (XML –
Expansible Markup Language). La definición de cada archivo XML sigue un estándar denominado “Schema
XML”, o lenguaje de esquema, utilizado para describir la estructura y restricciones de los documentos XML2 .
Esta estructura reside en un archivo con extensión “.xsd” (XML Schema Definition), el que establece qué
elementos contendrá el documento, como están organizados, cuáles son los atributos y de qué tipo deben ser
estos elementos.
7.2.1. Estándar de codificación
La especificación de los documentos XML es el estándar 150, con la codificación de caracteres UTF-8, por lo
cual todos los documentos se inician con la declaración:
<?xml version="150" encoding="UTF-8"?> (*)
Para mejor comprensión, se puede utilizar el siguiente enlace:
http://www.w3.org/TR/REC-xml
Cada archivo XML, debe poseer solo una declaración (*), para el caso de los envíos de lotes, la estructura
completa del archivo debe contener solo una declaración.
7.2.2. Declaración namespace
El comúnmente denominado “Espacio de Nombres”3 en XML, es utilizado para proporcionar elementos y
atributos con nombre único en un documento XML.
Este espacio de nombres se declara utilizando el atributo xmlns, el cual estará incluido en el elemento raíz del
documento como, por ejemplo:
<rDE
xmlns=”http://ekuatia.set.gov.py/sifen/xsd”
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd siRecepDE_v150.xsd">
Namespace utilizado en Eventos:
2 https://es.wikipedia.org/wiki/XML_Schema
(*) <?xml version="100" encoding="UTF-8" ?>
3 https://es.wikipedia.org/wiki/Espacio_de_nombres_XML
www.w3.org/TR/REC-xml
septiembre de 2019 30

--- PAGE 32 / 217 ---

<rEnviEventoDe
xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dEvReg>
<gGroupGesEve>
<rGesEve
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd
siRecepEvento_v150.xsd"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<rEve Id="123">
</rEve>
</rGesEve>
</gGroupGesEve>
</dEvReg>
</rEnviEventoDe>
Cabe aclarar que no se podrá utilizar:
• Namespace distintos a los definidos en el presente documento
• Prefijos de namespace
Cada documento XML tendrá su namespace individual en su correspondiente elemento raíz.
7.2.2.1. Particularidad de la firma digital
La declaración namespace de la firma digital debe realizarse en la etiqueta <Signature>, conforme con el
siguiente ejemplo:
<rDE
xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd">
<dVerFor>150</dVerFor>
<DE Id="0144444401700100100145282201170125158732260988">
</DE>
<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
</Signature>
</rDE>
7.2.2.2. Particularidad del envío de lote
En el caso de envío de lote, cada DE debe contener la declaración de su namespace individual, conforme el
ejemplo:
septiembre de 2019 31

--- PAGE 33 / 217 ---

<rDE
xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi=http://www.w3.org/2001/XMLSchema-instance
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd">
<dVerFor>150</dVerFor>
<DE Id="0144444401700100100145282201170125158732260988">
...
</DE>
<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
...
</Signature>
</rDE>
<rDE
xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi=http://www.w3.org/2001/XMLSchema-instance
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd">
<dVerFor>150</dVerFor>
<DE Id="0144444401700100100145282201170125158732260988">
...
</DE>
<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
...
</Signature>
</rDE>
7.2.3. Convenciones referenciadas en tablas
La Gráfica Nº 08 muestra la relación entre los elementos del archivo XML
Gráfica N° 08: Relación elementos XML
La definición de las columnas de las tablas, conforme los esquemas relacionados a los archivos XML, se expone
a continuación en la Tabla A:
Tabla A – Convenciones Utilizadas en la Tablas de Definición de los Formatos XML
Título Descripción
Grupo Conjunto de campos
ID Identificación del campo para fines de referencia
Nombre del campo. La primera letra indica:
Campo
c: código integrante de una tabla existente en el Capítulo 16
septiembre de 2019 32

--- PAGE 34 / 217 ---

Tabla A – Convenciones Utilizadas en la Tablas de Definición de los Formatos XML
Título Descripción
i: código integrante de una tabla que se encuentra en la columna “Observaciones”
d: nombre de un campo común
g: nombre de un grupo
r: raíz de XML
Descripción Descripción del campo y su significado
Referencia al ID del campo de grupo que contiene este campo específico (campo
Nodo Padre
padre)
Tipo de Dato Tipo de dato (ver Tabla B)
Longitud Tamaño del campo (ver Tabla C)
Ocurrencias, en el formato m-n, en el cual
Ocurrencia
m: número mínimo de veces que el campo debe aparecer en el grupo
n: número máximo de veces que el campo puede aparecer en el grupo
Observaciones importantes sobre el campo, incluyendo listas de valores posibles,
Observaciones
validaciones relevantes entre otras.
Versión que el campo fue introducido en el formato, o versión en la cual ha sido
Versión
modificado por la última vez
Los tipos de campos de los archivos XML tienen su contenido descrito en la Tabla B.
Tabla B – Tipos de Datos en los Archivos XML
Tipo Descripción
XML Documento XML, descripto en un schema contenido en esta ficha técnica
G Grupo de elementos y/o grupos de elementos
“Choice Group”, elemento que excluye la ocurrencia de otro Choice Group, con el
CG
mismo padre
“Choice Element”, elemento que excluye la ocurrencia de otro Choice Element con
el mismo padre
CE • Por ejemplo los varios tipos de RUC
El tipo de elemento aparece luego al lado
• Por ejemplo, “CEA” indica un Choice Element alfanumérico
A Alfanumérico
N Numérico: Vea los diversos formatos en la Tabla C
Fecha: Los campos de fecha, según corresponda, deberán contener fecha y hora en
el formato: AAAA-MM-DDThh:mm:ss o AAAA-MM-DD
F • Por ejemplo, para expresar 2:23 PM de 01 de febrero de 2018: 2018-02-01-
14:23:00
Por ejemplo, para expresar 01 de febrero de 2018: 2018-02-01
B Binario en Base64 para envío de lote
septiembre de 2019 33

--- PAGE 35 / 217 ---

Los tamaños de campo utilizados en los archivos XML tienen su contenido descripto en la Tabla C. En el caso
de campos con tamaño exacto los espacios no utilizados deben ser llenados con ceros no significativos (a la
izquierda del campo).
Tabla C: Tamaños de campos
Título Descripción
Tamaño exacto del campo
X
• ej.: 2
Tamaño mínimo x, máximo y
x-y
• ej.: 0-10 (es posible expresar ningún valor, porque se permite el tamaño 0)
Tamaño exacto del campo x, con n cifras decimales exactamente
Xpn
• ej.: 22p4
Tamaño exacto del campo x, con cifras decimales entre n y m
xp(n-m)
• ej.: 22p(0-7)
Tamaño mínimo x, máximo y, con cifras decimales entre n y m
(x-y)p(n-m) • ej.: 1-11p(0-6) (es obligatorio expresar algún valor, porque no se permite el tamaño
0, pero la parte decimal es opcional)
Valores El campo deberá ser informado con tamaño exacto de una de las opciones listadas
separados • ej.: 1, 3, 5, 8. Significa que se debe informar el campo con uno de estos cuatro
por comas tamaños fijos
En la Tabla D se ejemplifica la manera de informar los formatos numéricos.
Tabla D: Formatos numéricos
Formato Para Informar Llenar campo con
1.105,13 1105.13
1.105,137 1105.137
0-11p0-6 1.105 1105
0 0
para no informar cantidad No incluir
1.105 1105
0-11 0 0
para no informar cantidad No incluir
1.105 1105
1-11 0 0
para no informar cantidad no es posible
NOTA: De manera a simplificar y utilizar toda la potencia del lenguaje, el punto (.) se utilizará como separador de decimales, tal y como lo muestra la
Tabla D
7.2.4. Recomendaciones mejores prácticas de generación del archivo
Como buenas prácticas al momento de la generación de los DE, tener precaución de NO incorporar:
• Espacios en blanco en el inicio o en el final de campos numéricos y alfanuméricos.
• Comentarios, anotaciones y documentaciones, léase las etiquetas annotation y documentation.
septiembre de 2019 34

--- PAGE 36 / 217 ---

• Caracteres de formato de archivo, como line-feed, carriage return, tab, espacios entre etiquetas.
• Prefijos en el namespace de las etiquetas.
• No incluir etiquetas de campos que no contengan valor, sean estas numéricas, que contienen ceros,
vacíos o blancos para campos del tipo alfanumérico. Están excluidos de esta regla todos aquellos
campos identificados como obligatorios en los distintos formatos de archivo XML, la obligatoriedad
de los mismos será plenamente detallada.
• No utilizar valores negativos
• El nombre de los campos es sensible a minúsculas y mayúsculas, por lo que deben ser comunicados
de la misma forma en la que se visualiza en el presente manual técnico.
• Ej: el grupo gOpeDE, es diferente a GopeDE, a gopede y a cualquier otra combinación distinta a la
inicial.
7.3. Contenedor de documento electrónico
Un contenedor del DE es un archivo XML que contiene el DE, con su validación de recepción, por parte del
SIFEN, así como cualquier evento, registrado que lo involucre.
La estructura está definida en la sección 9.4, correspondiente al SW “SiConsDE”.
7.4. Estándar de comunicación
La comunicación entre los contribuyentes y la SET está basada en los Servicios Web disponibles por el SIFEN.
El medio para establecer esta comunicación es la Internet, apoyado en la utilización del protocolo de seguridad
TLS versión 1.2, con autenticación mutua. Esto garantiza una comunicación segura, considerando la
identificación del cliente consumidor del servicio por medio de certificados digitales.
El modelo de comunicación sigue el estándar de Servicios Web definido por el WS-I4 BasicProfile5.
El intercambio de documentos o mensajes entre el SIFEN y el sistema de los contribuyentes, utiliza el estándar
SOAP, versión 1.26, con intercambio de mensajes XML basados en Style/Encoding: Document/Literal.
La llamada o Request a cualquiera de los Servicios Web del SIFEN, es realizada con el envío de un mensaje XML
incluido en el campo soap:Body.
Request de ejemplo utilizando SOAP:
4Web Services Interoperability Organization (WS-I, http://www.ws-i.org/about/Default.aspx)
5http://www.ws-i.org/Profiles/BasicProfile-1.0-2004-04-16.html
6Web Services Interoperability Organization (WS-I, http://www.ws-i.org/about/Default.aspx)
6http://www.ws-i.org/Profiles/BasicProfile-1.0-2004-04-16.html
6https://www.w3.org/TR/soap12/
septiembre de 2019 35

--- PAGE 37 / 217 ---

<soap:Envelope
xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<soap:Header/>
<soap:body>
<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">
<dId>10000011111111</dId>
<xDE>
<rDE
xmlns="http://ekuatia.set.gov.py/sifen/xsd"
xmlns:xsi=http://www.w3.org/2001/XMLSchema-instance
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd/siR
ecepDE_v150.xsd">
...
</rDE>
</xDE>
</rEnviDe>
</soap:body>
</soap:Envelope>
Response de ejemplo utilizando SOAP:
<env:Envelope
xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
<env:Header/>
<env:body>
<ns2:rRetEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
<ns2:rProtDe>
<ns2:dId>00000000000000000000000000000000000000000000</ns2:dId>
<ns2:dFecProc>2019-06-03T12:00:00</ns2:dFecProc>
<ns2:dDigVal>0000000000000000000000000000</ns2:dDigVal>
<ns2:gResProc>
<ns2:dEstRes>Rechazado</ns2:dEstRes>
<ns2:dProtAut>0000000000</ns2:dProtAut>
<ns2:dCodRes>0160</ns2:dCodRes>
<ns2:dMsgRes>XML malformado</ns2:dMsgRes>
</ns2:gResProc>
</ns2:rProtDe>
</ns2:rRetEnviDe>
</env:body>
</soap:Envelope>
7.5. Estándar de certificado digital
El SIFEN utiliza un certificado digital, emitido por cualquiera de los PSC7, habilitados por el Ministerio de
Industria y Comercio8 en su carácter de Administrador de la Autoridad Certificadora Raíz del Paraguay9 y ente
regulador. El certificado será utilizado para firmar digitalmente y para autenticarse en los servicios del SIFEN.
Puede ser del TIPO F110 o F211 de persona física o jurídica. En el caso de optar por el certificado de persona
jurídica, el RUC del contribuyente estará contenido en el campo SerialNumber. En el caso de optar por el
certificado de persona física, éste debe ser de un personal dependiente del contribuyente y el certificado debe
7 (PSC) Prestador de Servicios de Certificación https://www.acraiz.gov.py/html/Certif_1PrestaServ.html
8 www.acraiz.gov.py
9 (AA) Según la Ley N°4017 de Firma Digital es el Ministerio de Industria y Comercio
10 Tipo F1: corresponde a Certificado de Firma Digital por Software
11 Tipo F2: corresponde a Certificado de Firma Digital por Hardware
septiembre de 2019 36

--- PAGE 38 / 217 ---

contar obligatoriamente con el nombre y el RUC de la entidad en el que presta servicio el titular del certificado.
En este último caso el RUC del contribuyente estará contenido en el campo SubjectAlternativeName.
Estos certificados digitales serán exigidos por la SET en los siguientes momentos:
• Para firma de mensajes de datos: Se refiere al archivo de documento electrónico, registro de evento y/o
cualquier otro archivo XML admisible por el SIFEN, que requiera ser firmado digitalmente. El certificado
digital debe contener el RUC del contribuyente emisor y la clave prevista para la función de firma digital.
• Para establecimiento de conexiones y autenticaciones mutuas: (Comunicación entre el servidor del
contribuyente y el servidor del SIFEN). Para este efecto, el certificado digital debe contener el RUC del
contribuyente emisor y propietario responsable por la trasmisión del mensaje, con la extensión Extended
Key Usage con el permiso clientAuth.
Aclaración:
• Certificado de persona jurídica: el RUC del contribuyente debe estar informado en el:
o Campo X509 V3: Subject
o Nombre: “Serial Number” OID: 2.5.4.5
• Certificado de persona física: el RUC del contribuyente emisor debe estar informado en el:
o Campo X509 V3: SubjectAlternativeName
o Nombre: “SerialNumber” OID: 2.5.4.5
Para ambos casos, la información del RUC debe informarse de la siguiente manera:
RUCXXXXXXXXX-X -> es decir, se escribe la palabra RUC con mayúsculas, seguido del número de RUC
correspondiente con guion y el dígito verificador, sin ningún espacio en toda la cadena.
7.6. Estándar de firma digital
Los archivos enviados al SIFEN son documentos electrónicos construidos en lenguaje XML y deben estar
firmados con la firma digital amparada con el certificado correspondiente al RUC del contribuyente emisor del
documento.
Existen elementos que se encuentran presentes en el certificado digital del emisor de forma natural, lo que
implica innecesaria su exposición en la estructura XML. En este contexto los DE firmados digitalmente no
deben contener los siguientes elementos:
<X509SubjectName>
<X509IssuerSerial>
<X509IssuerName>
<X509SKI>
De igual manera se debe evitar el uso de los siguientes elementos, ya que esta información será obtenida a
partir del certificado digital del emisor.
septiembre de 2019 37

--- PAGE 39 / 217 ---

<KeyValue>
<RSAKeyValue>
<Modulus>
<Exponent>
Los DE utilizan el subconjunto del estándar de firma digital definido según W3C,
http://www.w3.org/TR/xmldsig-core/, conforme a lo expuesto en el Schema XML1.
Cada Documento Electrónico deberá ser firmado por el contribuyente emisor abarcando el grupo de
información A001, con sus respectivos subgrupos, identificado por el Atributo “Id” cuyo valor será el CDC
(Código de Control).
Véase la Tabla de Formato de Campos de un Documento Electrónico (DE). El mismo literal único (CDC)
precedido por el caracter “#” deberá ser informado en el atributo URI del tag Reference.
Schema XML 1: xmldsig-core-schema- v150.xsd (Estándar de la Firma Digital)
Descrip Nodo Ocurren
ID Campo Observaciones
ción Padre cia
XS01 Signature - - Raíz
XS02 SinnedInfo G XS01 1-1 Grupo de información de la firma
CanonicalizationMetho
XS03 G XS02 1-1 Grupo del método canónico
d
Atributo Algorithm de CanonicalizationMethod
XS04 Algorithm A XS03 1-1 https://www.w3.org/TR/2001/REC-xml-c14n-
20010315
XS05 SignatureMethod G XS02 1-1 Grupo del método de firma
Atributo Algorithm de SignatureMethod:
Sha256RSA
XS06 Algorithm A XS05 1-1
http://www.w3.org/2001/04/xmldsig-more#rsa-
sha256
XS07 Reference G XS02 1-1 Grupo Reference
Atributo del Tag Reference que identifica los datos
XS08 URI A XS07 1-1
que se están firmandos
XS10 Transforms G XS07 1-1 Grupo Algorithm Transforms
XS12 Transforms G XS10 2-2 Grupo del Transform
Atributos válidos Algorithm de Transform:
https://www.w3.org/TR/xmldsig-core1/#sec-
XS13 Algorithm A XS12 2-2 EnvelopedSignature
http://www.w3.org/2001/10/xml-exc-c14n#
XS14 XPath E XS12 0-n XPath
XS15 DigestMethod G XS07 1-1 Grupo del método del DigestMethod
Atributo del algoritmo utilizado para el
DigestMethod:
XS16 Algortihm A XS15 1-1
https://www.w3.org/TR/2002/REC-xmlenc-core-
20021210/Overview.html#sha256
XS17 DigestValue E XS07 1 Digest Value (HASH SHA256)
XS18 SignatureValue G XS01 1-1 Grupo del Signature Value
XS19 KeyInfo G XS01 1-1 Grupo del KeyInfo
XS20 X509Data G XS19 1-1 Grupo X509
XS21 X509Certificate E XS20 1-1 Certificado Digital X509.v3
septiembre de 2019 38

--- PAGE 40 / 217 ---

Significado de la columna Descripción del Schema XML 1:
• G: Grupo
• A: Algoritmo
• RC: Regla
• E: Elemento
Esta estructura se debe utilizar para todos los archivos firmados, utilizando el CDC, para el atributo Id
<rDE xmlns=http://ekuatia.set.gov.py/sifen/xsd
xmlns:xsi=http://www.w3.org/2001/XMLSchema-instance
xsi:schemaLocation="http://ekuatia.set.gov.py/sifen/xsd/siRecepDE_v150.xsd">
<dVerFor>150</dVerFor>
<DE Id="0144444401700100100145282201170125158732260988">
...
</DE>
<Signature xmlns="http://www.w3.org/2000/09/xmldsig#">
<SignedInfo>
<CanonicalizationMethod
Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
<SignatureMethod Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"/>
<Reference URI="#0144444401700100100145282201170125158732260988">
<Transforms>
<Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-
signature"/>
<Transform Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#"/>
</Transforms>
<DigestMethod Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"/>
<DigestValue>Nt2UmpjUHuu2DT6CJc2mtKhhqbq94LHSak1IsEOtuWk=
</DigestValue>
</Reference>
</SignedInfo>
<SignatureValue>DWN1my9sH4FI7ygPT3KF1ce...</SignatureValue>
<KeyInfo>
<X509Data>
<X509Certificate>MIIIxzCCBq+gAwIBAgITXAA...
</X509Certificate>
</X509Data>
</KeyInfo>
</Signature>
</rDE>
En el proceso de verificación de los certificados, el SIFEN se encargará de consultar la lista de certificados
revocados (LCR) al momento de la validación correspondiente, de manera que el contribuyente no necesitará
anexar esta lista al firmar el documento.
7.7. Especificaciones técnicas del estándar de certificado y firma digital
• Estándar de Firma: XML Digital Signature, se utiliza el formato Enveloped
http://www.w3.org/TR/xmldsig-core/
• Certificado Digital: Expedido por una de los PSC habilitados en la República del Paraguay, estándar
http://www.w3.org/2000/09/xmldsig#X509Data
https://www.acraiz.gov.py/html/Certif_1PrestaServ.html
septiembre de 2019 39

--- PAGE 41 / 217 ---

• Tamaño de la Clave Criptográfica: RSA 2048, para cifrado por software, para cifrado por hardware
pueden ser de RSA 2048 o RSA 4096.
• Función Criptográfica Asimétrica: RSA conforme a (https://www.w3.org/TR/2002/REC-xmlenc-core-
20021210/Overview.html#rsa-1_5 ).
• Función de “message digest”: SHA-2
https://www.w3.org/TR/2002/REC-xmlenc-core-20021210/Overview.html#sha256
• Codificación: Base64
https://www.w3.org/TR/xmldsig-core1/#sec-Base-64
• Transformaciones exigidas: Útil para canonizar el XML enviado, con el propósito de realizar la
validación correcta de la firma digital:
Enveloped, https://www.w3.org/TR/xmldsig-core1/#sec-EnvelopedSignature
C14N, http://www.w3.org/2001/10/xml-exc-c14n#
7.8. Procedimiento para la validación de la firma digital:
a) Extraer la clave pública del certificado digital,
b) Verificar el plazo de validez del certificado digital del emisor
c) Validar la cadena de confianza, identificando al PSC, así como la lista de certificados revocados de la
cadena
d) Verificar que el certificado digital utilizado es del contribuyente y no de una autoridad certificadora
e) Validar la integridad de las LCR utilizadas
f) Verificar el Plazo de validez de cada LCR (Effective Date y NextUpdate) en relación al momento de la
firma (campo fecha de la firma).
7.9. Síntesis de definiciones tecnológicas
La Tabla E resume los principales estándares de tecnología utilizados.
Tabla E: Estándares de tecnología utilizados
Característica Descripción
Web Services Estándar definido por WS-I Basic Profile 1.1
Medio lógico de comunicación Web Services disponibilizados por la SET
Medio físico de comunicación Internet
TLS versión 1.2, con autenticación mutua utilizando los Certificados
Protocolo de Internet
Digitales.
Estándar de intercambio de datos SOAP versión 1.2
Estándar de Mensaje XML en el Estándar Style/Encoding: Document/Literal.
ITU-T X.509 V.3 Information Technology Open Systems
Interconnection. The Directory: Public-key and attribute certificate
Estándar de Certificado Digital
frameworks. Emitido por un PSC habilitado por el MIC.
https://www.acraiz.gov.py/html/Certif_1PrestaServ.html
XML Digital Signature, Enveloped, con Certificado Digital X.509
Estándar de la Firma Digital versión 3, con clave privada de 2048 y estándares de criptografía
asimétrica RSA, RFC5639 y algoritmo SHA-256
Se validarán la integridad y la autoría, además la cadena de
Validación de la Firma Digital confianza, por medio de las LCR en relación al momento de la firma
(campo fecha de la firma).
Definidos según las mejores prácticas a la hora de armar un archivo
Estándares de utilización XML
XML
septiembre de 2019 40

--- PAGE 42 / 217 ---

7.10. Resumen de las Direcciones Electrónicas de los Servicios Web para Ambientes de Pruebas y
Producción
URL Ambiente
https://sifen.set.gov.py/de/ws/sync/recibe.wsdl?wsdl Producción
https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl Producción
https://sifen.set.gov.py/de/ws/eventos/evento.wsdl?wsdl Producción
https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl Producción
https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl Producción
https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl?wsdl Producción
https://sifen-test.set.gov.py/de/ws/sync/recibe.wsd?wsdl Test
https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl?wsdl Test
https://sifen-test.set.gov.py/de/ws/eventos/evento.wsdl?wsdl Test
https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl?wsdl Test
https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl?wsdl Test
https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl?wsdl Test
7.11. Servidor para sincronización externa de horario
Las direcciones para acceder a los servidores NTP para sincronización de horario son:
• aravo1.set.gov.py
• aravo2.set.gov.py
El acceso a los servicios, citados en los puntos 7.10 y 7.11, dependerá de la política de seguridad establecida
por la SET. Por lo que, podrá limitar y/o restringir la utilización de los servicios por contribuyente, por
direcciones IP u otros, de tal forma a asegurar la disponibilidad de los recursos según cada etapa del plan
general del SIFEN.
septiembre de 2019 41

--- PAGE 43 / 217 ---

8. Aspectos Tecnológicos de los Servicios Web del SIFEN
Los contribuyentes con naturaleza de emisores electrónicos realizarán el envío de sus DE, utilizando los
Servicios Web que el SIFEN pondrá a disposición de manera a operar máquina a máquina sin intervención del
usuario.
Para ello el sistema de los contribuyentes afectados, en adelante, clientes del servicio, deberán tener las
siguientes consideraciones:
• Poseer conexión a Internet de banda ancha.
• Para el envío de los DE deberán desarrollar el software cliente según lo enmarcado en el presente
documento, independientemente al lenguaje de programación utilizado.
• El lenguaje de intercambio de información utilizado será el XML.
• Para garantizar la comunicación segura, el software cliente deberá autenticarse ante el SIFEN
utilizando su certificado y firma digital.
El SIFEN dispondrá los siguientes servicios a ser consumidos por los clientes:
• Síncronos:
o Recepción DE
o Recepción evento
o Consulta DE
o Consulta RUC
o Consulta DE destinados (Futuro)
o Consulta DTE a entidades u organismos externos autorizados (a Futuro)
• Asíncronos:
o Recepción lote DE
o Consulta resultado lote
8.1. Servicio síncrono
La llamada (Request) del servidor del cliente a los servicios síncronos es procesado de forma inmediata por el
servidor del SIFEN y la respuesta (Response) se realiza en la misma conexión.
8.1.1. Flujo funcional:
a) El software cliente realiza la conexión enviando la solicitud (Request) al servicio del SIFEN.
b) El WS SIFEN recibe el Request y llama al software encargado del procesamiento del DE.
c) Éste, al culminar el proceso devuelve el resultado al WS SIFEN.
d) El WS SIFEN responde al cliente.
e) El software cliente, al obtener la respuesta, cierra la conexión.
septiembre de 2019 42

--- PAGE 44 / 217 ---

8.2. Servicio asíncrono
La llamada (Request) del servidor del cliente es procesada de la siguiente manera:
8.2.1. Secuencia del servicio asíncrono:
a) El Cliente realiza la conexión realizando un Request al WS SIFEN.
b) El WS SIFEN recibe la solicitud y responde con un mensaje de aprobación o rechazo, según las primeras
validaciones. Esta respuesta contiene:
a. Identificador de respuesta. (IdResp)
b. Situación (Aprobación o Rechazo).
c. Fecha y hora de recepción del mensaje.
d. Tiempo promedio de procesamiento, expresado en segundos.
c) El software cliente, al obtener el Response, cierra la conexión.
d) El procesamiento de los DE será realizado de manera posterior a esta conexión.
8.2.2. Tiempo promedio de procesamiento de un lote:
El tiempo de procesamiento en SIFEN para la validación de un DE es una información esencial del rendimiento
del sistema. Esta información está asociada directamente al procesamiento asincrónico de lotes de DE. En la
respuesta de procesamiento de un lote, una de las informaciones que se proporcionará será, justamente, el
tiempo promedio de procesamiento de un DE en los últimos 5 minutos.
Este tiempo promedio de procesamiento tendrá como unidad de medida milisegundos.
Para el cálculo del tiempo promedio de procesamiento se debe realizar la diferencia aritmética de tiempos de
procesamiento de los DE en los últimos 5 minutos, calculado como diferencia entre las fechas (considerando
día, mes, año, hora, minuto y segundo) de recepción de los lotes en SIFEN y sus fechas de procesamiento de
las respuestas de los lotes procesados (considerando día, mes, año, hora, minuto y segundo).
Este mismo tiempo promedio de procesamiento de DE estará disponible en el Portal e-Kuatia en el servicio de
semáforo de monitoreo de los WS.
Siempre que el tiempo calculado sea inferior a un segundo, la aplicación contestará como valor un segundo
de tiempo promedio.
Para los cálculos que arrojen cifras superiores a un segundo, se presentará:
• En los casos que los decimales sean inferiores a 500 ms, el valor entero se redondeará por debajo.
• En caso de que los decimales sean superiores a 500 ms, el valor entero se redondeará por encima.
Los contribuyentes (clientes) deberán considerar este promedio de tiempo, antes de consumir el servicio de
consulta de procesamiento y para la decisión del inicio del uso de la contingencia.
septiembre de 2019 43

--- PAGE 45 / 217 ---

8.3. Estándar de mensajes de los servicios del SIFEN
La solicitud de consumo de los servicios dispuestos por el SIFEN debe seguir el estándar:
• Área de datos: Esquema XML definido para cada WS.
8.4. Versión de los Schemas XML
Las modificaciones de los Schemas correspondientes a los servicios del SIFEN, pueden originarse como
necesidades técnicas, cambios normativos o de funcionalidad.
Estos cambios no serán aplicados de forma frecuente, considerando siempre el tiempo necesario para la
adecuación de los sistemas de los contribuyentes afectados.
Los mensajes recepcionados en una versión desactualizada serán rechazados especificando el error de versión.
Toda actualización de formato de los WS del SIFEN será correctamente respaldada por la actualización de su
correspondiente Schema.
8.4.1. Identificación de la versión de los Schemas XML
La versión del Schema de los DE es identificada en el nombre del archivo correspondiente, con el número
antecedido por los caracteres “_v”.
El nombre del Schema XML de la factura electrónica, versión 150 es: FE_v150.xsd
8.4.2. Liberación de versiones de los Schemas XML
Los Schemas utilizados por el SIFEN serán reglamentados y publicados en la dirección
“http://ekuatia.set.gov.py/sifen/xsd”.
Las actualizaciones de Schemas estarán publicadas en forma comprimida y contendrá el conjunto de Schemas
utilizados para la generación de los DE y consumo de WS, si correspondiera.
Este Schema tendrá la misma versión que el DE equivalente. Los archivos comprimidos serán nominados de la
siguiente manera “PS_FE_150.zip”, donde las primeras dos letras son constantes, las siguientes corresponden
al tipo de DE, seguido de la versión a la cual corresponde, en el ejemplo, versión 150.
Los archivos correspondientes a Schemas XML, se distinguen por la extensión .xsd
Según lo descripto, el archivo correspondiente al Schema XML de la recepción del DE de la versión 150 es:
SiRecepDE_v150.xsd
8.4.3. Paquete inicial de Schemas
Al momento de la publicación de la versión oficial del presente Manual Técnico, también se disponibilizará el
paquete de Schemas afectados inicialmente.
septiembre de 2019 44

--- PAGE 46 / 217 ---

9. Descripción de los Servicios Web del SIFEN
Ciertas validaciones son aplicadas igualitariamente a todos los DE y en todos los WS establecidos por el SIFEN,
según se identifican en el capítulo de validaciones del presente Manual Técnico. Estas validaciones son
empleadas en la secuencia que están dispuestas, así como, los procedimientos afectados.
De forma independiente son aplicadas las validaciones particulares, ya sea en los DE como en los WS.
9.1. WS recepción documento electrónico – siRecepDE
Función: Recibir un DE
Proceso: Sincrónico
Método: SiRecepDE
9.1.1. Definición del protocolo que consume este servicio
El protocolo de entrada para este servicio es la estructura XML que contiene un DE firmado, según el detalle
del siguiente cuadro:
Schema XML 2: siRecepDE_v150.xsd (WS Recepción DE)
Nodo
ID Campo Descripción Tipo Dato Longitud Ocu Observaciones
Padre
ASch01 rEnviDe Raíz - - - - Elemento raíz
Número secuencial
autoincremental, para
identificación del archivo
Identificador de enviado. La
ASch02 dId ASch01 N 1-15 1-1
control de envío responsabilidad de
generar y controlar este
número es exclusiva del
contribuyente.
Siguiendo las
XML del DE
ASch03 xDe ASch01 XML - 1-1 definiciones del formato
transmitido
del DE
9.1.2. Descripción del procesamiento
Servicio encargado de recibir un documento electrónico firmado digitalmente, en formato XML y construido
según el esquema detallado en este Manual Técnico.
Procesa las validaciones12 correspondientes y responde con un protocolo en XML, el resultado
correspondiente.
12 Las validaciones están detalladas en el capítulo 12 del presente Manual
septiembre de 2019 45

--- PAGE 47 / 217 ---

Este procedimiento se aplica concretamente sobre el contenido del campo ASch02 (campo XML del DE
transmitido).
9.1.3. Protocolo de respuesta
Contiene el resultado del procesamiento del DE, conforme lo detallado en el siguiente cuadro:
El Schema correspondiente al protocolo de respuesta será como sigue:
Schema XML 3: resRecepDE_v150.xsd (Respuesta del “WS Recepción DE”)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
ARSch01 rRetEnviDe Raíz - - - - Elemento raíz
Protocolo de
ARSch02 xProtDe ARSch01 XML - 1-1 Schema XML 4
procesamiento del DE
Schema XML 4: ProtProcesDE_v150.xsd (Protocolo de Procesamiento de DE)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
PP01 rProtDe Raíz - - - -
PP02 id CDC del DE Procesado PP01 A 44 1-1
Formato: “AAAA-
Fecha y hora del
PP03 dFecProc PP01 D 19 1-1 MM-DD-
procesamiento
hh:mm:ss”
Permite verificar la
correspondencia
DigestValue del DE
PP04 dDigVal PP01 28 1-1 con el DE
procesado
transmitido por el
contribuyente
Aprobado
Aprobado con
PP050 dEstRes Estado del resultado PP05 A 8-30 1-1
observación
Rechazado
Número de
PP051 dProtAut PP05 N 10 0-1
Transacción
Para producción se
limitará a 5
Grupo Resultado de
PP05 gResProc PP01 G 1-100 mensajes máximos
Procesamiento
sin modificación de
esta especificación.
Definido en el
Código del resultado de tópico
PP052 dCodRes PP05 N 4 1-1
procesamiento correspondiente del
capítulo 12
Definido en el
Mensaje del resultado tópico
dMsgRes PP05 A 1-255 1-1
PP053 de procesamiento correspondiente del
capítulo 12
septiembre de 2019 46

--- PAGE 48 / 217 ---

9.2. WS recepción lote DE – siRecepLoteDE
Función: Recibir un lote conteniendo varios DE
Proceso: Asíncrono
Método: SiRecepLoteDE
Particularidad: Archivo comprimido “.zip”
9.2.1. Definición del protocolo que consume este servicio
Para consumir este servicio, el cliente deberá construir la estructura en XML, según el Schema siguiente y
comprimir dicho archivo. Cabe aclarar que el lote podrá contener hasta 50 DE del mismo tipo (ejemplo:
Facturas Electrónicas), cada uno de ellos debe estar firmado.
Schema XML 5: SiRecepLoteDE_v150.xsd (WS Recepción DE Lote)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
BSch01 rEnvioLote Raíz - - Elemento raíz
Número secuencial
autoincremental, para
identificación del
Identificador de mensaje enviado. La
BSch02 dId BSch01 N 1-15 1-1
control de envío responsabilidad de
generar y controlar este
número es exclusiva del
contribuyente.
Campo comprimido en
formato Base64 según
Archivo de Lote
BSch03 xDE BSch01 B - 1-1 el esquema del
comprimido
Protocolo de
procesamiento del Lote
Schema XML 5A: ProtProcesLoteDE_v150.xsd (Protocolo de procesamiento del Lote)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
LSch01 rLoteDE Raíz - - Elemento raíz
Sigue las
Protocolo de definiciones del
LSch02 rDE LSch01 XML - 1-50
procesamiento del DE Capítulo Formato
de los DE
9.2.2. Descripción del procesamiento
Servicio disponible para recibir un lote que puede contener hasta 50 DE de un solo tipo, cada uno firmado
digitalmente y agrupados mediante un contenedor el cual posee el certificado digital del emisor. No se
requiere que el número del DE sea secuencial en el lote. Un lote debe contener solo un mismo tipo de DE.
septiembre de 2019 47

--- PAGE 49 / 217 ---

Una vez establecida la conexión con el SIFEN se realizarán las validaciones iniciales13, la respuesta corresponde
a un protocolo XML, donde se informa si superó o no las primeras validaciones.
9.2.3. Protocolo de respuesta
Corresponde al protocolo de procesamiento del DE y la definición de los Schemas XML 3 y XML 4.
Schema XML 6: resRecepLoteDE_v150.xsd (Respuesta del WS Recepción Lote)
Nodo Tipo Longitu
ID Campo Descripción Ocu Observaciones
Padre Dato d
rResEnviLo
BRSch01 Raíz - - - - Elemento raíz
teDe
Fecha y hora de Formato: “AAAA-
BRSch02 dFecProc BRSch01 D 19 1-1
recepción MM- DD-hh:mm:ss”
Definido en el tópico
Código del resultado de
BRSch03 dCodRes BRSch01 N 4 1-1 correspondiente del
recepción
capítulo 12
Definido en el tópico
Mensaje del resultado
BRSch04 dMsgRes BRSch01 A 1-255 1-1 correspondiente del
de recepción
capítulo 12
Generado solamente
si dCodRes=0300,
dProtConsL
BRSch05 Número de Lote BRSch01 N 1-15 0-1 Definido en el tópico
ote
correspondiente del
capítulo 12
Conforme a la
Tiempo medio de
sección
BRSch06 dTpoProces procesamiento en BRSch01 N 1-5 1-1
correspondiente en
segundos
el presente manual
9.3. WS consulta resultado de lote DE – siResultLoteDE
Devuelve el resultado del proceso de cada uno
Función:
de los DE del lote
Proceso: Asíncrono
Método: SiResultLoteDE
9.3.1. Definición del protocolo que consume este servicio
El Request que consumirá este servicio estará construido en XML, según el Schema expuesto a continuación:
Schema XML 7: SiResultLoteDE_v150.xsd (WS Consulta Resultado de Lote)
Nodo Tipo Longitu
ID Campo Descripción Ocu Observaciones
Padre Dato d
rEnviCons
CSch01 Raíz - - - - Elemento raíz
LoteDe
13 Estas validaciones iniciales, están contenidas en el Capítulo 12 del presente Manual.
septiembre de 2019 48

--- PAGE 50 / 217 ---

Nodo Tipo Longitu
ID Campo Descripción Ocu Observaciones
Padre Dato d
Número secuencial
autoincremental, para
identificación del mensaje
Identificador de enviado. La
CSch02 dId CSch01 N 1-15 1-1
control de envío responsabilidad de
generar y controlar este
número es exclusiva del
contribuyente.
Obtenido a partir del
mensaje de respuesta al
dProtCons
CSch03 Número del lote CSch01 N 1-15 1-1 WS
Lote
soRecepLoteDE(Schema
XML 5)
9.3.2. Descripción del procesamiento
Servicio que se encarga de retornar el resultado del procesamiento de cada DE contenido en el lote que fuera
recibido. Cada uno de los DE es identificado y contiene el resultado de su procesamiento y la situación, si fue
aprobado, aprobado con observación, o rechazado; en caso de aprobado con observación, serán informadas
las mismas (hasta 5 observaciones); y en caso de rechazo, será informado el motivo (solo el primer motivo de
rechazo).
Tabla F – Resultados de Procesamiento del WS Consulta Resultado de Lote
Condición Mensaje generado
No existe número de lote consultado 0360 (Número del Lote inexistente)
No se ha culminado el procesamiento de los DE
0361 Lote en procesamiento
del lote consultado
0362 (Procesamiento de lote concluido)
Éxito en la consulta - La respuesta también contiene el contenedor del
DE, definido en el Schema XML 11
9.3.3. Protocolo de respuesta
Conforme a lo definido deberá contener alguno de los mensajes de la tabla anterior, con la respuesta
correspondiente.
Para el caso que el procesamiento del lote haya concluido, el Response también contendrá el protocolo de
respuesta de cada uno de los DE contenidos en el lote, de acuerdo al Schema descrito a continuación.
Schema XML 8: resResultLoteDE_v150.xsd (Respuesta del WS Consulta Resultado Lote)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
CRSch0 rResEnviCon
Raíz - - - - Elemento raíz
1 sLoteDe
Formato: “AAAA-MM-
DDhh:mm:ss”
CRSch0 Fecha y hora del
dFecProc CRSch01 D 19 1-1 Si el lote no fue
2 procesamiento del lote
procesado, el valor será
vacío.
septiembre de 2019 49

--- PAGE 51 / 217 ---

Definido en el tópico
CRSch0 Código de resultado de correspondiente del
dCodResLot CRSch01 N 4 1-1
3 procesamiento del lote capítulo 12 referente al
lote
Definido en el tópico
Mensaje de resultado
CRSch0 correspondiente del
dMsgResLot de procesamiento del CRSch01 A 1-255 1-1
4 capítulo 12 referente al
lote
lote
Grupo Resultado de
CRSch0 gResProcLot
5 e
Proc esamiento del CRSch01 G 0-50
Lote
CRSch0 CDC del DE
50
id
procesado
CRSch05 A 44 1-1
Aprobado
CRSch0 Aprobado con
dEstRes Estado del resultado CRSch05 A 8-30 1-1
51 observación
Rechazado
Generado para el DE
CRSch0
dProtAut Número de transacción CRSch05 N 10 0-1 del lote consultado si
52
dCodResLot=0362
Si es error solo se
presentará el primero.
CRSch0
gResProc
Grupo Mensaje de
CRSch05 G 1-100
Se pueden tener hasta
53 Resultado 100 mensajes en caso
de aprobación con
observaciones.
Definido en el tópico
CRSch0 Código de resultado de correspondiente del
dCodRes CRSch05 N 4 1-1
54 procesamiento capítulo 12 referente a
cada DE
Definido en el tópico
CRSch0 Mensaje de resultado correspondiente del
dMsgRes CRSch05 A 1-255 1-1
55 de procesamiento capítulo 12 referente a
cada DE
9.4. WS consulta DE – siConsDE
Función: Devuelve el resultado de la consulta de un DE
por su CDC
Proceso: Síncrono
Método: SiConsDE
9.4.1. Definición del protocolo que consume este servicio
El Request que consumirá este servicio estará construido en XML, según el Schema expuesto a continuación.
Schema XML 9: siConsDE_v150.xsd (WS Consulta DE)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
DSch01 rEnviConsDe Raíz - - - - Elemento Raíz
Número secuencial
autoincremental, para
identificación del mensaje
Identificador de control de enviado. La
DSch02 dId DSch01 N 1-15 1-1
envío responsabilidad de generar
y controlar este número es
exclusiva del
contribuyente.
CDC del DE que se
DSch03 dCDC CDC del DE consultado DSch01 C 44 1-1 requiere la consulta en la
base de datos de SIFEN
septiembre de 2019 50

--- PAGE 52 / 217 ---

9.4.2. Descripción del procesamiento
Este servicio es el encargado de recibir la petición de consulta de un DTE de la base de datos de SIFEN. En caso
de no haber superado las validaciones, el Response contendrá el motivo.
Tabla G – Resultados de Procesamiento del WS Consulta DE
Condición Mensaje generado
No existe DE consultado 0420=CDC inexistente
RUC del certificado utilizado en la conexión no tiene
0421=RUC Certificado sin permiso
permiso para consultar el DE
Éxito en la consulta 0422=CDC encontrado
9.4.3. Protocolo de respuesta
Como ya manifestamos en el punto anterior, si las pruebas no son superadas, contendrá el error, de
lo contrario el response tendrá la información conforme al siguiente Schema.
Schema XML 10: resConsDE_v150.xsd (Respuesta del WS Consulta DE)
Tipo Longitu
ID Campo Descripción Nodo Padre Ocu Observaciones
Dato d
DRSc rResEnviCo
Raíz - - - - Elemento raíz
h01 nsDe
DRSc Fecha y hora del Formato: “AAAA-MM-DD-
dFecProc DRSch01 D 19 1-1
h02 procesamiento hh:mm:ss”
Definido en el tópico
DRSc Código del resultado de
dCodRes DRSch01 N 4 1-1 correspondiente del
h03 procesamiento
capítulo 12
Definido en el tópico
DRSc Mensaje del resultado
dMsgRes DRSch01 C 1-255 1-1 correspondiente del
h04 de procesamiento
capítulo 12
Existe solamente si
DRSc dCodRes = 0422
xContenDE Contenedor del DE DRSch01 XML - 0-1
h05 Definido en el Schema XML
11
Schema XML 11: ContenedorDE_v150.xsd (Contenedor de DE)
Tipo Longitu
ID Campo Descripción Nodo Padre Ocu Observaciones
Dato d
ContD
rContDe Raíz DRSch01 - - - Elemento raíz
E01
ContD
rDE Archivo XML del DE ContDE01 XML - 1-1
E02
Número de transacción del
ContD Número De DE, recibido por el
dProtAut ContDE01 XML - 1-1
E03 Transacción contribuyente en el
mensaje de respuesta del
septiembre de 2019 51

--- PAGE 53 / 217 ---

Tipo Longitu
ID Campo Descripción Nodo Padre Ocu Observaciones
Dato d
WS DeRecepDE o del WS
deResultLoteDE
• definido en el Schema
XML 4
Información de todos los
eventos registrados
(contenedor montado por la
ContD SET) o disponibles
xContEv Contenedor de Evento ContDE01 XML - 0-n
E04 (contenedor montado por el
emisor) hasta la fecha
• Definido en el Schema
XML 12
Schema XML 12: ContenedorEvento_v150.xsd (Contenedor de Evento)
Nodo Tipo Longitu
ID Campo Descripción Ocu Observaciones
Padre Dato d
ContE
rContEv Raíz - - - - Elemento raíz
v01
ContE ContEv Definido en el capítulo de
xEvento XML del Evento XML - 1-1
v02 01 Eventos del DE
ContE rResEnviE Respuesta del WS ContEv Definido en el Schema XML
XML -
v03 ventoDe Recepción Evento 01 14
9.5. WS recepción evento – siRecepEvento
Función: Registra un evento en un DE
Proceso: Síncrono
Método: siRecepEvento
9.5.1. Definición del protocolo que consume este Servicio
Contiene el tipo de evento y el evento.
Schema XML 13: siRecepEvento_v150.xsd (WS Recepción Evento)
Nodo Tipo Longit
ID Campo Descripción Ocu Observaciones
Padre Dato ud
rEnviEvent
GSch01 Raíz - - - - Elemento raíz
oDe
Número secuencial
autoincremental, para
identificación del mensaje
Identificador de control
GSch02 dId GSch01 N 1-15 1-1 enviado. La responsabilidad
de envío
de generar y controlar este
número es exclusiva del
contribuyente.
De acuerdo con el schema y
GSch03 dEvReg Evento a ser registrado GSch01 XML 1 1-1 grupos correspondientes
Descripto en el capítulo 11
septiembre de 2019 52

--- PAGE 54 / 217 ---

9.5.2. Descripción del procesamiento
Una vez superadas todas las validaciones iniciales y particulares, se registra el evento del DE correspondiente
y este queda debidamente almacenado en el SIFEN.
9.5.3. Protocolo de respuesta
Conforme al Schema que precede y conforme a las validaciones efectuadas, si el procesamiento concluye con
éxito, el registro de evento, contiene una respuesta satisfactoria, en caso de rechazo contiene el código y
motivo de rechazo.
Schema XML 14: resRecepEvento_v150.xsd (Respuesta del WS Recepción Evento)
Tipo Longit
ID Campo Descripción Nodo Padre Ocu Observaciones
Dato ud
rRetEnviEven
GRSch01 Raíz - - - - Elemento raíz
toDe
Fecha y hora del
procesamiento del Formato: “AAAA-MM-DD-
GRSch02 dFecProc GRSch01 D 19 1-1
último evento hh:mm:ss-ss:ss”
enviado
GRSch03
gResProcEV
G
de
ru p
P
o
roce
R
s
e
a
s
m
ul
i
t
e
a
n
d
t
o
o GRSch01 G 1-15
e
del Evento
Aprobado
Estado del
GRSch030 dEstRes CRSch03 A 8-30 1-1 Aprobado con observación
resultado
Rechazado
Generado para cada registro
Número de
GRSch031 dProtAut GRSch03 N 10 0-1 de evento conforme
transacción
dCodRes=0600
Corresponde al id
Identificador del
GRSch032 id GRSch03 N 10 1-1 autogenerado por el emisor,
evento
para identificar cada evento
Para producción se limitará a 5
GRSch033 gResProc
Grupo Resultado de
GRSch03 G
1- mensajes máximos sin
Procesamiento 100 modificación de esta
especificación.
Definido en el tópico
Código del resultado
GRSch034 dCodRes GRSch03 N 4 1-1 correspondiente del capítulo
de procesamiento
11
Mensaje del Definido en el tópico
GRSch035 dMsgRes resultado de GRSch03 A 1-255 1-1 correspondiente del capítulo
procesamiento 11
9.6. WS consulta RUC – siConsRUC
Función: Devuelve el resultado de la consulta de los
datos y estado del RUC de un contribuyente
receptor.
Proceso: Síncrono
Método: SiConsRUC
septiembre de 2019 53

--- PAGE 55 / 217 ---

9.6.1. Definición del protocolo que consume este servicio
El Request que consumirá este servicio estará construido en XML, según el Schema expuesto a continuación.
Schema XML 15: siConsRUC_v150.xsd (WS Consulta RUC)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
RSch01 rEnviConsRUC Raíz - - - - Elemento Raíz
Número secuencial
autoincremental, para
identificación del mensaje
Identificador de
RSch02 dId RSch01 N 1-15 1-1 enviado. La responsabilidad
control de envío
de generar y controlar este
número es exclusiva del
contribuyente.
RUC No incluye el Digito de
RSch03 dRUCCons RUC consultado RSch01 A 5-8 1-1
verificación
9.6.2. Descripción del procesamiento
Este servicio es el encargado de recibir la petición de consulta de los datos y estado del RUC de un
contribuyente receptor en la base de datos de SIFEN. Solamente se permiten conexiones con certificado
digital. Los posibles resultados se listan en la tabla H.
Tabla H – Resultados de Procesamiento del WS Consulta RUC
Condición Mensaje generado
El RUC consultado no existe en el Sistema 0500=RUC no existe
RUC no tiene permiso para utilizar el WS 0501=RUC sin permiso consulta WS
Éxito en la consulta 0502=RUC encontrado
9.6.3. Protocolo de respuesta
En casos de que haya concluido con éxito la consulta, contiene el código de respuesta 0502, o en caso contrario
contiene el código de respuesta correspondiente.
Schema XML 16: resConsRUC_v150.xsd (Respuesta del WS Consulta RUC)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
RRSch0 rResEnviConsR
Raíz - - - - Elemento raíz
1 UC
Código del Definido en el tópico
RRSch0
dCodRes resultado de la RRSch01 N 4 1-1 correspondiente del
2
consulta RUC capítulo 12
Mensaje del Definido en el tópico
RRSch0
dMsgRes resultado de la RRSch01 A 1-255 1-1 correspondiente del
3
consulta RUC capítulo 12
septiembre de 2019 54

--- PAGE 56 / 217 ---

Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
Existe solamente si
RRSch0 Contenedor del dCodRes = 0502
xContRUC RRSch01 XML - 0-1
4 RUC Definido en el Schema
XML 17
Schema XML 17: ContenedorRUC_v150.xsd (Contenedor de RUC)
Nodo Tipo
ID Campo Descripción Longitud Ocu Observaciones
Padre Dato
ContRU
rContRUC Raíz RRSch01 - - - Elemento raíz
C01
ContRU
dRUCCons RUC Consultado ContRUC01 A 5-8 1-1
C02
ContRU Razón social del
dRazCons ContRUC01 A 1-250 1-1
C03 RUC Consultado
ACT=Activo
SUS=Suspensión
Temporal
Código del Estado SAD=Suspensión
ContRU
dCodEstCons del RUC ContRUC01 A 3 1-1 Administrativa
C04
Consultado BLQ=Bloqueado
CAN=Cancelado
CDE=Cancelado
Definitivo
ACT=Activo
SUS=Suspensión
Temporal
Descripción
SAD=Suspensión
ContRU Código del Estado
dDesEstCons ContRUC01 A 6-25 1-1 Administrativa
C05 del RUC
BLQ=Bloqueado
Consultado
CAN=Cancelado
CDE=Cancelado
Definitivo
S = Es facturador
RUC consultado
ContRU electrónico
dRUCFactElec es facturador ContRUC01 A 1 1-1
C06 N = No es facturador
electrónico
electrónico
9.7. WS consulta DE de entidades u organismos externos autorizados – siConsDEST (a futuro)
Función: Web service que tiene por objetivo entregar los DE y sus eventos para
las entidades que tiene derecho legal de recibir determinadas facturas
(Ej: DNA, con respecto a operaciones de comercio exterior, DNCP con
respecto a operaciones de venta al Estado)
Proceso: Síncrono
Método: siConsDEST
Observación: A futuro
septiembre de 2019 55

--- PAGE 57 / 217 ---

10. Formato de los Documentos Electrónicos
10.1. Estructura del código de control (CDC) de los DE
A fin de mantener una única identificación para cada documento electrónico, implementamos el código de
control o CDC14.
Este CDC debe ser generado por el sistema de facturación del emisor conforme a los delineamientos
contenidos en el presente Manual Técnico.
Conformación del CDC
Para lograr una mayor comprensión se describe a continuación un ejemplo de cómo generar un CDC:
Consideraremos:
Por lo tanto, el CDC estará conformado como sigue:
14 CDC Código de Control, único en cada DE, se referencia de forma unívoca en el SIFEN
septiembre de 2019 56

--- PAGE 58 / 217 ---

Cabe destacar que este código de control es incluido dentro del Schema XML, en el campo A002 como atributo
para la firma del DE.
En la representación gráfica (KuDE) deberá ser visible, por lo tanto, debe ser expuesto en grupos de cuatro
caracteres, tal como sigue:
Representación Gráfica
0144 4444 0170 0100 1001 4528 2201 7012 5158 7326 0988
10.2. Dígito verificador del CDC
Para el cálculo del dígito verificador del código de control se debe utilizar el módulo 11, con el cual se
determina su validez.
La documentación acerca de cómo generar este dígito, la cual se basa en la conformación antes descripta, se
encuentra en la siguiente dirección:
https://www.set.gov.py/portal/PARAGUAY-SET/detail?content-id=/repository/collaboration/sites/PARAGUAY-SET/documents/herramientas/digito-
verificador.pdf
10.3. Generación del código de seguridad
El código de seguridad de los documentos electrónicos (campo dCodSeg) tiene como objetivo asegurar la
privacidad de los documentos emitidos, debe ser generado por el contribuyente emisor, conforme a las
siguientes condiciones:
• Debe ser un número positivo de 9 dígitos.
• Aleatorio.
• Debe ser distinto para cada DE y generado por un algoritmo de complejidad suficiente para evitar la
reproducción del valor.
• Rango NO SECUENCIAL entre 000000001 y 999999999.
• No tener relación con ninguna información específica o directa del DE o del emisor de manera a
garantizar su seguridad.
• No debe ser igual al número de documento campo dNumDoc.
• En caso de ser un número de menos de 9 dígitos completar con 0 a la izquierda.
septiembre de 2019 57

--- PAGE 59 / 217 ---

10.4. Datos que se deben informar en los documentos electrónicos (DE)
A fin de facilitar la comprensión de la estructura de información de los documentos electrónicos, a
continuación, se referencian los campos contenidos en los mismos, los cuales se han organizado, definido y
agrupado conforme a la Tabla I:
Tabla I – Grupos de campos del Archivo XML
AA. Campos que identifican el formato electrónico XML (AA001-AA009)
A. Campos firmados del Documento Electrónico (A001-A099)
B. Campos inherentes a la operación de Documentos Electrónicos (B001-B099)
C. Campos de datos del Timbrado (C001-C099)
D. Campos Generales del Documento Electrónico DE (D001-D299)
D1. Campos inherentes a la operación comercial (D010-D099)
D2. Campos que identifican al emisor del Documento Electrónico DE (D100-D129)
D2.1 Campos que describen la actividad económica del emisor (D130-D139)
D3. Campos que identifican al receptor del Documento Electrónico DE (D200 al D299)
E. Campos específicos por tipo de Documento Electrónico (E001-E009)
E1. Campos que componen la Factura Electrónica FE (E010-E099)
E1.1. Campos de informaciones de Compras Públicas (E020-E029)
E2. Campos que componen la Factura Electrónica de Exportación FEE (E100-E199)
E3. Campos que componen la Factura Electrónica de Importación FEI (E200-E299)
E4. Campos que componen la Autofactura Electrónica AFE (E300-E399)
E5. Campos que componen la Nota de Crédito/Débito Electrónica NCE-NDE (E400-E499)
E6. Campos que componen la Nota de Remisión Electrónica (E500-E599)
E7. Campos que describen la condición de la operación (E600-E699)
E7.1. Campos que describen la forma de pago de la operación al contado o del
monto de la entrega inicial (E605-E619)
E7.1.1. Campos que describen el pago o entrega inicial de la operación con
tarjeta de crédito/débito (E620-E629)
E7.1.2. Campos que describen el pago o entrega inicial de la operación con
cheque (E630-E639)
E7.2. Campos que describen la operación a crédito (E640-E649)
E7.2.1. Campos que describen las cuotas (E650-E659)
E8. Campos que describen los ítems de la operación (E700-E899)
E8.1. Campos que describen el precio, tipo de cambio y valor total de la operación
por ítem (E720-E729)
E8.1.1 Campos que describen los descuentos, anticipos y valor total por
ítem (EA001-EA050)
E8.2. Campos que describen el IVA de la operación por ítem (E730-E739)
E8.3. Campos que describen el ISC de la operación por ítem (futuro)
E8.4. Grupo de rastreo de la mercadería (E750-E760)
E8.5. Sector de automotores nuevos y usados (E770-E789)
E9. Campos complementarios comerciales de uso específico (E790-E899)
E9.2. Sector Energía Eléctrica (E791-E799)
E9.3. Sector de Seguros (E800-E809)
E9.3.1. Póliza de seguros (EA790-EA799)
E9.4. Sector de Supermercados (E810-E819)
E9.5. Grupo de datos adicionales de uso comercial (E820-E829)
E10. Campos que describen el transporte de las mercaderías (E900-E999)
septiembre de 2019 58

--- PAGE 60 / 217 ---

E10.1. Campos que identifican el local de salida de las mercaderías (E920-E939)
E10.2. Campos que identifican el local de entrega de las mercaderías (E940-E959)
E10.3. Campos que identifican el vehículo de traslado de mercaderías (E960-E979)
E10.4. Campos que identifican al transportista (persona física o jurídica) (E980-E999)
F. Campos que describen los subtotales y totales de la transacción documentada (F001-F099)
G. Campos complementarios comerciales de uso general (G001-G049)
G1. Campos generales de la carga (G050 - G099)
H. Campos que identifican al documento asociado (H001-H049)
I. Información de la Firma Digital del DTE (I001-I049)
J. Campos fuera de la Firma Digital (J001-J049)
10.5. Manejo del timbrado y Numeración
Se maneja la siguiente secuencia de campos que identifican a cada DE:
• Número de timbrado
• Establecimiento
• Punto de expedición
• Tipo de documento
• Número de documento
• Serie
Se ha incluido el uso de la serie (todas las combinaciones de a dos que se puedan realizar entre 2 letras
mayúsculas, excepto la Ñ) ya que el timbrado no manejará una fecha de fin de vigencia.
Ejemplo de uso:
Situación inicial
• Número de timbrado: 12345678
• Establecimiento: 001
• Punto de expedición: 001
• Tipo de documento: 01
• Número de documento: 0000001 al 9999999
Inicio de la serie
• Número de timbrado: 12345678
• Establecimiento: 001
• Punto de expedición: 001
• Tipo de documento: 01
• Número de documento: 0000001 al 9999999
• Serie: AA
Uso de la siguiente serie
• Número de timbrado: 12345678
septiembre de 2019 59

--- PAGE 61 / 217 ---

• Establecimiento: 001
• Punto de expedición: 001
• Tipo de documento: 01
• Número de documento: 0000001 al 9999999
• Serie: AB
Inicialmente no se utilizará serie hasta consumir toda la numeración que va desde 0000001 al 9999999 para
cada tipo de documento, luego la se tendrá que hacer uso de la serie según el siguiente orden.
• Orden de Serie: AA, AB, AC, … , AZ …BA, BB, …., BZ, … ZA, ZB, … , ZZ
El sistema validará la secuencialidad del uso de la serie. Esta secuencialidad se dará según el orden mencionado
en el ejemplo anterior.
Una vez que el SIFEN reciba un DE con serie, se tomará la fecha y hora de firma digital del DE como fecha inicial
de inicio de la serie.
El sistema aprobará solo aquellos DE en las siguientes condiciones:
(*) Serie inmediatamente anterior: DE con serie anterior a la mayor serie enviada al SIFEN, cuya fecha y hora
de firma digital es anterior a la fecha de inicio de vigencia de la serie actual en el sistema.
(*) Serie igual: DE con serie igual a la mayor serie enviada al SIFEN
(*) Serie inmediatamente posterior: DE con serie posterior a la mayor serie enviada al SIFEN, cuya fecha y
hora de firma digital es posterior a la fecha de inicio de vigencia de la serie actual en el sistema.
Ejemplo:
Serie actual: AC
Fecha de inicio de vigencia de la serie: 07/06/2019 08:30:00
Ejemplo de DE con Series aprobadas:
AB con fecha de firma anterior a 07/06/2019 08:30:00
Todos los DE con serie AC
AD con fecha de firma posterior a 07/06/2019 08:30:00
septiembre de 2019 60

--- PAGE 62 / 217 ---

TABLA DE FORMATO DE CAMPOS DE UN DOCUMENTO ELECTRÓNICO (DE)
Schema XML 18: DE_v150.xsd (Documento Electrónico)
AA. Campos que identifican el formato electrónico XML (AA001-AA009)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Documento Electrónico
AA AA001 rDE Raíz G 1-1
elemento raíz
Control de versiones
AA AA002 dVerFor Versión del formato AA001 N 3 1-1 Este campo debe contener la
versión 150
A. Campos firmados del Documento Electrónico (A001-A099)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos firmados del
A A001 DE AA001 G 1-1
DE
Atributo del Tag <DE>
NOTA: Con carácter excepcional
cuando un RUC contenga letras para
A A002 Id Identificador del DE A001 A 44 efectos del cálculo del Dígito verificador
y la generación del CDC se realizará la
conversión de dicha letra por su valor en
código ASCII
Dígito verificador del
A A003 dDVId
identificador del DE
A001 N 1 1-1 Según algoritmo módulo 11

--- PAGE 63 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
La fecha y hora de la firma digital debe
ser anterior a la fecha y hora de
transmisión al SIFEN
El certificado digital debe estar vigente
al momento de la firma digital del DE
A A004 dFecFirma Fecha de la firma A001 F 19 1-1 Fecha y hora en el formato
AAAA-MM-DDThh:mm:ss
El plazo límite de transmisión del DE al
SIFEN para la aprobación normal es
de 72 h contadas a partir de la fecha y
hora de la firma digital.
1=Sistema de facturación del
A A005 dSisFact Sistema de facturación A001 N 1 1-1 contribuyente
2=SIFEN solución gratuita
B. Campos inherentes a la operación de Documentos Electrónicos (B001-B099)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos inherentes a
B B001 gOpeDE A001 G 1-1
la operación de DE
1= Normal
B B002 iTipEmi Tipo de emisión B001 N 1 1-1
2= Contingencia
Referente al campo B002
Descripción del tipo de
B B003 dDesTipEmi B001 A 6-12 1-1 1= “Normal”
emisión
2= “Contingencia”
Código generado por el emisor de
manera aleatoria para asegurar la
B B004 dCodSeg Código de seguridad B001 N 9 1-1
confidencialidad de la consulta
pública del DE
Información de interés
B B005 dInfoEmi del emisor respecto al B001 A 1-3000 0-1
DE
septiembre de 2019 62

--- PAGE 64 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Esta información debe ser impresa
en el KuDE.
Información de interés Cuando el tipo de documento es
B B006 dInfoFisc del Fisco respecto al B001 A 1-3000 0-1 Nota de remisión (C002=7) es
DE obligatorio informar el mensaje
según el Art. 3 Inc. 7 de la Resolución
general Nro. 41/2014
C. Campos de datos del Timbrado (C001-C099)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
C C001 gTimb Datos del timbrado A001 G 1-1
1= Factura electrónica
2= Factura electrónica de exportación
(Futuro)
3= Factura electrónica de importación
(Futuro)
Tipo de Documento
C C002 iTiDE C001 N 1-2 1-1 4= Autofactura electrónica
Electrónico
5= Nota de crédito electrónica
6= Nota de débito electrónica
7= Nota de remisión electrónica
8= Comprobante de retención
electrónico (Futuro)
Referente al campo C002
1= “Factura electrónica”
2= “Factura electrónica de
exportación”
3= “Factura electrónica de
Descripción del tipo de importación”
C C003 dDesTiDE C001 A 15-40 1-1
documento electrónico 4= “Autofactura electrónica”
5= “Nota de crédito electrónica”
6= “Nota de débito electrónica”
7= “Nota de remisión electrónica”
8= “Comprobante de retención
electrónico”
Debe coincidir con la estructura de
C C004 dNumTim Número del timbrado C001 N 8 1-1
timbrado
septiembre de 2019 63

--- PAGE 65 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Completar con 0 (cero) a la izquierda
C C005 dEst Establecimiento C001 A 3 1-1 Debe coincidir con la estructura de
timbrado
Completar con 0 (cero) a la izquierda
C C006 dPunExp Punto de expedición C001 A 3 1-1 Debe coincidir con la estructura de
timbrado
Debe empezar con 1 (uno) para un
nuevo timbrado.
Completar con 0 (cero) a la izquierda
hasta alcanzar 7 (siete) cifras
Debe coincidir con la estructura de
timbrado
C C007 dNumDoc Número del documento C001 A 7 1-1
Una vez que se haya agotado la
numeración permitida por el sistema
(9999999), la numeración de los
comprobantes electrónicos se
reinicia con la utilización de la serie,
para evitar rechazos por duplicidad
Campo obligatorio cuando ya se ha
consumido la totalidad de la
Serie del número de numeración permitida por el sistema
C C010 dSerieNum C001 A 2 0-1
timbrado (9999999).
Referirse a la sección Manejo del
timbrado y Numeración.
Formato AAAA-MM-DD
Para el KuDE el formato de la fecha
Fecha inicio de vigencia
C C008 dFeIniT C001 F 10 1-1 de inicio de vigencia debe contener
del timbrado
los guiones separadores. Ejemplo:
2018-05-31
Formato AAAA-MM-DD
Para el KuDE el formato de la fecha
Fecha fin de vigencia del
C C009 dFeFinT C001 F 10 1-1 de inicio de vigencia debe contener
timbrado
los guiones separadores. Ejemplo:
2018-05-31
septiembre de 2019 64

--- PAGE 66 / 217 ---

D. Campos Generales del Documento Electrónico DE (D001-D299)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos generales del
D D001 gDatGralOpe A001 G 1-1
DE
Fecha y hora en el formato
AAAA-MM-DDThh:mm:ss
Para el KuDE el formato de la fecha
de emisión debe contener los
guiones separadores. Ejemplo:
2018-05-31T12:00:00
Fecha y hora de
D D002 dFeEmiDE D001 F 19 1-1 Se aceptará como límites técnicos
emisión del DE
del sistema, que la fecha de emisión
del DE sea atrasada hasta 720
horas (30 días) y adelantada hasta
120 horas (5 días) en relación a la
fecha y hora de transmisión al
SIFEN
D1. Campos inherentes a la operación comercial (D010-D099)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos inherentes a Obligatorio si C002 ≠ 7
D1 D010 gOpeCom D001 G 0-1
la operación comercial No informar si C002 = 7
septiembre de 2019 65

--- PAGE 67 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Obligatorio si C002 = 1 o 4
No informar si C002 ≠ 1 o 4
Tipo de transacción para el emisor
1= Venta de mercadería
2= Prestación de servicios
3= Mixto (Venta de mercadería y
servicios)
4= Venta de activo fijo
5= Venta de divisas
D1 D011 iTipTra Tipo de transacción D010 N 1-2 0-1 6= Compra de divisas
7= Promoción o entrega de
muestras
8= Donación
9= Anticipo
10= Compra de productos
11= Compra de servicios
12= Venta de crédito fiscal
13=Muestras médicas (Art. 3 RG
24/2014)
Obligatorio si existe el campo D011
1= “Venta de mercadería”
2= “Prestación de servicios”
3= “Mixto” (Venta de mercadería y
servicios)
4= “Venta de activo fijo”
5= “Venta de divisas”
6= “Compra de divisas”
Descripción del tipo
D1 D012 dDesTipTra D010 A 5-36 0-1 7= “Promoción o entrega de
de transacción
muestras”
8= “Donación”
9= “Anticipo”
10= “Compra de productos”
11= “Compra de servicios”
12= “Venta de crédito fiscal”
13= ”Muestras médicas (Art. 3 RG
24/2014)”
1= IVA
2= ISC
Tipo de impuesto
D1 D013 iTImp D010 N 1 1-1 3=Renta
afectado
4=Ninguno
5=IVA - Renta
septiembre de 2019 66

--- PAGE 68 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
1= “IVA”
2= “ISC”
Descripción del tipo
D1 D014 dDesTImp D010 A 3-11 1-1 3= “Renta”
de impuesto afectado
4= “Ninguno”
5= “IVA – Renta”
Según tabla de códigos para
monedas de acuerdo con la norma
Moneda de la
D1 D015 cMoneOpe D010 A 3 1-1 ISO 4217
operación
Se requiere la misma moneda para
todos los ítems del DE
Descripción de la
D1 D016 dDesMoneOpe moneda de la D010 A 3-20 1-1 Referente al campo D015
operación
Obligatorio si D015 ≠ PYG
No informar si D015 = PYG
Condición del tipo de 1= Global (un solo tipo de cambio
D1 D017 dCondTiCam D010 N 1 0-1
cambio para todo el DE)
2= Por ítem (tipo de cambio distinto
por ítem)
Obligatorio si D017 = 1
Tipo de cambio de la
D1 D018 dTiCam D010 N 1-5p(0-4) 0-1 No informar si D017 = 2
operación
No informar si D015=PYG
1= Anticipo Global (un solo tipo de
anticipo para todo el DE)
D1 D019 iCondAnt Condición del Anticipo D010 N 1 0-1 2= Anticipo por ítem (corresponde a
la distribución de Anticipos
facturados por ítem)
Descripción de la 1= “Anticipo Global”
D1 D020 dDesCondAnt D010 A 15-17 0-1
condición del Anticipo 2= “Anticipo por Ítem”
D2. Campos que identifican al emisor del Documento Electrónico DE (D100-D129)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Grupo de campos que
D2 D100 gEmis D001 G 1-1
identifican al emisor
septiembre de 2019 67

--- PAGE 69 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Debe corresponder al RUC del
RUC del contribuyente
D2 D101 dRucEm D100 A 3-8 1-1 certificado digital utilizado para
emisor
firmar el DE
Dígito verificador del
D2 D102 dDVEmi RUC del contribuyente D100 N 1 1-1 Según algoritmo módulo 11
emisor
1= Persona Física
D2 D103 iTipCont Tipo de contribuyente D100 N 1 1-1
2= Persona Jurídica
D2 D104 cTipReg Tipo de régimen D100 N 1-2 0-1 Según Tabla 1 – Tipo de Régimen
En caso de ambiente de prueba,
debe contener obligatoriamente el
Nombre o razón social
D2 D105 dNomEmi D100 A 4-255 1-1 literal "DE generado en ambiente
del emisor del DE
de prueba - sin valor comercial ni
fiscal"
Debe corresponder a lo declarado
D2 D106 dNomFanEmi Nombre de fantasía D100 A 4-255 0-1
en el RUC
Nombre de la calle principal. Debe
Dirección del local
D2 D107 dDirEmi D100 A 1-255 1-1 corresponder a lo declarado en el
donde se emite el DE
RUC
Si no tiene numeración, colocar 0
(cero)
D2 D108 dNumCas Número de casa D100 N 1-6 1-1
Debe corresponder a lo declarado
en el RUC
Complemento de
D2 D109 dCompDir1 D100 A 1-255 0-1 Nombre de la calle secundaria
dirección 1
Complemento de Número de departamento/ piso/
D2 D110 dCompDir2 D100 A 1-255 0-1
dirección 2 local/ edificio/ depósito
Código del Según XSD de Departamentos
D2 D111 cDepEmi departamento de D100 N 1-2 1-1 Debe corresponder a lo declarado
emisión en el RUC
Descripción del Referente al campo D111
D2 D112 dDesDepEmi departamento de D100 A 6-16 1-1 Debe corresponder a lo declarado
emisión en el RUC
Según Tabla 2.1 – Distritos
Código del distrito de
D2 D113 cDisEmi D100 N 1-4 0-1 Debe corresponder a lo declarado
emisión
en el RUC
Obligatorio si existe el campo D113
Descripción del distrito
D2 D114 dDesDisEmi D100 A 1-30 0-1 Debe corresponder a lo declarado
de emisión
en el RUC
septiembre de 2019 68

--- PAGE 70 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Según Tabla 2.2 – Ciudades
Código de la ciudad
D2 D115 cCiuEmi D100 N 1-5 1-1 Debe corresponder a lo declarado
de emisión
en el RUC
Referente al campo D115
Descripción de la
D2 D116 dDesCiuEmi D100 A 1-30 1-1 Debe corresponder a lo declarado
ciudad de emisión
en el RUC
Debe incluir el prefijo de la ciudad
Teléfono local de
D2 D117 dTelEmi D100 A 6-15 1-1 Debe corresponder a lo declarado
emisión de DE
en el RUC
Correo electrónico del Debe corresponder a lo declarado
D2 D118 dEmailE D100 A 3-80 1-1
emisor en el RUC
Denominación
Denominación interna del emisor
D2 D119 dDenSuc comercial de la D100 A 1-30 0-1
sucursal
D2.1 Campos que describen la actividad económica del emisor (D130-D139)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Grupo de campos que
D2.1 D130 gActEco describen la actividad D100 G - 1-9
económica del emisor
Según Tabla 3 – Actividades
Código de la actividad Económicas
D2.1 D131 cActEco D130 A 1-8 1-1
económica del emisor Debe corresponder a lo declarado en
el RUC
Referente al campo D120
Descripción de la Según Tabla 3 – Actividades
D2.1 D132 dDesActEco actividad económica D130 A 1-300 1-1 Económicas
del emisor Debe corresponder a lo declarado en
el RUC
septiembre de 2019 69

--- PAGE 71 / 217 ---

D2.2 Campos que identifican al responsable de la generación del DE (D140-D160)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Grupo de campos que
D2.2 D140 gRespDE
identifican al
D100 G - 0-1
responsable de la
generación del DE
Tipo de documento de 1= Cédula paraguaya
identidad del 2= Pasaporte
iTipIDRespDE
D2.2 D141 responsable de la D140 N 1 1-1 3= Cédula extranjera
generación del DE 4= Carnet de residencia
9= Otro
1= “Cédula paraguaya”
Descripción del tipo de 2= “Pasaporte”
documento de 3= “Cédula extranjera”
D2.2 D142 dDTipIDRespDE identidad del D140 A 9-41 1-1 4= “Carnet de residencia”
responsable de la Si D141 = 9 informar el tipo de
generación del DE documento de identidad del
responsable de la generación del DE
Número de documento
D2.2 D143 dNumIDRespDE
de identidad del
D140 A 1-20 1-1
responsable de la
generación del DE
Nombre o razón social
D2.2 D144 dNomRespDE del responsable de la D140 A 4-255 1-1
generación del DE
Cargo del responsable
D2.2 D145 dCarRespDE de la generación del D140 A 4-100 1-1
DE
D3. Campos que identifican al receptor del Documento Electrónico DE (D200-D299)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Grupo de campos que
D3 D200 gDatRec D001 G 1-1
identifican al receptor
septiembre de 2019 70

--- PAGE 72 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
1= contribuyente
D3 D201 iNatRec Naturaleza del receptor D200 N 1 1-1
2= no contribuyente
1= B2B
2= B2C
3= B2G
4= B2F
D3 D202 iTiOpe Tipo de operación D200 N 1 1-1
(Esta última opción debe utilizarse
solo en caso de servicios para
empresas o personas físicas del
exterior)
Código de país del Según XSD de Codificación de
D3 D203 cPaisRec D200 A 3 1-1
receptor Países
Descripción del país
D3 D204 dDesPaisRe D200 A 4-30 1-1 Referente al campo D203
receptor
Obligatorio si D201 = 1
Tipo de contribuyente No informar si D201 = 2
D3 D205 iTiContRec D200 N 1 0-1
receptor 1= Persona Física
2= Persona Jurídica
Obligatorio si D201 = 1
D3 D206 dRucRec RUC del receptor D200 A 3-8 0-1
No informar si D201 = 2
Dígito verificador del Obligatorio si existe el campo D206
D3 D207 dDVRec D200 N 1 0-1
RUC del receptor Según algoritmo módulo 11
Obligatorio si D201 = 2 y D202 ≠ 4
No informar si D201 = 1 o D202=4
1= Cédula paraguaya
2= Pasaporte
Tipo de documento de
iTipIDRec 3= Cédula extranjera
D3 D208 identidad del receptor D200 N 1 0-1
4= Carnet de residencia
5= Innominado
6=Tarjeta Diplomática de
exoneración fiscal
9= Otro
septiembre de 2019 71

--- PAGE 73 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Obligatorio si existe el campo D208
1= “Cédula paraguaya”
2= “Pasaporte”
3= “Cédula extranjera”
4= “Carnet de residencia”
Descripción del tipo de
D3 D209 dDTipIDRec D200 A 9-41 0-1 5 = “Innominado”
documento de identidad
6= “Tarjeta Diplomática de
exoneración fiscal”
Si D208 = 9 informar el tipo de
documento de identidad del
receptor
Obligatorio si D201 = 2 y D202 ≠ 4
Número de documento No informar si D201 = 1 o D202=4
D3 D210 dNumIDRec D200 A 1-20 0-1
de identidad En caso de DE innominado,
completar con 0 (cero)
Nombre o razón social En caso de DE innominado,
D3 D211 dNomRec D200 A 4-255 1-1
del receptor del DE completar con “Sin Nombre”
D3 D212 dNomFanRec Nombre de fantasía D200 A 4-255 0-1
Campo obligatorio cuando C002=7
D3 D213 dDirRec Dirección del receptor D200 A 1-255 0-1
o cuando D202=4
Campo obligatorio si se informa el
campo D213
Número de casa del
D3 D218 dNumCasRec D200 N 1-6 0-1 Cuando D201 = 1, debe
receptor
corresponder a lo declarado en el
RUC
Campo obligatorio si se informa el
Código del
campo D213 y D202≠4, no se debe
D3 D219 cDepRec departamento del D200 N 1-2 0-1
informar cuando D202 = 4.
receptor
Según XSD de Departamentos
Descripción del
D3 D220 dDesDepRec departamento del D200 A 6-16 0-1 Referente al campo D219
receptor
Código del distrito del
D3 D221 cDisRec D200 N 1-4 0-1 Según Tabla 2.1 – Distritos
receptor
Descripción del distrito
D3 D222 dDesDisRec D200 A 1-30 0-1 Obligatorio si existe el campo D221
del receptor
septiembre de 2019 72

--- PAGE 74 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campo obligatorio si se informa el
Código de la ciudad del campo D213 y D202≠4, no se debe
D3 D223 cCiuRec D200 N 1-5 0-1
receptor informar cuando D202 = 4.
Según Tabla 2.2 – Ciudades
Descripción de la ciudad
D3 D224 dDesCiuRec D200 A 1-30 0-1 Referente al campo D223
del receptor
Número de teléfono del Debe incluir el prefijo de la ciudad si
D3 D214 dTelRec D200 A 6-15 0-1
receptor D203 = PRY
Número de celular del
D3 D215 dCelRec D200 A 10-20 0-1
receptor
Correo electrónico del
D3 D216 dEmailRec D200 A 3-80 0-1
receptor
D3 D217 dCodCliente Código del cliente D200 A 3-15 0-1
E. Campos específicos por tipo de Documento Electrónico (E001-E009)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos específicos
por tipo de
E E001 gDtipDE A001 G 1-1
Documento
Electrónico
E1. Campos que componen la Factura Electrónica FE (E002-E099)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que Obligatorio si C002 = 1
E1 E010 gCamFE E001 G 0-1
componen la FE No informar si C002 ≠ 1
septiembre de 2019 73

--- PAGE 75 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
1= Operación presencial
2= Operación electrónica
3= Operación telemarketing
E1 E011 iIndPres Indicador de presencia E010 N 1 1-1 4= Venta a domicilio
5= Operación bancaria
6= Operación cíclica
9= Otro
Referente al campo E011
1= “Operación presencial”
2= “Operación electrónica”
3= “Operación telemarketing”
Descripción del
E1 E012 dDesIndPres E010 A 10-30 1-1 4= “Venta a domicilio”
indicador de presencia
5= “Operación bancaria”
6=” Operación cíclica”
Si E011 = 9 informar el indicador de
presencia
Fecha en el formato: AAAA-MM-DD
Fecha estimada para el traslado de
Fecha futura del
E1 E013 dFecEmNR E010 F 10 0-1 la mercadería y emisión de la nota
traslado de mercadería
de remisión electrónica cuando
corresponda. RG 41/14
E1.1. Campos de informaciones de Compras Públicas (E020-E029)
Nodo Tipo Longit
Grupo ID Campo Descripción Ocurrencia Observaciones
Padre Dato ud
Campos que describen
Obligatorio si D202 = 3 (Tipo de
E1.1 E020 gCompPub las informaciones de E010 G 0-1
operación B2G)
compras públicas
Modalidad - Código
E1.1 E021 dModCont E020 A 2 1-1
emitido por la DNCP
Entidad - Código emitido
E1.1 E022 dEntCont E020 N 5 1-1
por la DNCP
Año - Código emitido por
E1.1 E023 dAnoCont E020 N 2 1-1
la DNCP
Secuencia - emitido por
E1.1 E024 dSecCont E020 N 7 1-1
la DNCP
septiembre de 2019 74

--- PAGE 76 / 217 ---

Nodo Tipo Longit
Grupo ID Campo Descripción Ocurrencia Observaciones
Padre Dato ud
Fecha de emisión del Fecha en el formato: AAAA-MM-DD.
E1.1 E025 dFeCodCont código de contratación E020 F 10 1-1 Esta fecha debe ser anterior a la fecha
por la DNCP de emisión de la FE
E4. Campos que componen la Autofactura Electrónica AFE (E300-E399)
Nodo Tipo Longit
Grupo ID Campo Descripción Ocurrencia Observaciones
Padre Dato ud
Campos que componen Obligatorio si C002 = 4
E4 E300 gCamAE E001 G 0-1
la Autofactura Electrónica No informar si C002 ≠ 4
1= No contribuyente
E4 E301 iNatVen Naturaleza del vendedor E300 N 1 1-1
2= Extranjero
Referente al campo E301.
Descripción de la
E4 E302 dDesNatVen E300 A 10-16 1-1 1= “No contribuyente”
naturaleza del vendedor
2= “Extranjero”
1= Cédula paraguaya
iTipIDVen Tipo de documento de 2= Pasaporte
E4 E304 E300 N 1 1-1
identidad del vendedor 3= Cédula extranjera
4= Carnet de residencia
Referente al campo E304
Descripción del tipo de 1= “Cédula paraguaya”
E4 E305 dDTipIDVen documento de identidad E300 A 9-20 1-1 2= “Pasaporte”
del vendedor 3= “Cédula extranjera”
4= “Carnet de residencia”
Número de documento
E4 E306 dNumIDVen de identidad del E300 A 1-20 1-1
vendedor
Nombre y apellido del
E4 E307 dNomVen E300 A 4-60 1-1
vendedor
En caso de extranjeros, colocar la
dirección en donde se realizó la
E4 E308 dDirVen Dirección del vendedor E300 A 1-255 1-1
transacción.
Nombre de la calle principal
Número de casa del
E4 E309 dNumCasVen E300 N 1-6 1-1 Si no tiene numeración colocar 0 (cero)
vendedor
septiembre de 2019 75

--- PAGE 77 / 217 ---

Nodo Tipo Longit
Grupo ID Campo Descripción Ocurrencia Observaciones
Padre Dato ud
En caso de extranjeros, colocar el
Código del departamento departamento en donde se realizó la
E4 E310 cDepVen E300 N 1-2 1-1
del vendedor transacción.
Según XSD de Departamentos
Descripción del
E4 E311 dDesDepVen departamento del E300 A 6-16 1-1 Referente al campo E310
vendedor
En caso de extranjeros, colocar el
Código del distrito del distrito en donde se realizó la
E4 E312 cDisVen E300 N 1-4 0-1
vendedor transacción.
Según Tabla 2.1 - Distritos
Descripción del distrito
E4 E313 dDesDisVen E300 A 1-30 0-1 Obligatorio si existe el campo E312
del vendedor
En caso de extranjeros, colocar la
Código de la ciudad del ciudad en donde se realizó la
E4 E314 cCiuVen E300 N 1-5 1-1
vendedor transacción.
Según Tabla 2.2 - Ciudades
Descripción de la ciudad
E4 E315 dDesCiuVen E300 A 1-30 1-1 Referente al campo E314
del vendedor
Nombre de la calle principal (Dirección
E4 E316 dDirProv Lugar de la transacción E300 A 1-255 1-1
donde se provee el servicio o producto)
Código del departamento
E4 E317 cDepProv donde se realiza la E300 N 1-2 1-1 Según XSD de Departamentos
transacción
Descripción del
E4 E318 dDesDepProv departamento donde se E300 A 6-16 1-1 Referente al campo E317
realiza la transacción
Código del distrito donde
E4 E319 cDisProv E300 N 1-4 0-1 Según Tabla 2.1 - Distritos
se realiza la transacción
Descripción del distrito
E4 E320 dDesDisProv donde se realiza la E300 A 1-30 0-1 Obligatorio si existe el campo E319
transacción
Código de la ciudad
E4 E321 cCiuProv donde se realiza la E300 N 1-5 1-1 Según Tabla 2.2 - Ciudades
transacción
Descripción de la ciudad
E4 E322 dDesCiuProv donde se realiza la E300 A 1-30 1-1 Referente al campo E321
transacción
septiembre de 2019 76

--- PAGE 78 / 217 ---

E5. Campos que componen la Nota de Crédito/Débito Electrónica NCE-NDE (E400-E499)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos de la Nota de Obligatorio si C002 = 5 o 6 (NCE y
E5 E400 gCamNCDE Crédito/Débito E001 G 0-1 NDE)
Electrónica No informar si C002 ≠ 5 o 6
1= Devolución y Ajuste de precios
2= Devolución
3= Descuento
4= Bonificación
E5 E401 iMotEmi Motivo de emisión E400 N 1-2 1-1
5= Crédito incobrable
6= Recupero de costo
7= Recupero de gasto
8= Ajuste de precio
Referente al campo E401
1= “Devolución y Ajuste de precios”
2= “Devolución”
3= “Descuento”
Descripción del motivo
E5 E402 dDesMotEmi E400 A 6-30 1-1 4= “Bonificación”
de emisión
5= “Crédito incobrable”
6= “Recupero de costo”
7= “Recupero de gasto”
8= “Ajuste de precio”
E6. Campos que componen la Nota de Remisión Electrónica (E500-E599)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que
Obligatorio si C002 = 7
E6 E500 gCamNRE componen la Nota de E001 G 0-1
No informar si C002 ≠ 7
Remisión Electrónica
septiembre de 2019 77

--- PAGE 79 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
1= Traslado por venta
2= Traslado por consignación
3= Exportación
4= Traslado por compra
5= Importación
6= Traslado por devolución
7= Traslado entre locales de la
empresa
8= Traslado de bienes por
transformación
9= Traslado de bienes por
reparación
E6 E501 iMotEmiNR Motivo de emisión E500 N 1-2 1-1 10= Traslado por emisor móvil
11= Exhibición o demostración
12= Participación en ferias
13= Traslado de encomienda
14= Decomiso
99=Otro (deberá consignarse
expresamente el o los motivos
diferentes a los mencionados
anteriormente)
Obs.: Cuando el motivo sea por
operaciones internas de la empresa,
el RUC del receptor debe ser igual al
RUC del emisor.
septiembre de 2019 78

--- PAGE 80 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Referente al campo E501
1= “Traslado por ventas”
2= “Traslado por consignación”
3= “Exportación”
4= “Traslado por compra”
5= “Importación”
6= “Traslado por devolución”
7= “Traslado entre locales de la
empresa”
E6 E502 dDesMotEmiNR Descripción del motivo E500 A 5-60 1-1 8= “Traslado de bienes por
de emisión transformación”
9= “Traslado de bienes por
reparación”
10= “Traslado por emisor móvil”
11= “Exhibición o Demostración”
12= “Participación en ferias”
13= “Traslado de encomienda”
14= “Decomiso”
Si E501=99 describir el motivo de la
emisión
1= Emisor de la factura
2= Poseedor de la factura y bienes
Responsable de la
3= Empresa transportista
E6 E503 iRespEmiNR emisión de la Nota E500 N 1 1-1
4=Despachante de Aduanas
Remisión Electrónica
5= Agente de transporte o
intermediario
1= “Emisor de la factura”
2= “Poseedor de la factura y
Descripción del
bienes”
responsable de la
E6 E504 dDesRespEmiNR E500 A 20-36 1-1 3= “Empresa transportista”
emisión de la Nota de
4= “Despachante de Aduanas”
Remisión Electrónica
5= “Agente de transporte o
intermediario”
Kilómetros estimados
E6 E505 dKmR E500 N 1-5 0-1
de recorrido
Fecha en el formato AAAA-MM-
DD
Fecha futura de
E6 E506 dFecEm E500 F 10 0-1 Obs.: Informar cuando no se ha
emisión de la factura
emitido aún la factura electrónica,
en caso que corresponda
septiembre de 2019 79

--- PAGE 81 / 217 ---

E7. Campos que describen la condición de la operación (E600-E699)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
Obligatorio si C002 = 1 o 4
E7 E600 gCamCond la condición de la E001 G 0-1
No informar si C002 ≠ 1 o 4
operación
Condición de la 1= Contado
E7 E601 iCondOpe E600 N 1 1-1
operación 2= Crédito
Referente al campo E601
Descripción de la
E7 E602 dDCondOpe E600 A 7 1-1 1= “Contado”
condición de operación
2= “Crédito”
E7.1. Campos que describen la forma de pago de la operación al contado o del monto de la entrega inicial (E605-
E619)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que
describen la forma de Obligatorio si E601 = 1
E7.1 E605 gPaConEIni pago al contado o del E600 G 0-999 Obligatorio si existe el campo
monto de la entrega E645
inicial
septiembre de 2019 80

--- PAGE 82 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
1= Efectivo
2= Cheque
3= Tarjeta de crédito
4= Tarjeta de débito
5= Transferencia
6= Giro
7= Billetera electrónica
8= Tarjeta empresarial
9= Vale
10= Retención
11= Pago por anticipo
E7.1 E606 iTiPago Tipo de pago E605 N 1-2 1-1 12= Valor fiscal
13= Valor comercial
14= Compensación
15= Permuta
16= Pago bancario (Informar solo
si E011=5)
17 = Pago Móvil
18 = Donación
19 = Promoción
20 = Consumo Interno
21 = Pago Electrónico
99 = Otro
septiembre de 2019 81

--- PAGE 83 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Referente al campo E606
1= “Efectivo”
2= “Cheque”
3= “Tarjeta de crédito”
4= “Tarjeta de débito”
5= “Transferencia”
6= “Giro”
7= “Billetera electrónica”
8= “Tarjeta empresarial”
9= “Vale”
10= “Retención”
Descripción del tipo de 11= “Pago por anticipo”
E7.1 E607 dDesTiPag E605 A 4-30 1-1
pago 12= “Valor fiscal”
13= “Valor comercial”
14= “Compensación”
15= “Permuta”.
16= “Pago bancario”
7= “Pago Móvil”
18 = “Donación”
19 = “Promoción”
20 = “Consumo Interno”
21 = “Pago Electrónico”
Si E606 = 99, informar el tipo de
pago
E7.1 E608 dMonTiPag Monto por tipo de pago E605 N 1-15p(0-4) 1-1
Según tabla de códigos para
monedas de acuerdo con la
Moneda por tipo de
E7.1 E609 cMoneTiPag E605 A 3 1-1 norma ISO 4217
pago
Se requiere la misma moneda para
todos los ítems del DE
Descripción de la
E7.1 E610 dDMoneTiPag moneda por tipo de E605 A 3-20 1-1 Referente al campo E609
pago
Tipo de cambio por tipo
E7.1 E611 dTiCamTiPag E605 N 1-5p(0-4) 0-1 Obligatorio si E609 ≠ PYG
de pago
septiembre de 2019 82

--- PAGE 84 / 217 ---

E7.1.1. Campos que describen el pago o entrega inicial de la operación con tarjeta de crédito/débito
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
el pago o entrega inicial
E7.1.1 E620 gPagTarCD E605 G 0-1 Se activa si E606 = 3 o 4
de la operación con
tarjeta de crédito/débito
1= Visa
2= Mastercard
3= American Express
Denominación de la
E7.1.1 E621 iDenTarj E620 N 1-2 1-1 4= Maestro
tarjeta
5= Panal
6= Cabal
99= Otro
Referente al campo E621
1= “Visa”
2= “Mastercard”
3= “American Express”
Descripción de
4= “Maestro”
E7.1.1 E622 dDesDenTarj denominación de la E620 A 4-20 1-1
5= “Panal”
tarjeta
6= “Cabal”
Si E621 = 99 informar la
descripción de la denominación
de la tarjeta
Razón social de la
E7.1.1 E623 dRSProTar E620 A 4-60 0-1
procesadora de tarjeta
RUC de la procesadora
E7.1.1 E624 dRUCProTar E620 A 3-8 0-1
de tarjeta
Dígito verificador del
E7.1.1 E625 dDVProTar RUC de la procesadora E620 N 1 0-1 Según algoritmo módulo 11
de tarjeta
1= POS
Forma de 2= Pago Electrónico (Ejemplo:
E7.1.1 E626 iForProPa E620 N 1 1-1
procesamiento de pago compras por Internet)
9= Otro
Código de autorización
E7.1.1 E627 dCodAuOpe E620 N 6-10 0-1
de la operación
Nombre del titular de la
E7.1.1 E628 dNomTit E620 A 4-30 0-1
tarjeta
septiembre de 2019 83

--- PAGE 85 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
E7.1.1 E629 dNumTarj Número de la tarjeta E620 N 4 0-1 Cuatro últimos dígitos de la tarjeta
E7.1.2. Campos que describen el pago o entrega inicial de la operación con cheque (E630-E639)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
el pago o entrega inicial
E7.1.2 E630 gPagCheq E605 G 0-1 Se activa si E606 = 2
de la operación con
cheque
Completar con 0 (cero) a la
E7.1.2 E631 dNumCheq Número de cheque E630 A 8 1-1 izquierda hasta alcanzar 8 (ocho)
cifras
E7.1.2 E632 dBcoEmi Banco emisor E630 A 4-20 1-1
E7.2. Campos que describen la operación a crédito (E640-E649)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen Obligatorio si E601 = 2
E7.2 E640 gPagCred E600 G 0-1
la operación a crédito No informar si E601 ≠ 2
Condición de la 1= Plazo
E7.2 E641 iCondCred E640 N 1 1-1
operación a crédito 2= Cuota
Descripción de la
1= “Plazo”
E7.2 E642 dDCondCred condición de la E640 A 5-6 1-1
2= “Cuota”
operación a crédito
Obligatorio si E641 = 1
E7.2 E643 dPlazoCre Plazo del crédito E640 A 2-15 0-1
Ejemplo: 30 días, 12 meses
Obligatorio si E641 = 2
E7.2 E644 dCuotas Cantidad de cuotas E640 N 1-3 0-1
Ejemplo: 12, 24, 36
Monto de la entrega 1-15p(0-
E7.2 E645 dMonEnt E640 N 0-1
inicial 4)
septiembre de 2019 84

--- PAGE 86 / 217 ---

E7.2.1. Campos que describen las cuotas (E650-E659)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
E7.2.1 E650 gCuotas E640 G 0-999 Se activa si E641 = 2
las cuotas
Según tabla de códigos para
monedas de acuerdo con la
E7.2.1 E653 cMoneCuo Moneda de las cuotas E650 A 3 1-1 norma ISO 4217
Se requiere la misma moneda
para todos los ítems del DE
Descripción de la
E7.2.1 E654 dDMoneCuo E650 A 3-20 1-1 Referente al campo E653
moneda de las cuotas
1-15p(0-
E7.2.1 E651 dMonCuota Monto de cada cuota E650 N 1-1
4)
Fecha de vencimiento Fecha en el formato: AAAA-MM-
E7.2.1 E652 dVencCuo E650 F 10 0-1
de cada cuota DD
E8. Campos que describen los ítems de la operación (E700-E899)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
E8 E700 gCamItem los ítems de la E001 G 1-999
operación
Código interno de identificación de
la mercadería o servicio de
responsabilidad del emisor. No se
pueden tener ítems distintos de
mercadería o servicio con el mismo
E8 E701 dCodInt Código interno E700 A 1-20 1-1
código interno en su catastro de
productos o servicios. Este código
se puede repetir en el DE siempre
que el producto o servicio sea el
mismo.
E8 E702 dParAranc Partida arancelaria E700 N 4 0-1
Nomenclatura común
E8 E703 dNCM E700 N 6-8 0-1
del Mercosur (NCM)
septiembre de 2019 85

--- PAGE 87 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Obligatorio si D202 = 3
Informar se existe el código de la
Código DNCP – Nivel DNCP
E8 E704 dDncpG E700 A 8 0-1
General Colocar 0 (cero) a la izquierda
para completar los espacios
vacíos
Código DNCP – Nivel Obligatorio si existe el campo
E8 E705 dDncpE E700 A 3-4 0-1
Especifico E704)
Código GTIN por Informar si la mercadería tiene
E8 E706 dGtin E700 N 8,12,13,14 0-1
producto GTIN
Código GTIN por
E8 E707 dGtinPq E700 N 8,12,13,14 0-1 Informar si el paquete tiene GTIN
paquete
Equivalente a nombre del
Descripción del producto
E8 E708 dDesProSer E700 A 1-120 1-1 producto establecido en la RG
y/o servicio
24/2019
Según Tabla 5 – Unidad de
Medida
E8 E709 cUniMed Unidad de medida E700 N 1-5 1-1 Si D202 = 3 utilizar los datos del
WS del link de la DNCP
Utilizar el atributo “ID”
Referente al campo E709
Descripción de la unidad
E8 E710 dDesUniMed E700 A 1-10 1-1 Utilizar el atributo “Código”
de medida
Ejemplo: UNI
Cantidad del producto
E8 E711 dCantProSer E700 N 1-10p(0-4) 1-1
y/o servicio
Código del país de Según XSD de Codificación de
E8 E712 cPaisOrig E700 A 3 0-1
origen del producto Países
Descripción del país de Obligatorio si existe el campo
E8 E713 dDesPaisOrig E700 A 4-30 0-1
origen del producto E712
Información de interés
E8 E714 dInfItem del emisor con respecto E700 A 1-500 0-1
al ítem
Opcional si C002 = 7
Código de datos de
1=Tolerancia de quiebra
E8 E715 cRelMerc relevancia de las E700 N 1 0-1
2= Tolerancia de merma
mercaderías
Según RG 41/14
Descripción del código
1=“Tolerancia de quiebra”
E8 E716 dDesRelMerc de datos de relevancia E700 A 19-21 0-1
2=“Tolerancia de merma”
de las mercaderías
septiembre de 2019 86

--- PAGE 88 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Obligatorio si se informa E715
Lo informado en este campo se
Cantidad de quiebra o
E8 E717 dCanQuiMer E700 N 1-10(0-4) 0-1 encuentra en la unidad de medida
merma
elegida en E709
Según RG 41/14
Porcentaje de quiebra o Obligatorio si se informa E715
E8 E718 dPorQuiMer E700 N 1-3(0-8) 0-1
merma Según RG 41/14
Obligatorio cuando se utilice una
factura asociada con el tipo de
E8 E719 dCDCAnticipo CDC del anticipo E700 A 44 0-1 transacción igual a Anticipo
(D011 de la factura asociada
igual a 9)
E8.1. Campos que describen el precio, tipo de cambio y valor total de la operación por ítem (E720-E729)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
Obligatorio si C002 ≠ 7
E8.1 E720 gValorItem los precios, descuentos E700 G 0-1
No informar si C002 = 7
y valor total por ítem
Precio unitario del
1-15p(0-
E8.1 E721 dPUniProSer producto y/o servicio E720 N 1-1
8)
(incluidos impuestos)
Obligatorio si D015 ≠ PYG
E8.1 E725 dTiCamIt Tipo de cambio por ítem E720 N 1-5p(0-4) 0-1 Obligatorio si D017 = 2
No informar si D017 = 1
Corresponde a la multiplicación
Total bruto de la 1-15p(0-
E8.1 E727 dTotBruOpeItem E720 N 1-1 del precio por ítem (E721) y la
operación por ítem 8)
cantidad por ítem (E711)
E8.1.1 Campos que describen los descuentos, anticipos y valor total por ítem (EA001-EA050)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Campos que describen
los descuentos,
E8.1.1 EA001 gValorRestaItem E720 G 1-1
anticipos valor total por
ítem
septiembre de 2019 87

--- PAGE 89 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Descuento particular
E8.1.1 EA002 dDescItem
sobre el precio unitario
EA001 N
1-15p(0-
0-1
Si no hay descuento por ítem
por ítem (incluidos 8) completar con 0 (cero)
impuestos)
Porcentaje de Debe existir si EA002 es mayor a
E8.1.1 EA003 dPorcDesIt descuento particular EA001 N 1-3p(0-8) 0-1 0 (cero)
por ítem [EA002 * 100 / E721]
Si se cuenta con un descuento
Descuento global sobre global, debe ser aplicado (no es
E8.1.1 EA004 dDescGloItem
el precio unitario por
EA001 N
1-15p(0-
0-1
prorrateo) a cada uno de los
ítem (incluidos 8) ítems, independientemente que un
impuestos) ítem cuente con un descuento
particular.
Se debe informar en la misma
denominación monetaria en la que
Anticipo particular
se informó en la FE de anticipo
E8.1.1 EA006 dAntPreUniIt
sobre el precio unitario
EA001 N
1-15p(0-
0-1 asociada (D015 de la FE
por ítem (incluidos 8)
asociada)
impuestos)
Si no hay anticipo por ítem
completar con 0 (cero)
Si se cuenta con un anticipo
global, debe ser aplicado a cada
uno de los ítems,
Anticipo global sobre el
E8.1.1 EA007 dAntGloPreUniIt precio unitario por ítem N
1-15p(0-
0-1
independientemente de que un
(incluidos impuestos) EA001
8) ítem cuente con un anticipo
particular.
Si no hay anticipo global por ítem,
completar con 0 (cero)
septiembre de 2019 88

--- PAGE 90 / 217 ---

Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Cálculo para IVA, Renta,
ninguno, IVA - Renta
Si D013 = 1, 3, 4 o 5 (afectado al
IVA, Renta, ninguno, IVA - Renta),
entonces EA008 corresponde al
cálculo aritmético: (E721 (Precio
E8.1.1 EA008 dTotOpeItem
Valor total de la
EA001 N
1-15p(0-
1-1
unitario) – EA002 (Descuento
operación por ítem 8) particular) – EA004 (Descuento
global) – EA006 (Anticipo
particular) – EA007 (Anticipo
global)) * E711(cantidad)
Cálculo para Autofactura
(C002=4):
E721*E711
Obligatorio si existe el campo
Valor total de la
E8.1.1 EA009 dTotOpeGs operación por ítem en EA001 N
1-15p(0-
0-1
E725
8) Corresponde al cálculo aritmético
guaraníes
EA008* E725
E8.2. Campos que describen el IVA de la operación por ítem (E730-E739)
Nodo Tipo
Grupo ID Campo Descripción Longitud Ocurrencia Observaciones
Padre Dato
Obligatorio si D013=1, 3, 4 o 5 y
Campos que describen C002 ≠ 4 o 7
E8.2 E730 gCamIVA E700 G 0-1
el IVA de la operación No informar si D013=2 y C002= 4
o 7
1= Gravado IVA
2= Exonerado (Art. 83- Ley
Forma de afectación
E8.2 E731 iAfecIVA E730 N 1 1-1 125/91)
tributaria del IVA
3= Exento
4= Gravado parcial (Grav-Exento)
septiembre de 2019 89
```
