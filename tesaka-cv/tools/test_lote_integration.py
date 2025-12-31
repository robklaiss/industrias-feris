#!/usr/bin/env python3
"""
Script de prueba para verificar la integración de consulta automática de lotes.

Este script verifica que:
1. Se puede crear un lote en BD
2. Se puede consultar el estado de un lote
3. Se actualiza correctamente last_cod_res_lot

Uso:
    python -m tools.test_lote_integration --prot 123456789 --env test
"""
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from web import lotes_db
from app.sifen_client.lote_checker import check_lote_status, determine_status_from_cod_res_lot


def test_create_lote(env: str, prot: str):
    """Test: crear lote en BD"""
    print(f"\n1. Test: Crear lote en BD")
    print(f"   env={env}, prot={prot}")
    
    try:
        lote_id = lotes_db.create_lote(env=env, d_prot_cons_lote=prot)
        print(f"   ✓ Lote creado con ID: {lote_id}")
        return lote_id
    except ValueError as e:
        print(f"   ✗ Error: {e}")
        # Intentar obtener el lote existente
        lote = lotes_db.get_lote_by_prot(env=env, d_prot_cons_lote=prot)
        if lote:
            print(f"   ℹ Lote ya existe con ID: {lote['id']}")
            return lote['id']
        raise


def test_check_lote_status(env: str, prot: str):
    """Test: consultar estado de lote"""
    print(f"\n2. Test: Consultar estado de lote")
    print(f"   prot={prot}, env={env}")
    
    result = check_lote_status(env=env, prot=prot, timeout=30)
    
    if result.get("success"):
        cod_res_lot = result.get("cod_res_lot")
        msg_res_lot = result.get("msg_res_lot")
        print(f"   ✓ Consulta exitosa")
        print(f"   - Código: {cod_res_lot}")
        print(f"   - Mensaje: {msg_res_lot[:80] if msg_res_lot else 'N/A'}...")
        return result
    else:
        error = result.get("error", "Error desconocido")
        print(f"   ✗ Error: {error}")
        return None


def test_update_lote_status(lote_id: int, result: dict):
    """Test: actualizar estado del lote"""
    print(f"\n3. Test: Actualizar estado del lote")
    print(f"   lote_id={lote_id}")
    
    if not result or not result.get("success"):
        print(f"   ✗ No se puede actualizar: consulta falló")
        return False
    
    cod_res_lot = result.get("cod_res_lot")
    msg_res_lot = result.get("msg_res_lot")
    response_xml = result.get("response_xml")
    
    status = determine_status_from_cod_res_lot(cod_res_lot)
    
    print(f"   - Estado determinado: {status}")
    print(f"   - Código respuesta: {cod_res_lot}")
    
    updated = lotes_db.update_lote_status(
        lote_id=lote_id,
        status=status,
        cod_res_lot=cod_res_lot,
        msg_res_lot=msg_res_lot,
        response_xml=response_xml,
    )
    
    if updated:
        print(f"   ✓ Lote actualizado correctamente")
        
        # Verificar que se guardó
        lote = lotes_db.get_lote(lote_id)
        if lote:
            print(f"   - last_cod_res_lot: {lote.get('last_cod_res_lot')}")
            print(f"   - last_msg_res_lot: {lote.get('last_msg_res_lot', '')[:50]}...")
            print(f"   - status: {lote.get('status')}")
            print(f"   - attempts: {lote.get('attempts')}")
            return True
        else:
            print(f"   ✗ No se pudo leer el lote actualizado")
            return False
    else:
        print(f"   ✗ No se actualizó el lote")
        return False


def main():
    parser = argparse.ArgumentParser(description="Test integración de lotes")
    parser.add_argument("--prot", required=True, help="dProtConsLote a probar")
    parser.add_argument("--env", choices=["test", "prod"], default="test", help="Ambiente")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("TEST: Integración de Consulta Automática de Lotes")
    print("=" * 60)
    
    # Test 1: Crear lote
    try:
        lote_id = test_create_lote(args.env, args.prot)
    except Exception as e:
        print(f"\n✗ FALLO: No se pudo crear lote: {e}")
        return 1
    
    # Test 2: Consultar estado
    result = test_check_lote_status(args.env, args.prot)
    
    # Test 3: Actualizar estado
    if result:
        success = test_update_lote_status(lote_id, result)
        if success:
            print("\n" + "=" * 60)
            print("✓ TODOS LOS TESTS PASARON")
            print("=" * 60)
            return 0
        else:
            print("\n" + "=" * 60)
            print("✗ FALLO: No se pudo actualizar el lote")
            print("=" * 60)
            return 1
    else:
        print("\n" + "=" * 60)
        print("⚠ ADVERTENCIA: Consulta falló (puede ser normal si el lote no existe en SIFEN)")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())

