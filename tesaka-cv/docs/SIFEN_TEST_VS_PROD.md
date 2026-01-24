# SIFEN: TEST vs PROD (perfiles y switch rápido)

Este repo soporta 2 perfiles:
- **TEST**: sandbox SIFEN (no impacta producción)
- **PROD**: producción SIFEN (impacta producción)

## 1) Dónde se define cada perfil
Los perfiles viven en:
- `config/sifen_test.env` 
- `config/sifen_prod.env` 

El wrapper para ejecutar es:
- `tools/sifen_run.sh` 

## 2) Cómo cambiar de TEST a PROD (y viceversa)
**La selección es SOLO el primer argumento del wrapper.** No hay migraciones ni "trabajo extra".

Ejemplos:

### Enviar (send)
- TEST:
  `./tools/sifen_run.sh test send --xml /path/a.xml --artifacts-dir /path/artifacts --iteration 1 --bump-doc 1 --dump-http` 
- PROD:
  `./tools/sifen_run.sh prod send --xml /path/a.xml --artifacts-dir /path/artifacts --iteration 1 --bump-doc 1 --dump-http` 

### Follow (follow)
- TEST:
  `./tools/sifen_run.sh test follow --once /path/response.json --artifacts-dir /path/artifacts` 
- PROD:
  `./tools/sifen_run.sh prod follow --once /path/response.json --artifacts-dir /path/artifacts` 

### Auto-fix loop (autofix)
- TEST:
  `./tools/sifen_run.sh test autofix --xml /path/a.xml --artifacts-dir /path/artifacts --max-iters 10 --start-iteration 1 --bump-doc 1 --dump-http` 
- PROD:
  `./tools/sifen_run.sh prod autofix --xml /path/a.xml --artifacts-dir /path/artifacts --max-iters 10 --start-iteration 1 --bump-doc 1 --dump-http` 

## 3) Qué cambia entre TEST y PROD (lo importante)
### 3.1 Endpoints / WSDL
- TEST usa base `https://sifen-test.set.gov.py/...` 
- PROD usa base `https://sifen.set.gov.py/...` 

Esto lo resuelve `app/sifen_client/config.py` según `SIFEN_ENV`.

### 3.2 Certificados (mTLS)
El cliente soporta 2 modos mTLS (resuelto por `get_mtls_config()`):
- **Modo PEM (preferido)**: `SIFEN_CERT_PATH` + `SIFEN_KEY_PATH` 
- **Modo P12 (fallback)**: `SIFEN_MTLS_P12_PATH` + `SIFEN_MTLS_P12_PASSWORD` (o equivalentes)

Regla anti-regresión:
- **Nunca** tratar `.pem/.crt/.key` como PKCS#12.

### 3.3 Riesgo de "facturas falsas"
- En **PROD**, cada envío puede quedar registrado (aunque sea rechazado).
- En **TEST**, no afecta producción.

Por eso, para loops automáticos (autofix), **recomendado** hacerlo en TEST hasta que el XML pase.

## 4) Checklist rápido antes de correr
- ¿Estoy usando el perfil correcto? (`test` vs `prod`)
- ¿Artifacts van a la carpeta correcta? (ej: Desktop/SIFEN_ARTIFACTS_TEST_*)
- ¿Certs en modo PEM están presentes? (`SIFEN_CERT_PATH` + `SIFEN_KEY_PATH`)
- ¿Evité usar PROD para loops? (solo cuando ya está validado en TEST)

## 5) Ver diferencias entre perfiles (comando)
```bash
diff -u config/sifen_test.env config/sifen_prod.env || true
```
