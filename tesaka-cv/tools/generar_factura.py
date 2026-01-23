#!/usr/bin/env python3
"""
Generador de facturas electrónicas SIFEN basado en el modelo proporcionado.
Este script utiliza la plantilla factura_template.xml para generar facturas válidas.
"""

from datetime import datetime
from jinja2 import Environment, FileSystemLoader
import os
import sys


def generar_factura(datos_factura, output_file=None):
    """
    Genera una factura electrónica SIFEN a partir de los datos proporcionados.
    
    Args:
        datos_factura (dict): Diccionario con todos los datos de la factura
        output_file (str): Ruta del archivo de salida (opcional)
    
    Returns:
        str: XML generado de la factura
    """
    # Configurar Jinja2
    template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template('factura_template.xml')
    
    # Generar XML
    xml_factura = template.render(**datos_factura)
    
    # Guardar en archivo si se especificó
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(xml_factura)
        print(f"Factura guardada en: {output_file}")
    
    return xml_factura


def datos_ejemplo():
    """
    Retorna datos de ejemplo basados en la factura modelo.
    """
    return {
        # Datos generales
        "CDC": "01040090310001001000011912026011911890577982",
        "dFecFirma": "2026-01-19T11:57:10",
        "dCodSeg": "189057798",
        
        # Timbrado
        "dNumTim": "18502837",
        "dEst": "001",
        "dPunExp": "001",
        "dNumDoc": "0000119",
        "dFeIniT": "2025-12-06",
        
        # Emisor
        "dRucEm": "4009031",
        "dDVEmi": "0",
        "dNomEmi": "ANTONIO VIDAL OVIEDO BENITEZ",
        "dDirEmi": "SAN PEDRO CASI EMILIO JOHANSEN",
        "cDepEmi": "12",
        "dDesDepEmi": "CENTRAL",
        "cCiuEmi": "165",
        "dDesCiuEmi": "VILLA ELISA",
        "dTelEmi": "(0961)822555",
        "dEmailE": "antoniooviedo56@gmail.com",
        "gActEco": [
            {"cActEco": "47211", "dDesActEco": "Comercio al por menor de frutas y verduras"},
            {"cActEco": "47890", "dDesActEco": "Comercio al por menor de otros artículos en puestos de venta y mercados"}
        ],
        
        # Receptor
        "dRucRec": "7524653",
        "dDVRec": "8",
        "dNomRec": "ROBIN KLAISS",
        "dEmailRec": "robin@vinculo.com.py",
        
        # Fecha de emisión
        "dFeEmiDE": "2026-01-19T11:57:10",
        
        # Pagos
        "pagos": [
            {
                "iTiPago": "1",
                "dDesTiPag": "Efectivo",
                "dMonTiPag": "250000",
                "cMoneTiPag": "PYG",
                "dDMoneTiPag": "Guaraní"
            }
        ],
        
        # Items
        "items": [
            {
                "dDesProSer": "PLANCHAS DE HUEVO",
                "cUniMed": "77",
                "dDesUniMed": "UNI",
                "dCantProSer": "5",
                "dPUniProSer": "26000",
                "dTotBruOpeItem": "130000",
                "dDescItem": "0",
                "dPorcDescItem": "0",
                "dTotOpeItem": "130000",
                "iAfecIVA": "1",
                "dDesAfecIVA": "Gravado IVA",
                "dPropIVA": "100",
                "dTasaIVA": "5",
                "dBasGravIVA": "123810",
                "dLiqIVAItem": "6190",
                "dBasExe": "0"
            },
            {
                "dDesProSer": "PLANCHAS DE HUEVO",
                "cUniMed": "77",
                "dDesUniMed": "UNI",
                "dCantProSer": "5",
                "dPUniProSer": "24000",
                "dTotBruOpeItem": "120000",
                "dDescItem": "0",
                "dPorcDescItem": "0",
                "dTotOpeItem": "120000",
                "iAfecIVA": "1",
                "dDesAfecIVA": "Gravado IVA",
                "dPropIVA": "100",
                "dTasaIVA": "5",
                "dBasGravIVA": "114286",
                "dLiqIVAItem": "5714",
                "dBasExe": "0"
            }
        ],
        
        # Totales
        "totales": {
            "dSubExe": "0",
            "dSubExo": "0",
            "dSub5": "250000",
            "dSub10": "0",
            "dTotOpe": "250000",
            "dTotDesc": "0",
            "dTotDescGlotem": "0",
            "dTotAntItem": "0",
            "dTotAnt": "0",
            "dPorcDescTotal": "0",
            "dDescTotal": "0",
            "dAnticipo": "0",
            "dRedon": "0",
            "dTotGralOpe": "250000",
            "dIVA5": "11904",
            "dIVA10": "0",
            "dLiqTotIVA5": "0",
            "dLiqTotIVA10": "0",
            "dTotIVA": "11904",
            "dBaseGrav5": "238096",
            "dBaseGrav10": "0",
            "dTBasGraIVA": "238096"
        }
    }


def main():
    """
    Función principal para ejecutar el generador.
    """
    # Obtener fecha actual para el nombre del archivo
    fecha_actual = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Generar factura de ejemplo
    print("Generando factura de ejemplo...")
    xml_generado = generar_factura(
        datos_ejemplo(),
        output_file=f"factura_generada_{fecha_actual}.xml"
    )
    
    print("\n¡Factura generada exitosamente!")
    print(f"Longitud del XML: {len(xml_generado)} caracteres")
    
    # Opcional: mostrar vista previa
    print("\nVista previa del XML generado:")
    print(xml_generado[:500] + "..." if len(xml_generado) > 500 else xml_generado)


if __name__ == "__main__":
    main()
