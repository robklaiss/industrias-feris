"""
Rutas para gestión de notas internas de entrega
"""
from typing import Optional, List
from datetime import datetime
from fastapi import Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from .db import get_db
from .models_system import DeliveryNote
from .utils import get_next_delivery_note_number, validate_delivery_note_quantities
from jinja2 import Environment


def register_delivery_note_routes(app, jinja_env: Environment):
    """Registra las rutas de notas de entrega en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.get("/delivery-notes", response_class=HTMLResponse)
    async def delivery_notes_list(
        request: Request,
        cliente: Optional[str] = Query(None),
        contract_id: Optional[int] = Query(None)
    ):
        """Lista todas las notas de entrega con filtros"""
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            SELECT dn.id, dn.created_at, dn.fecha, dn.numero_nota, dn.contract_id,
                   c.numero_contrato, cl.nombre as cliente_nombre, cl.ruc,
                   dn.direccion_entrega, dn.sync_mode
            FROM delivery_notes dn
            LEFT JOIN contracts c ON dn.contract_id = c.id
            LEFT JOIN clients cl ON dn.client_id = cl.id OR c.client_id = cl.id
            WHERE 1=1
        """
        params = []
        
        if cliente:
            query += " AND cl.nombre LIKE ?"
            params.append(f"%{cliente}%")
        if contract_id:
            query += " AND dn.contract_id = ?"
            params.append(contract_id)
        
        query += " ORDER BY dn.fecha DESC, dn.id DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        delivery_notes = []
        for row in rows:
            dn = DeliveryNote.from_row(row)
            dn.cliente_nombre = row.get('cliente_nombre')
            dn.cliente_ruc = row.get('ruc')
            dn.numero_contrato = row.get('numero_contrato')
            delivery_notes.append(dn)
        
        conn.close()
        
        return render_template_internal("delivery_notes/list.html", request,
                                       delivery_notes=delivery_notes,
                                       filters={'cliente': cliente, 'contract_id': contract_id})
    
    @app.get("/delivery-notes/new", response_class=HTMLResponse)
    async def delivery_note_form(request: Request):
        """Muestra el formulario para crear una nueva nota de entrega"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, nombre, ruc FROM clients ORDER BY nombre")
        clients = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, numero_contrato FROM contracts WHERE estado = 'vigente' ORDER BY fecha DESC")
        contracts = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, codigo, nombre, unidad_medida FROM products WHERE activo = 1 ORDER BY nombre")
        products = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("delivery_notes/form.html", request,
                                       delivery_note=None, clients=clients, contracts=contracts, products=products)
    
    @app.post("/delivery-notes")
    async def create_delivery_note(
        request: Request,
        fecha: str = Form(...),
        contract_id: Optional[int] = Form(None),
        client_id: Optional[int] = Form(None),
        direccion_entrega: Optional[str] = Form(None),
        firma_recibe: Optional[str] = Form(None),
        firma_entrega: Optional[str] = Form(None),
        sync_mode: str = Form("linked"),
        producto: List[str] = Form(...),
        unidad_medida: List[str] = Form(...),
        cantidad: List[float] = Form(...)
    ):
        """Crea una nueva nota de entrega"""
        conn = get_db()
        cursor = conn.cursor()
        
        numero_nota = get_next_delivery_note_number()
        
        # Construir items
        items = []
        for i in range(len(producto)):
            items.append({
                'producto': producto[i],
                'unidad_medida': unidad_medida[i],
                'cantidad': cantidad[i]
            })
        
        # Validar cantidades (simplificado - requiere implementar validación completa)
        
        # Insertar nota de entrega
        cursor.execute("""
            INSERT INTO delivery_notes 
            (fecha, numero_nota, contract_id, client_id, direccion_entrega, 
             firma_recibe, firma_entrega, sync_mode)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (fecha, numero_nota, contract_id, client_id, direccion_entrega,
              firma_recibe, firma_entrega, sync_mode))
        
        dn_id = cursor.lastrowid
        
        # Insertar items
        for item in items:
            cursor.execute("""
                INSERT INTO delivery_note_items 
                (delivery_note_id, producto, unidad_medida, cantidad)
                VALUES (?, ?, ?, ?)
            """, (dn_id, item['producto'], item['unidad_medida'], item['cantidad']))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/delivery-notes/{dn_id}", status_code=303)
    
    @app.get("/delivery-notes/{dn_id}", response_class=HTMLResponse)
    async def delivery_note_view(request: Request, dn_id: int):
        """Muestra el detalle de una nota de entrega"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT dn.*, cl.nombre as cliente_nombre, cl.ruc, c.numero_contrato
            FROM delivery_notes dn
            LEFT JOIN clients cl ON dn.client_id = cl.id
            LEFT JOIN contracts c ON dn.contract_id = c.id
            WHERE dn.id = ?
        """, (dn_id,))
        
        row = cursor.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Nota de entrega no encontrada")
        
        dn = DeliveryNote.from_row(row)
        dn.cliente_nombre = row.get('cliente_nombre')
        dn.numero_contrato = row.get('numero_contrato')
        
        # Obtener items
        cursor.execute("""
            SELECT dni.* FROM delivery_note_items dni
            WHERE dni.delivery_note_id = ?
            ORDER BY dni.id
        """, (dn_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("delivery_notes/view.html", request,
                                       delivery_note=dn, items=items)
    
    @app.get("/delivery-notes/{dn_id}/print", response_class=HTMLResponse)
    async def delivery_note_print(request: Request, dn_id: int):
        """Vista imprimible de nota de entrega"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT dn.*, cl.*, c.numero_contrato
            FROM delivery_notes dn
            LEFT JOIN clients cl ON dn.client_id = cl.id
            LEFT JOIN contracts c ON dn.contract_id = c.id
            WHERE dn.id = ?
        """, (dn_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Nota de entrega no encontrada")
        
        dn = DeliveryNote.from_row(row)
        dn.numero_contrato = row.get('numero_contrato')
        
        cliente = dict(row) if row.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM delivery_note_items
            WHERE delivery_note_id = ?
            ORDER BY id
        """, (dn_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        template = jinja_env.get_template("print_delivery_note.html")
        return HTMLResponse(template.render(
            delivery_note=dn,
            cliente=cliente,
            items=items,
            fecha_emision=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
    
    @app.get("/delivery-notes/{dn_id}.pdf")
    async def delivery_note_pdf(dn_id: int):
        """Exporta nota de entrega como PDF"""
        from .pdf_generator import generate_delivery_note_pdf
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT dn.*, cl.*, c.numero_contrato
            FROM delivery_notes dn
            LEFT JOIN clients cl ON dn.client_id = cl.id
            LEFT JOIN contracts c ON dn.contract_id = c.id
            WHERE dn.id = ?
        """, (dn_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Nota de entrega no encontrada")
        
        dn = DeliveryNote.from_row(row)
        dn.numero_contrato = row.get('numero_contrato')
        
        cliente = dict(row) if row.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM delivery_note_items
            WHERE delivery_note_id = ?
            ORDER BY id
        """, (dn_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        pdf_data = generate_delivery_note_pdf(dn, cliente, items)
        
        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=nota_entrega_{dn.numero_nota}.pdf"}
        )

