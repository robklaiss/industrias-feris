# Wrapper SIFEN - make_de_wrapper.sh

Script universal para generar XML SIFEN → firmar → recalcular QR en un solo comando.

## Configuración por ambiente

El wrapper soporta ambientes `test` y `prod` con carga automática de credenciales desde archivo `.env`.

### 1. Crear archivo .env

```bash
# Copiar plantilla
cp .env.example .env

# Editar con tus credenciales reales
nano .env
```

**Importante**: Nunca commitear el archivo `.env` con secretos reales. Solo `.env.example` va al repo.

### 2. Variables de entorno

El wrapper busca las variables en este orden:

1. **Override directo** (máxima prioridad):
   ```bash
   export SIFEN_IDCSC="0001"
   export SIFEN_CSC="TU_CSC_SECRETO"
   ```

2. **Por ambiente** (recomendado):
   - Test: `SIFEN_IDCSC_TEST` / `SIFEN_CSC_TEST`
   - Prod: `SIFEN_IDCSC_PROD` / `SIFEN_CSC_PROD`

3. **Variable de ambiente**: `SIFEN_ENV=test|prod` (default: `test`)

### 3. Archivos .env soportados

El wrapper busca automáticamente en este orden:
- `.env` en la raíz del repo
- `.env.sifen` en la raíz del repo
- Path personalizado con `--env-file`

## Uso básico

### Opción 1: Flujo Prevalidador (recomendado)

El `generar_prevalidador.py` ya incluye la firma, por lo que solo generamos y recalculamos QR:

```bash
# Usando ambiente test (default)
./tools/make_de_wrapper.sh \
  --gen '.venv/bin/python tools/generar_prevalidador.py' \
  --sign 'echo "YA FIRMA EL GENERADOR"' \
  --out '~/Desktop/de_final.xml'

# Usando ambiente producción
./tools/make_de_wrapper.sh \
  --env prod \
  --gen '.venv/bin/python tools/generar_prevalidador.py' \
  --sign 'echo "YA FIRMA EL GENERADOR"' \
  --out '~/Desktop/de_final.xml'
```

### Opción 2: Flujo manual completo

Si necesitas separar generación y firma:

```bash
# Con archivo .env personalizado
./tools/make_de_wrapper.sh \
  --env-file '/path/al/.env' \
  --env test \
  --gen '.venv/bin/python tools/generar_xml_desde_cero.py --out /tmp/sifen_de.xml' \
  --sign '.venv/bin/python tools/firmar_xml.py --in /tmp/sifen_de.xml --out /tmp/sifen_de_signed.xml' \
  --out '~/Desktop/de_final.xml'
```

### Opción 3: Override directo (sin .env)

```bash
# Para pruebas rápidas
export SIFEN_IDCSC="0001"
export SIFEN_CSC="TESTING"

./tools/make_de_wrapper.sh \
  --gen '.venv/bin/python tools/generar_prevalidador.py' \
  --sign 'echo "YA FIRMA EL GENERADOR"' \
  --out '~/Desktop/de_final.xml'
```

## Opciones

- `--env-file PATH`: Archivo .env personalizado (default: .env o .env.sifen)
- `--env test|prod`: Ambiente a usar (default: test)
- `--keep-tmp`: No borra los archivos temporales (`/tmp/sifen_de.xml` y `/tmp/sifen_de_signed.xml`)
- `-h, --help`: Muestra la ayuda

## Seguridad

- **El CSC nunca se muestra en los logs** (aparece como `***`)
- **IdCSC sí se muestra** porque no es secreto
- **El archivo .env nunca debe ir al repositorio**
- **Usa credenciales diferentes para test y prod**

## Flujo interno

1. **Generación**: Ejecuta `--gen` → produce XML sin firma
2. **Firma**: Ejecuta `--sign` → produce XML firmado
3. **QR**: Usa `make_valid_de.py` → recalcula dCarQR sin tocar firma
4. **Resultado**: XML final listo para el Prevalidador SIFEN

## Ejemplo completo

```bash
#!/bin/bash
# Configurar credenciales
export SIFEN_IDCSC="0001"
export SIFEN_CSC="MI_CSC_SECRETO"

# Ejecutar wrapper
./tools/make_de_wrapper.sh \
  --gen '.venv/bin/python tools/generar_prevalidador.py' \
  --sign 'echo "YA FIRMA EL GENERADOR"' \
  --out '~/Desktop/factura_final.xml'

# Verificar QR generado
grep -o 'cHashQR=[^&]*' ~/Desktop/factura_final.xml
```

## Notas

- El wrapper detecta automáticamente si `generar_prevalidador.py` ya firmó el XML
- Los archivos temporales se guardan en `/tmp/` por defecto
- El XML final mantiene la firma digital intacta, solo se recalcula el QR

## Troubleshooting

- **"No encuentro XML generado"**: Asegúrate que tu `--gen` cree `/tmp/sifen_de.xml`
- **"No encuentro XML firmado"**: Asegúrate que tu `--sign` cree `/tmp/sifen_de_signed.xml`
- **"Falta SIFEN_IDCSC/SIFEN_CSC"**: Exporta las variables de entorno antes de ejecutar
