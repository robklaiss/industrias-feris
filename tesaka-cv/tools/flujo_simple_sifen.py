#!/usr/bin/env python3
"""
Flujo simple SIFEN - Todo en uno sin dependencias externas
"""

import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree

def flujo_simple(xml_validado, ruc, dv, timbrado, num_doc, output_dir):
    """
    Flujo simple - solo genera el XML listo para firmar manualmente
    """
    
    print("🚀 Flujo Simple SIFEN...")
    print(f"   RUC: {ruc}-{dv}")
    print(f"   Timbrado: {timbrado}")
    print(f"   Documento: {num_doc}")
    
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # === PASO 1: Crear XML con tus datos ===
    print("\n📝 Paso 1: Creando XML con tus datos...")
    
    parser = etree.XMLParser(remove_blank_text=False)
    tree = etree.parse(xml_validado, parser)
    root = tree.getroot()
    
    SIFEN_NS = "{http://ekuatia.set.gov.py/sifen/xsd}"
    rde = root
    if root.tag == f'{SIFEN_NS}rLoteDE':
        rde = root.find(f".//{SIFEN_NS}rDE")
    
    # Cambiar datos esenciales
    gEmis = rde.find(f".//{SIFEN_NS}gEmis")
    gEmis.find(f"{SIFEN_NS}dRucEm").text = ruc
    gEmis.find(f"{SIFEN_NS}dDVEmi").text = dv
    gEmis.find(f"{SIFEN_NS}dNomEmi").text = "EMPRESA DE PRUEBA S.A."
    gEmis.find(f"{SIFEN_NS}dNomFanEmi").text = "EMPRESA DE PRUEBA"
    gEmis.find(f"{SIFEN_NS}dDirEmi").text = "AVDA. ESPAÑA 123"
    gEmis.find(f"{SIFEN_NS}dTelEmi").text = "0971 123456"
    gEmis.find(f"{SIFEN_NS}dEmailE").text = "info@empresa.com.py"
    
    gTimb = rde.find(f".//{SIFEN_NS}gTimb")
    gTimb.find(f"{SIFEN_NS}dNumTim").text = timbrado
    gTimb.find(f"{SIFEN_NS}dNumDoc").text = num_doc
    
    gDatGralOpe = rde.find(f".//{SIFEN_NS}gDatGralOpe")
    gDatGralOpe.find(f"{SIFEN_NS}dFeEmiDE").text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')
    
    gDatRec = rde.find(f".//{SIFEN_NS}gDatRec")
    gDatRec.find(f"{SIFEN_NS}dNomRec").text = "CONSUMIDOR FINAL"
    
    # Limpiar firma y QR
    for sig in rde.findall(".//{http://www.w3.org/2000/09/xmldsig#}Signature"):
        sig.getparent().remove(sig)
    gCamFuFD = rde.find(f"{SIFEN_NS}gCamFuFD")
    if gCamFuFD is not None:
        gCamFuFD.getparent().remove(gCamFuFD)
    
    # Guardar XML listo para firmar
    xml_listo = output_path / f"xml_listo_{num_doc}.xml"
    xml_bytes = etree.tostring(rde, encoding='utf-8', xml_declaration=True)
    xml_listo.write_bytes(xml_bytes)
    print(f"   ✅ XML listo para firmar: {xml_listo}")
    
    # === PASO 2: Crear script de firma ===
    print("\n📜 Paso 2: Creando script de firma...")
    
    script_firma = output_path / f"firmar_{num_doc}.sh"
    script_contenido = f"""#!/bin/bash
# Script para firmar XML SIFEN

# Configurar variables de entorno
export SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/F1T_65478.p12"
export SIFEN_SIGN_P12_PATH="/Users/robinklaiss/.sifen/certs/F1T_65478.p12"
export SIFEN_SIGN_P12_PASSWORD="bH1%T7EP"

# Firmar XML
cd /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv
.venv/bin/python tools/send_sirecepde.py \\
    --xml {xml_listo} \\
    --env test \\
    --artifacts-dir {output_path}/artifacts \\
    --skip-ruc-gate

# Esperar a que termine
sleep 2

# Buscar XML firmado en el directorio de artifacts de tesaka-cv
XML_FIRMADO=$(find /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv/artifacts -name "rde_signed_*.xml" -type f | sort -r | head -n 1)

if [ -z "$XML_FIRMADO" ]; then
    echo "❌ No se encontró XML firmado"
    echo "Buscando en:"
    ls -la /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/tesaka-cv/artifacts/
    exit 1
fi

echo "✅ XML firmado encontrado: $XML_FIRMADO"
cp "$XML_FIRMADO" {output_path}/xml_firmado_{num_doc}.xml

# Agregar gCamFuFD con QR mejorado
.venv/bin/python tools/agregar_camfu_mejorado.py \\
    --xml {output_path}/xml_firmado_{num_doc}.xml \\
    --output {output_path}/xml_final_{num_doc}.xml \\
    --id-csc 0001

echo ""
echo "✅ ¡Flujo completado!"
echo "   XML final: {output_path}/xml_final_{num_doc}.xml"
echo ""
echo "📋 Próximo paso:"
echo "   Validar en: https://sifen.set.gov.py/prevalidador/"
"""
    
    script_firma.write_text(script_contenido)
    script_firma.chmod(0o755)
    print(f"   ✅ Script de firma: {script_firma}")
    
    # === PASO 3: Crear README ===
    print("\n📖 Paso 3: Creando instrucciones...")
    
    readme = output_path / "README.md"
    readme_contenido = f"""# Flujo SIFEN - Documento {num_doc}

## Archivos Generados

1. **xml_listo_{num_doc}.xml** - XML con tus datos, listo para firmar
2. **firmar_{num_doc}.sh** - Script para firmar el XML
3. **xml_final_{num_doc}.xml** - XML final (se genera al ejecutar el script)

## Pasos para Completar

1. **Firmar el XML:**
   ```bash
   cd {output_path}
   ./firmar_{num_doc}.sh
   ```

2. **Validar en SIFEN:**
   - Abre: https://sifen.set.gov.py/prevalidador/
   - Sube: xml_final_{num_doc}.xml
   - Debería mostrar: "XML y Firma Válidos"

## Datos del Documento

- **RUC:** {ruc}-{dv}
- **Timbrado:** {timbrado}
- **Documento:** {num_doc}
- **Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Notas

- El XML mantiene la estructura exacta del XML validado
- Solo se modificaron los datos esenciales
- gCamFuFD se agrega después de firmar para mantener la validez
"""
    
    readme.write_text(readme_contenido)
    print(f"   ✅ Instrucciones: {readme}")
    
    print("\n🎯 Flujo simple completado!")
    print(f"\n📁 Archivos en: {output_dir}")
    print(f"\n📋 Para completar:")
    print(f"   1. cd {output_dir}")
    print(f"   2. ./firmar_{num_doc}.sh")
    print(f"   3. Validar xml_final_{num_doc}.xml en SIFEN")
    
    return str(xml_listo)

def main():
    parser = argparse.ArgumentParser(description="Flujo simple SIFEN")
    parser.add_argument('--validado', required=True, help='XML validado original')
    parser.add_argument('--ruc', required=True, help='RUC (sin DV)')
    parser.add_argument('--dv', required=True, help='DV del RUC')
    parser.add_argument('--timbrado', required=True, help='Número de timbrado')
    parser.add_argument('--num-doc', required=True, help='Número documento (7 dígitos)')
    parser.add_argument('--output-dir', default='./output_sifen', help='Directorio de salida')
    
    args = parser.parse_args()
    
    # Formatear número de documento
    num_doc = str(args.num_doc).zfill(7)
    
    if not Path(args.validado).exists():
        print(f"❌ Archivo no encontrado: {args.validado}")
        sys.exit(1)
    
    try:
        xml_listo = flujo_simple(
            args.validado, args.ruc, args.dv, args.timbrado,
            num_doc, args.output_dir
        )
        
        print(f"\n✅ Listo! Ejecuta el script para completar el proceso.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
