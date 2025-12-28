"""
Configuración de base de datos SQLite
"""
import sqlite3
from pathlib import Path
from typing import Optional

# Ruta de la base de datos
DB_PATH = Path(__file__).parent.parent / "tesaka.db"


def get_db() -> sqlite3.Connection:
    """Obtiene una conexión a la base de datos"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Inicializa la base de datos creando las tablas necesarias"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Tabla invoices (existente - mantener compatibilidad)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            issue_date TEXT NOT NULL,
            buyer_name TEXT NOT NULL,
            data_json TEXT NOT NULL
        )
    """)
    
    # Tabla clients
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            nombre TEXT NOT NULL,
            ruc TEXT,
            direccion TEXT,
            telefono TEXT,
            email TEXT
        )
    """)
    
    # Tabla products
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            codigo TEXT UNIQUE,
            nombre TEXT NOT NULL,
            descripcion TEXT,
            unidad_medida TEXT NOT NULL,
            precio_base REAL,
            activo INTEGER DEFAULT 1
        )
    """)
    
    # Tabla contracts
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contracts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha TEXT NOT NULL,
            numero_contrato TEXT NOT NULL UNIQUE,
            numero_id TEXT,
            tipo_contrato TEXT,
            client_id INTEGER,
            estado TEXT DEFAULT 'vigente' CHECK(estado IN ('vigente', 'cancelado')),
            data_json TEXT,
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """)
    
    # Tabla contract_items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS contract_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contract_id INTEGER NOT NULL,
            producto TEXT NOT NULL,
            unidad_medida TEXT NOT NULL,
            cantidad_total REAL NOT NULL,
            precio_unitario REAL NOT NULL,
            FOREIGN KEY (contract_id) REFERENCES contracts(id) ON DELETE CASCADE
        )
    """)
    
    # Tabla purchase_orders
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha TEXT NOT NULL,
            numero TEXT NOT NULL,
            contract_id INTEGER,
            client_id INTEGER,
            sync_mode TEXT DEFAULT 'linked' CHECK(sync_mode IN ('linked', 'manual')),
            snapshot_json TEXT,
            FOREIGN KEY (contract_id) REFERENCES contracts(id),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """)
    
    # Tabla purchase_order_items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS purchase_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            purchase_order_id INTEGER NOT NULL,
            contract_item_id INTEGER,
            producto TEXT NOT NULL,
            unidad_medida TEXT NOT NULL,
            cantidad REAL NOT NULL,
            precio_unitario REAL NOT NULL,
            FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id) ON DELETE CASCADE,
            FOREIGN KEY (contract_item_id) REFERENCES contract_items(id)
        )
    """)
    
    # Tabla delivery_notes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fecha TEXT NOT NULL,
            numero_nota INTEGER NOT NULL,
            contract_id INTEGER,
            client_id INTEGER,
            direccion_entrega TEXT,
            firma_recibe TEXT,
            firma_entrega TEXT,
            sync_mode TEXT DEFAULT 'linked' CHECK(sync_mode IN ('linked', 'manual')),
            snapshot_json TEXT,
            FOREIGN KEY (contract_id) REFERENCES contracts(id),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """)
    # Crear índice único para numero_nota
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_delivery_notes_numero 
        ON delivery_notes(numero_nota)
    """)
    
    # Tabla delivery_note_items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS delivery_note_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            delivery_note_id INTEGER NOT NULL,
            source_po_item_id INTEGER,
            contract_item_id INTEGER,
            producto TEXT NOT NULL,
            unidad_medida TEXT NOT NULL,
            cantidad REAL NOT NULL,
            FOREIGN KEY (delivery_note_id) REFERENCES delivery_notes(id) ON DELETE CASCADE,
            FOREIGN KEY (source_po_item_id) REFERENCES purchase_order_items(id),
            FOREIGN KEY (contract_item_id) REFERENCES contract_items(id)
        )
    """)
    
    # Tabla remissions
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS remissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            numero_remision TEXT NOT NULL UNIQUE,
            fecha_inicio TEXT NOT NULL,
            fecha_fin TEXT,
            partida TEXT,
            llegada TEXT,
            vehiculo_marca TEXT,
            chapa TEXT,
            transportista_nombre TEXT,
            transportista_ruc TEXT,
            conductor_nombre TEXT,
            conductor_ci TEXT,
            contract_id INTEGER,
            client_id INTEGER,
            snapshot_json TEXT,
            FOREIGN KEY (contract_id) REFERENCES contracts(id),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """)
    
    # Tabla remission_items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS remission_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            remission_id INTEGER NOT NULL,
            delivery_note_item_id INTEGER,
            producto TEXT NOT NULL,
            unidad_medida TEXT NOT NULL,
            cantidad REAL NOT NULL,
            FOREIGN KEY (remission_id) REFERENCES remissions(id) ON DELETE CASCADE,
            FOREIGN KEY (delivery_note_item_id) REFERENCES delivery_note_items(id)
        )
    """)
    
    # Tabla sales_invoices
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            numero TEXT NOT NULL UNIQUE,
            fecha TEXT NOT NULL,
            condicion_venta TEXT DEFAULT 'contado' CHECK(condicion_venta IN ('contado', 'credito')),
            contract_id INTEGER,
            client_id INTEGER,
            direccion TEXT,
            snapshot_json TEXT,
            FOREIGN KEY (contract_id) REFERENCES contracts(id),
            FOREIGN KEY (client_id) REFERENCES clients(id)
        )
    """)
    
    # Tabla sales_invoice_items
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sales_invoice_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sales_invoice_id INTEGER NOT NULL,
            remission_item_id INTEGER,
            producto TEXT NOT NULL,
            unidad_medida TEXT NOT NULL,
            cantidad REAL NOT NULL,
            precio_unitario REAL NOT NULL,
            FOREIGN KEY (sales_invoice_id) REFERENCES sales_invoices(id) ON DELETE CASCADE,
            FOREIGN KEY (remission_item_id) REFERENCES remission_items(id)
        )
    """)
    
    # Tabla de configuración para números base
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    # Insertar valores por defecto si no existen
    cursor.execute("""
        INSERT OR IGNORE INTO system_config (key, value) VALUES 
        ('remission_prefix', 'REM-'),
        ('remission_base_number', '1'),
        ('invoice_base_number', '1')
    """)
    
    # Tabla submissions - Registro de envíos a Tesaka
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('factura', 'retencion', 'autofactura')),
            env TEXT NOT NULL CHECK(env IN ('prod', 'homo')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            request_json TEXT NOT NULL,
            response_json TEXT,
            ok INTEGER DEFAULT 0,
            error TEXT,
            FOREIGN KEY (invoice_id) REFERENCES invoices(id)
        )
    """)
    # Índice para búsquedas por invoice_id
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_submissions_invoice_id ON submissions(invoice_id)
    """)
    
    conn.commit()
    conn.close()

