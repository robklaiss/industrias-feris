# Checklist de Validación Final - SIFEN Pre-validador

## Ejecutar ANTES de subir XML a SIFEN

### 1. Regenerar XML con fix aplicado

```bash
cd ~/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv
export SIFEN_SIGN_P12_PASSWORD='bH1%T7EP'
source scripts/sifen_env.sh
bash scripts/preval_smoke_prevalidator.sh
```

**Verificar:** Debe terminar con "OK -> Archivo a subir: ~/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml"

---

### 2. Ejecutar Suite de Tests Automáticos

```bash
cd ~/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv
python tests/test_qr_validation.py
```

**Esperado:** 
```
RESULTADOS: 9 passed, 0 failed
```

**Si falla algún test:** NO subir a SIFEN. Revisar el output del test que falló.

---

### 3. Verificación Manual de cHashQR (crítico)

```bash
python3 << 'EOF'
import xml.etree.ElementTree as ET
import re

tree = ET.parse('/Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml')
root = tree.getroot()
ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
qr = root.find('.//sifen:dCarQR', ns)
qr_url = qr.text.strip().replace('&amp;', '&')

match = re.search(r'cHashQR=([a-fA-F0-9]+)', qr_url)
if match:
    chash = match.group(1)
    print(f"cHashQR: {chash}")
    print(f"Lowercase: {chash == chash.lower()}")
    print(f"Uppercase: {chash == chash.upper()}")
    print(f"Longitud: {len(chash)}")
    
    if chash == chash.lower() and len(chash) == 64:
        print("\n✓ cHashQR CORRECTO (lowercase, 64 chars)")
    else:
        print("\n✗ cHashQR INCORRECTO")
        exit(1)
EOF
```

**Esperado:**
```
cHashQR: a4b355cffbe09f12a52c8bae13dfb77f1134fb179b906abbb13ee9372d967313
Lowercase: True
Uppercase: False
Longitud: 64

✓ cHashQR CORRECTO (lowercase, 64 chars)
```

---

### 4. Verificar Firma Digital

```bash
python -m tools.verify_xmlsec ~/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml
```

**Esperado:**
```
SIGNATURE OK (xmlsec1)
```

---

### 5. Inspección Visual del QR en XML

```bash
grep -A 1 '<dCarQR>' ~/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml | head -2
```

**Verificar manualmente:**
- [ ] URL comienza con `https://ekuatia.set.gov.py/consultas-test/qr?` (sin www.)
- [ ] Parámetros separados por `&amp;` (no `&`)
- [ ] `IdCSC=0001` (4 dígitos)
- [ ] `cHashQR=` seguido de 64 caracteres en minúsculas (a-f, 0-9)

---

### 6. Comparación con Ejemplo Oficial SIFEN

```bash
python3 << 'EOF'
import re

# Ejemplo oficial SIFEN
sifen_official = "https://ekuatia.set.gov.py/consultas-test/qr?nVersion=150&Id=01800138848001001123456412018121817819792239&dFeEmiDE=323031392d30342d30395431323a35373a3137&dRucRec=80081294&dTotGralOpe=0&dTotIVA=0&cItems=1&DigestValue=5368453774502b6a74766a39662f4952734f7077694f366b574146346458366c487559547775556b304b4d3d&IdCSC=0001&cHashQR=3e4431dc88ee9c9c2b4037f40db15091c468bcc4a591c74c5d6a3e0b3a72aa40"

# Nuestro XML
import xml.etree.ElementTree as ET
tree = ET.parse('/Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml')
root = tree.getroot()
ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd'}
qr = root.find('.//sifen:dCarQR', ns)
our_qr = qr.text.strip().replace('&amp;', '&')

def check_format(url, label):
    print(f"\n{label}:")
    print(f"  Base URL: {url[:50]}...")
    
    # Extraer parámetros
    params = {}
    match = re.search(r'\?(.*)', url)
    if match:
        for p in match.group(1).split('&'):
            if '=' in p:
                k, v = p.split('=', 1)
                params[k] = v
    
    # Verificar formatos críticos
    checks = {
        'dFeEmiDE lowercase': params.get('dFeEmiDE', '') == params.get('dFeEmiDE', '').lower(),
        'DigestValue lowercase': params.get('DigestValue', '') == params.get('DigestValue', '').lower(),
        'IdCSC 4 digits': len(params.get('IdCSC', '')) == 4,
        'cHashQR lowercase': params.get('cHashQR', '') == params.get('cHashQR', '').lower(),
        'cHashQR 64 chars': len(params.get('cHashQR', '')) == 64,
    }
    
    for check, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check}")
    
    return all(checks.values())

sifen_ok = check_format(sifen_official, "SIFEN Oficial")
our_ok = check_format(our_qr, "Nuestro XML")

print("\n" + "=" * 60)
if our_ok:
    print("✓ NUESTRO XML CUMPLE TODOS LOS FORMATOS DE SIFEN")
else:
    print("✗ NUESTRO XML NO CUMPLE LOS FORMATOS")
    exit(1)
EOF
```

---

### 7. Test de Regresión - Verificar que no rompimos nada

```bash
# Verificar que el XML sigue siendo válido contra el schema
python3 << 'EOF'
import xml.etree.ElementTree as ET

tree = ET.parse('/Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml')
root = tree.getroot()

# Verificar estructura básica
ns = {'sifen': 'http://ekuatia.set.gov.py/sifen/xsd', 'ds': 'http://www.w3.org/2000/09/xmldsig#'}

checks = {
    'rDE existe': root.tag.endswith('rDE'),
    'DE existe': root.find('.//sifen:DE', ns) is not None,
    'Signature existe': root.find('.//ds:Signature', ns) is not None,
    'gCamFuFD existe': root.find('.//sifen:gCamFuFD', ns) is not None,
    'dCarQR existe': root.find('.//sifen:dCarQR', ns) is not None,
}

print("Verificación de estructura XML:")
for check, result in checks.items():
    status = "✓" if result else "✗"
    print(f"  {status} {check}")

if all(checks.values()):
    print("\n✓ Estructura XML intacta")
else:
    print("\n✗ Estructura XML dañada")
    exit(1)
EOF
```

---

## CHECKLIST FINAL (marcar antes de subir)

- [ ] XML regenerado con fix de cHashQR lowercase
- [ ] Suite de tests automáticos: 9/9 passed
- [ ] cHashQR verificado manualmente: lowercase, 64 chars
- [ ] Firma digital válida (xmlsec1)
- [ ] Inspección visual: URL base, &amp;, IdCSC=0001, cHashQR lowercase
- [ ] Comparación con ejemplo oficial: todos los formatos coinciden
- [ ] Test de regresión: estructura XML intacta

---

## Si TODO está ✓, proceder a:

1. **Subir a SIFEN Pre-validador:**
   - URL: https://ekuatia.set.gov.py/pre-validador/
   - Archivo: `~/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml`

2. **Resultado esperado:**
   - ✓ Validación Firma: Es Válido
   - ✓ Validaciones XML: Todas OK (sin error de "URL inválida")

3. **Si aún falla:**
   - Capturar mensaje de error exacto
   - Ejecutar: `python tests/test_qr_validation.py > test_results.txt`
   - Contactar soporte SIFEN con:
     - RUC: 4554737-8
     - Solicitud: 364010034907
     - Error reportado
     - Adjuntar: test_results.txt y XML

---

## Comandos rápidos para debugging

```bash
# Ver QR completo
python3 -c "import xml.etree.ElementTree as ET; tree = ET.parse('/Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml'); print(tree.getroot().find('.//{http://ekuatia.set.gov.py/sifen/xsd}dCarQR').text)"

# Ver solo cHashQR
python3 -c "import xml.etree.ElementTree as ET, re; tree = ET.parse('/Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml'); qr = tree.getroot().find('.//{http://ekuatia.set.gov.py/sifen/xsd}dCarQR').text; print(re.search(r'cHashQR=([a-f0-9]+)', qr.replace('&amp;', '&')).group(1))"

# Verificar hash manualmente
python3 -c "import xml.etree.ElementTree as ET, re, hashlib, os; tree = ET.parse('/Users/robinklaiss/Desktop/SIFEN_PREVALIDADOR_UPLOAD.xml'); qr = tree.getroot().find('.//{http://ekuatia.set.gov.py/sifen/xsd}dCarQR').text.replace('&amp;', '&'); m = re.search(r'\?(.*?)&cHashQR=([a-f0-9]+)', qr); print('Hash en XML:', m.group(2)); print('Hash calculado:', hashlib.sha256((m.group(1) + os.getenv('SIFEN_CSC', 'ABCD0000000000000000000000000000')).encode()).hexdigest()); print('Match:', m.group(2) == hashlib.sha256((m.group(1) + os.getenv('SIFEN_CSC', 'ABCD0000000000000000000000000000')).encode()).hexdigest())"
```
