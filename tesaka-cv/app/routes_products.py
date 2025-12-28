"""
Rutas para gestión de productos
"""
from typing import Optional, List
from fastapi import Request, Query, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse

from .db import get_db
from .models_products import Product
from jinja2 import Environment


def register_product_routes(app, jinja_env: Environment):
    """Registra las rutas de productos en la app"""
    
    def render_template_internal(template_name: str, request: Request, **kwargs):
        template = jinja_env.get_template(template_name)
        return HTMLResponse(template.render(request=request, **kwargs))
    
    @app.get("/products", response_class=HTMLResponse)
    async def products_list(
        request: Request,
        search: Optional[str] = Query(None),
        activo: Optional[str] = Query(None)
    ):
        """Lista todos los productos con filtros"""
        conn = get_db()
        cursor = conn.cursor()
        
        query = """
            SELECT * FROM products
            WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (nombre LIKE ? OR codigo LIKE ? OR descripcion LIKE ?)"
            search_term = f"%{search}%"
            params.extend([search_term, search_term, search_term])
        
        if activo is not None:
            query += " AND activo = ?"
            params.append(1 if activo == "1" else 0)
        else:
            # Por defecto mostrar solo activos
            query += " AND activo = 1"
        
        query += " ORDER BY nombre ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        products = [Product.from_row(row) for row in rows]
        
        conn.close()
        
        return render_template_internal("products/list.html", request,
                                       products=products,
                                       filters={'search': search, 'activo': activo})
    
    @app.get("/products/new", response_class=HTMLResponse)
    async def product_form(request: Request):
        """Muestra el formulario para crear un nuevo producto"""
        return render_template_internal("products/form.html", request, product=None)
    
    @app.get("/products/{product_id}", response_class=HTMLResponse)
    async def product_view(request: Request, product_id: int):
        """Muestra el detalle de un producto"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        
        product = Product.from_row(row)
        conn.close()
        
        return render_template_internal("products/view.html", request, product=product)
    
    @app.post("/products")
    async def create_product(
        request: Request,
        codigo: Optional[str] = Form(None),
        nombre: str = Form(...),
        descripcion: Optional[str] = Form(None),
        unidad_medida: str = Form(...),
        precio_base: Optional[float] = Form(None),
        activo: bool = Form(True)
    ):
        """Crea un nuevo producto"""
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar que código no exista si se proporciona
        if codigo:
            cursor.execute("SELECT id FROM products WHERE codigo = ?", (codigo,))
            if cursor.fetchone():
                conn.close()
                raise HTTPException(status_code=400, detail="El código de producto ya existe")
        
        cursor.execute("""
            INSERT INTO products (codigo, nombre, descripcion, unidad_medida, precio_base, activo)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (codigo, nombre, descripcion, unidad_medida, precio_base, 1 if activo else 0))
        
        product_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/products/{product_id}", status_code=303)
    
    @app.get("/products/{product_id}/edit", response_class=HTMLResponse)
    async def product_edit_form(request: Request, product_id: int):
        """Muestra el formulario para editar un producto"""
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        
        if not row:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        
        product = Product.from_row(row)
        conn.close()
        
        return render_template_internal("products/form.html", request, product=product)
    
    @app.post("/products/{product_id}")
    async def update_product(
        request: Request,
        product_id: int,
        codigo: Optional[str] = Form(None),
        nombre: str = Form(...),
        descripcion: Optional[str] = Form(None),
        unidad_medida: str = Form(...),
        precio_base: Optional[float] = Form(None),
        activo: bool = Form(True)
    ):
        """Actualiza un producto existente"""
        conn = get_db()
        cursor = conn.cursor()
        
        # Verificar que existe
        cursor.execute("SELECT id FROM products WHERE id = ?", (product_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        
        # Verificar que código no exista en otro producto
        if codigo:
            cursor.execute("SELECT id FROM products WHERE codigo = ? AND id != ?", 
                          (codigo, product_id))
            if cursor.fetchone():
                conn.close()
                raise HTTPException(status_code=400, detail="El código de producto ya existe en otro producto")
        
        cursor.execute("""
            UPDATE products
            SET codigo = ?, nombre = ?, descripcion = ?, unidad_medida = ?,
                precio_base = ?, activo = ?
            WHERE id = ?
        """, (codigo, nombre, descripcion, unidad_medida, precio_base, 1 if activo else 0, product_id))
        
        conn.commit()
        conn.close()
        
        return RedirectResponse(url=f"/products/{product_id}", status_code=303)
    
    @app.get("/api/products", response_class=HTMLResponse)
    async def api_products_json(request: Request):
        """API endpoint para obtener productos como JSON (para selects dinámicos)"""
        from fastapi.responses import JSONResponse
        import json
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT id, codigo, nombre, unidad_medida, precio_base FROM products WHERE activo = 1 ORDER BY nombre")
        rows = cursor.fetchall()
        conn.close()
        
        products = [dict(row) for row in rows]
        return JSONResponse(content=products)

