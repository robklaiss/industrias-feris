# SIFEN Smoke Test

Smoke test 100% reproducible para validar conectividad con SIFEN (ambiente DEV) usando la librería `rshk-jsifenlib`.

## Descripción

Este módulo ejecuta una consulta RUC contra SIFEN para validar:
- Conectividad con el servidor SIFEN
- Validez del certificado PFX
- Configuración correcta del CSC (Código de Seguridad)
- Funcionamiento básico de la librería

## Requisitos

- Java 8 o superior
- Maven 3.6 o superior
- Certificado PFX válido para SIFEN
- Acceso a internet (para conectarse a SIFEN)

## Configuración Rápida

1. **Copiar el archivo de ejemplo:**
   ```bash
   cd sifen-smoketest
   cp .env.example .env
   ```

2. **Editar `.env` con tus valores:**
   - `PFX_PATH`: Ruta completa a tu certificado PFX
   - `PFX_PASSWORD`: Contraseña del certificado
   - `CSC_ID` y `CSC`: Código de Seguridad (opcional pero recomendado)
   - `RUC_QUERY`: RUC a consultar (puede ser el tuyo o cualquier otro)

3. **Ejecutar el smoke test:**
   ```bash
   ./run.sh
   ```

## Variables de Entorno

El script `run.sh` carga automáticamente las variables desde `.env` si existe. También puedes definir las variables directamente en el shell:

```bash
export SIFEN_ENV=DEV
export PFX_PATH=/ruta/al/certificado.pfx
export PFX_PASSWORD=xxxxx
export CSC_ID=0001
export CSC=ABCD0000000000000000000000000000
export RUC_QUERY=80012345-7
./run.sh
```

### Variables Requeridas

- `PFX_PATH`: Ruta al archivo certificado PFX (requerido)
- `PFX_PASSWORD`: Contraseña del certificado PFX (requerido)
- `RUC_QUERY`: RUC a consultar, puede incluir DV (ej: `80012345-7`) (requerido)

### Variables Opcionales

- `SIFEN_ENV`: Ambiente (`DEV` o `PROD`). Default: `DEV`
- `CSC_ID`: ID del Código de Seguridad. Si no se proporciona, se usan valores por defecto
- `CSC`: Código de Seguridad. Si no se proporciona, se usan valores por defecto

## Salida Esperada

### Éxito (SMOKETEST: OK)
```
Consultando RUC: 80012345 (ambiente: DEV)
SMOKETEST: OK
Código HTTP: 200
Código Respuesta: 0500
Mensaje: [mensaje de SIFEN]

Datos del Contribuyente:
  RUC: 80012345
  Razón Social: EMPRESA EJEMPLO S.A.
  Código Estado: 01
  Descripción Estado: Activo
  RUC Facturación Electrónica: 80012345
```

### Error (SMOKETEST: FAIL)
```
SMOKETEST: FAIL
Código HTTP: 200
Código Respuesta: 0502
Mensaje: [mensaje de error de SIFEN]
```

O en caso de excepción:
```
SMOKETEST: FAIL
Excepción SIFEN: [descripción del error]
```

## Compilación Manual

Si prefieres compilar y ejecutar manualmente:

```bash
# Compilar
mvn clean package

# Ejecutar
mvn exec:java
```

O ejecutar el JAR directamente:
```bash
mvn clean package
java -jar target/sifen-smoketest-1.0.0.jar
```

## Troubleshooting

### 1. PFX Incorrecto

**Síntoma:**
```
SMOKETEST: FAIL
Excepción SIFEN: Error al cargar el certificado
```

**Solución:**
- Verificar que la ruta `PFX_PATH` sea correcta y el archivo exista
- Verificar que el archivo sea un PFX válido
- Asegurarse de tener permisos de lectura sobre el archivo

### 2. Password Incorrecto

**Síntoma:**
```
SMOKETEST: FAIL
Excepción SIFEN: Error al acceder al certificado / Contraseña incorrecta
```

**Solución:**
- Verificar que `PFX_PASSWORD` sea la contraseña correcta del certificado
- Asegurarse de que no haya espacios en blanco al inicio/final de la contraseña
- Verificar que el certificado no esté corrupto

### 3. CSC Incorrecto

**Síntoma:**
```
SMOKETEST: FAIL
Código Respuesta: 0502
Mensaje: Error en la validación del CSC
```

**Solución:**
- Verificar que `CSC_ID` y `CSC` sean correctos según la documentación de SIFEN
- Asegurarse de que el CSC corresponda al ambiente correcto (DEV vs PROD)
- Verificar que el CSC no haya expirado

### 4. Reloj del Sistema Desincronizado

**Síntoma:**
```
SMOKETEST: FAIL
Excepción SIFEN: Error de firma digital / Certificado expirado
```

**Solución:**
- Verificar que la fecha y hora del sistema sean correctas
- Sincronizar el reloj del sistema con un servidor NTP
- En Linux/Mac: `sudo ntpdate -s time.nist.gov` o `sudo timedatectl set-ntp true`
- En Windows: Configurar sincronización automática de tiempo

### 5. Problema TLS/CA

**Síntoma:**
```
SMOKETEST: FAIL
Excepción SIFEN: Error de conexión SSL / Handshake failed
```

**Solución:**
- Verificar conectividad a internet
- Verificar que no haya firewall bloqueando la conexión a `sifen-test.set.gov.py` (DEV) o `sifen.set.gov.py` (PROD)
- Verificar que los certificados CA de Java estén actualizados
- Actualizar Java si es necesario
- Verificar que el certificado del servidor SIFEN sea válido

## Notas Técnicas

- El RUC se puede proporcionar con o sin dígito verificador. El script extrae automáticamente solo el RUC.
- El código de respuesta `0500` indica éxito en SIFEN.
- El código de respuesta `0502` indica error en la consulta (RUC no encontrado, CSC inválido, etc.).
- El código HTTP `200` indica que la comunicación con el servidor fue exitosa, pero el código de respuesta SIFEN puede indicar un error de negocio.

## Dependencias

Este módulo depende de:
- `com.roshka.sifen:rshk-jsifenlib:0.2.4` (desde Maven Central)

Si necesitas usar una versión local de la librería, compílala primero con Gradle:
```bash
cd ../rshk-jsifenlib
./gradlew publishToMavenLocal
```

Luego actualiza el `pom.xml` para usar la versión local o cambia el repositorio.

## Licencia

Este módulo es parte del proyecto de facturación electrónica y sigue la misma licencia que el proyecto principal.

