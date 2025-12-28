"""
Rutas para gestión de contratos
"""
import json
from datetime import datetime
from typing import List, Optional
from fastapi import Request, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from jinja2 import Environment, FileSystemLoader

from .db import get_db
from .models_system import Contract, ContractItem, Client
from .utils import get_contract_balance


def register_contract_routes(app, jinja_env: Environment):
    """Registra las rutas de contratos en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.get("/contracts", response_class=HTMLResponse)
    async def contracts_list(
        request: Request,
        cliente: Optional[str] = Query(None),
        numero_contrato: Optional[str] = Query(None),
        numero_id: Optional[str] = Query(None),
        estado: Optional[str] = Query(None)
    ):
        """Lista todos los contratos con filtros"""
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            SELECT c.id, c.created_at, c.fecha, c.numero_contrato, c.numero_id,
                   c.tipo_contrato, c.estado, cl.nombre as cliente_nombre, cl.ruc
            FROM contracts c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE 1=1
        """
        params = []
        
        if cliente:
            query += " AND cl.nombre LIKE ?"
            params.append(f"%{cliente}%")
        if numero_contrato:
            query += " AND c.numero_contrato LIKE ?"
            params.append(f"%{numero_contrato}%")
        if numero_id:
            query += " AND c.numero_id LIKE ?"
            params.append(f"%{numero_id}%")
        if estado:
            query += " AND c.estado = ?"
            params.append(estado)
        
        query += " ORDER BY c.fecha DESC, c.id DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        # Crear contratos con datos adicionales
        contracts = []
        for row in rows:
            contract = Contract.from_row(row)
            row_dict = dict(row) if hasattr(row, 'keys') else row
            contract.cliente_nombre = row_dict.get('cliente_nombre')
            contract.cliente_ruc = row_dict.get('ruc')
            # Obtener total
            cursor.execute("""
                SELECT SUM(cantidad_total * precio_unitario) as total
                FROM contract_items
                WHERE contract_id = ?
            """, (contract.id,))
            total_row = cursor.fetchone()
            if total_row:
                total_dict = dict(total_row) if hasattr(total_row, 'keys') else total_row
                contract.monto_total = total_dict.get('total') or 0.0
            else:
                contract.monto_total = 0.0
            contracts.append(contract)
        
        conn.close()
        
        return render_template_internal("contracts/list.html", request,
                                       contracts=contracts,
                                       filters={'cliente': cliente, 'numero_contrato': numero_contrato,
                                               'numero_id': numero_id, 'estado': estado})
    
    @app.get("/contracts/new", response_class=HTMLResponse)
    async def contract_form(request: Request):
        """Muestra el formulario para crear un nuevo contrato"""
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, nombre, ruc FROM clients ORDER BY nombre")
        clients = [Client.from_row(row) for row in cursor.fetchall()]
        cursor.execute("SELECT id, codigo, nombre, unidad_medida, precio_base FROM products WHERE activo = 1 ORDER BY nombre")
        products = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return render_template_internal("contracts/form.html", request, contract=None, clients=clients, products=products)
    
    @app.get("/contracts/{contract_id}", response_class=HTMLResponse)
    async def contract_view(request: Request, contract_id: int):
        """Muestra el detalle de un contrato"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT c.*, cl.nombre as cliente_nombre, cl.ruc, cl.direccion, cl.telefono, cl.email
            FROM contracts c
            LEFT JOIN clients cl ON c.client_id = cl.id
            WHERE c.id = ?
        """, (contract_id,))
        
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Contrato no encontrado")
        
        contract = Contract.from_row(row)
        row_dict = dict(row) if hasattr(row, 'keys') else row
        contract.cliente_nombre = row_dict.get('cliente_nombre')
        contract.cliente_ruc = row_dict.get('ruc')
        
        # Obtener items del contrato
        cursor.execute("""
            SELECT * FROM contract_items
            WHERE contract_id = ?
            ORDER BY id
        """, (contract_id,))
        
        items = [ContractItem.from_row(row) for row in cursor.fetchall()]
        
        # Calcular saldos
        balances = get_contract_balance(contract_id)
        for item in items:
            item.saldo_disponible = balances.get(item.id, item.cantidad_total)
        
        # Calcular totales
        monto_total = sum(item.precio_total for item in items)
        
        conn.close()
        
        return render_template_internal("contracts/view.html", request,
                                       contract=contract, items=items, monto_total=monto_total)
    
    @app.post("/contracts")
    async def create_contract(
        request: Request,
        fecha: str = Form(...),
        numero_contrato: str = Form(...),
        numero_id: Optional[str] = Form(None),
        tipo_contrato: Optional[str] = Form(None),
        client_id: Optional[int] = Form(None),
        estado: str = Form("vigente"),
        producto: List[str] = Form(...),  # Ahora viene del select, es el nombre del producto
        unidad_medida: List[str] = Form(...),
        cantidad_total: List[float] = Form(...),
        precio_unitario: List[float] = Form(...)
    ):
        """Guarda un nuevo contrato"""
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar que numero_contrato no exista
        cursor.execute("SELECT id FROM contracts WHERE numero_contrato = ?", (numero_contrato,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="El número de contrato ya existe")
        
        # Insertar contrato
        cursor.execute("""
            INSERT INTO contracts (fecha, numero_contrato, numero_id, tipo_contrato, client_id, estado)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (fecha, numero_contrato, numero_id, tipo_contrato, client_id, estado))
        
        contract_id = cursor.lastrowid
        
        # Insertar items
        for i in range(len(producto)):
            cursor.execute("""
                INSERT INTO contract_items (contract_id, producto, unidad_medida, cantidad_total, precio_unitario)
                VALUES (?, ?, ?, ?, ?)
            """, (contract_id, producto[i], unidad_medida[i], cantidad_total[i], precio_unitario[i]))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)
    
    @app.get("/contracts/{contract_id}/edit", response_class=HTMLResponse)
    async def contract_edit_form(request: Request, contract_id: int):
        """Muestra el formulario para editar un contrato"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Contrato no encontrado")
        
        contract = Contract.from_row(row)
        
        cursor.execute("SELECT * FROM contract_items WHERE contract_id = ? ORDER BY id", (contract_id,))
        items = [ContractItem.from_row(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, nombre, ruc FROM clients ORDER BY nombre")
        clients = [Client.from_row(row) for row in cursor.fetchall()]
        
        cursor.execute("SELECT id, codigo, nombre, unidad_medida, precio_base FROM products WHERE activo = 1 ORDER BY nombre")
        products = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return render_template_internal("contracts/form.html", request,
                                       contract=contract, items=items, clients=clients, products=products)
    
    @app.post("/contracts/{contract_id}")
    async def update_contract(
        request: Request,
        contract_id: int,
        fecha: str = Form(...),
        numero_contrato: str = Form(...),
        numero_id: Optional[str] = Form(None),
        tipo_contrato: Optional[str] = Form(None),
        client_id: Optional[int] = Form(None),
        estado: str = Form("vigente"),
        producto: List[str] = Form(...),
        unidad_medida: List[str] = Form(...),
        cantidad_total: List[float] = Form(...),
        precio_unitario: List[float] = Form(...)
    ):
        """Actualiza un contrato existente"""
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar que existe
        cursor.execute("SELECT id FROM contracts WHERE id = ?", (contract_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Contrato no encontrado")
        
        # Verificar que numero_contrato no exista en otro contrato
        cursor.execute("SELECT id FROM contracts WHERE numero_contrato = ? AND id != ?", 
                      (numero_contrato, contract_id))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="El número de contrato ya existe en otro contrato")
        
        # Actualizar contrato
        cursor.execute("""
            UPDATE contracts
            SET fecha = ?, numero_contrato = ?, numero_id = ?, tipo_contrato = ?,
                client_id = ?, estado = ?
            WHERE id = ?
        """, (fecha, numero_contrato, numero_id, tipo_contrato, client_id, estado, contract_id))
        
        # Eliminar items existentes y crear nuevos
        cursor.execute("DELETE FROM contract_items WHERE contract_id = ?", (contract_id,))
        
        for i in range(len(producto)):
            cursor.execute("""
                INSERT INTO contract_items (contract_id, producto, unidad_medida, cantidad_total, precio_unitario)
                VALUES (?, ?, ?, ?, ?)
            """, (contract_id, producto[i], unidad_medida[i], cantidad_total[i], precio_unitario[i]))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/contracts/{contract_id}", status_code=303)

