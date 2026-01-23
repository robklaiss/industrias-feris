#!/usr/bin/env python3
"""
Ejemplo completo de cómo generar una factura electrónica SIFEN.
Este script muestra cómo utilizar el generador con datos personalizados.
"""

from datetime import datetime
import sys
import os

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.generar_factura import generar_factura
import uuid


def calcular_totales(items):
    """
    Calcula los totales de la factura a partir de los items.
    
    Args:
        items (list): Lista de items con sus valores
    
    Returns:
        dict: Diccionario con los totales calculados
    """
    # Inicializar totales
    totales = {
        "dSubExe": "0",
        "dSubExo": "0",
        "dSub5": "0",
        "dSub10": "0",
        "dTotOpe": "0",
        "dTotDesc": "0",
        "dTotDescGlotem": "0",
        "dTotAntItem": "0",
        "dTotAnt": "0",
        "dPorcDescTotal": "0",
        "dDescTotal": "0",
        "dAnticipo": "0",
        "dRedon": "0",
        "dTotGralOpe": "0",
        "dIVA5": "0",
        "dIVA10": "0",
        "dLiqTotIVA5": "0",
        "dLiqTotIVA10": "0",
        "dTotIVA": "0",
        "dBaseGrav5": "0",
        "dBaseGrav10": "0",
        "dTBasGraIVA": "0"
    }
    
    # Sumar valores de los items
    total_operacion = 0
    total_iva5 = 0
    total_iva10 = 0
    base_gravada5 = 0
    base_gravada10 = 0
    
    for item in items:
        total_operacion += int(item["dTotOpeItem"])
        
        if item["dTasaIVA"] == "5":
            total_iva5 += int(item["dLiqIVAItem"])
            base_gravada5 += int(item["dBasGravIVA"])
        elif item["dTasaIVA"] == "10":
            total_iva10 += int(item["dLiqIVAItem"])
            base_gravada10 += int(item["dBasGravIVA"])
    
    # Actualizar totales
    totales["dTotOpe"] = str(total_operacion)
    totales["dTotGralOpe"] = str(total_operacion)
    totales["dIVA5"] = str(total_iva5)
    totales["dIVA10"] = str(total_iva10)
    totales["dTotIVA"] = str(total_iva5 + total_iva10)
    totales["dBaseGrav5"] = str(base_gravada5)
    totales["dBaseGrav10"] = str(base_gravada10)
    totales["dTBasGraIVA"] = str(base_gravada5 + base_gravada10)
    
    # Asignar subtotales según corresponda
    if base_gravada5 > 0:
        totales["dSub5"] = str(base_gravada5 + total_iva5)
    if base_gravada10 > 0:
        totales["dSub10"] = str(base_gravada10 + total_iva10)
    
    return totales


def ejemplo_factura_personalizada():
    """
    Ejemplo de cómo generar una factura con datos personalizados.
    """
    # Datos del emisor (debes usar tus datos reales)
    emisor = {
        "dRucEm": "1234567",
        "dDVEmi": "9",
        "dNomEmi": "MI EMPRESA S.A.",
        "dDirEmi": "AVENIDA PRINCIPAL 123",
        "cDepEmi": "12",
        "dDesDepEmi": "CENTRAL",
        "cCiuEmi": "165",
        "dDesCiuEmi": "VILLA ELISA",
        "dTelEmi": "(021) 123456",
        "dEmailE": "facturacion@miempresa.com.py",
        "gActEco": [
            {"cActEco": "46611", "dDesActEco": "Venta por menor de alimentos en general"},
            {"cActEco": "47191", "dDesActEco": "Venta por menor de otros productos nuevos"}
        ]
    }
    
    # Datos del receptor
    receptor = {
        "dRucRec": "80000000",
        "dDVRec": "1",
        "dNomRec": "CLIENTE DE EJEMPLO S.A.",
        "dDirRec": "CALLE SECUNDARIA 456",
        "cDepRec": "12",
        "dDesDepRec": "CENTRAL",
        "cCiuRec": "165",
        "dDesCiuRec": "VILLA ELISA",
        "dTelRec": "(021) 654321",
        "dEmailRec": "cliente@ejemplo.com.py"
    }
    
    # Items de la factura
    items = [
        {
            "dDesProSer": "PRODUCTO A - Descripción detallada del producto",
            "cUniMed": "77",
            "dDesUniMed": "UNI",
            "dCantProSer": "10",
            "dPUniProSer": "50000",
            "dTotBruOpeItem": "500000",
            "dDescItem": "0",
            "dPorcDescItem": "0",
            "dTotOpeItem": "500000",
            "iAfecIVA": "1",
            "dDesAfecIVA": "Gravado IVA",
            "dPropIVA": "100",
            "dTasaIVA": "10",
            "dBasGravIVA": "454545",
            "dLiqIVAItem": "45455",
            "dBasExe": "0"
        },
        {
            "dDesProSer": "SERVICIO B - Descripción del servicio prestado",
            "cUniMed": "81",
            "dDesUniMed": "HOR",
            "dCantProSer": "5",
            "dPUniProSer": "100000",
            "dTotBruOpeItem": "500000",
            "dDescItem": "0",
            "dPorcDescItem": "0",
            "dTotOpeItem": "500000",
            "iAfecIVA": "1",
            "dDesAfecIVA": "Gravado IVA",
            "dPropIVA": "100",
            "dTasaIVA": "10",
            "dBasGravIVA": "454545",
            "dLiqIVAItem": "45455",
            "dBasExe": "0"
        },
        {
            "dDesProSer": "PRODUCTO EXENTO - Medicina",
            "cUniMed": "77",
            "dDesUniMed": "UNI",
            "dCantProSer": "2",
            "dPUniProSer": "100000",
            "dTotBruOpeItem": "200000",
            "dDescItem": "0",
            "dPorcDescItem": "0",
            "dTotOpeItem": "200000",
            "iAfecIVA": "2",
            "dDesAfecIVA": "Exento IVA",
            "dPropIVA": "0",
            "dTasaIVA": "0",
            "dBasGravIVA": "0",
            "dLiqIVAItem": "0",
            "dBasExe": "200000"
        }
    ]
    
    # Calcular totales
    totales = calcular_totales(items)
    
    # Datos de timbrado (debes usar tus datos reales)
    timbrado = {
        "dNumTim": "12345678",
        "dEst": "001",
        "dPunExp": "001",
        "dNumDoc": "0000001",
        "dFeIniT": "2025-01-01"
    }
    
    # Fecha y hora actual
    ahora = datetime.now()
    fecha_hora = ahora.strftime("%Y-%m-%dT%H:%M:%S")
    
    # Generar código de seguridad (ejemplo - debes implementar tu propia lógica)
    dCodSeg = str(uuid.uuid4().int)[:9]
    
    # Construir datos completos de la factura
    datos_factura = {
        **emisor,
        **receptor,
        **timbrado,
        "CDC": f"0104{emisor['dRucEm']}{emisor['dDVEmi']}0010010000001{ahora.strftime('%Y%m%d')}{dCodSeg}",
        "dFecFirma": fecha_hora,
        "dCodSeg": dCodSeg,
        "dFeEmiDE": fecha_hora,
        "items": items,
        "totales": totales,
        "pagos": [
            {
                "iTiPago": "1",
                "dDesTiPag": "Efectivo",
                "dMonTiPag": totales["dTotGralOpe"],
                "cMoneTiPag": "PYG",
                "dDMoneTiPag": "Guaraní"
            }
        ]
    }
    
    return datos_factura


def main():
    """
    Función principal.
    """
    print("=" * 60)
    print("GENERADOR DE FACTURAS ELECTRÓNICAS SIFEN")
    print("=" * 60)
    
    # Generar factura personalizada
    print("\n1. Generando factura personalizada...")
    datos = ejemplo_factura_personalizada()
    
    fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"factura_personalizada_{fecha_actual}.xml"
    
    xml_generado = generar_factura(datos, output_file)
    
    print(f"\n✓ Factura generada: {output_file}")
    print(f"✓ Total operación: Gs. {datos['totales']['dTotGralOpe']}")
    print(f"✓ Total IVA: Gs. {datos['totales']['dTotIVA']}")
    print(f"✓ CDC: {datos['CDC']}")
    
    # También generar la de ejemplo
    print("\n2. Generando factura de ejemplo (basada en el modelo)...")
    from tools.generar_factura import datos_ejemplo
    
    output_ejemplo = f"factura_ejemplo_{fecha_actual}.xml"
    generar_factura(datos_ejemplo(), output_ejemplo)
    
    print(f"\n✓ Factura de ejemplo generada: {output_ejemplo}")
    
    print("\n" + "=" * 60)
    print("¡Proceso completado!")
    print("\nRecuerda:")
    print("- Debes usar tus datos reales de emisor y timbrado")
    print("- El CDC debe generarse según las reglas de SIFEN")
    print("- Los archivos XML deben ser firmados digitalmente")
    print("=" * 60)


if __name__ == "__main__":
    main()
