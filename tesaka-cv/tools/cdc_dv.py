#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Módulo único para cálculo y validación del DV (dígito verificador) del CDC SIFEN.

Este módulo es la fuente única de verdad para el cálculo del DV.
Todos los demás módulos deben usar estas funciones.
"""


def calc_cdc_dv(base_43: str) -> int:
    """
    Calcula el dígito verificador (DV) del CDC usando módulo 11.
    
    Esta es la implementación oficial que debe coincidir con SIFEN (Roshka reference).
    
    Args:
        base_43: String con exactamente 43 dígitos (base del CDC sin el DV)
        
    Returns:
        DV calculado (0-9)
        
    Raises:
        ValueError: Si base_43 no tiene 43 dígitos o no es numérico
        
    Algoritmo SIFEN (Roshka):
        - Recorrer los 43 dígitos desde la DERECHA hacia la IZQUIERDA
        - Multiplicar cada dígito por un peso que va de 2 a 11 (y se reinicia a 2)
        - Sumar todos los productos
        - Si (total % 11) > 1: dv = 11 - (total % 11)
        - Si no: dv = 0
    """
    if not base_43 or not isinstance(base_43, str):
        raise ValueError(f"base_43 debe ser un string: {base_43!r}")
    
    # Limpiar y validar
    digits = ''.join(c for c in base_43 if c.isdigit())
    if len(digits) != 43:
        raise ValueError(f"base_43 debe tener exactamente 43 dígitos. Recibido: {len(digits)} dígitos en {base_43!r}")
    
    # Algoritmo Roshka: pesos de 2 a 11, luego se reinicia a 2
    base_max = 11
    k = 2
    total = 0
    
    # Recorrer desde la derecha (último dígito primero)
    for digit in reversed(digits):
        if k > base_max:
            k = 2
        total += int(digit) * k
        k += 1
    
    # Calcular DV (algoritmo Roshka)
    remainder = total % 11
    if remainder > 1:
        dv = 11 - remainder
    else:
        dv = 0
    
    return dv


def is_cdc_valid(cdc_44: str) -> bool:
    """
    Valida si un CDC de 44 dígitos tiene el DV correcto.
    
    Args:
        cdc_44: CDC completo de 44 dígitos
        
    Returns:
        True si el DV es correcto, False en caso contrario
    """
    if not cdc_44 or not isinstance(cdc_44, str):
        return False
    
    # Validar formato
    digits = ''.join(c for c in cdc_44 if c.isdigit())
    if len(digits) != 44:
        return False
    
    # Extraer base y DV
    base43 = digits[:43]
    dv_original = int(digits[43])
    
    try:
        dv_calculado = calc_cdc_dv(base43)
        return dv_original == dv_calculado
    except Exception:
        return False


def fix_cdc(cdc_44: str) -> str:
    """
    Corrige el DV de un CDC de 44 dígitos reemplazando el último dígito.
    
    Args:
        cdc_44: CDC completo de 44 dígitos (puede tener DV incorrecto)
        
    Returns:
        CDC corregido con DV válido
        
    Raises:
        ValueError: Si el CDC no tiene 44 dígitos o no es numérico
    """
    if not cdc_44 or not isinstance(cdc_44, str):
        raise ValueError(f"CDC debe ser un string: {cdc_44!r}")
    
    # Validar formato
    digits = ''.join(c for c in cdc_44 if c.isdigit())
    if len(digits) != 44:
        raise ValueError(f"CDC debe tener exactamente 44 dígitos. Recibido: {len(digits)} dígitos en {cdc_44!r}")
    
    # Obtener base (primeros 43 dígitos)
    base43 = digits[:43]
    
    # Calcular DV correcto
    dv_correcto = calc_cdc_dv(base43)
    
    # Reemplazar último dígito por DV correcto
    cdc_corregido = base43 + str(dv_correcto)
    
    return cdc_corregido

