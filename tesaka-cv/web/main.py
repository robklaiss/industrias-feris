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
from datetime import datetime, timezone
from pathlib import Path as FSPath
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

try:
    from dotenv import load_dotenv
    PROJECT_ROOT = FSPath(__file__).resolve().parent.parent
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    else:
        parent_env = PROJECT_ROOT.parent / ".env"
        if parent_env.exists():
            load_dotenv(parent_env)
except ImportError:
    PROJECT_ROOT = FSPath(__file__).resolve().parent.parent

ARTIFACTS_DIR = FSPath(os.getenv("SIFEN_ARTIFACTS_DIR", PROJECT_ROOT / "artifacts")).resolve()
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

from . import db
from . import lotes_db

app = FastAPI(title="TESAKA-SIFEN", version="1.0.0")

# Obtener ruta base del proyecto (directorio padre de web/)
WEB_DIR = FSPath(__file__).parent

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
    default_ruc_num = os.getenv("SIFEN_TEST_RUC", "80012345").split("-")[0].strip()
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


@app.get("/health")
def health():
    return JSONResponse(
        {
            "ok": True,
            "service": "tesaka-web",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
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
    xml_gen_path = FSPath(__file__).parent.parent / "app" / "sifen_client" / "xml_generator_v150.py"
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
    
    # Extraer solo dígitos del CDC
    cdc_base = ''.join(c for c in cdc if c.isdigit())
    cdc_base = cdc_base.strip()
    
    # Si viene con 44 dígitos, es porque ya trae el DV pegado; sacarlo
    if len(cdc_base) == 44:
        cdc_base = cdc_base[:-1]
    
    if len(cdc_base) != 43:
        raise ValueError(f"Base CDC inválida para DV (len={len(cdc_base)}): {cdc_base}")
    
    dv_id = calculate_digit_verifier(cdc_base)
    cdc = cdc_base + str(dv_id)
    
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
    
    # Obtener ambiente (test/prod) desde env var o default a test
    env = os.getenv("SIFEN_ENV", "test")
    
    # Parsear número solicitado por el usuario
    requested_raw = numero_documento.strip()
    requested = None
    if requested_raw and requested_raw.isdigit():
        requested = int(requested_raw)
    
    # Obtener contador secuencial ANTES de generar CDC/DE
    from . import counters
    from .db import get_conn, ensure_tables
    
    conn = get_conn()
    ensure_tables(conn)
    
    try:
        # Tipo de documento: 1 = Factura electrónica
        tipo_documento = "1"
        
        next_num = counters.next_dnumdoc(
            conn,
            env=env,
            timbrado=timbrado,
            est=establecimiento,
            punexp=punto_expedicion,
            tipode=tipo_documento,
            requested=requested,
        )
        
        # Formatear a 7 dígitos con cero a la izquierda
        numero_documento = f"{next_num:07d}"
    finally:
        conn.close()
    
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
        sys.path.insert(0, str(FSPath(__file__).parent.parent))
        
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
        
        # Importar constantes de estado
        from .document_status import STATUS_ERROR
        from .sifen_status_mapper import map_recepcion_response_to_status
        
        # Importar cliente SIFEN (lazy import)
        import sys
        import re
        sys.path.insert(0, str(FSPath(__file__).parent.parent))
        
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
                from tools.send_sirecepde import build_r_envio_lote_xml, build_and_sign_lote_from_xml
                from app.sifen_client.config import get_mtls_cert_path_and_password
                
                de_xml_bytes = de_xml.encode("utf-8")
                
                # Obtener certificado de firma (usar mTLS si no hay específico de firma)
                sign_cert_path, sign_cert_password = get_mtls_cert_path_and_password()
                
                # GUARD-RAIL: Verificar dependencias críticas ANTES de construir/firmar
                try:
                    from tools.send_sirecepde import _check_signing_dependencies
                    _check_signing_dependencies()
                except RuntimeError as e:
                    error_msg = f"BLOQUEADO: {str(e)}. Ver artifacts/sign_blocked_reason.txt"
                    db.update_document_status(doc_id, status="error", message=error_msg)
                    return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                
                # Construir y firmar lote usando el pipeline correcto
                try:
                    zip_base64, lote_xml_bytes, zip_bytes, _ = build_and_sign_lote_from_xml(
                        xml_bytes=de_xml_bytes,
                        cert_path=sign_cert_path,
                        cert_password=sign_cert_password,
                        return_debug=True
                    )
                except Exception as e:
                    error_msg = f"BLOQUEADO: Error al construir/firmar lote: {str(e)}"
                    db.update_document_status(doc_id, status="error", message=error_msg)
                    return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                
                payload_xml = build_r_envio_lote_xml(did=1, xml_bytes=de_xml_bytes, zip_base64=zip_base64)
                
                # PREFLIGHT: Validar antes de enviar
                from tools.send_sirecepde import preflight_soap_request
                preflight_success, preflight_error = preflight_soap_request(
                    payload_xml=payload_xml,
                    zip_bytes=zip_bytes,
                    lote_xml_bytes=lote_xml_bytes,
                    artifacts_dir=FSPath("artifacts")
                )
                
                if not preflight_success:
                    error_msg = f"BLOQUEADO: Preflight falló - {preflight_error}. Ver artifacts/preflight_*.xml y artifacts/preflight_zip.zip"
                    db.update_document_status(doc_id, status="error", message=error_msg)
                    return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                
                # --- GATE: verificar habilitación FE del RUC antes de enviar ---
                import logging
                logger = logging.getLogger(__name__)
                
                try:
                    from lxml import etree
                    from tools.send_sirecepde import _extract_ruc_from_cert
                    # Constante de namespace SIFEN
                    SIFEN_NS_URI = "http://ekuatia.set.gov.py/sifen/xsd"
                    
                    # Helper para extraer localname
                    def _localname(tag: str) -> str:
                        """Extrae el localname de un tag (sin namespace)"""
                        if isinstance(tag, str) and "}" in tag:
                            return tag.split("}", 1)[1]
                        return tag
                    
                    # Extraer RUC emisor del lote.xml
                    ruc_de = None
                    ruc_de_with_dv = None
                    ruc_dv = None
                    if lote_xml_bytes:
                        try:
                            lote_root = etree.fromstring(lote_xml_bytes)
                            # Buscar DE dentro de rDE
                            de_elem = None
                            for elem in lote_root.iter():
                                if isinstance(elem.tag, str) and _localname(elem.tag) == "DE":
                                    de_elem = elem
                                    break
                            
                            if de_elem is not None:
                                # Buscar dRucEm y dDVEmi dentro de gEmis
                                g_emis = de_elem.find(f".//{{{SIFEN_NS_URI}}}gEmis")
                                if g_emis is not None:
                                    d_ruc_elem = g_emis.find(f"{{{SIFEN_NS_URI}}}dRucEm")
                                    if d_ruc_elem is not None and d_ruc_elem.text:
                                        ruc_de = d_ruc_elem.text.strip()
                                    
                                    d_dv_elem = g_emis.find(f"{{{SIFEN_NS_URI}}}dDVEmi")
                                    if d_dv_elem is not None and d_dv_elem.text:
                                        ruc_dv = d_dv_elem.text.strip()
                                    
                                    # Construir RUC-DE completo si hay DV
                                    if ruc_de and ruc_dv:
                                        ruc_de_with_dv = f"{ruc_de}-{ruc_dv}"
                                    elif ruc_de:
                                        ruc_de_with_dv = ruc_de
                        except Exception as e:
                            logger.warning(f"No se pudo extraer RUC del lote.xml para gate: {e}")
                    
                    # Extraer RUC del certificado P12
                    ruc_cert = None
                    ruc_cert_with_dv = None
                    try:
                        if sign_cert_path and sign_cert_password:
                            cert_info = _extract_ruc_from_cert(sign_cert_path, sign_cert_password)
                            if cert_info:
                                ruc_cert = cert_info.get("ruc")
                                ruc_cert_with_dv = cert_info.get("ruc_with_dv")
                    except Exception:
                        pass  # Silenciosamente fallar si no se puede extraer
                    
                    # --- SANITY CHECK: Comparar RUCs ---
                    ruc_gate = None
                    if ruc_de:
                        # ruc_gate debe ser SOLO el número (sin DV)
                        ruc_gate = str(ruc_de).strip().split("-", 1)[0].strip()
                    
                    # Loggear sanity check
                    logger.info("="*60)
                    logger.info("=== SIFEN SANITY CHECK ===")
                    logger.info(f"RUC-DE:     {ruc_de_with_dv or ruc_de or '(no encontrado)'}")
                    logger.info(f"RUC-GATE:   {ruc_gate or '(no encontrado)'}")
                    logger.info(f"RUC-CERT:   {ruc_cert_with_dv or ruc_cert or '(no disponible)'}")
                    
                    # Comparaciones booleanas
                    match_de_gate = (ruc_de and ruc_gate and ruc_de.split("-", 1)[0].strip() == ruc_gate)
                    match_cert_gate = (ruc_cert and ruc_gate and ruc_cert == ruc_gate)
                    
                    logger.info(f"match(DE.ruc == GATE.ruc):   {match_de_gate}")
                    if ruc_cert:
                        logger.info(f"match(CERT.ruc == GATE.ruc): {match_cert_gate}")
                    
                    # Warnings si hay mismatch (pero no bloquear todavía)
                    if ruc_de and ruc_gate and not match_de_gate:
                        logger.warning(f"RUC del DE ({ruc_de.split('-', 1)[0]}) no coincide con RUC-GATE ({ruc_gate})")
                    if ruc_cert and ruc_gate and not match_cert_gate:
                        logger.warning(f"RUC del certificado ({ruc_cert}) no coincide con RUC-GATE ({ruc_gate})")
                    
                    logger.info("="*60)
                    
                    # Guardar artifact JSON si debug está habilitado
                    if debug_enabled:
                        try:
                            artifacts_dir = FSPath("artifacts")
                            artifacts_dir.mkdir(parents=True, exist_ok=True)
                        except Exception:
                            artifacts_dir = None
                    else:
                        artifacts_dir = None
                    
                    if artifacts_dir:
                        try:
                            import json
                            from datetime import datetime
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            sanity_data = {
                                "timestamp": datetime.now().isoformat(),
                                "ruc_de": ruc_de_with_dv or ruc_de,
                                "ruc_gate": ruc_gate,
                                "ruc_cert": ruc_cert_with_dv or ruc_cert,
                                "matches": {
                                    "de_gate": match_de_gate,
                                    "cert_gate": match_cert_gate if ruc_cert else None
                                }
                            }
                            sanity_file = artifacts_dir / f"sanity_check_{timestamp}.json"
                            sanity_file.write_text(json.dumps(sanity_data, indent=2, ensure_ascii=False), encoding="utf-8")
                        except Exception:
                            pass  # Silenciosamente fallar si no se puede guardar
                    
                    # Hard-fail si falta dRucEm o es inválido
                    if not ruc_de or not ruc_gate:
                        error_msg = f"BLOQUEADO: No se pudo extraer RUC válido del DE. dRucEm={ruc_de!r} RUC-GATE={ruc_gate!r}"
                        logger.error(error_msg)
                        db.update_document_status(doc_id, status="error", message=error_msg)
                        return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                    
                    # Consultar habilitación FE del RUC
                    logger.info(f"Verificando habilitación FE del RUC: {ruc_gate}")
                    dump_http = os.getenv("SIFEN_DUMP_HTTP", "0") in ("1", "true", "True")
                    ruc_check = client.consulta_ruc_raw(ruc=ruc_gate, dump_http=dump_http)
                    cod = (ruc_check.get("dCodRes") or "").strip()
                    msg = (ruc_check.get("dMsgRes") or "").strip()
                    
                    # Extraer dRUCFactElec de xContRUC
                    x_cont_ruc = ruc_check.get("xContRUC", {})
                    d_fact_raw = x_cont_ruc.get("dRUCFactElec") if isinstance(x_cont_ruc, dict) else None
                    # Normalizar: convertir a string, trim, uppercase
                    d_fact_normalized = (str(d_fact_raw).strip().upper() if d_fact_raw is not None else "")
                    
                    # Valores que indican HABILITADO: "1", "S", "SI"
                    habilitado = d_fact_normalized in ("1", "S", "SI")
                    
                    if cod != "0502":
                        http_status = ruc_check.get("http_status", 0)
                        raw_xml = ruc_check.get("raw_xml", "")
                        response_snippet = raw_xml[:300] if raw_xml else "(sin respuesta)"
                        
                        error_msg = (
                            f"BLOQUEADO: SIFEN siConsRUC no confirmó el RUC. "
                            f"dCodRes={cod} dMsgRes={msg} | HTTP status={http_status} | "
                            f"Respuesta: {response_snippet}"
                        )
                        logger.error(error_msg)
                        db.update_document_status(doc_id, status="error", message=error_msg)
                        return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                    
                    if not habilitado:
                        razon = x_cont_ruc.get("dRazCons", "") if isinstance(x_cont_ruc, dict) else ""
                        est = x_cont_ruc.get("dDesEstCons", "") if isinstance(x_cont_ruc, dict) else ""
                        # Mostrar valor original y normalizado para diagnóstico
                        d_fact_display = repr(d_fact_raw) if d_fact_raw is not None else "None"
                        error_msg = (
                            f"BLOQUEADO: RUC NO habilitado para Facturación Electrónica en SIFEN ({env}). "
                            f"RUC={ruc_gate} RazónSocial='{razon}' Estado='{est}' "
                            f"dRUCFactElec={d_fact_display} (normalizado='{d_fact_normalized}'). "
                            "Debés gestionar la habilitación FE del RUC en SIFEN/SET."
                        )
                        logger.error(error_msg)
                        db.update_document_status(doc_id, status="error", message=error_msg)
                        return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                    
                    logger.info(f"RUC {ruc_gate} habilitado para FE (dRUCFactElec={d_fact_raw!r} -> '{d_fact_normalized}')")
                except Exception as e:
                    # hard-fail: no enviar lote si el gate falla
                    error_msg = f"BLOQUEADO: Error en gate de habilitación FE: {str(e)}"
                    logger.error(f"GATE FALLÓ: {e}", exc_info=True)
                    db.update_document_status(doc_id, status="error", message=error_msg)
                    return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                # --- FIN GATE ---
                
                # Enviar lote a SIFEN (solo si preflight y gate pasaron)
                response = client.recepcion_lote(payload_xml)
                
                # Extraer campos de la respuesta (SIEMPRE parsear aunque dProtConsLote sea 0)
                d_prot_cons_lote = response.get('d_prot_cons_lote')
                d_cod_res = response.get('codigo_respuesta')
                d_msg_res = response.get('mensaje')
                d_tpo_proces = response.get('d_tpo_proces')
                
                # Guardar artifact de debug si está habilitado
                debug_enabled = os.getenv("SIFEN_DEBUG_SOAP", "0") in ("1", "true", "True")
                if debug_enabled:
                    try:
                        artifacts_dir = FSPath("artifacts")
                        artifacts_dir.mkdir(parents=True, exist_ok=True)
                        import json
                        parsed_response = {
                            "dCodRes": d_cod_res,
                            "dMsgRes": d_msg_res,
                            "dProtConsLote": d_prot_cons_lote,
                            "dTpoProces": d_tpo_proces
                        }
                        artifacts_dir.joinpath("last_lote_response_parsed.json").write_text(
                            json.dumps(parsed_response, indent=2, ensure_ascii=False),
                            encoding="utf-8"
                        )
                    except Exception:
                        pass
                
                # Mapear respuesta de recepción a estado (NO es aprobación, solo recepción)
                status, code, message = map_recepcion_response_to_status(response)
                
                # Guardar paquete de diagnóstico automáticamente si dCodRes=0301 con dProtConsLote=0
                if d_cod_res == "0301" and (d_prot_cons_lote is None or d_prot_cons_lote == 0 or str(d_prot_cons_lote) == "0"):
                    try:
                        artifacts_dir = FSPath("artifacts")
                        artifacts_dir.mkdir(parents=True, exist_ok=True)
                        
                        # Importar función de diagnóstico
                        sys.path.insert(0, str(FSPath(__file__).parent.parent))
                        from tools.send_sirecepde import _save_0301_diagnostic_package
                        
                        # Extraer dId del payload
                        from lxml import etree
                        SIFEN_NS = "http://ekuatia.set.gov.py/sifen/xsd"
                        payload_root = etree.fromstring(payload_xml.encode("utf-8"))
                        did = "1"  # Default
                        d_id_elem = payload_root.find(f".//{{{SIFEN_NS}}}dId")
                        if d_id_elem is None:
                            d_id_elem = payload_root.find(".//dId")
                        if d_id_elem is not None and d_id_elem.text:
                            did = d_id_elem.text.strip()
                        
                        # Llamar función de diagnóstico (zip_bytes y lote_xml_bytes ya están disponibles)
                        # Nota: zip_bytes y lote_xml_bytes están disponibles desde build_and_sign_lote_from_xml
                        if lote_xml_bytes:
                            _save_0301_diagnostic_package(
                                artifacts_dir=artifacts_dir,
                                response=response,
                                payload_xml=payload_xml,
                                zip_bytes=zip_bytes,
                                lote_xml_bytes=lote_xml_bytes,
                                env=env,
                                did=did
                            )
                        else:
                            # Si no se pudo extraer, al menos guardar un resumen básico
                            import json
                            from datetime import datetime
                            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                            basic_summary = {
                                "diagnostic_package": {
                                    "trigger": "dCodRes=0301 with dProtConsLote=0",
                                    "timestamp": timestamp,
                                    "env": env,
                                    "note": "No se pudo extraer lote_xml_bytes (no disponible en contexto)"
                                },
                                "response": {
                                    "dCodRes": d_cod_res,
                                    "dMsgRes": d_msg_res,
                                    "dProtConsLote": d_prot_cons_lote,
                                },
                                "request": {
                                    "dId": did,
                                    "soap_request_redacted": payload_xml[:1000] + "... [truncado]"
                                }
                            }
                            summary_file = artifacts_dir / f"diagnostic_0301_summary_basic_{timestamp}.json"
                            summary_file.write_text(
                                json.dumps(basic_summary, indent=2, ensure_ascii=False, default=str),
                                encoding="utf-8"
                            )
                    except Exception as e:
                        # No bloquear el flujo si falla el diagnóstico
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.warning(f"Error al guardar paquete de diagnóstico 0301: {e}")
                
                # Guardar respuesta del documento con d_prot_cons_lote si existe
                db.update_document_status(
                    doc_id=doc_id,
                    status=status,
                    code=code,
                    message=message,
                    sirecepde_xml=payload_xml,
                    d_prot_cons_lote=d_prot_cons_lote
                )
                
                # Si se recibió dProtConsLote > 0, guardar lote y consultar automáticamente
                # NO consultar si dProtConsLote es 0 o None (no hay protocolo)
                d_prot_int = None
                if d_prot_cons_lote:
                    try:
                        d_prot_str = str(d_prot_cons_lote).strip()
                        if d_prot_str and d_prot_str != "0":
                            d_prot_int = int(d_prot_str)
                    except (ValueError, AttributeError):
                        pass
                
                if d_prot_int and d_prot_int > 0:
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
                # IMPORTANTE: En modo directo, siRecepDE puede devolver aprobación inmediata,
                # pero según documentación SIFEN, esto es raro. Mapear correctamente.
                if isinstance(response, dict):
                    # Mapear respuesta de recepción a estado
                    status, code, message = map_recepcion_response_to_status(response)
                    
                    # Guardar respuesta XML parseada si está disponible
                    response_xml = response.get('parsed_fields', {}).get('xml')
                else:
                    # Respuesta inesperada (no dict), guardar como error
                    status = STATUS_ERROR
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


if __name__ == "__main__":
    import os
    import uvicorn

    host = os.getenv("SIFEN_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("SIFEN_WEB_PORT", "8001"))
    uvicorn.run("web.main:app", host=host, port=port, reload=True)


async def _check_lote_status_async(lote_id: int, env: str, prot: str):
    """
    Helper async para consultar el estado de un lote y actualizar DEs asociados.
    Se ejecuta en background después de recibir dProtConsLote.
    """
    import asyncio
    from app.sifen_client.lote_checker import (
        check_lote_status,
        determine_status_from_cod_res_lot,
    )
    from .sifen_status_mapper import map_lote_consulta_to_de_status
    
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
        
        # Determinar estado del lote
        lote_status = determine_status_from_cod_res_lot(cod_res_lot)
        
        # Actualizar lote
        lotes_db.update_lote_status(
            lote_id=lote_id,
            status=lote_status,
            cod_res_lot=cod_res_lot,
            msg_res_lot=msg_res_lot,
            response_xml=response_xml,
        )
        
        # Actualizar estado de los DEs asociados al lote
        # Buscar DEs asociados a este lote
        try:
            lote = lotes_db.get_lote(lote_id)
            if lote and lote.get('de_document_id'):
                doc_id = lote['de_document_id']
                document = db.get_document(doc_id)
                if document:
                    cdc = document.get('cdc')
                    if cdc:
                        # Mapear respuesta de consulta al estado del DE
                        de_status, de_code, de_message, approved_at = map_lote_consulta_to_de_status(
                            cod_res_lot=cod_res_lot,
                            xml_response=response_xml,
                            cdc=cdc
                        )
                        
                        # Actualizar estado del DE
                        db.update_document_status(
                            doc_id=doc_id,
                            status=de_status,
                            code=de_code,
                            message=de_message,
                            approved_at=approved_at
                        )
                        
                        # Log de transición de estado
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(
                            f"DE {doc_id} (CDC: {cdc}) actualizado a estado {de_status} "
                            f"después de consultar lote {prot}"
                        )
        except Exception as e:
            # Error al actualizar DE, pero no fallar la consulta del lote
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Error al actualizar estado de DE después de consultar lote: {e}")
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


@app.get("/de/{doc_id}/status", response_class=HTMLResponse)
async def de_check_status(request: Request, doc_id: int):
    """
    Consulta el estado de un DE en SIFEN y actualiza la base de datos.
    
    Si el DE tiene d_prot_cons_lote, consulta el lote.
    Si no, intenta consulta directa por CDC (siConsDE).
    
    Query params:
    - force: Si es "1", fuerza la consulta incluso si el estado es final (APPROVED/REJECTED)
    """
    try:
        # Leer query param force
        force = request.query_params.get("force", "0")
        force_consult = force == "1"
        
        document = db.get_document(doc_id)
        if not document:
            raise HTTPException(status_code=404, detail=f"Documento {doc_id} no encontrado")
        
        cdc = document.get('cdc')
        d_prot_cons_lote = document.get('d_prot_cons_lote')
        current_status = document.get('last_status')
        
        # Importar constantes y mappers
        from .document_status import STATUS_PENDING_SIFEN, STATUS_SENT_TO_SIFEN, STATUS_ERROR, is_final_status
        from .sifen_status_mapper import map_lote_consulta_to_de_status
        
        # Determinar si se puede consultar
        is_final = is_final_status(current_status) if current_status else False
        
        # Permitir consulta si:
        # - Está en estado que puede cambiar (SENT_TO_SIFEN, PENDING_SIFEN, ERROR)
        # - O si force=1 (incluso si es final, pero solo si tiene protocolo)
        can_consult = (
            current_status in [STATUS_SENT_TO_SIFEN, STATUS_PENDING_SIFEN, STATUS_ERROR]
            or (force_consult and d_prot_cons_lote)  # Solo force si tiene protocolo
        )
        
        if can_consult:
            env = os.getenv("SIFEN_ENV", "test")
            
            if d_prot_cons_lote:
                # Consultar por lote
                from app.sifen_client.lote_checker import check_lote_status
                
                try:
                    result = check_lote_status(
                        env=env,
                        prot=d_prot_cons_lote,
                        timeout=30
                    )
                    
                    if result.get("success"):
                        cod_res_lot = result.get("cod_res_lot")
                        response_xml = result.get("response_xml")
                        
                        # Mapear al estado del DE
                        de_status, de_code, de_message, approved_at = map_lote_consulta_to_de_status(
                            cod_res_lot=cod_res_lot,
                            xml_response=response_xml,
                            cdc=cdc
                        )
                        
                        # Actualizar estado del DE
                        db.update_document_status(
                            doc_id=doc_id,
                            status=de_status,
                            code=de_code,
                            message=de_message,
                            approved_at=approved_at
                        )
                        
                        return RedirectResponse(url=f"/de/{doc_id}?checked=1", status_code=303)
                    else:
                        # Error en la consulta - SOBRESCRIBIR con el nuevo error
                        error_msg = result.get("error", "Error desconocido")
                        # Si es error de conexión transitorio, mantener mensaje claro pero no bloquear reintentos
                        if "reset by peer" in error_msg.lower() or "no respondió" in error_msg.lower():
                            error_msg = "SIFEN no respondió (reset by peer). Reintentar."
                        db.update_document_status(
                            doc_id=doc_id,
                            status=STATUS_ERROR,
                            code=None,  # Limpiar código anterior
                            message=error_msg  # Sobrescribir mensaje anterior
                        )
                        return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
                except Exception as e:
                    # Error al consultar - SOBRESCRIBIR con el nuevo error
                    error_msg = f"Error al consultar lote: {str(e)}"
                    db.update_document_status(
                        doc_id=doc_id,
                        status=STATUS_ERROR,
                        code=None,  # Limpiar código anterior
                        message=error_msg  # Sobrescribir mensaje anterior
                    )
                    return RedirectResponse(url=f"/de/{doc_id}?error=1", status_code=303)
            else:
                # TODO: Implementar consulta directa por CDC (siConsDE)
                # Por ahora, solo redirigir
                return RedirectResponse(url=f"/de/{doc_id}?note=Consulta por CDC no implementada aún", status_code=303)
        else:
            # No se puede consultar (estado final sin force, o sin protocolo)
            if is_final and not force_consult:
                return RedirectResponse(url=f"/de/{doc_id}?note=Estado final. Use ?force=1 para forzar consulta", status_code=303)
            else:
                return RedirectResponse(url=f"/de/{doc_id}?note=No se puede consultar (falta d_prot_cons_lote)", status_code=303)
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
