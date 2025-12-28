"""
Modelos para productos
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Product:
    """Modelo de producto"""
    id: Optional[int]
    created_at: datetime
    codigo: Optional[str]
    nombre: str
    descripcion: Optional[str]
    unidad_medida: str
    precio_base: Optional[float]
    activo: bool
    
    @classmethod
    def from_row(cls, row) -> 'Product':
        """Crea una instancia desde una fila de SQLite"""
        # Convertir row a dict para facilitar acceso con .get()
        if hasattr(row, 'keys'):
            row_dict = dict(row)
        else:
            row_dict = row
        
        created_at = row_dict['created_at']
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            except:
                try:
                    created_at = datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
                except:
                    created_at = datetime.now()
        
        return cls(
            id=row_dict['id'],
            created_at=created_at,
            codigo=row_dict.get('codigo'),
            nombre=row_dict['nombre'],
            descripcion=row_dict.get('descripcion'),
            unidad_medida=row_dict['unidad_medida'],
            precio_base=row_dict.get('precio_base'),
            activo=bool(row_dict.get('activo', 1))
        )

