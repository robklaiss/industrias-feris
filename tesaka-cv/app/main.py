"""
Aplicación web FastAPI para crear y administrar comprobantes Tesaka
"""
import json
import os
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Template, Environment, FileSystemLoader
from dotenv import load_dotenv

from .db import get_db, init_db
from .models import Invoice
from .tesaka import convert_to_tesaka, validate_tesaka, load_schema
from .tesaka_client import TesakaClient, TesakaClientError

# Cargar variables de entorno
load_dotenv()

# ===== GUARDRAIL MODO TEST - PROHIBIDO PROD =====
# Forzar ambiente TEST sin importar configuración
SIFEN_ENV_FORCED = "test"
if os.getenv("SIFEN_ENV") == "prod":
    raise RuntimeError("MODO TEST: Producción está deshabilitada. SIFEN_ENV no puede ser 'prod'")
# Sobrescribir cualquier variable de entorno
os.environ["SIFEN_ENV"] = SIFEN_ENV_FORCED
print(f"🔒 SIFEN_ENV_FORCED={SIFEN_ENV_FORCED} (MODO TEST)")
# ===============================================

# Inicializar FastAPI
app = FastAPI(title="Industrias Feris")

# Configurar templates
from pathlib import Path
# Buscar templates desde el directorio actual o desde el directorio raíz del proyecto
template_dir = Path(__file__).parent / "templates"
if not template_dir.exists():
    # Si no existe, buscar desde el directorio raíz
    template_dir = Path(__file__).parent.parent / "app" / "templates"
jinja_env = Environment(loader=FileSystemLoader(str(template_dir)), autoescape=True)
# Agregar filtro tojson
jinja_env.filters['tojson'] = lambda obj, **kwargs: json.dumps(obj, **kwargs, ensure_ascii=False)

def render_template(template_name: str, request: Request, **kwargs):
    """Helper para renderizar templates"""
    template = jinja_env.get_template(template_name)
    return HTMLResponse(template.render(request=request, **kwargs))

# Montar archivos estáticos (opcional)
try:
    app.mount("/static", StaticFiles(directory="app/static"), name="static")
except:
    pass  # Si no existe el directorio, no pasa nada

# Inicializar base de datos al arrancar
@app.on_event("startup")
def startup_event():
    init_db()

# Importar y registrar rutas de módulos
from .routes_contracts import register_contract_routes
from .routes_purchase_orders import register_purchase_order_routes
from .routes_delivery_notes import register_delivery_note_routes
from .routes_remissions import register_remission_routes
from .routes_sales_invoices import register_sales_invoice_routes
from .routes_products import register_product_routes
from .routes_sifen import register_sifen_routes
from .routes_artifacts import register_artifacts_routes
from .routes_emit import register_emit_routes

register_product_routes(app, jinja_env)
register_contract_routes(app, jinja_env)
register_purchase_order_routes(app, jinja_env)
register_delivery_note_routes(app, jinja_env)
register_remission_routes(app, jinja_env)
register_sales_invoice_routes(app, jinja_env)
register_sifen_routes(app, jinja_env)
register_artifacts_routes(app, jinja_env)
register_emit_routes(app, jinja_env)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return render_template("home.html", request)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Muestra el dashboard con estadísticas del sistema"""
    conn = get_db()
    cursor = conn.cursor()
    
    stats = {}
    
    # Productos
    cursor.execute("SELECT COUNT(*) as total, SUM(CASE WHEN activo = 1 THEN 1 ELSE 0 END) as activos FROM products")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['products'] = {
            'total': row_dict.get('total', 0) or 0,
            'activos': row_dict.get('activos', 0) or 0
        }
    else:
        stats['products'] = {'total': 0, 'activos': 0}
    
    # Clientes
    cursor.execute("SELECT COUNT(*) as total FROM clients")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['clients'] = {'total': row_dict.get('total', 0) or 0}
    else:
        stats['clients'] = {'total': 0}
    
    # Contratos
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN estado = 'vigente' THEN 1 ELSE 0 END) as vigentes,
            SUM(CASE WHEN estado = 'cancelado' THEN 1 ELSE 0 END) as cancelados
        FROM contracts
    """)
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['contracts'] = {
            'total': row_dict.get('total', 0) or 0,
            'vigentes': row_dict.get('vigentes', 0) or 0,
            'cancelados': row_dict.get('cancelados', 0) or 0
        }
    else:
        stats['contracts'] = {'total': 0, 'vigentes': 0, 'cancelados': 0}
    
    # Monto total de contratos
    cursor.execute("""
        SELECT COALESCE(SUM(ci.cantidad_total * ci.precio_unitario), 0) as total_monto
        FROM contracts c
        LEFT JOIN contract_items ci ON c.id = ci.contract_id
        WHERE c.estado = 'vigente'
    """)
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['contracts']['monto_total'] = float(row_dict.get('total_monto', 0) or 0)
    else:
        stats['contracts']['monto_total'] = 0.0
    
    # Órdenes de Compra
    cursor.execute("SELECT COUNT(*) as total FROM purchase_orders")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['purchase_orders'] = {'total': row_dict.get('total', 0) or 0}
    else:
        stats['purchase_orders'] = {'total': 0}
    
    # Notas de Entrega
    cursor.execute("SELECT COUNT(*) as total FROM delivery_notes")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['delivery_notes'] = {'total': row_dict.get('total', 0) or 0}
    else:
        stats['delivery_notes'] = {'total': 0}
    
    # Remisiones
    cursor.execute("SELECT COUNT(*) as total FROM remissions")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['remissions'] = {'total': row_dict.get('total', 0) or 0}
    else:
        stats['remissions'] = {'total': 0}
    
    # Facturas de Venta
    cursor.execute("SELECT COUNT(*) as total FROM sales_invoices")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['sales_invoices'] = {'total': row_dict.get('total', 0) or 0}
    else:
        stats['sales_invoices'] = {'total': 0}
    
    # Facturas Tesaka
    cursor.execute("SELECT COUNT(*) as total FROM invoices")
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['invoices'] = {'total': row_dict.get('total', 0) or 0}
    else:
        stats['invoices'] = {'total': 0}
    
    # Total facturado (Tesaka)
    cursor.execute("SELECT data_json FROM invoices")
    rows = cursor.fetchall()
    total_facturado = 0.0
    for row in rows:
        try:
            invoice_data = json.loads(row['data_json'])
            total_facturado += sum(
                item.get('cantidad', 0) * item.get('precioUnitario', 0)
                for item in invoice_data.get('items', [])
            )
        except:
            pass
    stats['invoices']['total_facturado'] = total_facturado
    
    # Envíos a Tesaka
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END) as exitosos,
            SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END) as fallidos
        FROM submissions
    """)
    row = cursor.fetchone()
    if row:
        row_dict = dict(row)
        stats['submissions'] = {
            'total': row_dict.get('total', 0) or 0,
            'exitosos': row_dict.get('exitosos', 0) or 0,
            'fallidos': row_dict.get('fallidos', 0) or 0
        }
    else:
        stats['submissions'] = {'total': 0, 'exitosos': 0, 'fallidos': 0}
    
    # Últimos registros
    recent = {}
    
    cursor.execute("SELECT id, numero_contrato, fecha FROM contracts ORDER BY created_at DESC LIMIT 5")
    recent['contracts'] = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT id, numero, fecha FROM purchase_orders ORDER BY created_at DESC LIMIT 5")
    recent['purchase_orders'] = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT id, numero_remision, fecha_inicio FROM remissions ORDER BY created_at DESC LIMIT 5")
    recent['remissions'] = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT id, numero, fecha FROM sales_invoices ORDER BY created_at DESC LIMIT 5")
    recent['sales_invoices'] = [dict(row) for row in cursor.fetchall()]
    
    cursor.execute("SELECT id, issue_date, buyer_name FROM invoices ORDER BY created_at DESC LIMIT 5")
    recent['invoices'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return render_template("dashboard.html", request, stats=stats, recent=recent)


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_list(request: Request):
    """Lista todas las facturas guardadas"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, created_at, issue_date, buyer_name, data_json
        FROM invoices
        ORDER BY created_at DESC
    """)
    
    rows = cursor.fetchall()
    invoices = [Invoice.from_row(row) for row in rows]
    
    conn.close()
    
    return render_template("invoices_list.html", request, invoices=invoices)


@app.get("/invoices/new", response_class=HTMLResponse)
async def invoice_form(request: Request):
    """Muestra el formulario para crear una nueva factura"""
    return render_template("invoice_form.html", request, invoice=None)


@app.post("/invoices")
async def create_invoice(
    request: Request,
    issue_date: str = Form(...),
    issue_datetime: Optional[str] = Form(None),
    # Buyer
    buyer_situacion: str = Form(...),
    buyer_nombre: str = Form(...),
    buyer_ruc: Optional[str] = Form(None),
    buyer_dv: Optional[str] = Form(None),
    buyer_tipoIdentificacion: Optional[str] = Form(None),
    buyer_identificacion: Optional[str] = Form(None),
    buyer_correoElectronico: Optional[str] = Form(None),
    buyer_pais: Optional[str] = Form(None),
    buyer_tieneRepresentante: Optional[str] = Form(None),
    buyer_representante_tipoIdentificacion: Optional[str] = Form(None),
    buyer_representante_identificacion: Optional[str] = Form(None),
    buyer_representante_nombre: Optional[str] = Form(None),
    buyer_tieneBeneficiario: Optional[str] = Form(None),
    buyer_beneficiario_tipoIdentificacion: Optional[str] = Form(None),
    buyer_beneficiario_identificacion: Optional[str] = Form(None),
    buyer_beneficiario_nombre: Optional[str] = Form(None),
    buyer_domicilio: Optional[str] = Form(None),
    buyer_direccion: Optional[str] = Form(None),
    buyer_telefono: Optional[str] = Form(None),
    # Transaction
    transaction_condicionCompra: str = Form(...),
    transaction_cuotas: Optional[int] = Form(None),
    transaction_tipoComprobante: int = Form(...),
    transaction_numeroComprobanteVenta: str = Form(...),
    transaction_numeroTimbrado: str = Form(...),
    transaction_fecha: Optional[str] = Form(None),
    # Items (vienen como listas)
    item_cantidad: List[float] = Form(...),
    item_tasaAplica: List[int] = Form(...),
    item_precioUnitario: List[float] = Form(...),
    item_descripcion: List[str] = Form(...),
    # Retention
    retention_fecha: str = Form(...),
    retention_moneda: str = Form(...),
    retention_tipoCambio: Optional[int] = Form(None),
    retention_retencionRenta: bool = Form(False),
    retention_conceptoRenta: Optional[str] = Form(None),
    retention_retencionIva: bool = Form(False),
    retention_conceptoIva: Optional[str] = Form(None),
    retention_rentaPorcentaje: float = Form(...),
    retention_ivaPorcentaje5: float = Form(...),
    retention_ivaPorcentaje10: float = Form(...),
    retention_rentaCabezasBase: float = Form(...),
    retention_rentaCabezasCantidad: float = Form(...),
    retention_rentaToneladasBase: float = Form(...),
    retention_rentaToneladasCantidad: float = Form(...),
):
    """Guarda una nueva factura en la base de datos"""
    
    # Construir buyer
    buyer = {
        "situacion": buyer_situacion,
        "nombre": buyer_nombre
    }
    if buyer_ruc:
        buyer["ruc"] = buyer_ruc
    if buyer_dv:
        buyer["dv"] = buyer_dv
    if buyer_tipoIdentificacion:
        buyer["tipoIdentificacion"] = buyer_tipoIdentificacion
    if buyer_identificacion:
        buyer["identificacion"] = buyer_identificacion
    if buyer_correoElectronico:
        buyer["correoElectronico"] = buyer_correoElectronico
    if buyer_pais:
        buyer["pais"] = buyer_pais
    if buyer_tieneRepresentante:
        buyer["tieneRepresentante"] = buyer_tieneRepresentante.lower() in ('true', '1', 'yes', 'on')
    if buyer_tieneBeneficiario:
        buyer["tieneBeneficiario"] = buyer_tieneBeneficiario.lower() in ('true', '1', 'yes', 'on')
    if buyer_domicilio:
        buyer["domicilio"] = buyer_domicilio
    if buyer_direccion:
        buyer["direccion"] = buyer_direccion
    if buyer_telefono:
        buyer["telefono"] = buyer_telefono
    
    # Representante
    if buyer_representante_nombre:
        buyer["representante"] = {}
        if buyer_representante_tipoIdentificacion:
            buyer["representante"]["tipoIdentificacion"] = buyer_representante_tipoIdentificacion
        if buyer_representante_identificacion:
            buyer["representante"]["identificacion"] = buyer_representante_identificacion
        if buyer_representante_nombre:
            buyer["representante"]["nombre"] = buyer_representante_nombre
    
    # Beneficiario
    if buyer_beneficiario_nombre:
        buyer["beneficiario"] = {}
        if buyer_beneficiario_tipoIdentificacion:
            buyer["beneficiario"]["tipoIdentificacion"] = buyer_beneficiario_tipoIdentificacion
        if buyer_beneficiario_identificacion:
            buyer["beneficiario"]["identificacion"] = buyer_beneficiario_identificacion
        if buyer_beneficiario_nombre:
            buyer["beneficiario"]["nombre"] = buyer_beneficiario_nombre
    
    # Construir transaction
    transaction = {
        "condicionCompra": transaction_condicionCompra,
        "tipoComprobante": transaction_tipoComprobante,
        "numeroComprobanteVenta": str(transaction_numeroComprobanteVenta),
        "numeroTimbrado": str(transaction_numeroTimbrado)
    }
    if transaction_cuotas is not None:
        transaction["cuotas"] = transaction_cuotas
    if transaction_fecha:
        transaction["fecha"] = transaction_fecha
    
    # Construir items
    items = []
    for i in range(len(item_cantidad)):
        items.append({
            "cantidad": item_cantidad[i],
            "tasaAplica": item_tasaAplica[i],
            "precioUnitario": item_precioUnitario[i],
            "descripcion": item_descripcion[i]
        })
    
    # Construir retention
    retention = {
        "fecha": retention_fecha,
        "moneda": retention_moneda,
        "retencionRenta": retention_retencionRenta,
        "retencionIva": retention_retencionIva,
        "rentaPorcentaje": retention_rentaPorcentaje,
        "ivaPorcentaje5": retention_ivaPorcentaje5,
        "ivaPorcentaje10": retention_ivaPorcentaje10,
        "rentaCabezasBase": retention_rentaCabezasBase,
        "rentaCabezasCantidad": retention_rentaCabezasCantidad,
        "rentaToneladasBase": retention_rentaToneladasBase,
        "rentaToneladasCantidad": retention_rentaToneladasCantidad
    }
    if retention_tipoCambio is not None:
        retention["tipoCambio"] = retention_tipoCambio
    if retention_conceptoRenta:
        retention["conceptoRenta"] = retention_conceptoRenta
    if retention_conceptoIva:
        retention["conceptoIva"] = retention_conceptoIva
    
    # Construir factura completa
    invoice_data = {
        "issue_date": issue_date,
        "buyer": buyer,
        "transaction": transaction,
        "items": items,
        "retention": retention
    }
    if issue_datetime:
        # Convertir formato datetime-local (YYYY-MM-DDTHH:mm) a formato esperado (YYYY-MM-DD HH:mm:SS)
        if 'T' in issue_datetime:
            issue_datetime = issue_datetime.replace('T', ' ') + ':00'
        invoice_data["issue_datetime"] = issue_datetime
    
    # Guardar en base de datos
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO invoices (issue_date, buyer_name, data_json)
        VALUES (?, ?, ?)
    """, (
        issue_date,
        buyer_nombre,
        json.dumps(invoice_data, ensure_ascii=False)
    ))
    
    invoice_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Redirigir a la vista de la factura
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)


@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
async def invoice_view(request: Request, invoice_id: int):
    """Muestra el detalle de una factura"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT id, created_at, issue_date, buyer_name, data_json
        FROM invoices
        WHERE id = ?
    """, (invoice_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    invoice = Invoice.from_row(row)
    
    return render_template("invoice_view.html", request, invoice=invoice)


@app.post("/invoices/{invoice_id}/validate")
async def validate_invoice(invoice_id: int):
    """Valida una factura contra el schema de importación"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT data_json
        FROM invoices
        WHERE id = ?
    """, (invoice_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    invoice_data = json.loads(row['data_json'])
    
    # Convertir a Tesaka
    try:
        tesaka_data = convert_to_tesaka(invoice_data)
    except Exception as e:
        return JSONResponse({
            "valid": False,
            "errors": [f"Error durante la conversión: {str(e)}"]
        })
    
    # Validar
    errors = validate_tesaka(tesaka_data)
    
    return JSONResponse({
        "valid": len(errors) == 0,
        "errors": errors
    })


@app.get("/invoices/{invoice_id}/export")
async def export_invoice(invoice_id: int):
    """Exporta una factura como JSON Tesaka"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT data_json, buyer_name, issue_date
        FROM invoices
        WHERE id = ?
    """, (invoice_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    invoice_data = json.loads(row['data_json'])
    
    # Convertir a Tesaka
    try:
        tesaka_data = convert_to_tesaka(invoice_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error durante la conversión: {str(e)}")
    
    # Validar contra el schema
    errors = validate_tesaka(tesaka_data)
    
    # Si hay errores, no exportar
    if errors:
        return JSONResponse(
            status_code=400,
            content={
                "valid": False,
                "errors": errors,
                "message": "No se puede exportar: el comprobante no es válido según schema de importación."
            }
        )
    
    # Generar nombre de archivo
    buyer_name = row['buyer_name'].replace(' ', '_')
    issue_date = row['issue_date']
    filename = f"tesaka_import_{buyer_name}_{issue_date}.json"
    
    # Retornar JSON como descarga
    return Response(
        content=json.dumps(tesaka_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# ===== Rutas de Envío a Tesaka =====

def _get_tesaka_config():
    """Obtiene la configuración de Tesaka desde variables de entorno"""
    env = os.getenv('TESAKA_ENV', 'homo')
    user = os.getenv('TESAKA_USER', '')
    password = os.getenv('TESAKA_PASS', '')
    timeout = int(os.getenv('REQUEST_TIMEOUT', '30'))
    
    return {
        'env': env,
        'user': user,
        'password': password,
        'timeout': timeout
    }


@app.post("/invoices/{invoice_id}/send/{kind}")
async def send_invoice_to_tesaka(invoice_id: int, kind: str):
    """
    Envía una factura a Tesaka (SET)
    
    Args:
        invoice_id: ID de la factura
        kind: Tipo de comprobante ('factura', 'retencion', 'autofactura')
    """
    if kind not in ['factura', 'retencion', 'autofactura']:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {kind}. Debe ser 'factura', 'retencion' o 'autofactura'")
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Obtener factura
    cursor.execute("""
        SELECT data_json
        FROM invoices
        WHERE id = ?
    """, (invoice_id,))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    invoice_data = json.loads(row['data_json'])
    
    # Convertir a formato Tesaka
    try:
        tesaka_data = convert_to_tesaka(invoice_data)
    except Exception as e:
        conn.close()
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": f"Error durante la conversión: {str(e)}"
            }
        )
    
    # Validar antes de enviar
    errors = validate_tesaka(tesaka_data)
    if errors:
        conn.close()
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "errors": errors,
                "error": "El comprobante no es válido según el schema de importación"
            }
        )
    
    # Obtener configuración de Tesaka
    config = _get_tesaka_config()
    
    # Enviar a Tesaka
    try:
        with TesakaClient(
            env=config['env'],
            user=config['user'],
            password=config['password'],
            timeout=config['timeout']
        ) as client:
            # Determinar método según el tipo
            if kind == 'factura':
                response = client.enviar_facturas(tesaka_data)
            elif kind == 'retencion':
                response = client.enviar_retenciones(tesaka_data)
            else:  # autofactura
                response = client.enviar_autofacturas(tesaka_data)
            
            # Guardar submission exitoso
            cursor.execute("""
                INSERT INTO submissions 
                (invoice_id, kind, env, request_json, response_json, ok)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                invoice_id,
                kind,
                config['env'],
                json.dumps(tesaka_data, ensure_ascii=False),
                json.dumps(response, ensure_ascii=False),
                1
            ))
            
            conn.commit()
            conn.close()
            
            return JSONResponse({
                "ok": True,
                "response": response
            })
    
    except TesakaClientError as e:
        # Guardar submission con error
        error_msg = str(e)
        cursor.execute("""
            INSERT INTO submissions 
            (invoice_id, kind, env, request_json, response_json, ok, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            kind,
            config['env'],
            json.dumps(tesaka_data, ensure_ascii=False),
            None,
            0,
            error_msg
        ))
        
        conn.commit()
        conn.close()
        
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": error_msg
            }
        )
    
    except Exception as e:
        # Guardar submission con error inesperado
        error_msg = f"Error inesperado: {str(e)}"
        cursor.execute("""
            INSERT INTO submissions 
            (invoice_id, kind, env, request_json, response_json, ok, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_id,
            kind,
            config['env'],
            json.dumps(tesaka_data, ensure_ascii=False),
            None,
            0,
            error_msg
        ))
        
        conn.commit()
        conn.close()
        
        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "error": error_msg
            }
        )


@app.get("/invoices/{invoice_id}/submissions")
async def get_invoice_submissions(invoice_id: int):
    """
    Obtiene el historial de envíos (submissions) de una factura
    """
    conn = get_db()
    cursor = conn.cursor()
    
    # Verificar que la factura existe
    cursor.execute("SELECT id FROM invoices WHERE id = ?", (invoice_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Factura no encontrada")
    
    # Obtener submissions
    cursor.execute("""
        SELECT id, kind, env, created_at, request_json, response_json, ok, error
        FROM submissions
        WHERE invoice_id = ?
        ORDER BY created_at DESC
    """, (invoice_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    submissions = []
    for row in rows:
        submissions.append({
            'id': row['id'],
            'kind': row['kind'],
            'env': row['env'],
            'created_at': row['created_at'],
            'ok': bool(row['ok']),
            'error': row['error'],
            'request_json': json.loads(row['request_json']) if row['request_json'] else None,
            'response_json': json.loads(row['response_json']) if row['response_json'] else None
        })
    
    return JSONResponse({'submissions': submissions})


# ===== Rutas de Reportes =====
@app.get("/reports/contracts.xlsx")
async def export_contracts_excel(
    cliente: Optional[str] = Query(None),
    numero_contrato: Optional[str] = Query(None),
    numero_id: Optional[str] = Query(None),
    estado: Optional[str] = Query(None)
):
    """Exporta reporte Excel de contratos"""
    from .reports import generate_contracts_excel
    filters = {
        'cliente': cliente,
        'numero_contrato': numero_contrato,
        'numero_id': numero_id,
        'estado': estado
    }
    data = generate_contracts_excel(filters)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=contratos.xlsx"}
    )


@app.get("/reports/contracts.pdf")
async def export_contracts_pdf(
    cliente: Optional[str] = Query(None),
    numero_contrato: Optional[str] = Query(None),
    numero_id: Optional[str] = Query(None),
    estado: Optional[str] = Query(None)
):
    """Exporta reporte PDF de contratos"""
    from .reports import generate_contracts_pdf
    filters = {
        'cliente': cliente,
        'numero_contrato': numero_contrato,
        'numero_id': numero_id,
        'estado': estado
    }
    data = generate_contracts_pdf(filters)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=contratos.pdf"}
    )


# ===== Rutas de Clientes =====
@app.get("/clients", response_class=HTMLResponse)
async def clients_list(request: Request):
    """Lista todos los clientes"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clients ORDER BY nombre")
    clients = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return render_template("clients/list.html", request, clients=clients)


@app.get("/clients/new", response_class=HTMLResponse)
async def client_form(request: Request):
    """Formulario para crear cliente"""
    return render_template("clients/form.html", request, client=None)


@app.post("/clients")
async def create_client(
    request: Request,
    nombre: str = Form(...),
    ruc: Optional[str] = Form(None),
    direccion: Optional[str] = Form(None),
    telefono: Optional[str] = Form(None),
    email: Optional[str] = Form(None)
):
    """Crea un nuevo cliente"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO clients (nombre, ruc, direccion, telefono, email)
        VALUES (?, ?, ?, ?, ?)
    """, (nombre, ruc, direccion, telefono, email))
    client_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return RedirectResponse(url="/clients", status_code=303)


# ===== Endpoints de Reportes Adicionales =====
@app.get("/reports/purchase_orders.xlsx")
async def export_purchase_orders_excel(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    id: Optional[int] = Query(None)
):
    """Exporta reporte Excel de órdenes de compra"""
    from .reports import generate_purchase_orders_excel
    filters = {'cliente': cliente, 'contract_id': contract_id, 'id': id}
    data = generate_purchase_orders_excel(filters)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ordenes_compra.xlsx"}
    )


@app.get("/reports/purchase_orders.pdf")
async def export_purchase_orders_pdf(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None),
    id: Optional[int] = Query(None)
):
    """Exporta reporte PDF de órdenes de compra"""
    from .reports import generate_purchase_orders_pdf
    filters = {'cliente': cliente, 'contract_id': contract_id, 'id': id}
    data = generate_purchase_orders_pdf(filters)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ordenes_compra.pdf"}
    )


@app.get("/reports/delivery_notes.xlsx")
async def export_delivery_notes_excel(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None)
):
    """Exporta reporte Excel de notas de entrega"""
    from .reports import generate_delivery_notes_excel
    filters = {'cliente': cliente, 'contract_id': contract_id}
    data = generate_delivery_notes_excel(filters)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=notas_entrega.xlsx"}
    )


@app.get("/reports/delivery_notes.pdf")
async def export_delivery_notes_pdf(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None)
):
    """Exporta reporte PDF de notas de entrega"""
    from .reports import generate_delivery_notes_pdf
    filters = {'cliente': cliente, 'contract_id': contract_id}
    data = generate_delivery_notes_pdf(filters)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=notas_entrega.pdf"}
    )


@app.get("/reports/remissions.xlsx")
async def export_remissions_excel(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None)
):
    """Exporta reporte Excel de remisiones"""
    from .reports import generate_remissions_excel
    filters = {'cliente': cliente, 'contract_id': contract_id}
    data = generate_remissions_excel(filters)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=remisiones.xlsx"}
    )


@app.get("/reports/remissions.pdf")
async def export_remissions_pdf(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None)
):
    """Exporta reporte PDF de remisiones"""
    from .reports import generate_remissions_pdf
    filters = {'cliente': cliente, 'contract_id': contract_id}
    data = generate_remissions_pdf(filters)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=remisiones.pdf"}
    )


@app.get("/reports/sales_invoices.xlsx")
async def export_sales_invoices_excel(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None)
):
    """Exporta reporte Excel de facturas de venta"""
    from .reports import generate_sales_invoices_excel
    filters = {'cliente': cliente, 'contract_id': contract_id}
    data = generate_sales_invoices_excel(filters)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=facturas_venta.xlsx"}
    )


@app.get("/reports/sales_invoices.pdf")
async def export_sales_invoices_pdf(
    cliente: Optional[str] = Query(None),
    contract_id: Optional[int] = Query(None)
):
    """Exporta reporte PDF de facturas de venta"""
    from .reports import generate_sales_invoices_pdf
    filters = {'cliente': cliente, 'contract_id': contract_id}
    data = generate_sales_invoices_pdf(filters)
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=facturas_venta.pdf"}
    )

