"""
Modelos de datos para la aplicación
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional
import json


@dataclass
class Invoice:
    """Modelo de factura"""
    id: Optional[int]
    created_at: datetime
    issue_date: str
    buyer_name: str
    data_json: str
    
    @property
    def data(self) -> Dict[str, Any]:
        """Retorna los datos JSON como diccionario"""
        return json.loads(self.data_json)
    
    @classmethod
    def from_row(cls, row) -> 'Invoice':
        """Crea una instancia desde una fila de SQLite"""
        return cls(
            id=row['id'],
            created_at=datetime.fromisoformat(row['created_at']) if isinstance(row['created_at'], str) else row['created_at'],
            issue_date=row['issue_date'],
            buyer_name=row['buyer_name'],
            data_json=row['data_json']
        )
    
    def calculate_total(self) -> float:
        """Calcula el total simple desde los items"""
        total = 0.0
        data = self.data
        if 'items' in data:
            for item in data['items']:
                cantidad = item.get('cantidad', 0)
                precio = item.get('precioUnitario', 0)
                total += cantidad * precio
        return total

