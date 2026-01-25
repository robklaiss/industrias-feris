"""
Cálculo/validación de CDC (Código de Control) SIFEN.

Algoritmo: Módulo 11 con ponderadores 2..9 (cíclico) aplicado de derecha a izquierda.
Regla DV:
  dv = 11 - (suma % 11)
  si dv == 11 -> 0
  si dv == 10 -> 1
"""

from __future__ import annotations


def _only_digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def calc_cdc_dv(base43: str) -> int:
    """
    Calcula el DV (0-9) de una base CDC de 43 dígitos.
    """
    digits = _only_digits(base43)
    if len(digits) != 43:
        raise ValueError(f"calc_cdc_dv() requiere 43 dígitos, recibió {len(digits)}")

    total = 0
    factor = 2
    # de derecha a izquierda
    for ch in reversed(digits):
        total += int(ch) * factor
        factor += 1
        if factor > 9:
            factor = 2

    mod = total % 11
    dv = 11 - mod
    if dv == 11:
        return 0
    if dv == 10:
        return 1
    return dv


def fix_cdc(cdc44: str) -> str:
    """
    Devuelve el CDC de 44 dígitos con DV corregido.
    """
    digits = _only_digits(cdc44)
    if len(digits) != 44:
        raise ValueError(f"fix_cdc() requiere 44 dígitos, recibió {len(digits)}")

    base43 = digits[:43]
    dv = calc_cdc_dv(base43)
    return f"{base43}{dv}"


def is_cdc_valid(cdc44: str) -> bool:
    """
    True si el CDC (44 dígitos) tiene DV correcto.
    """
    digits = _only_digits(cdc44)
    if len(digits) != 44:
        return False
    base43 = digits[:43]
    dv_orig = int(digits[43])
    try:
        return calc_cdc_dv(base43) == dv_orig
    except Exception:
        return False
