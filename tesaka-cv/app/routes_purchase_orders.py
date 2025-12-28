"""
Rutas para gestión de órdenes de compra
"""
from typing import Optional, List
from datetime import datetime
from fastapi import Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from .db import get_db
from .models_system import PurchaseOrder
from .utils import validate_po_item_quantities
from jinja2 import Environment


def register_purchase_order_routes(app, jinja_env: Environment):
    """Registra las rutas de órdenes de compra en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.get("/purchase-orders", response_class=HTMLResponse)
    async def purchase_orders_list(
        request: Request,
        cliente: Optional[str] = Query(None),
        contract_id: Optional[int] = Query(None),
        id: Optional[int] = Query(None)
    ):
        """Lista todas las órdenes de compra con filtros"""
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            SELECT po.id, po.created_at, po.fecha, po.numero, po.contract_id,
                   c.numero_contrato, cl.nombre as cliente_nombre, cl.ruc, po.sync_mode
            FROM purchase_orders po
            LEFT JOIN contracts c ON po.contract_id = c.id
            LEFT JOIN clients cl ON po.client_id = cl.id OR c.client_id = cl.id
            WHERE 1=1
        """
        params = []
        
        if cliente:
            query += " AND cl.nombre LIKE ?"
            params.append(f"%{cliente}%")
        if contract_id:
            query += " AND po.contract_id = ?"
            params.append(contract_id)
        if id:
            query += " AND po.id = ?"
            params.append(id)
        
        query += " ORDER BY po.fecha DESC, po.id DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        purchase_orders = []
        for row in rows:
            po = PurchaseOrder.from_row(row)
            row_dict = dict(row) if hasattr(row, 'keys') else row
            po.cliente_nombre = row_dict.get('cliente_nombre')
            po.cliente_ruc = row_dict.get('ruc')
            po.numero_contrato = row_dict.get('numero_contrato')
            # Calcular total
            cursor.execute("""
                SELECT SUM(cantidad * precio_unitario) as total
                FROM purchase_order_items
                WHERE purchase_order_id = ?
            """, (po.id,))
            total_row = cursor.fetchone()
            if total_row:
                total_dict = dict(total_row) if hasattr(total_row, 'keys') else total_row
                po.monto_total = float(total_dict.get('total') or 0.0)
            else:
                po.monto_total = 0.0
            purchase_orders.append(po)
        
        conn.close()
        
        return render_template_internal("purchase_orders/list.html", request,
                                       purchase_orders=purchase_orders,
                                       filters={'cliente': cliente, 'contract_id': contract_id, 'id': id})
    
    @app.get("/purchase-orders/new", response_class=HTMLResponse)
    async def purchase_order_form(request: Request):
        """Muestra el formulario para crear una nueva orden de compra"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, nombre, ruc FROM clients ORDER BY nombre")
        clients = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, numero_contrato, numero_id FROM contracts WHERE estado = 'vigente' ORDER BY fecha DESC")
        contracts = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, codigo, nombre, unidad_medida, precio_base FROM products WHERE activo = 1 ORDER BY nombre")
        products = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("purchase_orders/form.html", request,
                                       purchase_order=None, clients=clients, contracts=contracts, products=products)
    
    @app.post("/purchase-orders")
    async def create_purchase_order(
        request: Request,
        fecha: str = Form(...),
        numero: str = Form(...),
        contract_id: Optional[int] = Form(None),
        client_id: Optional[int] = Form(None),
        sync_mode: str = Form("linked"),
        producto: List[str] = Form(...),
        unidad_medida: List[str] = Form(...),
        cantidad: List[float] = Form(...),
        precio_unitario: List[float] = Form(...)
    ):
        """Crea una nueva orden de compra"""
        conn = get_db()
        cursor = conn.cursor()
        
        # Construir items
        items = []
        for i in range(len(producto)):
            items.append({
                'producto': producto[i],
                'unidad_medida': unidad_medida[i],
                'cantidad': cantidad[i],
                'precio_unitario': precio_unitario[i]
            })
        
        # Validar cantidades si está vinculado a contrato
        if contract_id and sync_mode == 'linked':
            is_valid, errors = validate_po_item_quantities(items, contract_id)
            if not is_valid:
                conn.close()
                # Devolver errores (simplificado por ahora)
                raise HTTPException(status_code=400, detail="; ".join(errors))
        
        # Insertar orden de compra
        cursor.execute("""
            INSERT INTO purchase_orders (fecha, numero, contract_id, client_id, sync_mode)
            VALUES (?, ?, ?, ?, ?)
        """, (fecha, numero, contract_id, client_id, sync_mode))
        
        po_id = cursor.lastrowid
        
        # Insertar items
        for i, item in enumerate(items):
            contract_item_id = None
            # Si está vinculado, buscar contract_item_id
            if contract_id and sync_mode == 'linked':
                cursor.execute("""
                    SELECT id FROM contract_items
                    WHERE contract_id = ? AND producto = ?
                    LIMIT 1
                """, (contract_id, item['producto']))
                ci_row = cursor.fetchone()
                if ci_row:
                    contract_item_id = ci_row['id']
            
            cursor.execute("""
                INSERT INTO purchase_order_items 
                (purchase_order_id, contract_item_id, producto, unidad_medida, cantidad, precio_unitario)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (po_id, contract_item_id, item['producto'], item['unidad_medida'], 
                  item['cantidad'], item['precio_unitario']))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/purchase-orders/{po_id}", status_code=303)
    
    @app.get("/purchase-orders/{po_id}", response_class=HTMLResponse)
    async def purchase_order_view(request: Request, po_id: int):
        """Muestra el detalle de una orden de compra"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT po.*, cl.nombre as cliente_nombre, cl.ruc, c.numero_contrato
            FROM purchase_orders po
            LEFT JOIN clients cl ON po.client_id = cl.id
            LEFT JOIN contracts c ON po.contract_id = c.id
            WHERE po.id = ?
        """, (po_id,))
        
        row = cursor.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Orden de compra no encontrada")
        
        po = PurchaseOrder.from_row(row)
        row_dict = dict(row) if hasattr(row, 'keys') else row
        po.cliente_nombre = row_dict.get('cliente_nombre')
        po.numero_contrato = row_dict.get('numero_contrato')
        
        # Obtener items
        cursor.execute("""
            SELECT poi.*, ci.producto as contract_producto
            FROM purchase_order_items poi
            LEFT JOIN contract_items ci ON poi.contract_item_id = ci.id
            WHERE poi.purchase_order_id = ?
            ORDER BY poi.id
        """, (po_id,))
        
        items = []
        for item_row in cursor.fetchall():
            item_dict = dict(item_row) if hasattr(item_row, 'keys') else item_row
            items.append(item_dict)
        
        # Calcular total
        monto_total = sum(item['cantidad'] * item['precio_unitario'] for item in items)
        
        conn.close()
        
        return render_template_internal("purchase_orders/view.html", request,
                                       purchase_order=po, items=items, monto_total=monto_total)
    
    @app.get("/purchase-orders/{po_id}/print", response_class=HTMLResponse)
    async def purchase_order_print(request: Request, po_id: int):
        """Vista imprimible de orden de compra"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT po.*, cl.*, c.numero_contrato
            FROM purchase_orders po
            LEFT JOIN clients cl ON po.client_id = cl.id
            LEFT JOIN contracts c ON po.contract_id = c.id
            WHERE po.id = ?
        """, (po_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Orden de compra no encontrada")
        
        po = PurchaseOrder.from_row(row)
        row_dict = dict(row) if hasattr(row, 'keys') else row
        po.numero_contrato = row_dict.get('numero_contrato')
        
        cliente = dict(row) if row_dict.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM purchase_order_items
            WHERE purchase_order_id = ?
            ORDER BY id
        """, (po_id,))
        
        items = []
        for item_row in cursor.fetchall():
            item_dict = dict(item_row) if hasattr(item_row, 'keys') else item_row
            items.append(item_dict)
        
        monto_total = sum(float(item['cantidad']) * float(item['precio_unitario']) for item in items)
        
        conn.close()
        
        template = jinja_env.get_template("print_purchase_order.html")
        return HTMLResponse(template.render(
            purchase_order=po,
            cliente=cliente,
            items=items,
            monto_total=monto_total,
            fecha_emision=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
    
    @app.get("/purchase-orders/{po_id}.pdf")
    async def purchase_order_pdf(po_id: int):
        """Exporta orden de compra como PDF"""
        from .pdf_generator import generate_purchase_order_pdf
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT po.*, cl.*, c.numero_contrato
            FROM purchase_orders po
            LEFT JOIN clients cl ON po.client_id = cl.id
            LEFT JOIN contracts c ON po.contract_id = c.id
            WHERE po.id = ?
        """, (po_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Orden de compra no encontrada")
        
        po = PurchaseOrder.from_row(row)
        row_dict = dict(row) if hasattr(row, 'keys') else row
        po.numero_contrato = row_dict.get('numero_contrato')
        
        cliente = dict(row) if row_dict.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM purchase_order_items
            WHERE purchase_order_id = ?
            ORDER BY id
        """, (po_id,))
        
        items = []
        for item_row in cursor.fetchall():
            item_dict = dict(item_row) if hasattr(item_row, 'keys') else item_row
            items.append(item_dict)
        
        monto_total = sum(float(item['cantidad']) * float(item['precio_unitario']) for item in items)
        
        conn.close()
        
        pdf_data = generate_purchase_order_pdf(po, cliente, items, monto_total)
        
        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=orden_compra_{po.numero}.pdf"}
        )

