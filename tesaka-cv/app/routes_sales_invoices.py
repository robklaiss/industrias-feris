"""
Rutas para gestión de facturas de venta
"""
from typing import Optional, List
from datetime import datetime
from fastapi import Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from .db import get_db
from .models_system import SalesInvoice
from .utils import get_next_invoice_number
from jinja2 import Environment


def register_sales_invoice_routes(app, jinja_env: Environment):
    """Registra las rutas de facturas de venta en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.get("/sales-invoices", response_class=HTMLResponse)
    async def sales_invoices_list(
        request: Request,
        cliente: Optional[str] = Query(None),
        contract_id: Optional[int] = Query(None)
    ):
        """Lista todas las facturas de venta con filtros"""
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            SELECT si.id, si.created_at, si.numero, si.fecha, si.condicion_venta,
                   si.contract_id, cl.nombre as cliente_nombre, cl.ruc
            FROM sales_invoices si
            LEFT JOIN clients cl ON si.client_id = cl.id
            WHERE 1=1
        """
        params = []
        
        if cliente:
            query += " AND cl.nombre LIKE ?"
            params.append(f"%{cliente}%")
        if contract_id:
            query += " AND si.contract_id = ?"
            params.append(contract_id)
        
        query += " ORDER BY si.fecha DESC, si.id DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        sales_invoices = []
        for row in rows:
            si = SalesInvoice.from_row(row)
            si.cliente_nombre = row.get('cliente_nombre')
            si.cliente_ruc = row.get('ruc')
            # Calcular total
            cursor.execute("""
                SELECT SUM(cantidad * precio_unitario) as total
                FROM sales_invoice_items
                WHERE sales_invoice_id = ?
            """, (si.id,))
            total_row = cursor.fetchone()
            si.monto_total = total_row['total'] if total_row and total_row['total'] else 0.0
            sales_invoices.append(si)
        
        conn.close()
        
        return render_template_internal("sales_invoices/list.html", request,
                                       sales_invoices=sales_invoices,
                                       filters={'cliente': cliente, 'contract_id': contract_id})
    
    @app.get("/sales-invoices/new", response_class=HTMLResponse)
    async def sales_invoice_form(request: Request):
        """Muestra el formulario para crear una nueva factura de venta"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, nombre, ruc FROM clients ORDER BY nombre")
        clients = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, numero_contrato FROM contracts WHERE estado = 'vigente' ORDER BY fecha DESC")
        contracts = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, numero_remision FROM remissions ORDER BY fecha_inicio DESC")
        remissions = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, codigo, nombre, unidad_medida, precio_base FROM products WHERE activo = 1 ORDER BY nombre")
        products = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("sales_invoices/form.html", request,
                                       sales_invoice=None, clients=clients, contracts=contracts, remissions=remissions, products=products)
    
    @app.post("/sales-invoices")
    async def create_sales_invoice(
        request: Request,
        fecha: str = Form(...),
        condicion_venta: str = Form("contado"),
        contract_id: Optional[int] = Form(None),
        client_id: Optional[int] = Form(None),
        direccion: Optional[str] = Form(None),
        producto: List[str] = Form(...),
        unidad_medida: List[str] = Form(...),
        cantidad: List[float] = Form(...),
        precio_unitario: List[float] = Form(...)
    ):
        """Crea una nueva factura de venta"""
        conn = get_db()
        cursor = conn.cursor()
        
        numero = get_next_invoice_number()
        
        # Construir items
        items = []
        for i in range(len(producto)):
            items.append({
                'producto': producto[i],
                'unidad_medida': unidad_medida[i],
                'cantidad': cantidad[i],
                'precio_unitario': precio_unitario[i]
            })
        
        # Insertar factura
        cursor.execute("""
            INSERT INTO sales_invoices 
            (numero, fecha, condicion_venta, contract_id, client_id, direccion)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (numero, fecha, condicion_venta, contract_id, client_id, direccion))
        
        invoice_id = cursor.lastrowid
        
        # Insertar items
        for item in items:
            cursor.execute("""
                INSERT INTO sales_invoice_items 
                (sales_invoice_id, producto, unidad_medida, cantidad, precio_unitario)
                VALUES (?, ?, ?, ?, ?)
            """, (invoice_id, item['producto'], item['unidad_medida'], 
                  item['cantidad'], item['precio_unitario']))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/sales-invoices/{invoice_id}", status_code=303)
    
    @app.get("/sales-invoices/{invoice_id}", response_class=HTMLResponse)
    async def sales_invoice_view(request: Request, invoice_id: int):
        """Muestra el detalle de una factura de venta"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT si.*, cl.nombre as cliente_nombre, cl.ruc, c.numero_contrato
            FROM sales_invoices si
            LEFT JOIN clients cl ON si.client_id = cl.id
            LEFT JOIN contracts c ON si.contract_id = c.id
            WHERE si.id = ?
        """, (invoice_id,))
        
        row = cursor.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Factura no encontrada")
        
        si = SalesInvoice.from_row(row)
        si.cliente_nombre = row.get('cliente_nombre')
        si.numero_contrato = row.get('numero_contrato')
        
        # Obtener items
        cursor.execute("""
            SELECT sii.* FROM sales_invoice_items sii
            WHERE sii.sales_invoice_id = ?
            ORDER BY sii.id
        """, (invoice_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        # Calcular total
        monto_total = sum(item['cantidad'] * item['precio_unitario'] for item in items)
        
        conn.close()
        
        return render_template_internal("sales_invoices/view.html", request,
                                       sales_invoice=si, items=items, monto_total=monto_total)
    
    @app.get("/sales-invoices/{invoice_id}/print", response_class=HTMLResponse)
    async def sales_invoice_print(request: Request, invoice_id: int):
        """Vista imprimible de factura de venta"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT si.*, cl.*, c.numero_contrato
            FROM sales_invoices si
            LEFT JOIN clients cl ON si.client_id = cl.id
            LEFT JOIN contracts c ON si.contract_id = c.id
            WHERE si.id = ?
        """, (invoice_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Factura no encontrada")
        
        si = SalesInvoice.from_row(row)
        si.numero_contrato = row.get('numero_contrato')
        
        cliente = dict(row) if row.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM sales_invoice_items
            WHERE sales_invoice_id = ?
            ORDER BY id
        """, (invoice_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        monto_total = sum(item['cantidad'] * item['precio_unitario'] for item in items)
        
        conn.close()
        
        template = jinja_env.get_template("print_invoice.html")
        return HTMLResponse(template.render(
            sales_invoice=si,
            cliente=cliente,
            items=items,
            monto_total=monto_total,
            fecha_emision=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
    
    @app.get("/sales-invoices/{invoice_id}.pdf")
    async def sales_invoice_pdf(invoice_id: int):
        """Exporta factura de venta como PDF"""
        from .pdf_generator import generate_sales_invoice_pdf
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT si.*, cl.*, c.numero_contrato
            FROM sales_invoices si
            LEFT JOIN clients cl ON si.client_id = cl.id
            LEFT JOIN contracts c ON si.contract_id = c.id
            WHERE si.id = ?
        """, (invoice_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Factura no encontrada")
        
        si = SalesInvoice.from_row(row)
        si.numero_contrato = row.get('numero_contrato')
        
        cliente = dict(row) if row.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM sales_invoice_items
            WHERE sales_invoice_id = ?
            ORDER BY id
        """, (invoice_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        monto_total = sum(item['cantidad'] * item['precio_unitario'] for item in items)
        
        conn.close()
        
        pdf_data = generate_sales_invoice_pdf(si, cliente, items, monto_total)
        
        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=factura_{si.numero}.pdf"}
        )

