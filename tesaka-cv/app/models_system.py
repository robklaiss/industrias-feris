"""
Modelos de datos para el sistema de gestión
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List
import json


def _parse_datetime(dt_value):
    """Helper para parsear datetime desde string"""
    if isinstance(dt_value, datetime):
        return dt_value
    if isinstance(dt_value, str):
        try:
            return datetime.fromisoformat(dt_value.replace('Z', '+00:00'))
        except:
            try:
                return datetime.strptime(dt_value, '%Y-%m-%d %H:%M:%S')
            except:
                return datetime.now()
    return datetime.now()


def _row_to_dict(row):
    """Helper para convertir sqlite3.Row a dict"""
    if hasattr(row, 'keys'):
        return dict(row)
    return row


@dataclass
class Client:
    """Modelo de cliente"""
    id: Optional[int]
    created_at: datetime
    nombre: str
    ruc: Optional[str]
    direccion: Optional[str]
    telefono: Optional[str]
    email: Optional[str]
    
    @classmethod
    def from_row(cls, row) -> 'Client':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            created_at=_parse_datetime(row_dict['created_at']),
            nombre=row_dict['nombre'],
            ruc=row_dict.get('ruc'),
            direccion=row_dict.get('direccion'),
            telefono=row_dict.get('telefono'),
            email=row_dict.get('email')
        )


@dataclass
class Contract:
    """Modelo de contrato"""
    id: Optional[int]
    created_at: datetime
    fecha: str
    numero_contrato: str
    numero_id: Optional[str]
    tipo_contrato: Optional[str]
    client_id: Optional[int]
    estado: str
    data_json: Optional[str]
    
    @classmethod
    def from_row(cls, row) -> 'Contract':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            created_at=_parse_datetime(row_dict['created_at']),
            fecha=row_dict['fecha'],
            numero_contrato=row_dict['numero_contrato'],
            numero_id=row_dict.get('numero_id'),
            tipo_contrato=row_dict.get('tipo_contrato'),
            client_id=row_dict.get('client_id'),
            estado=row_dict.get('estado', 'vigente'),
            data_json=row_dict.get('data_json')
        )


@dataclass
class ContractItem:
    """Modelo de item de contrato"""
    id: Optional[int]
    contract_id: int
    producto: str
    unidad_medida: str
    cantidad_total: float
    precio_unitario: float
    
    @classmethod
    def from_row(cls, row) -> 'ContractItem':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            contract_id=row_dict['contract_id'],
            producto=row_dict['producto'],
            unidad_medida=row_dict['unidad_medida'],
            cantidad_total=row_dict['cantidad_total'],
            precio_unitario=row_dict['precio_unitario']
        )
    
    @property
    def precio_total(self) -> float:
        """Calcula el precio total"""
        return self.cantidad_total * self.precio_unitario


@dataclass
class PurchaseOrder:
    """Modelo de orden de compra"""
    id: Optional[int]
    created_at: datetime
    fecha: str
    numero: str
    contract_id: Optional[int]
    client_id: Optional[int]
    sync_mode: str
    snapshot_json: Optional[str]
    
    @classmethod
    def from_row(cls, row) -> 'PurchaseOrder':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            created_at=_parse_datetime(row_dict['created_at']),
            fecha=row_dict['fecha'],
            numero=row_dict['numero'],
            contract_id=row_dict.get('contract_id'),
            client_id=row_dict.get('client_id'),
            sync_mode=row_dict.get('sync_mode', 'linked'),
            snapshot_json=row_dict.get('snapshot_json')
        )


@dataclass
class PurchaseOrderItem:
    """Modelo de item de orden de compra"""
    id: Optional[int]
    purchase_order_id: int
    contract_item_id: Optional[int]
    producto: str
    unidad_medida: str
    cantidad: float
    precio_unitario: float
    
    @classmethod
    def from_row(cls, row) -> 'PurchaseOrderItem':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            purchase_order_id=row_dict['purchase_order_id'],
            contract_item_id=row_dict.get('contract_item_id'),
            producto=row_dict['producto'],
            unidad_medida=row_dict['unidad_medida'],
            cantidad=row_dict['cantidad'],
            precio_unitario=row_dict['precio_unitario']
        )
    
    @property
    def monto_total(self) -> float:
        """Calcula el monto total"""
        return self.cantidad * self.precio_unitario


@dataclass
class DeliveryNote:
    """Modelo de nota interna de entrega"""
    id: Optional[int]
    created_at: datetime
    fecha: str
    numero_nota: int
    contract_id: Optional[int]
    client_id: Optional[int]
    direccion_entrega: Optional[str]
    firma_recibe: Optional[str]
    firma_entrega: Optional[str]
    sync_mode: str
    snapshot_json: Optional[str]
    
    @classmethod
    def from_row(cls, row) -> 'DeliveryNote':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            created_at=_parse_datetime(row_dict['created_at']),
            fecha=row_dict['fecha'],
            numero_nota=row_dict['numero_nota'],
            contract_id=row_dict.get('contract_id'),
            client_id=row_dict.get('client_id'),
            direccion_entrega=row_dict.get('direccion_entrega'),
            firma_recibe=row_dict.get('firma_recibe'),
            firma_entrega=row_dict.get('firma_entrega'),
            sync_mode=row_dict.get('sync_mode', 'linked'),
            snapshot_json=row_dict.get('snapshot_json')
        )


@dataclass
class DeliveryNoteItem:
    """Modelo de item de nota de entrega"""
    id: Optional[int]
    delivery_note_id: int
    source_po_item_id: Optional[int]
    contract_item_id: Optional[int]
    producto: str
    unidad_medida: str
    cantidad: float
    
    @classmethod
    def from_row(cls, row) -> 'DeliveryNoteItem':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            delivery_note_id=row_dict['delivery_note_id'],
            source_po_item_id=row_dict.get('source_po_item_id'),
            contract_item_id=row_dict.get('contract_item_id'),
            producto=row_dict['producto'],
            unidad_medida=row_dict['unidad_medida'],
            cantidad=row_dict['cantidad']
        )


@dataclass
class Remission:
    """Modelo de remisión"""
    id: Optional[int]
    created_at: datetime
    numero_remision: str
    fecha_inicio: str
    fecha_fin: Optional[str]
    partida: Optional[str]
    llegada: Optional[str]
    vehiculo_marca: Optional[str]
    chapa: Optional[str]
    transportista_nombre: Optional[str]
    transportista_ruc: Optional[str]
    conductor_nombre: Optional[str]
    conductor_ci: Optional[str]
    contract_id: Optional[int]
    client_id: Optional[int]
    snapshot_json: Optional[str]
    
    @classmethod
    def from_row(cls, row) -> 'Remission':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            created_at=_parse_datetime(row_dict['created_at']),
            numero_remision=row_dict['numero_remision'],
            fecha_inicio=row_dict['fecha_inicio'],
            fecha_fin=row_dict.get('fecha_fin'),
            partida=row_dict.get('partida'),
            llegada=row_dict.get('llegada'),
            vehiculo_marca=row_dict.get('vehiculo_marca'),
            chapa=row_dict.get('chapa'),
            transportista_nombre=row_dict.get('transportista_nombre'),
            transportista_ruc=row_dict.get('transportista_ruc'),
            conductor_nombre=row_dict.get('conductor_nombre'),
            conductor_ci=row_dict.get('conductor_ci'),
            contract_id=row_dict.get('contract_id'),
            client_id=row_dict.get('client_id'),
            snapshot_json=row_dict.get('snapshot_json')
        )


@dataclass
class RemissionItem:
    """Modelo de item de remisión"""
    id: Optional[int]
    remission_id: int
    delivery_note_item_id: Optional[int]
    producto: str
    unidad_medida: str
    cantidad: float
    
    @classmethod
    def from_row(cls, row) -> 'RemissionItem':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            remission_id=row_dict['remission_id'],
            delivery_note_item_id=row_dict.get('delivery_note_item_id'),
            producto=row_dict['producto'],
            unidad_medida=row_dict['unidad_medida'],
            cantidad=row_dict['cantidad']
        )


@dataclass
class SalesInvoice:
    """Modelo de factura de venta"""
    id: Optional[int]
    created_at: datetime
    numero: str
    fecha: str
    condicion_venta: str
    contract_id: Optional[int]
    client_id: Optional[int]
    direccion: Optional[str]
    snapshot_json: Optional[str]
    
    @classmethod
    def from_row(cls, row) -> 'SalesInvoice':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            created_at=_parse_datetime(row_dict['created_at']),
            numero=row_dict['numero'],
            fecha=row_dict['fecha'],
            condicion_venta=row_dict.get('condicion_venta', 'contado'),
            contract_id=row_dict.get('contract_id'),
            client_id=row_dict.get('client_id'),
            direccion=row_dict.get('direccion'),
            snapshot_json=row_dict.get('snapshot_json')
        )


@dataclass
class SalesInvoiceItem:
    """Modelo de item de factura de venta"""
    id: Optional[int]
    sales_invoice_id: int
    remission_item_id: Optional[int]
    producto: str
    unidad_medida: str
    cantidad: float
    precio_unitario: float
    
    @classmethod
    def from_row(cls, row) -> 'SalesInvoiceItem':
        """Crea una instancia desde una fila de SQLite"""
        row_dict = _row_to_dict(row)
        
        return cls(
            id=row_dict['id'],
            sales_invoice_id=row_dict['sales_invoice_id'],
            remission_item_id=row_dict.get('remission_item_id'),
            producto=row_dict['producto'],
            unidad_medida=row_dict['unidad_medida'],
            cantidad=row_dict['cantidad'],
            precio_unitario=row_dict['precio_unitario']
        )
    
    @property
    def subtotal(self) -> float:
        """Calcula el subtotal"""
        return self.cantidad * self.precio_unitario
