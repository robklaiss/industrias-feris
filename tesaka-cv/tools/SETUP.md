# Setup de Herramientas SIFEN

## Instalación de Dependencias

```bash
# Desde el directorio raíz del proyecto
pip install -r tesaka-cv/app/requirements.txt
```

O instalar solo las necesarias para las herramientas:

```bash
pip install lxml requests
```

## Uso Rápido

### 1. Descargar XSD Oficiales

```bash
cd tesaka-cv
python -m tools.download_xsd
```

Los XSD se guardarán en `tesaka-cv/xsd/`

### 2. Validar un XML

```bash
cd tesaka-cv
python -m tools.validate_xml archivo.xml
```

Con prevalidación SIFEN:

```bash
python -m tools.validate_xml archivo.xml --prevalidate
```

## Estructura de Archivos

```
tesaka-cv/
├── tools/
│   ├── download_xsd.py     # Descarga XSD oficiales
│   ├── validate_xml.py     # Valida XML contra XSD
│   └── README.md           # Documentación completa
├── xsd/                    # XSD descargados (se crea automáticamente)
├── manual/                 # Documentación manual (opcional)
└── app/
    └── sifen_client/
        └── validator.py    # Validador integrado (usa XSD)
```

## Ejemplos

### Ejemplo 1: Validar XML del smoke test

```bash
# Generar XML de prueba
cd tesaka-cv
python3 -c "
from app.sifen_client.xml_generator import create_minimal_test_xml
xml = create_minimal_test_xml()
with open('test.xml', 'w') as f:
    f.write(xml)
print('XML generado: test.xml')
"

# Validar
python -m tools.validate_xml test.xml --prevalidate
```

### Ejemplo 2: Solo validar estructura

```bash
python -m tools.validate_xml archivo.xml --xsd-dir /ruta/custom/xsd
```

## Troubleshooting

### Error: "XSD no encontrado"
- Ejecuta: `python -m tools.download_xsd`
- O especifica XSD manualmente: `--xsd xsd/DE_v150.xsd`

### Error: "lxml no instalado"
- Instala: `pip install lxml`

### Error: "requests no instalado"
- Instala: `pip install requests`

