"""
Catálogo de ciudades de Paraguay para SIFEN
Basado en "Código de Referencia Geográfica" oficial
"""

# Catálogo de ciudades - formato: {codigo: descripcion}
# cCiu es un código GLOBAL que combina departamento y distrito
CIUDADES_PY = {
    # Alto Paraná
    "3428": "CIUDAD DEL ESTE(PLANTA URBANA)",  # Para Alto Paraná - Ciudad del Este (cDis=145)
    
    # Central
    "6106": "LAMBARE",  # Para Central - Lambare (cDis=169)
    
    # Agregar más según sea necesario
}

def get_descripcion_ciudad(cod_ciu):
    """
    Obtiene la descripción oficial de la ciudad
    
    Args:
        cod_ciu (str): Código de la ciudad (global, hasta 4 dígitos)
    
    Returns:
        str: Descripción exacta de la ciudad según catálogo SIFEN
    """
    # Buscar en catálogo
    if cod_ciu in CIUDADES_PY:
        return CIUDADES_PY[cod_ciu]
    
    # Si no encuentra, devolver None para indicar que no hay coincidencia
    return None
