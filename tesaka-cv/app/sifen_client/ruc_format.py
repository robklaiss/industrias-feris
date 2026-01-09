"""
Normalización de RUC según especificación SIFEN consultaRUC

Reglas de negocio confirmadas:
- Un RUC paraguayo NUNCA tiene letras
- El RUC siempre tiene 7 a 8 dígitos en total (incluyendo el DV)
- Input puede venir como "4554737-8" o "45547378" (con o sin guión)
- El servicio SIFEN consultaRUC espera dRUCCons sin guión (solo dígitos)
"""
import re
from typing import Optional


class RucFormatError(ValueError):
    """Error de formato de RUC según especificación SIFEN"""
    pass


def normalize_sifen_truc(raw: str) -> str:
    """
    Normaliza un RUC para cumplir con la especificación SIFEN consultaRUC.
    
    Reglas:
    - Si viene "BASE-DV":
       - BASE debe ser 6 o 7 dígitos
       - DV debe ser 1 dígito
       - Retornar BASE+DV (7 u 8 dígitos)
    - Si NO tiene guión:
       - Debe ser solo dígitos
       - Longitud debe ser 7 u 8
       - Retornar tal cual
    
    Validación final estricta:
    - regex: ^[0-9]{7,8}$
    - Si no cumple: lanzar error con mensaje claro
    
    Args:
        raw: RUC en formato raw (puede tener guión, espacios, etc.)
        
    Returns:
        RUC normalizado (7-8 dígitos, sin guión, solo números)
        
    Raises:
        RucFormatError: Si el RUC no puede normalizarse según especificación
    """
    if not raw:
        raise RucFormatError("RUC no puede estar vacío")
    
    # Trim
    ruc_clean = raw.strip()
    
    if not ruc_clean:
        raise RucFormatError("RUC no puede estar vacío (solo espacios)")
    
    # Si contiene guión, separar
    if '-' in ruc_clean:
        parts = ruc_clean.split('-', 1)
        base_raw = parts[0].strip()
        dv_raw = parts[1].strip() if len(parts) > 1 else ""
        
        # Base: solo dígitos
        if not re.match(r'^[0-9]+$', base_raw):
            raise RucFormatError(
                f"RUC base contiene caracteres no numéricos: '{base_raw}'. "
                f"El RUC paraguayo solo contiene dígitos. Input: '{raw}'"
            )
        
        # DV: solo dígitos, máximo 1 caracter
        if dv_raw:
            if not re.match(r'^[0-9]+$', dv_raw):
                raise RucFormatError(
                    f"Dígito verificador (DV) contiene caracteres no numéricos: '{dv_raw}'. "
                    f"El DV debe ser un dígito. Input: '{raw}'"
                )
            if len(dv_raw) > 1:
                # Tomar solo el primer dígito
                dv = dv_raw[0]
            else:
                dv = dv_raw
        else:
            raise RucFormatError(
                f"RUC con guión debe incluir dígito verificador (DV). Input: '{raw}'"
            )
        
        # Validar longitud de base (debe ser 6 o 7 dígitos)
        base_len = len(base_raw)
        if base_len < 6 or base_len > 7:
            raise RucFormatError(
                f"RUC base tiene longitud inválida: {base_len} (debe ser 6 o 7 dígitos). "
                f"Input: '{raw}', Base: '{base_raw}'"
            )
        
        # Concatenar base + dv
        ruc_normalized = base_raw + dv
        
        # Validar longitud final (debe ser 7 u 8 dígitos)
        if len(ruc_normalized) < 7 or len(ruc_normalized) > 8:
            raise RucFormatError(
                f"RUC normalizado tiene longitud inválida: {len(ruc_normalized)} (debe ser 7 u 8 dígitos). "
                f"Input: '{raw}', Normalizado: '{ruc_normalized}'"
            )
    else:
        # No tiene guión, usar tal cual pero validar
        # Eliminar espacios y otros caracteres no numéricos
        ruc_normalized = re.sub(r'[^0-9]', '', ruc_clean)
        
        if not ruc_normalized:
            raise RucFormatError(
                f"RUC no contiene dígitos válidos. Input: '{raw}'"
            )
        
        # Validar longitud (debe ser 7 u 8 dígitos)
        ruc_len = len(ruc_normalized)
        if ruc_len < 7 or ruc_len > 8:
            raise RucFormatError(
                f"RUC tiene longitud inválida: {ruc_len} (debe ser 7 u 8 dígitos). "
                f"Input: '{raw}', Normalizado: '{ruc_normalized}'"
            )
    
    # Validación final estricta: regex ^[0-9]{7,8}$
    if not re.match(r'^[0-9]{7,8}$', ruc_normalized):
        raise RucFormatError(
            f"RUC normalizado no cumple especificación: debe ser 7 u 8 dígitos. "
            f"Input: '{raw}', Normalizado: '{ruc_normalized}'"
        )
    
    return ruc_normalized
