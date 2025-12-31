#!/usr/bin/env python3
"""
Web mínima FastAPI para TESAKA-SIFEN

INSTRUCCIONES DE EJECUCIÓN:

OPCIÓN 1 (Recomendada - Script helper):
   cd tesaka-cv/
   export SIFEN_EMISOR_RUC="4554737-8"
   ./web/run.sh

OPCIÓN 2 (Manual):
1. Asegurarse de estar en el directorio tesaka-cv/
2. Activar el entorno virtual:
   source ../.venv/bin/activate  # desde tesaka-cv/
3. Verificar dependencias:
   pip install fastapi uvicorn jinja2 python-dotenv lxml
   # O todas: pip install -r app/requirements.txt
4. Configurar: export SIFEN_EMISOR_RUC="4554737-8"
5. Ejecutar: python -m uvicorn web.main:app --reload --host 127.0.0.1 --port 8000
6. Abrir: http://127.0.0.1:8000

NOTA: Asegúrate de que el venv esté activado (deberías ver (.venv) en el prompt).
"""
import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# Cargar variables de entorno desde .env si existe
try:
    from dotenv import load_dotenv
    # Buscar .env en el directorio raíz del proyecto (tesaka-cv/)
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        # También intentar en el directorio padre (por si estamos en raíz del repo)
        parent_env = project_root.parent / ".env"
        if parent_env.exists():
            load_dotenv(parent_env)
except ImportError:
    # python-dotenv no está instalado, continuar sin cargar .env
    pass

from . import db
from . import lotes_db

app = FastAPI(title="TESAKA-SIFEN", version="1.0.0")

# Obtener ruta base del proyecto (directorio padre de web/)
WEB_DIR = Path(__file__).parent

# Montar archivos estáticos
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

# Configurar templates
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


def _check_emisor_ruc():
    """
    Obtiene SIFEN_EMISOR_RUC con fallbacks automáticos.
    
    Prioridad:
    1. SIFEN_EMISOR_RUC (variable de entorno o .env)
    2. SIFEN_TEST_RUC (variable de entorno o .env) + calcular DV
    3. Valor por defecto para desarrollo: "80012345-7" (RUC de prueba SIFEN)
    """
    # Intentar obtener RUC principal
    emisor_ruc = os.getenv("SIFEN_EMISOR_RUC")
    
    if emisor_ruc:
        return emisor_ruc.strip()
    
    # Fallback: usar SIFEN_TEST_RUC y calcular DV si es necesario
    test_ruc = os.getenv("SIFEN_TEST_RUC")
    if test_ruc:
        test_ruc = test_ruc.strip()
        # Si no tiene DV, calcularlo
        if '-' not in test_ruc:
            # Calcular DV simple (suma de dígitos mod 10)
            digits = ''.join(c for c in test_ruc if c.isdigit())
            if digits:
                dv = str(sum(int(d) for d in digits) % 10)
                return f"{test_ruc}-{dv}"
        return test_ruc
    
    # Fallback final: usar RUC de prueba por defecto para desarrollo
    # Este es el RUC oficial de prueba de SIFEN según documentación
    default_ruc_num = "80012345"
    # Calcular DV automáticamente
    digits = ''.join(c for c in default_ruc_num if c.isdigit())
    dv = str(sum(int(d) for d in digits) % 10) if digits else "0"
    default_ruc = f"{default_ruc_num}-{dv}"
    
    # Log informativo (solo en desarrollo)
    import logging
    logger = logging.getLogger(__name__)
    logger.info(
        f"SIFEN_EMISOR_RUC no configurado. Usando valor por defecto para desarrollo: {default_ruc}. "
        "Para producción, configurá SIFEN_EMISOR_RUC en .env o variables de entorno."
    )
    
    return default_ruc


def _extract_cdc_from_xml(de_xml: str) -> str:
    """Extrae el CDC del atributo Id del tag <DE>"""
    try:
        from lxml import etree
        root = etree.fromstring(de_xml.encode('utf-8'))
        cdc = root.get('Id')
        if not cdc:
            raise ValueError("No se encontró atributo Id en el tag <DE>")
        return cdc
    except ImportError:
        # Fallback: usar regex si lxml no está disponible
        import re
        match = re.search(r'<DE[^>]*\s+Id=["\']([^"\']+)["\']', de_xml)
        if match:
            return match.group(1)
        raise ValueError("No se encontró atributo Id en el tag <DE>")
    except Exception as e:
        raise ValueError(f"Error al extraer CDC del XML: {e}")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Lista los últimos 50 documentos"""
    try:
        documents = db.list_documents(limit=50)
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "documents": documents}
        )
    except (ConnectionError, Exception) as e:
        error_msg = str(e)
        # Si es error de conexión, mostrar página de error amigable
        error_lower = error_msg.lower()
        if any(keyword in error_lower for keyword in ["connection", "timeout", "could not connect", "connection refused", "operationalerror", "sqlite"]):
            return templates.TemplateResponse(
                "error.html",
                {
                    "request": request,
                    "error_title": "Error de Base de Datos",
                    "error_message": f"Error al acceder a la base de datos SQLite: {error_msg}",
                    "error_details": "Verifica que el archivo tesaka.db exista y tenga permisos de lectura/escritura",
                    "error_code": "DB_ERROR"
                },
                status_code=503
            )
        # Otros errores
        return templates.TemplateResponse(
            "error.html",
            {
                "request": request,
                "error_title": "Error",
                "error_message": f"Error al cargar documentos: {error_msg}",
                "error_code": "UNKNOWN_ERROR"
            },
            status_code=500
        )


@app.get("/de/new", response_class=HTMLResponse)
async def de_new_form(request: Request):
    """Muestra el formulario para crear un nuevo DE"""
    _check_emisor_ruc()  # Verificar que esté configurado
    return templates.TemplateResponse(
        "de_new.html",
        {"request": request}
    )


def _build_de_xml_with_items(
    ruc: str,
    timbrado: str,
    establecimiento: str,
    punto_expedicion: str,
    numero_documento: str,
    items: list,
    fecha: Optional[str] = None,
    hora: Optional[str] = None
) -> str:
    """
    Construye el XML DE con items dinámicos.
    
    Args:
        items: Lista de dicts con keys: codigo, descripcion, cantidad, precio, tasa_iva
    """
    from datetime import datetime
    import importlib.util
    
    # Importar xml_generator_v150 directamente sin pasar por __init__.py
    # para evitar cargar dependencias pesadas (cryptography, etc.)
    xml_gen_path = Path(__file__).parent.parent / "app" / "sifen_client" / "xml_generator_v150.py"
    spec = importlib.util.spec_from_file_location("xml_generator_v150", xml_gen_path)
    xml_gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(xml_gen)
    generate_cdc = xml_gen.generate_cdc
    calculate_digit_verifier = xml_gen.calculate_digit_verifier
    
    if fecha is None:
        fecha = datetime.now().strftime("%Y-%m-%d")
    if hora is None:
        hora = datetime.now().strftime("%H:%M:%S")
    
    # Parsear RUC
    ruc_str = str(ruc or "").strip()
    if not ruc_str or '-' not in ruc_str:
        raise ValueError("RUC debe venir como RUC-DV (ej: 4554737-8)")
    ruc_parts = ruc_str.split('-', 1)
    ruc_num = ruc_parts[0].strip()
    dv_ruc = ruc_parts[1].strip()
    ruc_for_cdc = ruc_num[:8].zfill(8) if len(ruc_num) < 8 else ruc_num[:8]
    
    fecha_firma = f"{fecha}T{hora}"
    tipo_documento = "1"
    
    # Calcular totales de items
    total_general = 0
    subtotal_exe = 0
    subtotal_5 = 0
    subtotal_10 = 0
    iva_5 = 0
    iva_10 = 0
    base_grav_5 = 0
    base_grav_10 = 0
    
    items_xml = []
    for idx, item in enumerate(items, 1):
        codigo = item.get('codigo', f"{idx:03d}")
        descripcion = item.get('descripcion', 'Producto')
        cantidad = float(item.get('cantidad', 1))
        precio = float(item.get('precio', 0))
        tasa_iva = int(item.get('tasa_iva', 0))
        
        subtotal_item = cantidad * precio
        iva_item = subtotal_item * (tasa_iva / 100) if tasa_iva > 0 else 0
        total_item = subtotal_item + iva_item
        
        total_general += total_item
        
        if tasa_iva == 0:
            subtotal_exe += subtotal_item
        elif tasa_iva == 5:
            subtotal_5 += subtotal_item
            iva_5 += iva_item
            base_grav_5 += subtotal_item
        elif tasa_iva == 10:
            subtotal_10 += subtotal_item
            iva_10 += iva_item
            base_grav_10 += subtotal_item
        
        items_xml.append(f"""        <gCamItem>
            <dCodInt>{codigo}</dCodInt>
            <dDesProSer>{descripcion}</dDesProSer>
            <cUniMed>77</cUniMed>
            <dDesUniMed>UNI</dDesUniMed>
            <dCantProSer>{cantidad:.2f}</dCantProSer>
            <gValorItem>
                <dPUniProSer>{precio:.0f}</dPUniProSer>
                <dTotBruOpeItem>{subtotal_item:.0f}</dTotBruOpeItem>
                <gValorRestaItem>
                    <dTotOpeItem>{total_item:.0f}</dTotOpeItem>
                </gValorRestaItem>
            </gValorItem>
        </gCamItem>""")
    
    # Monto para CDC (total general sin IVA, redondeado)
    monto_cdc = str(int(total_general - iva_5 - iva_10))
    
    # Generar CDC
    cdc = generate_cdc(ruc_for_cdc, timbrado, establecimiento, punto_expedicion, 
                      numero_documento, tipo_documento, fecha.replace("-", ""), monto_cdc)
    digits_in_cdc = ''.join(c for c in cdc if c.isdigit())
    dv_id = calculate_digit_verifier(digits_in_cdc)
    
    cod_seg = "123456789"
    
    # Construir XML
    items_xml_str = "\n".join(items_xml)
    
    xml = f"""<DE xmlns="http://ekuatia.set.gov.py/sifen/xsd" Id="{cdc}">
    <dDVId>{dv_id}</dDVId>
    <dFecFirma>{fecha_firma}</dFecFirma>
    <dSisFact>1</dSisFact>
    <gOpeDE>
        <iTipEmi>1</iTipEmi>
        <dDesTipEmi>Normal</dDesTipEmi>
        <dCodSeg>{cod_seg}</dCodSeg>
    </gOpeDE>
    <gTimb>
        <iTiDE>{tipo_documento}</iTiDE>
        <dNumTim>{timbrado}</dNumTim>
        <dEst>{establecimiento}</dEst>
        <dPunExp>{punto_expedicion}</dPunExp>
        <dNumDoc>{numero_documento}</dNumDoc>
        <dSerieNum>001</dSerieNum>
    </gTimb>
    <gDatGralOpe>
        <iTipEmi>1</iTipEmi>
        <dDesTipEmi>Normal</dDesTipEmi>
        <dFeEmiDE>{fecha}</dFeEmiDE>
        <dHoEmiDE>{hora}</dHoEmiDE>
        <iCondOpe>1</iCondOpe>
        <dDesCondOpe>Contado</dDesCondOpe>
        <iTipoCont>1</iTipoCont>
        <dDesTipoCont>Efectivo</dDesTipoCont>
        <iCondCred>1</iCondCred>
        <dPlazoCre>0</dPlazoCre>
        <dCuotas>0</dCuotas>
        <gEmis>
            <dRucEm>{ruc_num}</dRucEm>
            <dDVEmi>{dv_ruc}</dDVEmi>
            <dNomEmi>Marcio Ruben Feris Aguilera</dNomEmi>
            <dDirEmi>Asunción</dDirEmi>
            <dNumCasEmi>1234</dNumCasEmi>
            <cDepEmi>1</cDepEmi>
            <dDesDepEmi>CAPITAL</dDesDepEmi>
            <cCiuEmi>1</cCiuEmi>
            <dDesCiuEmi>Asunción</dDesCiuEmi>
            <dTelEmi>021123456</dTelEmi>
            <dEmailEmi>test@example.com</dEmailEmi>
            <gActEco>
                <cActEco>471100</cActEco>
                <dDesActEco>Venta al por menor en comercios no especializados</dDesActEco>
            </gActEco>
        </gEmis>
        <gDatRec>
            <iNatRec>1</iNatRec>
            <iTiOpe>1</iTiOpe>
            <cPaisRec>PRY</cPaisRec>
            <dDesPaisRec>Paraguay</dDesPaisRec>
            <dRucRec>80012345</dRucRec>
            <dDVRec>7</dDVRec>
            <dNomRec>Cliente de Prueba</dNomRec>
            <dDirRec>Asunción</dDirRec>
            <dNumCasRec>5678</dNumCasRec>
            <cDepRec>1</cDepRec>
            <dDesDepRec>CAPITAL</dDesDepRec>
            <cCiuRec>1</cCiuRec>
            <dDesCiuRec>Asunción</dDesCiuRec>
        </gDatRec>
    </gDatGralOpe>
    <gDtipDE>
{items_xml_str}
    </gDtipDE>
    <gTotSub>
        <dSubExe>{subtotal_exe:.0f}</dSubExe>
        <dSubExo>0</dSubExo>
        <dSub5>{subtotal_5:.0f}</dSub5>
        <dSub10>{subtotal_10:.0f}</dSub10>
        <dTotOpe>{total_general - iva_5 - iva_10:.0f}</dTotOpe>
        <dTotDesc>0</dTotDesc>
        <dTotDescGlotem>0</dTotDescGlotem>
        <dTotAntItem>0</dTotAntItem>
        <dTotAnt>0</dTotAnt>
        <dPorcDescTotal>0</dPorcDescTotal>
        <dDescTotal>0</dDescTotal>
        <dAnticipo>0</dAnticipo>
        <dRedon>0</dRedon>
        <dTotGralOpe>{total_general - iva_5 - iva_10:.0f}</dTotGralOpe>
        <dIVA5>{iva_5:.0f}</dIVA5>
        <dIVA10>{iva_10:.0f}</dIVA10>
        <dLiqTotIVA5>{iva_5:.0f}</dLiqTotIVA5>
        <dLiqTotIVA10>{iva_10:.0f}</dLiqTotIVA10>
        <dIVAComi>0</dIVAComi>
        <dTotIVA>{iva_5 + iva_10:.0f}</dTotIVA>
        <dBaseGrav5>{base_grav_5:.0f}</dBaseGrav5>
        <dBaseGrav10>{base_grav_10:.0f}</dBaseGrav10>
        <dTBasGraIVA>{base_grav_5 + base_grav_10:.0f}</dTBasGraIVA>
        <dTotalGs>{total_general:.0f}</dTotalGs>
    </gTotSub>
    <ds:Signature xmlns:ds="http://www.w3.org/2000/09/xmldsig#">
        <ds:SignedInfo>
            <ds:CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>
            <ds:SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>
            <ds:Reference URI="">
                <ds:Transforms>
                    <ds:Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>
                </ds:Transforms>
                <ds:DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>
                <ds:DigestValue>dGhpcyBpcyBhIHRlc3QgZGlnZXN0IHZhbHVl</ds:DigestValue>
            </ds:Reference>
        </ds:SignedInfo>
        <ds:SignatureValue>dGhpcyBpcyBhIHRlc3Qgc2lnbmF0dXJlIHZhbHVlIGZvciBwcnVlYmFzIG9ubHk=</ds:SignatureValue>
        <ds:KeyInfo>
            <ds:X509Data>
                <ds:X509Certificate>LS0tLS1CRUdJTiBDRVJUSUZJQ0FURS0tLS0tCk1JSUVKakNDQWpLZ0F3SUJBZ0lEQW5CZ2txaGtpRzl3MEJBUXNGQUFEV1lqRU1NQW9HQTFVRUNoTURVbVZzWVcKd2dnRWlNQTBHQ1NxR1NJYjM=</ds:X509Certificate>
            </ds:X509Data>
        </ds:KeyInfo>
    </ds:Signature>
    <gCamFuFD>
        <dCarQR>TESTQRCODE12345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890</dCarQR>
    </gCamFuFD>
</DE>"""
    
    return xml


@app.post("/de/new", response_class=HTMLResponse)
async def de_new_submit(
    request: Request,
    timbrado: str = Form(...),
    establecimiento: str = Form("001"),
    punto_expedicion: str = Form("001"),
    numero_documento: str = Form("0000001")
):
    """Procesa el formulario y crea un nuevo DE"""
    # Validar SIFEN_EMISOR_RUC
    emisor_ruc = _check_emisor_ruc()
    
    # Validar timbrado: solo dígitos, largo 8
    timbrado = timbrado.strip()
    if not timbrado:
        raise HTTPException(status_code=400, detail="El timbrado no puede estar vacío")
    if not timbrado.isdigit():
        raise HTTPException(status_code=400, detail="El timbrado debe contener solo dígitos")
    if len(timbrado) != 8:
        raise HTTPException(status_code=400, detail="El timbrado debe tener exactamente 8 dígitos")
    
    # Extraer items del formulario
    form_data = await request.form()
    items = []
    item_indices = set()
    
    # Identificar todos los índices de items (formato: item_codigo_0, item_descripcion_0, etc.)
    for key in form_data.keys():
        if key.startswith('item_'):
            # Formato: item_codigo_0, item_descripcion_0, item_cantidad_0, etc.
            parts = key.split('_')
            if len(parts) >= 3:
                index = parts[-1]  # Último segmento es el índice
                item_indices.add(index)
    
    # Construir lista de items
    for index in sorted(item_indices, key=lambda x: int(x) if x.isdigit() else 999):
        codigo = form_data.get(f'item_codigo_{index}', f"{len(items)+1:03d}")
        descripcion = form_data.get(f'item_descripcion_{index}', '')
        cantidad_str = form_data.get(f'item_cantidad_{index}', '1')
        precio_str = form_data.get(f'item_precio_{index}', '0')
        tasa_iva_str = form_data.get(f'item_tasa_iva_{index}', '0')
        
        # Solo agregar si tiene descripción (campo requerido)
        if descripcion.strip():
            try:
                items.append({
                    'codigo': codigo.strip() or f"{len(items)+1:03d}",
                    'descripcion': descripcion.strip(),
                    'cantidad': float(cantidad_str) if cantidad_str else 1.0,
                    'precio': float(precio_str) if precio_str else 0.0,
                    'tasa_iva': int(tasa_iva_str) if tasa_iva_str else 0
                })
            except (ValueError, TypeError):
                # Si hay error de conversión, usar defaults
                items.append({
                    'codigo': codigo.strip() or f"{len(items)+1:03d}",
                    'descripcion': descripcion.strip(),
                    'cantidad': 1.0,
                    'precio': 0.0,
                    'tasa_iva': 0
                })
    
    if not items:
        raise HTTPException(status_code=400, detail="Debe agregar al menos un item a la factura")
    
    # Generar DE XML con items
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        de_xml = _build_de_xml_with_items(
            ruc=emisor_ruc,
            timbrado=timbrado,
            establecimiento=establecimiento,
            punto_expedicion=punto_expedicion,
            numero_documento=numero_documento,
            items=items
        )
    except ImportError as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error al importar módulo de generación DE: {e}. Instala dependencias: pip install -r app/requirements.txt"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Extraer CDC del XML
    try:
        cdc = _extract_cdc_from_xml(de_xml)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Intentar insertar en la base de datos
    # Si hay unique violation por CDC, reintentar con numero_documento + 1
    max_retries = 2
    for attempt in range(max_retries):
        try:
            db.insert_document(
                cdc=cdc,
                ruc_emisor=emisor_ruc,
                timbrado=timbrado,
                de_xml=de_xml
            )
            return RedirectResponse(url="/", status_code=303)
        except ConnectionError as e:
            # Verificar si es error de unique violation (CDC duplicado)
            error_str = str(e).lower()
            if "unique" in error_str or "duplicate" in error_str or "cdc duplicado" in error_str:
                # CDC duplicado: regenerar con numero_documento incrementado
                if attempt < max_retries - 1:
                    try:
                        num_doc_int = int(numero_documento)
                        numero_documento = str(num_doc_int + 1).zfill(len(numero_documento))
                        # Regenerar DE con nuevo número (build_de_xml ya importado arriba)
                        from tools.build_de import build_de_xml
                        de_xml = build_de_xml(
                            ruc=emisor_ruc,
                            timbrado=timbrado,
                            establecimiento=establecimiento,
                            punto_expedicion=punto_expedicion,
                            numero_documento=numero_documento
                        )
                        cdc = _extract_cdc_from_xml(de_xml)
                        continue
                    except (ValueError, TypeError):
                        pass
            raise HTTPException(status_code=500, detail=f"Error al guardar documento: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al guardar documento: {str(e)}")
    
    raise HTTPException(status_code=500, detail="Error al guardar documento después de reintentos")


@app.get("/de/{doc_id}", response_class=HTMLResponse)
async def de_detail(request: Request, doc_id: int):
    """Muestra el detalle de un documento"""
    try:
        document = db.get_document(doc_id)
        if not document:
            raise HTTPException(status_code=404, detail=f"Documento {doc_id} no encontrado")
        
        return templates.TemplateResponse(
            "de_detail.html",
            {"request": request, "doc": document}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al cargar documento: {str(e)}")


@app.post("/de/{doc_id}/send", response_class=HTMLResponse)
async def de_send_to_sifen(request: Request, doc_id: int, mode: str = "lote"):
    """
    Envía un documento a SIFEN y actualiza su estado.
    
    Parámetros:
    - mode: "lote" (default) o "direct"
      * "lote": Envía como siRecepLoteDE, guarda dProtConsLote y consulta automáticamente
      * "direct": Envía como siRecepDE, respuesta inmediata sin consulta de lote
    """
    try:
        # Validar mode
        if mode not in ("lote", "direct"):
            raise HTTPException(
                status_code=400,
                detail=f"Parámetro 'mode' inválido: '{mode}'. Valores permitidos: 'lote', 'direct'"
            )
        
        document = db.get_document(doc_id)
        if not document:
            raise HTTPException(status_code=404, detail=f"Documento {doc_id} no encontrado")
        
        # Actualizar estado a "sending"
        db.update_document_status(doc_id, status="sending")
        
        # Importar cliente SIFEN (lazy import)
        import sys
        import re
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        try:
            from app.sifen_client.soap_client import SoapClient
            from app.sifen_client.exceptions import SifenClientError
            from app.sifen_client.config import get_sifen_config
            
            # Obtener configuración
            env = os.getenv("SIFEN_ENV", "test")
            config = get_sifen_config(env=env)
            
            # Crear cliente (puede lanzar SifenClientError si falta mTLS)
            try:
                client = SoapClient(config=config)
            except SifenClientError as e:
                # Error de configuración (mTLS, etc.) - guardar y redirigir
                error_msg = str(e)
                db.update_document_status(doc_id, status="error", message=error_msg)
                return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
            except Exception as e:
                # Otros errores al crear cliente - guardar y redirigir
                error_msg = f"Error al crear cliente SIFEN: {str(e)}"
                db.update_document_status(doc_id, status="error", message=error_msg)
                return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
            
            # Obtener DE XML
            de_xml = document['de_xml']
            
            if mode == "lote":
                # Flujo por lote (siRecepLoteDE)
                from tools.send_sirecepde import build_r_envio_lote_xml, build_lote_base64_from_single_xml
                
                de_xml_bytes = de_xml.encode("utf-8")
                zip_base64 = build_lote_base64_from_single_xml(de_xml_bytes)
                payload_xml = build_r_envio_lote_xml(did=1, xml_bytes=de_xml_bytes, zip_base64=zip_base64)
                
                # Enviar lote a SIFEN
                response = client.recepcion_lote(payload_xml)
                
                # Extraer dProtConsLote de la respuesta
                d_prot_cons_lote = response.get('d_prot_cons_lote')
                
                # Actualizar estado del documento según respuesta
                if response.get('ok'):
                    status = "approved"
                    code = response.get('codigo_respuesta', '0200')
                    message = response.get('mensaje', 'Lote aceptado')
                else:
                    status = "rejected"
                    code = response.get('codigo_respuesta', '0100')
                    message = response.get('mensaje', 'Lote rechazado')
                
                # Guardar respuesta del documento
                db.update_document_status(
                    doc_id=doc_id,
                    status=status,
                    code=code,
                    message=message,
                    sirecepde_xml=payload_xml
                )
                
                # Si se recibió dProtConsLote, guardar lote y consultar automáticamente
                if d_prot_cons_lote:
                    # Validar que sea solo dígitos
                    if not re.match(r'^\d+$', d_prot_cons_lote.strip()):
                        # Log warning pero continuar
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(
                            f"dProtConsLote no es solo dígitos: '{d_prot_cons_lote}'. "
                            "No se guardará ni consultará el lote."
                        )
                    else:
                        try:
                            # Guardar lote en BD
                            lote_id = lotes_db.create_lote(
                                env=env,
                                d_prot_cons_lote=d_prot_cons_lote.strip(),
                                de_document_id=doc_id
                            )
                            
                            # Consultar automáticamente el estado del lote
                            await _check_lote_status_async(lote_id, env, d_prot_cons_lote.strip())
                            
                        except ValueError as e:
                            # Lote ya existe o error de validación
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.warning(f"No se pudo guardar/consultar lote: {e}")
                        except Exception as e:
                            # Error al consultar, pero no fallar el envío
                            import logging
                            logger = logging.getLogger(__name__)
                            logger.error(f"Error al consultar lote automáticamente: {e}")
            
            else:  # mode == "direct"
                # Flujo directo (siRecepDE)
                from tools.build_sirecepde import build_sirecepde_xml
                
                # Construir rEnviDe desde el DE XML
                payload_xml = build_sirecepde_xml(
                    de_xml_content=de_xml,
                    d_id="1"
                )
                
                # Enviar directamente a SIFEN
                try:
                    response = client.recepcion_de(payload_xml)
                except SifenClientError as e:
                    # Error de SIFEN (mTLS, configuración, etc.) - guardar y redirigir
                    error_msg = str(e)
                    db.update_document_status(doc_id, status="error", message=error_msg)
                    return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                
                # Parsear respuesta (recepcion_de retorna dict con ok, codigo_respuesta, mensaje, etc.)
                if isinstance(response, dict):
                    # Respuesta parseada correctamente
                    if response.get('ok'):
                        status = "approved"
                        code = response.get('codigo_respuesta', '0200')
                        message = response.get('mensaje', 'DE aceptado')
                    else:
                        status = "rejected"
                        code = response.get('codigo_respuesta', '0100')
                        message = response.get('mensaje', 'DE rechazado')
                    
                    # Guardar respuesta XML parseada si está disponible
                    response_xml = response.get('parsed_fields', {}).get('xml')
                else:
                    # Respuesta inesperada (no dict), guardar como sent
                    status = "sent"
                    code = None
                    message = "Respuesta recibida pero no parseada correctamente"
                    response_xml = str(response) if response else None
                
                # Guardar respuesta del documento
                db.update_document_status(
                    doc_id=doc_id,
                    status=status,
                    code=code,
                    message=message,
                    sirecepde_xml=payload_xml
                )
            
            return RedirectResponse(url=f"/de/{doc_id}?sent=1", status_code=303)
            
        except ImportError as e:
            error_msg = f"Error de importación: {e}. Instala dependencias: pip install -r app/requirements.txt"
            db.update_document_status(doc_id, status="error", message=error_msg)
            return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
        except (SifenClientError, Exception) as e:
            # Capturar errores de SIFEN (mTLS, configuración, etc.) y otros errores
            error_msg = str(e)
            db.update_document_status(doc_id, status="error", message=error_msg)
            return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


async def _check_lote_status_async(lote_id: int, env: str, prot: str):
    """
    Helper async para consultar el estado de un lote.
    Se ejecuta en background después de recibir dProtConsLote.
    """
    import asyncio
    from app.sifen_client.lote_checker import (
        check_lote_status,
        determine_status_from_cod_res_lot,
    )
    
    # Ejecutar en thread pool para no bloquear
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        check_lote_status,
        env,
        prot,
        None,  # p12_path (usa env vars)
        None,  # p12_password (usa env vars)
        30,    # timeout
    )
    
    if result.get("success"):
        cod_res_lot = result.get("cod_res_lot")
        msg_res_lot = result.get("msg_res_lot")
        response_xml = result.get("response_xml")
        
        # Determinar estado
        status = determine_status_from_cod_res_lot(cod_res_lot)
        
        # Actualizar lote
        lotes_db.update_lote_status(
            lote_id=lote_id,
            status=status,
            cod_res_lot=cod_res_lot,
            msg_res_lot=msg_res_lot,
            response_xml=response_xml,
        )
    else:
        # Error al consultar
        error_msg = result.get("error", "Error desconocido")
        lotes_db.update_lote_status(
            lote_id=lote_id,
            status=lotes_db.LOTE_STATUS_ERROR,
            msg_res_lot=error_msg,
        )


@app.get("/admin/sifen/lotes", response_class=HTMLResponse)
async def admin_lotes_list(request: Request, env: Optional[str] = None, status: Optional[str] = None):
    """
    Lista lotes SIFEN con filtros opcionales.
    
    Query params:
        env: Filtrar por ambiente (test/prod)
        status: Filtrar por estado
    """
    try:
        lotes = lotes_db.list_lotes(env=env, status=status, limit=100)
        return templates.TemplateResponse(
            "admin_lotes_list.html",
            {"request": request, "lotes": lotes, "env_filter": env, "status_filter": status}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar lotes: {str(e)}")


@app.get("/admin/sifen/lotes/{lote_id}", response_class=HTMLResponse)
async def admin_lote_detail(request: Request, lote_id: int):
    """Muestra el detalle de un lote con su XML de respuesta"""
    try:
        lote = lotes_db.get_lote(lote_id)
        if not lote:
            raise HTTPException(status_code=404, detail=f"Lote {lote_id} no encontrado")
        
        return templates.TemplateResponse(
            "admin_lote_detail.html",
            {"request": request, "lote": lote}
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al cargar lote: {str(e)}")


@app.post("/admin/sifen/lotes/{lote_id}/check", response_class=HTMLResponse)
async def admin_lote_check(request: Request, lote_id: int):
    """
    Consulta manualmente el estado de un lote (una sola vez).
    """
    try:
        lote = lotes_db.get_lote(lote_id)
        if not lote:
            raise HTTPException(status_code=404, detail=f"Lote {lote_id} no encontrado")
        
        env = lote["env"]
        prot = lote["d_prot_cons_lote"]
        
        # Consultar estado
        await _check_lote_status_async(lote_id, env, prot)
        
        return RedirectResponse(url=f"/admin/sifen/lotes/{lote_id}?checked=1", status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar lote: {str(e)}")
