"""
Rutas para gestión de remisiones
"""
from typing import Optional, List
from datetime import datetime
from fastapi import Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, Response, RedirectResponse

from .db import get_db
from .models_system import Remission
from .utils import get_next_remission_number, get_config_value
from jinja2 import Environment


def register_remission_routes(app, jinja_env: Environment):
    """Registra las rutas de remisiones en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.get("/remissions", response_class=HTMLResponse)
    async def remissions_list(
        request: Request,
        cliente: Optional[str] = Query(None),
        contract_id: Optional[int] = Query(None)
    ):
        """Lista todas las remisiones con filtros"""
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            SELECT r.id, r.created_at, r.numero_remision, r.fecha_inicio, r.fecha_fin,
                   r.partida, r.llegada, r.transportista_nombre, r.transportista_ruc,
                   r.contract_id, cl.nombre as cliente_nombre, cl.ruc
            FROM remissions r
            LEFT JOIN contracts c ON r.contract_id = c.id
            LEFT JOIN clients cl ON r.client_id = cl.id OR c.client_id = cl.id
            WHERE 1=1
        """
        params = []
        
        if cliente:
            query += " AND cl.nombre LIKE ?"
            params.append(f"%{cliente}%")
        if contract_id:
            query += " AND r.contract_id = ?"
            params.append(contract_id)
        
        query += " ORDER BY r.fecha_inicio DESC, r.id DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        remissions = []
        for row in rows:
            r = Remission.from_row(row)
            r.cliente_nombre = row.get('cliente_nombre')
            r.cliente_ruc = row.get('ruc')
            remissions.append(r)
        
        conn.close()
        
        return render_template_internal("remissions/list.html", request,
                                       remissions=remissions,
                                       filters={'cliente': cliente, 'contract_id': contract_id})
    
    @app.get("/remissions/new", response_class=HTMLResponse)
    async def remission_form(request: Request):
        """Muestra el formulario para crear una nueva remisión"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, nombre, ruc FROM clients ORDER BY nombre")
        clients = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, numero_contrato FROM contracts WHERE estado = 'vigente' ORDER BY fecha DESC")
        contracts = [dict(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, codigo, nombre, unidad_medida FROM products WHERE activo = 1 ORDER BY nombre")
        products = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("remissions/form.html", request,
                                       remission=None, clients=clients, contracts=contracts, products=products)
    
    @app.post("/remissions")
    async def create_remission(
        request: Request,
        fecha_inicio: str = Form(...),
        fecha_fin: Optional[str] = Form(None),
        partida: Optional[str] = Form(None),
        llegada: Optional[str] = Form(None),
        vehiculo_marca: Optional[str] = Form(None),
        chapa: Optional[str] = Form(None),
        transportista_nombre: Optional[str] = Form(None),
        transportista_ruc: Optional[str] = Form(None),
        conductor_nombre: Optional[str] = Form(None),
        conductor_ci: Optional[str] = Form(None),
        contract_id: Optional[int] = Form(None),
        client_id: Optional[int] = Form(None),
        producto: List[str] = Form(...),
        unidad_medida: List[str] = Form(...),
        cantidad: List[float] = Form(...)
    ):
        """Crea una nueva remisión"""
        conn = get_db()
        cursor = conn.cursor()
        
        prefix = get_config_value('remission_prefix', 'REM-')
        numero_remision = get_next_remission_number(prefix)
        
        # Construir items
        items = []
        for i in range(len(producto)):
            items.append({
                'producto': producto[i],
                'unidad_medida': unidad_medida[i],
                'cantidad': cantidad[i]
            })
        
        # Insertar remisión
        cursor.execute("""
            INSERT INTO remissions 
            (numero_remision, fecha_inicio, fecha_fin, partida, llegada,
             vehiculo_marca, chapa, transportista_nombre, transportista_ruc,
             conductor_nombre, conductor_ci, contract_id, client_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (numero_remision, fecha_inicio, fecha_fin, partida, llegada,
              vehiculo_marca, chapa, transportista_nombre, transportista_ruc,
              conductor_nombre, conductor_ci, contract_id, client_id))
        
        remission_id = cursor.lastrowid
        
        # Insertar items
        for item in items:
            cursor.execute("""
                INSERT INTO remission_items 
                (remission_id, producto, unidad_medida, cantidad)
                VALUES (?, ?, ?, ?)
            """, (remission_id, item['producto'], item['unidad_medida'], item['cantidad']))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/remissions/{remission_id}", status_code=303)
    
    @app.get("/remissions/{remission_id}", response_class=HTMLResponse)
    async def remission_view(request: Request, remission_id: int):
        """Muestra el detalle de una remisión"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, cl.nombre as cliente_nombre, cl.ruc, c.numero_contrato
            FROM remissions r
            LEFT JOIN clients cl ON r.client_id = cl.id
            LEFT JOIN contracts c ON r.contract_id = c.id
            WHERE r.id = ?
        """, (remission_id,))
        
        row = cursor.fetchone()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Remisión no encontrada")
        
        r = Remission.from_row(row)
        r.cliente_nombre = row.get('cliente_nombre')
        r.numero_contrato = row.get('numero_contrato')
        
        # Obtener items
        cursor.execute("""
            SELECT ri.* FROM remission_items ri
            WHERE ri.remission_id = ?
            ORDER BY ri.id
        """, (remission_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("remissions/view.html", request,
                                       remission=r, items=items)
    
    @app.get("/remissions/{remission_id}/print", response_class=HTMLResponse)
    async def remission_print(request: Request, remission_id: int):
        """Vista imprimible de remisión"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, cl.*, c.numero_contrato
            FROM remissions r
            LEFT JOIN clients cl ON r.client_id = cl.id
            LEFT JOIN contracts c ON r.contract_id = c.id
            WHERE r.id = ?
        """, (remission_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Remisión no encontrada")
        
        r = Remission.from_row(row)
        r.numero_contrato = row.get('numero_contrato')
        
        cliente = dict(row) if row.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM remission_items
            WHERE remission_id = ?
            ORDER BY id
        """, (remission_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        template = jinja_env.get_template("print_remission.html")
        return HTMLResponse(template.render(
            remission=r,
            cliente=cliente,
            items=items,
            fecha_emision=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
    
    @app.get("/remissions/{remission_id}.pdf")
    async def remission_pdf(remission_id: int):
        """Exporta remisión como PDF"""
        from .pdf_generator import generate_remission_pdf
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT r.*, cl.*, c.numero_contrato
            FROM remissions r
            LEFT JOIN clients cl ON r.client_id = cl.id
            LEFT JOIN contracts c ON r.contract_id = c.id
            WHERE r.id = ?
        """, (remission_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Remisión no encontrada")
        
        r = Remission.from_row(row)
        r.numero_contrato = row.get('numero_contrato')
        
        cliente = dict(row) if row.get('nombre') else None
        
        cursor.execute("""
            SELECT * FROM remission_items
            WHERE remission_id = ?
            ORDER BY id
        """, (remission_id,))
        
        items = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        pdf_data = generate_remission_pdf(r, cliente, items)
        
        return Response(
            content=pdf_data,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=remision_{r.numero_remision}.pdf"}
        )

