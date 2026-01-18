# Git Hooks

Este directorio contiene hooks personalizados de Git para el proyecto.

## pre-push

Hook que ejecuta el smoke test 0160 automáticamente al hacer push si hay cambios en archivos relacionados con SIFEN.

### Archivos monitoreados:
- `tesaka-cv/tools/send_sirecepde.py`
- `tesaka-cv/app/sifen_client/soap_client.py`
- `tesaka-cv/app/sifen_client/sifen_client.py`
- `tesaka-cv/app/sifen/sifen_build_soap12_envelope.py`
- `tesaka-cv/app/sifen/xmldsig_signer.py`
- `tesaka-cv/app/sifen/sifen_xml_utils.py`

### Comportamiento:
- Si no hay cambios en estos archivos, el hook no se ejecuta
- Si hay cambios, busca un XML firmado en `artifacts/signed_lote.xml`
- Ejecuta el smoke test 0160
- Si falla, bloquea el push y muestra el error

### Instalación:
```bash
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
```
