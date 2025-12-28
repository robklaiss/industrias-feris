# Runner Node.js para xmlgen Oracle

Este directorio contiene el runner CommonJS para usar `facturacionelectronicapy-xmlgen` como oráculo de validación.

## Instalación

```bash
cd tools/node
npm install
```

Esto instalará `facturacionelectronicapy-xmlgen` desde el repositorio de GitHub.

## Uso Directo

```bash
# Ejecutar runner con archivos JSON
node xmlgen_runner.cjs --params params.json --data data.json [--options options.json]
```

El XML generado se escribe a stdout.

## Integración con Oracle Compare

El runner es llamado automáticamente por `tools/oracle_compare.py`. No es necesario invocarlo manualmente.

## Formato de Input

- **params.json**: Datos estáticos del emisor (RUC, razón social, timbrado, etc.)
- **data.json**: Datos variables del DE (receptor, items, totales, etc.)
- **options.json**: Opciones adicionales (opcional)

Ver `tools/oracle_compare.py` para el mapeo desde `de_input.json` a estos formatos.

