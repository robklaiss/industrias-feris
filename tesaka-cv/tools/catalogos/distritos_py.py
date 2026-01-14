"""
Catálogo de distritos de Paraguay para SIFEN
Basado en códigos válidos conocidos y XSD
"""

# Catálogo de distritos - formato: {codigo: descripcion}
# cDis es un código GLOBAL a nivel país, no por departamento
DISTRITOS_PY = {
    # Alto Paraná
    "1": "CIUDAD DEL ESTE",
    "14": "HERNANDARIAS",
    "145": "CIUDAD DEL ESTE",  # Código correcto para Ciudad del Este
    "87": "CIUDAD DEL ESTE",  # Código alternativo
    
    # Central
    "169": "LAMBARE",
    "1": "ASUNCION",  # Este código ya existe para Asunción
    
    # Otros códigos conocidos
    # Agregar más según sea necesario
}

# Mapeo especial para distritos con mismo código en diferentes departamentos
DISTRITOS_ESPECIALES = {
    # Para código "1" que existe en múltiples departamentos
    ("11", "1"): "CIUDAD DEL ESTE",  # Alto Paraná
    ("12", "1"): "ASUNCION",  # Central
}

# Catálogo de departamentos - formato: {codigo: descripcion}
DEPARTAMENTOS_PY = {
    "1": "CONCEPCION",
    "2": "SAN PEDRO",
    "3": "CORDILLERA",
    "4": "GUAIRA",
    "5": "CAAGUAZU",
    "6": "CAAZAPA",
    "7": "ITAPUA",
    "8": "MISIONES",
    "9": "PARAGUARI",
    "10": "ALTO PARANA",
    "11": "ALTO PARANA",  # Código alternativo
    "12": "CENTRAL",
    "13": "ÑEEMBUCU",
    "14": "AMAMBAY",
    "15": "CANINDEYU",
    "16": "PRESIDENTE HAYES",
    "17": "BOQUERON",
}

def get_descripcion_distrito(cod_dis):
    """
    Obtiene la descripción oficial del distrito
    
    Args:
        cod_dis (str): Código del distrito (global, hasta 4 dígitos)
    
    Returns:
        str: Descripción exacta del distrito según catálogo SIFEN
    """
    # Buscar en catálogo global
    if cod_dis in DISTRITOS_PY:
        return DISTRITOS_PY[cod_dis]
    
    # Si no encuentra, devolver None para indicar que no hay coincidencia
    return None

def get_descripcion_departamento(cod_dep):
    """
    Obtiene la descripción oficial del departamento
    
    Args:
        cod_dep (str): Código del departamento
    
    Returns:
        str: Descripción exacta del departamento según catálogo SIFEN
    """
    return DEPARTAMENTOS_PY.get(cod_dep, None)

# Lista de distritos válidos por departamento
DISTRITOS_POR_DEPARTAMENTO = {
    "11": [  # Alto Paraná
        "1", "14", "87", "2", "3", "4", "5", "6", "7", "8", "9", "10",
        "11", "12", "13", "15", "16", "17", "18", "19", "20", "21", "22"
    ],
    "12": [  # Central
        "1", "169", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11",
        "12", "13", "14", "15", "16", "17", "18", "19"
    ],
    # Agregar más departamentos según sea necesario
}
