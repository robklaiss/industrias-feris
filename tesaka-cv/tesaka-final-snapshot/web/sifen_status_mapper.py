"""
Mapeo de respuestas SIFEN a estados de documentos.

Este módulo contiene funciones para:
- Mapear códigos de respuesta de recepción a estados
- Parsear respuesta de consulta de lote y extraer resultados de DE individuales
- Determinar si un DE fue aprobado o rechazado según respuesta de SIFEN
"""
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

try:
    from lxml import etree
    HAS_LXML = True
except ImportError:
    try:
        import xml.etree.ElementTree as etree
        HAS_LXML = False
    except ImportError:
        etree = None
        HAS_LXML = False

from .document_status import (
    STATUS_SIGNED_LOCAL,
    STATUS_SENT_TO_SIFEN,
    STATUS_PENDING_SIFEN,
    STATUS_APPROVED,
    STATUS_REJECTED,
    STATUS_ERROR,
)


def map_recepcion_response_to_status(response: Dict[str, Any]) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Mapea la respuesta de recepción (siRecepLoteDE/siRecepDE) a estado de documento.
    
    IMPORTANTE: La recepción exitosa NO significa aprobación, solo que SIFEN recibió el lote/DE.
    
    Args:
        response: Respuesta de recepción con campos: ok, codigo_respuesta, mensaje, d_prot_cons_lote, d_tpo_proces
        
    Returns:
        Tupla (status, code, message)
        - status: STATUS_SENT_TO_SIFEN si ok, STATUS_ERROR si no
        - code: Código de respuesta SIFEN
        - message: Mensaje de respuesta SIFEN
    """
    if not response:
        return STATUS_ERROR, None, "Respuesta vacía"
    
    codigo = response.get('codigo_respuesta')
    mensaje = response.get('mensaje')
    d_prot = response.get('d_prot_cons_lote')
    
    # Parsear dProtConsLote como entero si es posible
    d_prot_int = None
    if d_prot:
        try:
            d_prot_str = str(d_prot).strip()
            if d_prot_str and d_prot_str != "0":
                d_prot_int = int(d_prot_str)
        except (ValueError, AttributeError):
            pass
    
    # Si dCodRes == "0300" y dProtConsLote > 0: ENVIADO/ENCOLADO
    if codigo == "0300" and d_prot_int and d_prot_int > 0:
        return STATUS_SENT_TO_SIFEN, codigo, mensaje or "Lote recibido por SIFEN"
    
    # Si dCodRes != "0300" (ej 0301) o dProtConsLote == 0: ERROR/RECHAZADO
    if codigo != "0300" or (d_prot_int is not None and d_prot_int == 0):
        # Mensaje específico para 0301
        if codigo == "0301":
            error_msg = mensaje or "Lote no encolado para procesamiento"
            return STATUS_ERROR, codigo, error_msg
        else:
            # Otro código de error
            return STATUS_ERROR, codigo, mensaje or "Error en recepción"
    
    # Caso especial: 0300 sin dProtConsLote (modo directo)
    if codigo == "0300":
        return STATUS_SENT_TO_SIFEN, codigo, mensaje or "DE recibido por SIFEN"
    
    # Fallback: usar ok si está disponible
    ok = response.get('ok', False)
    if ok:
        return STATUS_SENT_TO_SIFEN, codigo, mensaje
    else:
        return STATUS_ERROR, codigo, mensaje or "Error en recepción"


def parse_lote_de_results(xml_response: str) -> List[Dict[str, Any]]:
    """
    Parsea la respuesta de consulta de lote y extrae resultados de DE individuales.
    
    Cuando el código es 0362 (procesamiento concluido), la respuesta contiene:
    - gResProc: Lista de resultados de procesamiento, cada uno con:
      - id: CDC del DE
      - dEstRes: Estado del resultado ("Aceptado", "Rechazado", etc.)
      - dProtAut: Número de transacción (si está aprobado)
      - gResProc: Lista de códigos/mensajes de resultado
    
    Args:
        xml_response: XML de respuesta de consulta de lote
        
    Returns:
        Lista de dicts con:
            - cdc: CDC del DE
            - estado: "Aceptado" o "Rechazado"
            - d_prot_aut: Número de transacción (opcional)
            - codigos: Lista de códigos de resultado
            - mensajes: Lista de mensajes de resultado
    """
    if not xml_response or not etree:
        return []
    
    results = []
    
    try:
        if isinstance(xml_response, str):
            xml_bytes = xml_response.encode("utf-8")
        else:
            xml_bytes = xml_response
        
        root = etree.fromstring(xml_bytes)
        
        # Buscar todos los elementos gResProc (resultados de procesamiento)
        # Usar XPath solo si es lxml, sino usar iter
        if HAS_LXML:
            gresproc_list = root.xpath(".//*[local-name()='gResProc']")
        else:
            # Fallback para xml.etree.ElementTree: buscar por iteración
            gresproc_list = []
            for elem in root.iter():
                # Extraer localname
                tag = elem.tag
                if '}' in tag:
                    localname = tag.split('}', 1)[1]
                else:
                    localname = tag
                if localname == 'gResProc':
                    gresproc_list.append(elem)
        
        def find_by_localname(elem, localname):
            """Busca elemento por localname (compatible con lxml y ElementTree)"""
            if HAS_LXML:
                nodes = elem.xpath(f".//*[local-name()='{localname}']")
                return nodes[0] if nodes else None
            else:
                # Fallback para ElementTree
                for child in elem.iter():
                    tag = child.tag
                    if '}' in tag:
                        child_localname = tag.split('}', 1)[1]
                    else:
                        child_localname = tag
                    if child_localname == localname:
                        return child
                return None
        
        def find_all_by_localname(elem, localname):
            """Busca todos los elementos por localname"""
            if HAS_LXML:
                return elem.xpath(f".//*[local-name()='{localname}']")
            else:
                # Fallback para ElementTree
                results = []
                for child in elem.iter():
                    tag = child.tag
                    if '}' in tag:
                        child_localname = tag.split('}', 1)[1]
                    else:
                        child_localname = tag
                    if child_localname == localname:
                        results.append(child)
                return results
        
        for gresproc in gresproc_list:
            # Buscar id (CDC) - buscar directamente en hijos
            id_elem = find_by_localname(gresproc, 'id')
            cdc = id_elem.text.strip() if id_elem is not None and id_elem.text else None
            
            # Buscar dEstRes (estado del resultado)
            destres_elem = find_by_localname(gresproc, 'dEstRes')
            estado = destres_elem.text.strip() if destres_elem is not None and destres_elem.text else None
            
            # Buscar dProtAut (número de transacción)
            dprotaut_elem = find_by_localname(gresproc, 'dProtAut')
            d_prot_aut = dprotaut_elem.text.strip() if dprotaut_elem is not None and dprotaut_elem.text else None
            
            # Buscar dFecProc (fecha de procesamiento)
            dfecproc_elem = find_by_localname(gresproc, 'dFecProc')
            d_fec_proc = dfecproc_elem.text.strip() if dfecproc_elem is not None and dfecproc_elem.text else None
            
            # Buscar gResProc anidados (códigos y mensajes de resultado)
            # NOTA: gResProc puede estar anidado dentro de otro gResProc
            codigos = []
            mensajes = []
            # Buscar todos los gResProc hijos (no recursivo, solo hijos directos)
            for child in gresproc:
                tag = child.tag
                if '}' in tag:
                    child_localname = tag.split('}', 1)[1]
                else:
                    child_localname = tag
                if child_localname == 'gResProc':
                    # Buscar dCodRes y dMsgRes dentro de este gResProc hijo
                    cod_elem = find_by_localname(child, 'dCodRes')
                    if cod_elem is not None and cod_elem.text:
                        codigos.append(cod_elem.text.strip())
                    
                    msg_elem = find_by_localname(child, 'dMsgRes')
                    if msg_elem is not None and msg_elem.text:
                        mensajes.append(msg_elem.text.strip())
            
            if cdc:
                results.append({
                    'cdc': cdc,
                    'estado': estado,
                    'd_prot_aut': d_prot_aut,
                    'd_fec_proc': d_fec_proc,
                    'codigos': codigos,
                    'mensajes': mensajes,
                })
    
    except Exception as e:
        # Si falla el parsing, retornar lista vacía
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Error al parsear resultados de lote: {e}")
    
    return results


def map_lote_consulta_to_de_status(
    cod_res_lot: Optional[str],
    xml_response: Optional[str],
    cdc: str
) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
    """
    Mapea la respuesta de consulta de lote al estado de un DE específico.
    
    IMPORTANTE: La decisión final está en dEstRes por cada DE, NO solo en dCodResLot.
    - dCodResLot=0362 solo indica que el lote terminó; dEstRes indica aprobación/rechazo.
    - dEstRes="Aprobado", "Aprobado con observación", "Aceptado" => APPROVED
    - dEstRes="Rechazado", "Rechazado con observación" => REJECTED
    - dCodResLot=0361 => PENDING_SIFEN (lote en procesamiento)
    
    Args:
        cod_res_lot: Código de respuesta del lote (ej: "0361", "0362", "0364")
        xml_response: XML completo de respuesta (opcional, para parsear resultados de DE)
        cdc: CDC del DE a buscar en los resultados
        
    Returns:
        Tupla (status, code, message, approved_at)
        - status: STATUS_APPROVED, STATUS_REJECTED, STATUS_PENDING_SIFEN, o STATUS_ERROR
        - code: Código de resultado del DE (opcional)
        - message: Mensaje de resultado del DE (opcional)
        - approved_at: Fecha/hora de aprobación desde dFecProc (opcional)
    """
    if not cod_res_lot:
        return STATUS_ERROR, None, "Código de respuesta de lote no disponible", None
    
    cod_res_lot = cod_res_lot.strip()
    
    # 0361: Lote en procesamiento (aún no hay resultado final)
    if cod_res_lot == "0361":
        return STATUS_PENDING_SIFEN, cod_res_lot, "Lote en procesamiento", None
    
    # 0362: Procesamiento concluido - buscar resultado del DE específico
    # IMPORTANTE: NO decidir solo por 0362; la decisión final está en dEstRes
    if cod_res_lot == "0362":
        if xml_response:
            # Parsear resultados de DE
            de_results = parse_lote_de_results(xml_response)
            
            # Buscar el DE específico por CDC
            for de_result in de_results:
                if de_result.get('cdc') == cdc:
                    estado = de_result.get('estado', '').strip()
                    d_prot_aut = de_result.get('d_prot_aut')
                    codigos = de_result.get('codigos', [])
                    mensajes = de_result.get('mensajes', [])
                    d_fec_proc = de_result.get('d_fec_proc')  # Fecha de procesamiento
                    
                    # Determinar si fue aprobado o rechazado según dEstRes
                    estado_lower = estado.lower() if estado else ""
                    
                    # APROBADO: "Aprobado", "Aprobado con observación", "Aceptado" (compat)
                    if estado_lower in ["aprobado", "aprobado con observación", "aceptado", "autorizado"]:
                        code = codigos[0] if codigos else None
                        message = mensajes[0] if mensajes else estado
                        # Usar dFecProc si está disponible, sino fecha actual
                        approved_at = d_fec_proc if d_fec_proc else datetime.now().isoformat()
                        return STATUS_APPROVED, code, message, approved_at
                    # RECHAZADO: "Rechazado", "Rechazado con observación"
                    elif estado_lower in ["rechazado", "rechazado con observación"]:
                        code = codigos[0] if codigos else None
                        message = mensajes[0] if mensajes else estado
                        return STATUS_REJECTED, code, message, None
                    else:
                        # Estado desconocido
                        code = codigos[0] if codigos else None
                        message = mensajes[0] if mensajes else estado or "Estado desconocido"
                        return STATUS_ERROR, code, message, None
            
            # DE no encontrado en los resultados (puede ser que no esté en el lote)
            return STATUS_ERROR, None, f"DE con CDC {cdc} no encontrado en resultados del lote", None
        else:
            # Sin XML para parsear, pero el lote está procesado
            # No podemos determinar si fue aprobado o rechazado sin los resultados
            return STATUS_PENDING_SIFEN, cod_res_lot, "Lote procesado, pero no se pudo parsear resultado del DE", None
    
    # 0364: Consulta extemporánea (más de 48h) - requiere consulta por CDC
    if cod_res_lot == "0364":
        return STATUS_PENDING_SIFEN, cod_res_lot, "Consulta extemporánea, usar consulta por CDC", None
    
    # 0360: Lote inexistente
    if cod_res_lot == "0360":
        return STATUS_ERROR, cod_res_lot, "Lote inexistente", None
    
    # Otros códigos: error
    return STATUS_ERROR, cod_res_lot, f"Código de respuesta desconocido: {cod_res_lot}", None

