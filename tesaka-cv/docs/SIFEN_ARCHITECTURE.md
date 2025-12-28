# Arquitectura de Integración SIFEN

## Decisión de Arquitectura

**✅ Mantener FastAPI + Jinja2 (Server-Side Rendering)**

### Razones:
1. **Simplicidad**: La aplicación actual funciona bien con templates Jinja2
2. **No requiere Angular**: El Prevalidador SIFEN es una aplicación web externa (hecha por DNIT)
3. **Separación de responsabilidades**: 
   - Backend FastAPI: Lógica de negocio, generación XML, comunicación con SIFEN
   - Frontend Jinja2: Presentación y formularios
   - Prevalidador SIFEN: Validación externa (aplicación web Angular del DNIT)

## Flujo de Integración SIFEN

```
┌─────────────────┐
│  Usuario        │
│  (Navegador)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  FastAPI App    │
│  (Jinja2 UI)    │
└────────┬────────┘
         │
         ├──► Genera XML según esquema SIFEN
         │
         ├──► Valida estructura localmente
         │
         ├──► [Opcional] Usuario valida en Prevalidador web
         │    (https://ekuatia.set.gov.py/prevalidador/validacion)
         │
         └──► Envía XML a servicios SIFEN (ambiente pruebas/prod)
              │
              ▼
         ┌─────────────────┐
         │  Servicios SIFEN│
         │  (DNIT/SET)     │
         └─────────────────┘
```

## Componentes de la Integración

### 1. Backend FastAPI (`app/sifen_client/`)
- **`config.py`**: Configuración por ambiente (test/prod)
- **`client.py`**: Cliente HTTP para comunicación con servicios SIFEN
- **`validator.py`**: Validación XML local + integración Prevalidador
- **`models.py`**: Modelos de datos
- **`utils.py`**: Utilidades

### 2. Frontend Jinja2 (`app/templates/`)
- Templates HTML con formularios
- JavaScript para interactividad (fetch API)
- No requiere Angular ni frameworks frontend pesados

### 3. Prevalidador SIFEN (Externo)
- Aplicación web Angular del DNIT
- URL: https://ekuatia.set.gov.py/prevalidador/validacion
- Uso: Manual por el usuario o API programática (si disponible)

## Ventajas de esta Arquitectura

✅ **Simple**: Sin complejidad de SPA o frameworks frontend  
✅ **Rápido**: Server-side rendering, carga inicial rápida  
✅ **SEO-friendly**: HTML completo desde el servidor  
✅ **Mantenible**: Un solo stack (Python/FastAPI)  
✅ **Funcional**: Cumple todos los requisitos de integración SIFEN  

## Flujo de Validación

### Opción 1: Validación Local (Recomendada para desarrollo)
```python
# En FastAPI
validator = SifenValidator()
result = validator.validate_against_xsd(xml_content)
# Validar estructura, campos requeridos, etc.
```

### Opción 2: Prevalidador Web (Manual)
1. Usuario genera XML en nuestra app
2. Usuario copia XML
3. Usuario va a https://ekuatia.set.gov.py/prevalidador/validacion
4. Usuario pega XML en formulario web
5. Prevalidador muestra resultado

### Opción 3: API Programática (Si está disponible)
```python
# Cuando se confirme API del Prevalidador
result = validator.prevalidate_with_service(xml_content)
```

## Endpoints FastAPI

- `POST /dev/sifen-smoke-test` - Smoke test completo
- `GET /dev/sifen-smoke-test` - UI para testing
- `POST /dev/sifen-prevalidate` - Prevalidar XML
- `POST /sifen/documentos/enviar` - Enviar DE (cuando esté listo)
- `GET /sifen/documentos/{id}/consultar` - Consultar estado (cuando esté listo)

## Próximos Pasos

1. ✅ Estructura base creada
2. ⏳ Obtener documentación oficial (XSD, endpoints, datos prueba)
3. ⏳ Completar generador de XML según esquema oficial
4. ⏳ Implementar envío real cuando tengamos credenciales
5. ⏳ Agregar persistencia de resultados en BD

---

**Conclusión**: La arquitectura actual (FastAPI + Jinja2) es perfecta para la integración SIFEN. No se requiere Angular ni cambios arquitectónicos mayores.

