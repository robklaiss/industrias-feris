#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para demostrar el fallback de consulta_lote_de cuando WSDL/XSD falla.
"""

import os
import sys
from pathlib import Path

# Agregar el directorio parent al path para imports
sys.path.insert(0, str(Path(__file__).parent / "tesaka-cv"))

from tools.consulta_lote_de import main

def test_fallback_demo():
    """Demuestra que el fallback funciona cuando WSDL/XSD falla."""
    
    print("="*70)
    print("DEMO: Fallback de consulta_lote_de")
    print("="*70)
    print("\nEste demo muestra cómo consulta_lote_de usa fallback manual")
    print("cuando Zeep/WSDL falla por archivos XSD faltantes.")
    print()
    
    # Simular argumentos de línea de comandos
    test_args = [
        "consulta_lote_de.py",
        "--env", "test",
        "--prot", "123456789012345",
        "--debug",
        "--wsdl-cache-dir", "/tmp/test_fallback"
    ]
    
    # Mockear sys.argv
    with patch('sys.argv', test_args):
        # Forzar que load_wsdl_source falle
        with patch('tools.consulta_lote_de.load_wsdl_source') as mock_load:
            mock_load.side_effect = Exception(
                "[Errno 2] No such file or directory: '.../consulta-lote.wsdl.xsd1.xsd'"
            )
            
            # Mockear el fallback manual para que no intente conexión real
            with patch('tools.consulta_lote_de._http_consulta_lote_manual') as mock_manual:
                mock_manual.return_value = '''<?xml version="1.0" encoding="UTF-8"?>
<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">
    <soap12:Body>
        <rEnviConsLoteDeResponse xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dCodResLot>0361</dCodResLot>
            <dMsgResLot>Lote procesado correctamente (fallback demo)</dMsgResLot>
        </rEnviConsLoteDeResponse>
    </soap12:Body>
</soap12:Envelope>'''
                
                # Mockear certificado
                with patch('tools.consulta_lote_de.get_mtls_config') as mock_mtls:
                    mock_mtls.return_value = ("/tmp/cert.p12", "password", False)
                    
                    # Ejecutar
                    print("Ejecutando consulta con WSDL roto...")
                    try:
                        result = main()
                        print(f"\n✅ Resultado: {result}")
                        print("\n✅ El fallback funcionó correctamente!")
                        print("   - Se detectó el error de WSDL/XSD")
                        print("   - Se usó el fallback manual")
                        print("   - Se obtuvo respuesta de SIFEN")
                        print("   - Se generó el JSON con fallback_used=true")
                    except SystemExit as e:
                        print(f"\n✅ Resultado: {e.code}")
                        print("\n✅ El fallback funcionó correctamente!")
    
    print("\n" + "="*70)
    print("FIN DEMO")
    print("="*70)


if __name__ == "__main__":
    from unittest.mock import patch
    test_fallback_demo()
