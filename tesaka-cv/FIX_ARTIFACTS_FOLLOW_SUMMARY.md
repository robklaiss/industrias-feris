# Fix Artifacts + Follow endpoints - MODO TEST

## Cambios realizados

### 1. app/routes_artifacts.py
- **Problema**: `validate_did` y todas las rutas estaban indentadas dentro de `register_artifacts_routes`, lo que impedía que se registraran correctamente.
- **Solución**: Reescribí el archivo para que:
  - `validate_did` esté a nivel de módulo (puede ser importado)
  - Todas las rutas `@app.get("/api/v1/artifacts/...")` estén registradas correctamente
  - Las rutas funcionen como se espera

### 2. app/routes_emit.py
- **Problema**: El endpoint `/api/v1/follow` no validaba que el parámetro `prot` no estuviera vacío.
- **Solución**: Agregué validaciones:
  - Si `prot` es `None` o vacío, devuelve 400 con mensaje claro
  - Si `prot` contiene solo espacios, devuelve 400 con mensaje claro
  - Evita llamar a SIFEN si `prot` está vacío

### 3. tools/debug_routes.py
- **Creado**: Script para verificar que las rutas estén registradas
- **Funcionalidad**:
  - Lista todas las rutas `/api/v1/` registradas
  - Verifica que las rutas esperadas existan
  - Confirma que `validate_did` sea importable y funcione

### 4. tools/test_endpoints.py  
- **Creado**: Script de prueba para verificar el funcionamiento de los endpoints
- **Tests**:
  - `/api/v1/artifacts/latest` - devuelve 404 si no hay artifacts
  - `/api/v1/artifacts/{did}` - maneja dids inválidos
  - `/api/v1/follow` - valida parámetro `prot` correctamente

## Verificación

```bash
# Verificar rutas registradas
cd tesaka-cv
python3 tools/debug_routes.py

# Probar endpoints
python3 tools/test_endpoints.py
```

## Resultado

✅ Todas las rutas están registradas y funcionando en MODO TEST
✅ `/api/v1/artifacts/{did}` devuelve JSON con available/endpoints
✅ `/api/v1/artifacts/{did}/meta` funciona (404 si no hay meta)
✅ `/api/v1/follow` valida que `prot` no esté vacío (devuelve 400)
✅ MODO TEST forzado (no se puede usar prod)

## Notas

- FastAPI maneja path traversal (`../`) a nivel de router, devolviendo 404 antes de llegar a nuestra validación (esto es seguro)
- Todos los cambios mantienen el modo TEST forzado como se solicitó
- Los endpoints están listos para usarse en el ambiente de prueba
