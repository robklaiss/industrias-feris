# Oracle: facturacionelectronicapy-xmlgen

Este directorio contiene el wrapper para usar `facturacionelectronicapy-xmlgen` como oráculo de validación.

## Instalación

```bash
cd tools/oracles/xmlgen
npm install
```

Esto instalará `facturacionelectronicapy-xmlgen` desde el repositorio de GitHub.

## Uso

```bash
# Generar DE desde JSON de entrada
node generate_de.js <input_json_path> [output_xml_path]

# Ejemplo
node generate_de.js ../../examples/de_input.json ../../artifacts/oracle_de_test.xml
```

## Formato de Input JSON

El script espera un JSON con la siguiente estructura:

```json
{
  "buyer": {
    "ruc": "80012345",
    "dv": "7",
    "nombre": "Empresa Ejemplo S.A.",
    ...
  },
  "transaction": {
    "numeroTimbrado": "12345678",
    "numeroComprobanteVenta": "001-001-00000001",
    ...
  },
  "items": [
    {
      "cantidad": 10.5,
      "precioUnitario": 1000.0,
      "descripcion": "Producto",
      "tasaAplica": 10
    }
  ]
}
```

Ver `examples/de_input.json` para el formato completo.

## Notas

- El formato exacto depende de la API de `facturacionelectronicapy-xmlgen`
- Si el formato cambia, actualizar `generate_de.js` para mapear correctamente
- Revisar documentación del repo: https://github.com/TIPS-SA/facturacionelectronicapy-xmlgen

