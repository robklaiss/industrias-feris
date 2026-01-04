#!/usr/bin/env python3
"""
Script de debug para probar next_dnumdoc sin correr el servidor.

Uso:
    python -m tools.debug_next_numdoc --env test --timbrado 12345678 --est 001 --punexp 001 --tipode 1 --requested 5
"""
import sys
import argparse
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from web.db import get_conn, ensure_tables
from web.counters import next_dnumdoc


def main():
    parser = argparse.ArgumentParser(
        description="Prueba next_dnumdoc sin correr el servidor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python -m tools.debug_next_numdoc --env test --timbrado 12345678 --est 001 --punexp 001 --tipode 1 --requested 5
  python -m tools.debug_next_numdoc --env test --timbrado 12345678 --est 001 --punexp 001 --tipode 1
        """
    )
    parser.add_argument("--env", required=True, help="Ambiente (test/prod)")
    parser.add_argument("--timbrado", required=True, help="Número de timbrado (8 dígitos)")
    parser.add_argument("--est", required=True, help="Establecimiento (3 dígitos)")
    parser.add_argument("--punexp", required=True, help="Punto de expedición (3 dígitos)")
    parser.add_argument("--tipode", required=True, help="Tipo de documento (ej: 1)")
    parser.add_argument("--requested", type=int, help="Número solicitado (opcional)")
    parser.add_argument("--iterations", type=int, default=3, help="Número de iteraciones (default: 3)")
    
    args = parser.parse_args()
    
    # Validar argumentos
    if not args.timbrado.isdigit() or len(args.timbrado) != 8:
        print(f"❌ ERROR: timbrado debe ser 8 dígitos, recibido: {args.timbrado}")
        sys.exit(1)
    
    if not args.est.isdigit() or len(args.est) != 3:
        print(f"❌ ERROR: est debe ser 3 dígitos, recibido: {args.est}")
        sys.exit(1)
    
    if not args.punexp.isdigit() or len(args.punexp) != 3:
        print(f"❌ ERROR: punexp debe ser 3 dígitos, recibido: {args.punexp}")
        sys.exit(1)
    
    # Conectar a la BD
    conn = get_conn()
    ensure_tables(conn)
    
    try:
        print(f"🔢 Probando next_dnumdoc:")
        print(f"   env: {args.env}")
        print(f"   timbrado: {args.timbrado}")
        print(f"   est: {args.est}")
        print(f"   punexp: {args.punexp}")
        print(f"   tipode: {args.tipode}")
        print(f"   requested: {args.requested}")
        print(f"   iterations: {args.iterations}\n")
        
        # Llamar next_dnumdoc varias veces
        for i in range(args.iterations):
            # Solo pasar requested en la primera iteración
            requested = args.requested if i == 0 else None
            
            next_num = next_dnumdoc(
                conn,
                env=args.env,
                timbrado=args.timbrado,
                est=args.est,
                punexp=args.punexp,
                tipode=args.tipode,
                requested=requested,
            )
            
            print(f"   Iteración {i+1}: next = {next_num} (formateado: {next_num:07d})")
        
        print(f"\n✅ Prueba completada exitosamente")
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

