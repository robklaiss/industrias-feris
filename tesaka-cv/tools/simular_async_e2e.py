#!/usr/bin/env python3
"""
Simulación de corrida end-to-end de SIFEN async.
Este script simula el envío de un lote y prueba la consulta de estado.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def simular_envio_lote():
    """Simula un envío exitoso de lote."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Crear carpeta para la corrida
    run_dir = Path(f"artifacts/runs_async/{timestamp}_test")
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Simular response de envío con dProtConsLote != 0
    mock_response = {
        "endpoint": "https://sifen-test.set.gov.py/de/ws/async/recibe-lote",
        "http_status": 200,
        "dProtConsLote": "12345678901234567890",  # Protocolo simulado
        "dId": f"{timestamp}",
        "dCodRes": "000",
        "dMsgRes": "Lote recibido con éxito",
        "dEstRes": "Procesado",
        "ok": True
    }
    
    # Guardar response
    with open(run_dir / "send_response.json", "w") as f:
        json.dump(mock_response, f, indent=2)
    
    # Guardar protocolo en archivo txt como se solicitó
    with open(run_dir / "prot.txt", "w") as f:
        f.write(mock_response["dProtConsLote"])
    
    # Simular request SOAP
    soap_request = '''<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Header/>
    <env:Body>
        <rEnvioLote xmlns="http://ekuatia.set.gov.py/sifen/xsd">
            <dId>{dId}</dId>
            <xDE>UEsDBAoAAAAIACxtL1x...simulado...</xDE>
        </rEnvioLote>
    </env:Body>
</env:Envelope>'''.format(dId=mock_response["dId"])
    
    with open(run_dir / "send_request.xml", "w") as f:
        f.write(soap_request)
    
    # Simular response SOAP
    soap_response = '''<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Header/>
    <env:Body>
        <ns2:rRetEnviDe xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
            <ns2:rProtDe>
                <ns2:dFecProc>{fecha}</ns2:dFecProc>
                <ns2:dEstRes>Procesado</ns2:dEstRes>
                <ns2:gResProc>
                    <ns2:dCodRes>000</ns2:dCodRes>
                    <ns2:dMsgRes>Lote recibido con éxito</ns2:dMsgRes>
                </ns2:gResProc>
                <ns2:dProtConsLote>{dProtConsLote}</ns2:dProtConsLote>
            </ns2:rProtDe>
        </ns2:rRetEnviDe>
    </env:Body>
</env:Envelope>'''.format(
        fecha=datetime.now().isoformat(),
        dProtConsLote=mock_response["dProtConsLote"]
    )
    
    with open(run_dir / "send_response.xml", "w") as f:
        f.write(soap_response)
    
    print(f"✅ Simulación de envío creada en: {run_dir}")
    print(f"   dProtConsLote: {mock_response['dProtConsLote']}")
    
    return run_dir, mock_response["dProtConsLote"]

def consultar_lote_simulado(run_dir, dProtConsLote):
    """Simula consultas de lote hasta obtener resultado final."""
    print(f"\n📋 Iniciando consultas de lote para protocolo: {dProtConsLote}")
    
    # Simular varias consultas con backoff
    for i in range(1, 4):
        print(f"\n📨 Consulta {i}/3...")
        
        # Esperar simulada
        if i == 1:
            time.sleep(2)  # Primera consulta rápida
        else:
            time.sleep(1)  # Consultas subsequentes
        
        # Simular request de consulta
        consulta_request = f'''<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Header/>
    <env:Body>
        <ns2:rConsLoteDE xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
            <ns2:dProtConsLote>{dProtConsLote}</ns2:dProtConsLote>
        </ns2:rConsLoteDE>
    </env:Body>
</env:Envelope>'''
        
        with open(run_dir / f"poll_{i:02d}_request.xml", "w") as f:
            f.write(consulta_request)
        
        # Simular response según iteración
        if i < 3:
            # Respuestas intermedias: en procesamiento
            cod_res = "010"
            msg_res = "Lote en procesamiento"
            estado = "Procesando"
        else:
            # Respuesta final: procesado
            cod_res = "000"
            msg_res = "Lote procesado exitosamente"
            estado = "Procesado"
        
        consulta_response = f'''<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">
    <env:Header/>
    <env:Body>
        <ns2:rRetConsLoteDE xmlns:ns2="http://ekuatia.set.gov.py/sifen/xsd">
            <ns2:dProtConsLote>{dProtConsLote}</ns2:dProtConsLote>
            <ns2:estado>{estado}</ns2:estado>
            <ns2:gResProc>
                <ns2:dCodRes>{cod_res}</ns2:dCodRes>
                <ns2:dMsgRes>{msg_res}</ns2:dMsgRes>
            </ns2:gResProc>
            <ns2:cdcs>
                <ns2:dCDC>01045547378029010022141112026011410000000016</ns2:dCDC>
                <ns2:estado>{estado}</ns2:estado>
                <ns2:dCodRes>{cod_res}</ns2:dCodRes>
                <ns2:dMsgRes>{msg_res}</ns2:dMsgRes>
            </ns2:cdcs>
        </ns2:rRetConsLoteDE>
    </env:Body>
</env:Envelope>'''
        
        with open(run_dir / f"poll_{i:02d}_response.xml", "w") as f:
            f.write(consulta_response)
        
        print(f"   Estado: {estado} ({cod_res}) - {msg_res}")
    
    # Crear resumen final
    summary = {
        "dProtConsLote": dProtConsLote,
        "codigo_final": cod_res,
        "mensaje_final": msg_res,
        "estado_final": estado,
        "consultas_realizadas": 3,
        "cdcs": [
            {
                "cdc": "01045547378029010022141112026011410000000016",
                "estado": estado,
                "codigo": cod_res,
                "mensaje": msg_res
            }
        ]
    }
    
    with open(run_dir / "final_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    
    print(f"\n✅ Resumen final guardado en: {run_dir}/final_summary.json")
    
    return summary

def main():
    print("🚀 Iniciando simulación de corrida end-to-end SIFEN async")
    print("=" * 60)
    
    # 1. Simular envío de lote
    run_dir, dProtConsLote = simular_envio_lote()
    
    # 2. Simular consultas hasta resultado final
    summary = consultar_lote_simulado(run_dir, dProtConsLote)
    
    # 3. Mostrar resumen
    print("\n" + "=" * 60)
    print("📊 RESUMEN DE LA CORRIDA")
    print("=" * 60)
    print(f"Carpeta: {run_dir}")
    print(f"dProtConsLote: {summary['dProtConsLote']}")
    print(f"Código final: {summary['codigo_final']}")
    print(f"Mensaje final: {summary['mensaje_final']}")
    print(f"Consultas realizadas: {summary['consultas_realizadas']}")
    print(f"\n✅ Archivos generados:")
    print(f"   - send_request.xml (request de envío)")
    print(f"   - send_response.xml (response de envío)")
    print(f"   - prot.txt (protocolo)")
    print(f"   - poll_XX_request/response.xml (consultas)")
    print(f"   - final_summary.json (resumen final)")

if __name__ == "__main__":
    main()
