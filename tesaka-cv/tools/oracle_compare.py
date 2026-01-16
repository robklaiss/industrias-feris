#!/usr/bin/env python3
"""
Oracle Compare: Compara generación de DE entre nuestra implementación y xmlgen

Genera el mismo DE con ambas implementaciones, valida contra XSD, y compara campos clave.

Uso:
    python -m tools.oracle_compare --input examples/source_invoice_ok.json
    python -m tools.oracle_compare --input examples/de_input.json --strict
"""
import sys
import argparse
import subprocess
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from xml.etree import ElementTree as ET

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.build_de import build_de_xml
from tools.validate_xsd import validate_against_xsd
from lxml import etree as lxml_etree

try:
    from lxml.etree import tostring
    LXML_AVAILABLE = True
except ImportError:
    LXML_AVAILABLE = False
    from xml.etree.ElementTree import tostring


def load_input_json(input_path: Path) -> Dict[str, Any]:
    """Carga JSON de entrada"""
    try:
        content = input_path.read_text(encoding='utf-8')
        return json.loads(content)
    except Exception as e:
        raise ValueError(f"Error al cargar JSON: {e}")


def convert_input_to_build_de_params(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convierte formato de_input.json a parámetros de build_de_xml
    
    Args:
        input_data: Diccionario con datos de entrada
        
    Returns:
        Diccionario con parámetros para build_de_xml
    """
    # Extraer datos del comprador (emisor en nuestro caso)
    buyer = input_data.get('buyer', {})
    transaction = input_data.get('transaction', {})
    
    # Parsear número de comprobante (formato: EST-PEXP-NUM)
    numero_comprobante = transaction.get('numeroComprobanteVenta', '001-001-0000001')
    parts = numero_comprobante.split('-')
    establecimiento = parts[0] if len(parts) >= 1 else "001"
    punto_expedicion = parts[1] if len(parts) >= 2 else "001"
    numero_documento = parts[2] if len(parts) >= 3 else "0000001"
    
    # Parsear fecha/hora
    fecha = transaction.get('fecha') or input_data.get('issue_date')
    hora = None
    if 'issue_datetime' in input_data:
        dt_str = input_data['issue_datetime']
        if ' ' in dt_str:
            fecha, hora = dt_str.split(' ', 1)
            hora = hora.split('.')[0]  # Remover microsegundos si existen
    
    params = {
        'ruc': buyer.get('ruc', '80012345'),
        'timbrado': transaction.get('numeroTimbrado', '12345678'),
        'establecimiento': establecimiento,
        'punto_expedicion': punto_expedicion,
        'numero_documento': numero_documento,
        'tipo_documento': str(transaction.get('tipoComprobante', 1)),
        'fecha': fecha,
        'hora': hora,
        'csc': input_data.get('csc'),  # Opcional
    }
    
    return params


def generate_de_python(input_data: Dict[str, Any], output_path: Path) -> Path:
    """
    Genera DE usando nuestra implementación Python
    
    Returns:
        Path al archivo XML generado
    """
    params = convert_input_to_build_de_params(input_data)
    xml_content = build_de_xml(**params)
    
    output_path.write_text(xml_content, encoding='utf-8')
    return output_path


def map_input_to_xmlgen_format(input_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Mapea formato de_input.json a formato esperado por xmlgen (params, data, options)
    
    IMPORTANTE: xmlgen requiere:
    - params.establecimientos: array con objetos que tienen codigo, denominacion, ciudad, distrito, departamento
    - params.actividadesEconomicas: array no vacío
    - data.establecimiento: string que debe coincidir con params.establecimientos[].codigo
    
    Returns:
        Tupla (params, data, options)
    """
    buyer = input_data.get('buyer', {})
    transaction = input_data.get('transaction', {})
    items = input_data.get('items', [])
    
    # Si ya están separados, validar que tengan los campos requeridos y usar directamente
    if 'params' in input_data and 'data' in input_data:
        params = input_data['params']
        data = input_data['data']
        options = input_data.get('options', {})
        
        # Validar campos requeridos
        if 'establecimientos' not in params or not isinstance(params['establecimientos'], list) or len(params['establecimientos']) == 0:
            # Agregar establecimiento por defecto si falta
            codigo_est = data.get('establecimiento', '001')
            params['establecimientos'] = [{
                'codigo': codigo_est,
                'denominacion': params.get('razonSocial', 'Establecimiento Principal'),
                'ciudad': params.get('ciudad', '1'),  # 1 = Asunción
                'distrito': params.get('distrito', '1'),
                'departamento': params.get('departamento', '1'),
            }]
        
        if 'actividadesEconomicas' not in params or not isinstance(params['actividadesEconomicas'], list) or len(params['actividadesEconomicas']) == 0:
            params['actividadesEconomicas'] = ['47110']  # Comercio al por menor (default seguro)
        
        # Asegurar que data.establecimiento exista
        if 'establecimiento' not in data:
            data['establecimiento'] = params['establecimientos'][0]['codigo']
        
        return params, data, options
    
    # Parsear establecimiento y punto de expedición del número de comprobante
    numero_comprobante = transaction.get('numeroComprobanteVenta', '001-001-0000001')
    codigo_establecimiento = '001'
    punto_expedicion = '001'
    if '-' in numero_comprobante:
        parts = numero_comprobante.split('-')
        if len(parts) >= 1:
            codigo_establecimiento = parts[0]
        if len(parts) >= 2:
            punto_expedicion = parts[1]
    
    # Mapear a formato xmlgen
    # params: datos estáticos del emisor
    # CRÍTICO: params.ruc debe tener formato RUC-DV (ej: "80012345-7")
    ruc_emisor = buyer.get('ruc', '4554737')
    if '-' not in ruc_emisor:
        # Si no tiene DV, agregar uno por defecto (no ideal, pero funciona para pruebas)
        ruc_emisor_with_dv = f"{ruc_emisor}-7"
    else:
        ruc_emisor_with_dv = ruc_emisor
    
    params = {
        'ruc': ruc_emisor_with_dv,
        'razonSocial': buyer.get('nombre', 'Empresa Ejemplo S.A.'),
        'nombreFantasia': buyer.get('nombre', ''),
        'direccion': buyer.get('domicilio', ''),
        'ciudad': buyer.get('direccion', 'Asunción'),
        'telefono': buyer.get('telefono', ''),
        'timbradoNumero': transaction.get('numeroTimbrado', '12345678'),
        'timbradoFecha': transaction.get('fecha', '2024-01-15'),
    }
    
    # CRÍTICO: params.establecimientos es requerido por xmlgen
    # Debe ser un array con objetos que tienen: codigo, denominacion, ciudad, distrito, departamento
    # Basado en la validación de jsonDeMainValidate.service.js línea ~416-448
    # IMPORTANTE: Los códigos deben coincidir con las constantes de SIFEN
    # Usando Departamento 1 (CONCEPCIÓN) con códigos simples que xmlgen acepta
    # Departamento 1 = CONCEPCIÓN
    # Distrito 1 = CONCEPCIÓN (pertenece al departamento 1)
    # Ciudad 1 = CONCEPCIÓN (pertenece al distrito 1)
    params['establecimientos'] = [{
        'codigo': codigo_establecimiento,
        'denominacion': buyer.get('nombre', 'Empresa Ejemplo S.A.'),
        'ciudad': 1,  # 1 = CONCEPCIÓN - debe ser número, no string
        'distrito': 1,  # 1 = CONCEPCIÓN - debe ser número, no string
        'departamento': 1,  # 1 = CONCEPCIÓN - debe ser número, no string
        'telefono': buyer.get('telefono', '')[:15] if buyer.get('telefono') else None,  # Opcional, max 15 chars
    }]
    
    # CRÍTICO: params.actividadesEconomicas es requerido por xmlgen (línea ~431)
    # Debe ser un array no vacío de códigos de actividad económica
    params['actividadesEconomicas'] = ['47110']  # Comercio al por menor en establecimientos no especializados con surtido compuesto (default seguro)
    
    # data: datos variables del DE
    # CRÍTICO: data.establecimiento debe coincidir EXACTAMENTE con params.establecimientos[].codigo
    
    # Parsear fecha/hora para formato ISO datetime (requerido por xmlgen)
    fecha_emision = transaction.get('fecha', input_data.get('issue_date', '2024-01-15'))
    hora_emision = '10:30:00'  # Default
    if 'issue_datetime' in input_data:
        dt_str = input_data['issue_datetime']
        if ' ' in dt_str:
            fecha_emision, hora_raw = dt_str.split(' ', 1)
            hora_emision = hora_raw.split('.')[0]  # Remover microsegundos
        elif 'T' in dt_str:
            # Ya está en formato ISO
            fecha_emision = dt_str
            hora_emision = None
    
    # Construir fecha en formato ISO datetime (requerido: yyyy-MM-ddTHH:mm:ss)
    if hora_emision:
        fecha_iso = f"{fecha_emision}T{hora_emision}"
    else:
        fecha_iso = fecha_emision if 'T' in fecha_emision else f"{fecha_emision}T10:30:00"
    
    # Parsear número de documento
    # CRÍTICO: xmlgen requiere que data.numero tenga máximo 7 dígitos
    numero_doc = '0000001'
    if '-' in numero_comprobante:
        parts = numero_comprobante.split('-')
        if len(parts) >= 3:
            numero_doc_raw = parts[2]
            # Truncar o pad a 7 dígitos máximo
            if len(numero_doc_raw) > 7:
                numero_doc = numero_doc_raw[-7:]  # Tomar últimos 7 dígitos
            else:
                numero_doc = numero_doc_raw.zfill(7)  # Pad con ceros a la izquierda hasta 7
    
    data = {
        'tipoDocumento': transaction.get('tipoComprobante', 1),
        'numeroDocumento': numero_doc,  # Para compatibilidad
        'numero': numero_doc,  # CRÍTICO: requerido por xmlgen (mismo que numeroDocumento)
        'fechaEmision': fecha_emision,  # Mantener para compatibilidad
        'fecha': fecha_iso,  # CRÍTICO: formato ISO datetime requerido por xmlgen
        'horaEmision': hora_emision,
        'condicionVenta': transaction.get('condicionCompra', 'CONTADO'),
        'establecimiento': codigo_establecimiento,  # DEBE coincidir con params.establecimientos[].codigo
        'punto': punto_expedicion,
        'tipoImpuesto': 1,  # CRÍTICO: requerido por xmlgen (1 = IVA)
        'moneda': 'PYG',  # Guaraní paraguayo (default)
        'condicion': {  # CRÍTICO: requerido como objeto
            'tipo': 1 if transaction.get('condicionCompra', 'CONTADO') == 'CONTADO' else 2,  # 1=Contado, 2=Crédito
            # CRÍTICO: entregas es requerido cuando tipo=1 (Contado)
            'entregas': [
                {
                    'tipo': 1,  # 1 = Efectivo (default seguro)
                    'descripcion': 'Efectivo',
                    'moneda': 'PYG',
                }
            ] if transaction.get('condicionCompra', 'CONTADO') == 'CONTADO' else None,
        },
        'items': [],
        'totalGeneral': 0,
        'totalIva5': 0,
        'totalIva10': 0,
    }
    
    # CRÍTICO: data.factura es requerido para tipoDocumento=1 (Factura Electrónica)
    if data['tipoDocumento'] == 1:
        data['factura'] = {
            'tipoTransaccion': 1,  # 1 = Venta de mercadería
            'presencia': 1,  # CRÍTICO: requerido - 1=Operación presencial (default seguro)
        }
    
    # Mapear items
    total_general = 0
    total_iva5 = 0
    total_iva10 = 0
    
    for item in items:
        cantidad = float(item.get('cantidad', 0))
        precio_unitario = float(item.get('precioUnitario', 0))
        tasa = int(item.get('tasaAplica', 0))
        
        subtotal = cantidad * precio_unitario
        iva = subtotal * (tasa / 100) if tasa > 0 else 0
        total = subtotal + iva
        
        total_general += total
        if tasa == 5:
            total_iva5 += iva
        elif tasa == 10:
            total_iva10 += iva
        
        # CRÍTICO: xmlgen requiere ivaTipo en cada item (1=Gravado IVA, 2=Exonerado, 3=Exento, 4=Gravado parcial)
        # Si tiene tasa > 0, es gravado (ivaTipo=1)
        # Si tasa == 0, es exento (ivaTipo=3)
        iva_tipo = 1 if tasa > 0 else 3
        
        # CRÍTICO: xmlgen espera que:
        # - item['iva'] sea la TASA (0, 5, o 10), NO el monto calculado
        # - item['ivaProporcion'] sea 100 cuando ivaTipo=1, 0 cuando ivaTipo=2 o 3
        item_iva = tasa  # La tasa de IVA (0, 5, o 10)
        item_iva_proporcion = 100 if iva_tipo == 1 else 0  # 100% gravado o 0% exento
        
        data['items'].append({
            'descripcion': item.get('descripcion', 'Producto'),
            'cantidad': cantidad,
            'precioUnitario': precio_unitario,
            'tasaIva': tasa,
            'ivaTipo': iva_tipo,  # CRÍTICO: requerido por xmlgen
            'subtotal': subtotal,
            'iva': item_iva,  # Ajustar según ivaTipo
            'ivaProporcion': item_iva_proporcion,  # Ajustar según ivaTipo
            'total': total,
        })
    
    data['totalGeneral'] = total_general
    data['totalIva5'] = total_iva5
    data['totalIva10'] = total_iva10
    
    # Datos del receptor (si están en el input)
    if 'receptor' in input_data:
        receptor = input_data['receptor']
        receptor_ruc = receptor.get('ruc', '')
        receptor_nombre = receptor.get('nombre', '')
        data['receptor'] = {
            'ruc': receptor_ruc,
            'razonSocial': receptor_nombre,
            'direccion': receptor.get('domicilio', ''),
        }
    else:
        # Usar buyer como receptor si no hay receptor separado
        receptor_ruc = buyer.get('ruc', '4554737')
        receptor_nombre = buyer.get('nombre', 'Empresa Ejemplo S.A.')
        data['receptor'] = {
            'ruc': receptor_ruc,
            'razonSocial': receptor_nombre,
            'direccion': buyer.get('domicilio', ''),
        }
    
    # CRÍTICO: data.cliente es requerido por xmlgen (línea ~48-60 de jsonDeMainValidate.service.js)
    # Debe tener: contribuyente (boolean), tipoOperacion (número), documentoTipo (si aplica), ruc (si contribuyente=true)
    # tipoOperacion: 1=B2B, 2=B2C, 3=B2G, 4=B2F
    # Si tiene RUC, asumimos que es contribuyente
    receptor_ruc_clean = receptor_ruc.split('-')[0] if '-' in receptor_ruc else receptor_ruc
    is_contribuyente = len(receptor_ruc_clean) >= 6 and receptor_ruc_clean.isdigit()
    
    data['cliente'] = {
        'contribuyente': is_contribuyente,
        'tipoOperacion': 1,  # 1 = B2B (Business to Business) - default seguro
        'razonSocial': receptor_nombre,
        'pais': 'PRY',  # CRÍTICO: requerido - Paraguay (código ISO 3166-1 alpha-3)
    }
    
    if is_contribuyente:
        # Si es contribuyente, RUC es requerido (formato: RUC-DV)
        if '-' not in receptor_ruc:
            # Si no tiene DV, agregar uno por defecto (no ideal, pero funciona para pruebas)
            receptor_ruc_with_dv = f"{receptor_ruc_clean}-7"
        else:
            receptor_ruc_with_dv = receptor_ruc
        data['cliente']['ruc'] = receptor_ruc_with_dv
        # CRÍTICO: tipoContribuyente es requerido si contribuyente=true
        data['cliente']['tipoContribuyente'] = 1  # 1 = Nacional (default seguro)
    else:
        # Si no es contribuyente y tipoOperacion != 4, necesita documentoTipo
        if data['cliente']['tipoOperacion'] != 4:
            data['cliente']['documentoTipo'] = 1  # 1 = CI (Cédula de Identidad) - default seguro
    
    # options: opciones adicionales (vacío por defecto)
    options = input_data.get('options', {})
    
    return params, data, options


def check_node_and_xmlgen() -> Tuple[bool, Optional[str]]:
    """
    Verifica que Node.js y el paquete xmlgen estén disponibles
    
    Returns:
        Tupla (disponible, mensaje_error)
    """
    # Verificar Node.js
    try:
        result = subprocess.run(
            ['node', '--version'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            return False, "Node.js no está instalado o no está en PATH"
    except FileNotFoundError:
        return False, "Node.js no está instalado o no está en PATH"
    except Exception as e:
        return False, f"Error al verificar Node.js: {e}"
    
    # Verificar que el paquete está instalado
    node_dir = Path(__file__).parent / "node"
    node_modules = node_dir / "node_modules" / "facturacionelectronicapy-xmlgen"
    
    if not node_modules.exists():
        return False, (
            f"El paquete facturacionelectronicapy-xmlgen no está instalado.\n"
            f"   Ejecuta: cd {node_dir} && npm install"
        )
    
    return True, None


def generate_de_xmlgen(input_data: Dict[str, Any], artifacts_dir: Path, timestamp: str) -> Optional[Path]:
    """
    Genera DE usando xmlgen (Node.js) con el nuevo runner
    
    Args:
        input_data: Diccionario con datos de entrada
        artifacts_dir: Directorio para archivos temporales y salida
        timestamp: Timestamp para nombres de archivo
        
    Returns:
        Path al archivo XML generado, o None si falla
    """
    # Verificar Node.js y paquete
    available, error_msg = check_node_and_xmlgen()
    if not available:
        print(f"⚠️  {error_msg}")
        return None
    
    # Mapear input a formato xmlgen
    try:
        params, data, options = map_input_to_xmlgen_format(input_data)
    except Exception as e:
        print(f"❌ Error al mapear input a formato xmlgen: {e}")
        return None
    
    # Escribir archivos temporales
    params_file = artifacts_dir / f"xmlgen_params_{timestamp}.json"
    data_file = artifacts_dir / f"xmlgen_data_{timestamp}.json"
    options_file = artifacts_dir / f"xmlgen_options_{timestamp}.json"
    output_path = artifacts_dir / f"oracle_xmlgen_de_{timestamp}.xml"
    
    try:
        params_file.write_text(json.dumps(params, indent=2, ensure_ascii=False), encoding='utf-8')
        data_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
        options_file.write_text(json.dumps(options, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f"❌ Error al crear archivos temporales: {e}")
        return None
    
    # Ejecutar runner
    node_dir = Path(__file__).parent / "node"
    runner_script = node_dir / "xmlgen_runner.cjs"
    
    if not runner_script.exists():
        print(f"❌ Runner script no encontrado: {runner_script}")
        return None
    
    try:
        # Usar --out para escribir directamente al archivo (evita contaminar stdout)
        result = subprocess.run(
            [
                'node',
                str(runner_script),
                '--params', str(params_file),
                '--data', str(data_file),
                '--options', str(options_file),
                '--out', str(output_path)
            ],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=node_dir
        )
        
        if result.returncode != 0:
            print(f"❌ Error al ejecutar xmlgen runner:")
            if result.stdout:
                print(f"   stdout: {result.stdout}")
            if result.stderr:
                print(f"   stderr: {result.stderr}")
            
            # Mostrar resumen de params/data que se enviaron (redactando datos sensibles)
            print(f"\n📋 Resumen de params/data enviados a xmlgen:")
            try:
                params_summary = {
                    'ruc': params.get('ruc', 'N/A'),
                    'razonSocial': params.get('razonSocial', 'N/A')[:30] + '...' if len(params.get('razonSocial', '')) > 30 else params.get('razonSocial', 'N/A'),
                    'establecimientos_count': len(params.get('establecimientos', [])),
                    'establecimientos': [
                        {
                            'codigo': est.get('codigo', 'N/A'),
                            'denominacion': est.get('denominacion', 'N/A')[:20] + '...' if len(est.get('denominacion', '')) > 20 else est.get('denominacion', 'N/A'),
                            'ciudad': est.get('ciudad', 'N/A'),
                            'distrito': est.get('distrito', 'N/A'),
                            'departamento': est.get('departamento', 'N/A'),
                        }
                        for est in params.get('establecimientos', [])
                    ],
                    'actividadesEconomicas': params.get('actividadesEconomicas', []),
                    'timbradoNumero': params.get('timbradoNumero', 'N/A'),
                }
                print(f"   params: {json.dumps(params_summary, indent=2, ensure_ascii=False)}")
                
                data_summary = {
                    'tipoDocumento': data.get('tipoDocumento', 'N/A'),
                    'numeroDocumento': data.get('numeroDocumento', 'N/A'),
                    'establecimiento': data.get('establecimiento', 'N/A'),
                    'punto': data.get('punto', 'N/A'),
                    'fechaEmision': data.get('fechaEmision', 'N/A'),
                    'items_count': len(data.get('items', [])),
                    'totalGeneral': data.get('totalGeneral', 0),
                }
                print(f"   data: {json.dumps(data_summary, indent=2, ensure_ascii=False)}")
            except Exception as e:
                print(f"   (No se pudo generar resumen: {e})")
            
            return None
        
        # Verificar que el archivo fue creado
        if not output_path.exists():
            print(f"❌ xmlgen no generó archivo de salida")
            if result.stderr:
                print(f"   stderr: {result.stderr}")
            return None
        
        return output_path
            
    except subprocess.TimeoutExpired:
        print(f"❌ Timeout al ejecutar xmlgen runner")
        return None
    except FileNotFoundError:
        print(f"❌ node no está instalado o no está en PATH")
        return None
    except Exception as e:
        print(f"❌ Error al ejecutar xmlgen runner: {e}")
        return None


def canonicalize_xml(xml_path: Path) -> str:
    """
    Canonicaliza XML para comparación (remueve diferencias de formato)
    
    Returns:
        XML canonicalizado como string
    """
    try:
        if LXML_AVAILABLE:
            tree = lxml_etree.parse(str(xml_path))
            root = tree.getroot()
            # C14N canonicalization
            canonical = lxml_etree.tostring(
                root,
                method='c14n',
                encoding='utf-8'
            )
            return canonical.decode('utf-8')
        else:
            # Fallback: parsear y re-serializar sin espacios extras
            tree = ET.parse(str(xml_path))
            root = tree.getroot()
            # Normalización básica
            for elem in root.iter():
                if elem.text:
                    elem.text = elem.text.strip()
                if elem.tail:
                    elem.tail = elem.tail.strip()
            return ET.tostring(root, encoding='unicode')
    except Exception as e:
        print(f"⚠️  Error al canonicalizar XML: {e}")
        # Fallback: leer como está
        return xml_path.read_text(encoding='utf-8')


def extract_key_fields(xml_path: Path) -> Dict[str, Any]:
    """
    Extrae campos clave del DE para comparación
    
    Returns:
        Diccionario con campos extraídos
    """
    try:
        tree = ET.parse(str(xml_path))
        root = tree.getroot()
        
        # Namespace
        ns = {}
        if root.tag.startswith('{'):
            ns['sifen'] = root.tag[1:root.tag.index('}')]
        
        def find_text(xpath_expr: str) -> Optional[str]:
            """Busca texto usando XPath relativo"""
            try:
                if ns.get('sifen'):
                    # Con namespace
                    elems = root.findall(f".//{{{ns['sifen']}}}{xpath_expr.split('/')[-1]}")
                else:
                    elems = root.findall(f".//{xpath_expr.split('/')[-1]}")
                if elems:
                    return elems[0].text
            except:
                pass
            return None
        
        def find_attr(xpath_expr: str, attr: str) -> Optional[str]:
            """Busca atributo"""
            try:
                parts = xpath_expr.split('/')
                tag = parts[-1]
                if ns.get('sifen'):
                    elems = root.findall(f".//{{{ns['sifen']}}}{tag}")
                else:
                    elems = root.findall(f".//{tag}")
                if elems and attr in elems[0].attrib:
                    return elems[0].attrib[attr]
            except:
                pass
            return None
        
        # Extraer campos clave
        fields = {
            'root_element': root.tag,
            'dFecEmi': find_text('dFecEmi'),
            'dHorEmi': find_text('dHorEmi'),
            'dRucEm': find_text('dRucEm'),
            'dDVEm': find_text('dDVEm'),
            'dRucRec': find_text('dRucRec'),
            'dDVRec': find_text('dDVRec'),
            'Id': find_attr('DE', 'Id'),
            'items_count': len(root.findall('.//gItem')),
            'dTotGralOpe': find_text('dTotGralOpe'),
            'dIVA10': find_text('dIVA10'),
            'dIVA5': find_text('dIVA5'),
            'dTotalGs': find_text('dTotalGs'),
        }
        
        return fields
        
    except Exception as e:
        print(f"⚠️  Error al extraer campos: {e}")
        return {}


def normalize_xml_for_diff(xml_content: str) -> str:
    """
    Normaliza XML para comparación (remueve whitespace/indent, timestamps volátiles)
    pero NO altera contenido semántico
    
    Returns:
        XML normalizado
    """
    import re
    
    # Remover espacios/tabs/saltos de línea extras entre tags
    normalized = re.sub(r'>\s+<', '><', xml_content)
    
    # Remover timestamps volátiles (fechas/horas que pueden diferir por segundos)
    # Patrón común: YYYY-MM-DDTHH:MM:SS
    normalized = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', '[TIMESTAMP]', normalized)
    
    # Remover espacios múltiples
    normalized = re.sub(r' +', ' ', normalized)
    
    return normalized


def compare_xmls(python_xml: Path, xmlgen_xml: Path, strict: bool = False) -> Tuple[bool, List[str], str]:
    """
    Compara dos XMLs y retorna diferencias
    
    Returns:
        Tupla (son_iguales, lista_diferencias, diff_text)
    """
    differences = []
    
    # Extraer campos clave
    python_fields = extract_key_fields(python_xml)
    xmlgen_fields = extract_key_fields(xmlgen_xml)
    
    # Comparar campos clave
    all_keys = set(python_fields.keys()) | set(xmlgen_fields.keys())
    
    for key in sorted(all_keys):
        python_val = python_fields.get(key)
        xmlgen_val = xmlgen_fields.get(key)
        
        if python_val != xmlgen_val:
            differences.append(f"  {key}: Python='{python_val}' vs xmlgen='{xmlgen_val}'")
    
    # Comparación estructural normalizada
    try:
        python_content = python_xml.read_text(encoding='utf-8')
        xmlgen_content = xmlgen_xml.read_text(encoding='utf-8')
        
        python_normalized = normalize_xml_for_diff(python_content)
        xmlgen_normalized = normalize_xml_for_diff(xmlgen_content)
        
        if python_normalized != xmlgen_normalized:
            if strict:
                differences.append("  Estructura XML diferente (normalized comparison)")
            
            # Generar diff textual simple
            diff_lines = []
            diff_lines.append("=== DIFERENCIAS ESTRUCTURALES (normalizadas) ===\n")
            
            # Comparación línea por línea (simplificada)
            python_lines = python_normalized.split('\n')
            xmlgen_lines = xmlgen_normalized.split('\n')
            
            max_len = max(len(python_lines), len(xmlgen_lines))
            diff_count = 0
            for i in range(max_len):
                python_line = python_lines[i] if i < len(python_lines) else None
                xmlgen_line = xmlgen_lines[i] if i < len(xmlgen_lines) else None
                
                if python_line != xmlgen_line:
                    diff_count += 1
                    if diff_count <= 20:  # Limitar a 20 diferencias para legibilidad
                        if python_line:
                            diff_lines.append(f"- Python línea {i+1}: {python_line[:100]}")
                        if xmlgen_line:
                            diff_lines.append(f"+ xmlgen línea {i+1}: {xmlgen_line[:100]}")
            
            if diff_count > 20:
                diff_lines.append(f"\n... y {diff_count - 20} diferencias más")
            
            diff_text = '\n'.join(diff_lines)
        else:
            diff_text = "Estructura XML normalizada idéntica\n"
    except Exception as e:
        diff_text = f"Error al generar diff estructural: {e}\n"
    
    # Construir reporte completo
    report_lines = []
    report_lines.append("=== COMPARACIÓN DE CAMPOS CLAVE ===\n")
    if differences:
        report_lines.extend(differences)
    else:
        report_lines.append("  ✅ Todos los campos clave coinciden")
    
    report_lines.append("\n")
    report_lines.append(diff_text)
    
    full_diff_text = '\n'.join(report_lines)
    
    return len(differences) == 0, differences, full_diff_text


def main():
    parser = argparse.ArgumentParser(
        description="Compara generación de DE entre nuestra implementación y xmlgen",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path al archivo JSON de entrada (de_input.json)"
    )
    
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directorio para guardar artifacts (default: artifacts/)"
    )
    
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Comparación estricta (incluye canonicalización XML)"
    )
    
    parser.add_argument(
        "--skip-xmlgen",
        action="store_true",
        help="Omitir generación con xmlgen (solo validar nuestra implementación)"
    )
    
    args = parser.parse_args()
    
    # Resolver artifacts dir
    if args.artifacts_dir is None:
        artifacts_dir = Path(__file__).parent.parent / "artifacts"
    else:
        artifacts_dir = args.artifacts_dir
    
    artifacts_dir.mkdir(exist_ok=True)
    
    # Verificar input
    if not args.input.exists():
        print(f"❌ Archivo de entrada no encontrado: {args.input}")
        return 1
    
    # Cargar input
    try:
        input_data = load_input_json(args.input)
    except Exception as e:
        print(f"❌ Error al cargar JSON: {e}")
        return 1
    
    print(f"📄 Input JSON: {args.input}")
    print()
    
    # Timestamp para nombres de archivos
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # ===== PASO 1: Generar DE con nuestra implementación =====
    print("1️⃣  Generando DE con implementación Python...")
    python_xml_path = artifacts_dir / f"oracle_python_de_{timestamp}.xml"
    try:
        generate_de_python(input_data, python_xml_path)
        print(f"   ✅ Generado: {python_xml_path}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 1
    print()
    
    # ===== PASO 2: Validar nuestro DE contra XSD =====
    print("2️⃣  Validando DE Python contra XSD...")
    xsd_dir = Path(__file__).parent.parent / "schemas_sifen"
    is_valid, errors = validate_against_xsd(python_xml_path, "de", xsd_dir)
    if is_valid:
        print(f"   ✅ XML válido según XSD")
    else:
        print(f"   ❌ XML NO válido:")
        for error in errors:
            print(f"      - {error}")
        if args.strict:
            return 1
    print()
    
    # ===== PASO 3: Generar DE con xmlgen =====
    if args.skip_xmlgen:
        print("3️⃣  Omitiendo generación con xmlgen (--skip-xmlgen)")
        print()
        xmlgen_xml_path = None
    else:
        print("3️⃣  Generando DE con xmlgen (Node.js)...")
        
        generated = generate_de_xmlgen(input_data, artifacts_dir, timestamp)
        if generated:
            xmlgen_xml_path = generated
            print(f"   ✅ Generado: {xmlgen_xml_path}")
        else:
            print(f"   ⚠️  No se pudo generar con xmlgen")
            print(f"      Continuando solo con validación de nuestra implementación...")
            xmlgen_xml_path = None
        print()
        
        # ===== PASO 4: Validar xmlgen DE contra XSD =====
        if xmlgen_xml_path and xmlgen_xml_path.exists():
            print("4️⃣  Validando DE xmlgen contra XSD...")
            if xsd_dir.exists():
                is_valid, errors = validate_against_xsd(xmlgen_xml_path, "de", xsd_dir)
            else:
                is_valid, errors = False, ["XSD no disponible"]
            if is_valid:
                print(f"   ✅ XML válido según XSD")
            else:
                print(f"   ⚠️  XML NO válido según XSD:")
                for error in errors:
                    print(f"      - {error}")
            print()
    
    # ===== PASO 5: Comparar =====
    if xmlgen_xml_path and xmlgen_xml_path.exists():
        print("5️⃣  Comparando campos clave...")
        are_equal, differences, diff_text = compare_xmls(python_xml_path, xmlgen_xml_path, strict=args.strict)
        
        if are_equal:
            print("   ✅ Campos clave coinciden")
        else:
            print("   ⚠️  Diferencias encontradas:")
            for diff in differences:
                print(diff)
        
        # Guardar diff siempre (incluso si son iguales, para auditoría)
        diff_path = artifacts_dir / f"oracle_diff_{timestamp}.txt"
        with diff_path.open('w', encoding='utf-8') as f:
            f.write("=== COMPARACIÓN ORÁCULO ===\n\n")
            f.write(f"Python DE: {python_xml_path}\n")
            f.write(f"xmlgen DE: {xmlgen_xml_path}\n\n")
            f.write(diff_text)
        
        print(f"   📄 Diff guardado en: {diff_path}")
        
        if not are_equal and args.strict:
            print()
            print("❌ Comparación falló (modo strict)")
            return 1
        print()
    else:
        print("5️⃣  Comparación omitida (xmlgen no disponible)")
        print()
    
    # ===== RESUMEN =====
    print("=" * 70)
    print("✅ ORÁCULO COMPLETADO")
    print("=" * 70)
    print(f"   Python DE: {python_xml_path.name}")
    if xmlgen_xml_path:
        print(f"   xmlgen DE: {xmlgen_xml_path.name}")
    
    # Listar artifacts generados
    print(f"\n📦 Artifacts generados en: {artifacts_dir}")
    oracle_files = list(artifacts_dir.glob(f"oracle_*_{timestamp}.*"))
    if oracle_files:
        for f in sorted(oracle_files):
            print(f"   - {f.name}")
    
    # Buscar diff si existe
    diff_files = list(artifacts_dir.glob(f"oracle_diff_{timestamp}.txt"))
    if diff_files:
        print(f"   - {diff_files[0].name}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

