#!/usr/bin/env python3
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Forzar skip RUC gate para evitar necesidad de certificados
os.environ["SIFEN_SKIP_RUC_GATE"] = "1"

from tools.send_sirecepde import send_sirecepde

def main():
    if len(sys.argv) > 1:
        num_doc = sys.argv[1]
    else:
        num_doc = "1"
    
    print(f"Generando XML para Prevalidador con dNumDoc={num_doc}")
    
    # Usar un XML existente como base
    xml_base = "artifacts/rde_signed_01045547378001001000000112026010210000000013.xml"
    
    result = send_sirecepde(
        xml_path=Path(xml_base),
        env="test",
        artifacts_dir=Path("artifacts/prevalidador"),
        dump_http=False,
        skip_ruc_gate=True,
        skip_ruc_gate_reason="Generación para Prevalidador",
        bump_doc=num_doc,
        strict_xsd=True,
    )
    
    if result.get("success"):
        # Copiar al escritorio
        import shutil
        xml_files = list(Path("artifacts/prevalidador").glob("rde_signed_*.xml"))
        if xml_files:
            latest = max(xml_files, key=lambda p: p.stat().st_mtime)
            desktop = Path.home() / "Desktop" / "prevalidador_rde_signed.xml"
            shutil.copy2(latest, desktop)
            print(f"\n✅ XML copiado a: {desktop}")
            print(f"   CDC: {latest.stem.split('_')[1]}")
            
            # También generar payload para subir
            payload_file = Path.home() / "Desktop" / "prevalidador_payload.xml"
            shutil.copy2(latest, payload_file)
            print(f"✅ Payload copiado a: {payload_file}")
    else:
        print(f"❌ Error: {result.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()
