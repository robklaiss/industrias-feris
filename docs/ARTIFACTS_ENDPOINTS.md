# Artifacts Download Endpoints - Implementation Summary

## Overview
Se han implementado endpoints en FastAPI para permitir la descarga de artifacts generados por SIFEN.

## Endpoints Implementados

### 1. GET /api/v1/artifacts/latest
Retorna información del lote más reciente y los artifacts disponibles.

```bash
curl -s http://localhost:8000/api/v1/artifacts/latest | jq .
```

### 2. GET /api/v1/artifacts/{dId}
Retorna información sobre los artifacts disponibles para un dId específico.

```bash
curl -s http://localhost:8000/api/v1/artifacts/202601220154287 | jq .
```

### 3. GET /api/v1/artifacts/{dId}/de
Descarga el DE_TAL_CUAL_TRANSMITIDO.xml para un dId específico.

```bash
curl -s http://localhost:8000/api/v1/artifacts/202601220154287/de \
  -o DE_TAL_CUAL_TRANSMITIDO_202601220154287.xml
```

### 4. GET /api/v1/artifacts/{dId}/rechazo
Descarga el XML_DE_RECHAZO.xml para un dId específico (si existe).

```bash
curl -s http://localhost:8000/api/v1/artifacts/202601220154287/rechazo \
  -o XML_DE_RECHAZO_202601220154287.xml
```

### 5. GET /api/v1/artifacts/{dId}/meta
Descarga la metadata JSON para un dId específico (si existe).

```bash
curl -s http://localhost:8000/api/v1/artifacts/202601220154287/meta \
  -o metadata_202601220154287.json
```

## Interface Web

Se ha creado una página web en `/artifacts` que muestra:
- El último lote enviado con botones de descarga
- Historial de lotes con disponibilidad de archivos
- Botones para descargar cada tipo de artifact

## Características de Seguridad

1. **Validación de dId**: Solo se permiten dIds numéricos con longitud mínima de 10 dígitos
2. **Path Traversal Protection**: Los archivos se buscan solo en el directorio artifacts/ usando patrones predefinidos
3. **Read-Only**: Los endpoints solo permiten lectura, no escritura
4. **Content-Type Headers**: Se envían los headers correctos (application/xml, application/json)
5. **Content-Disposition**: Los archivos se descargan con nombres descriptivos

## Estructura de Archivos

- **DE Transmitido**: Se busca en archivos `sent_lote_{dId}_{timestamp}.xml`
- **XML Rechazo**: Se extrae del campo `raw_xml` en archivos `response_recepcion_*.json`
- **Metadata**: Se busca en archivos JSON que contengan el dId

## Testing

Para probar todos los endpoints, ejecutar:

```bash
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado
./test_artifacts_endpoints.sh
```

## Archivos Modificados

1. `/tesaka-cv/app/routes_artifacts.py` - Nuevo archivo con los endpoints
2. `/tesaka-cv/app/main.py` - Registro de las nuevas rutas
3. `/tesaka-cv/app/templates/artifacts/list.html` - Template para la página web
4. `/test_artifacts_endpoints.sh` - Script de testing

## Notas

- Los endpoints usan el prefijo `/api/v1/` para versionamiento
- Los nombres de archivo descargados incluyen el dId para evitar conflictos
- La página web se actualiza automáticamente para mostrar el último lote
