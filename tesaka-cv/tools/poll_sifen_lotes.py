#!/usr/bin/env python3
"""
Job de polling para consultar lotes SIFEN automáticamente

Este script consulta lotes en estado 'pending' o 'processing' y actualiza su estado
según la respuesta de SIFEN.

Uso:
    python -m tools.poll_sifen_lotes --env test
    python -m tools.poll_sifen_lotes --env test --max-attempts 10
    python -m tools.poll_sifen_lotes --env test --once  # Solo una ejecución, sin loop

Variables de entorno requeridas:
    SIFEN_CERT_PATH: Ruta al certificado P12
    SIFEN_CERT_PASSWORD: Contraseña del certificado P12
    SIFEN_ENV: Ambiente (test/prod) - puede ser overrideado con --env
"""
import sys
import argparse
import os
import time
import logging
from pathlib import Path

# Agregar el directorio padre al path para imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    from web.lotes_db import (
        get_lotes_pending_check,
        update_lote_status,
        LOTE_STATUS_PROCESSING,
        LOTE_STATUS_DONE,
        LOTE_STATUS_EXPIRED_WINDOW,
        LOTE_STATUS_REQUIRES_CDC,
        LOTE_STATUS_ERROR,
    )
    from app.sifen_client.lote_checker import (
        check_lote_status,
        determine_status_from_cod_res_lot,
    )
except ImportError as e:
    logger.error(f"Error al importar módulos: {e}")
    sys.exit(1)


def process_lote(lote: dict, env: str) -> bool:
    """
    Procesa un lote: lo consulta y actualiza su estado.

    Args:
        lote: Dict con datos del lote
        env: Ambiente ('test' o 'prod')

    Returns:
        True si se procesó correctamente, False si hubo error
    """
    lote_id = lote["id"]
    prot = lote["d_prot_cons_lote"]
    current_status = lote["status"]

    logger.info(f"Consultando lote ID={lote_id}, prot={prot}, status={current_status}")

    try:
        # Consultar estado del lote
        result = check_lote_status(
            env=env,
            prot=prot,
            timeout=30,
        )

        if not result.get("success"):
            error_msg = result.get("error", "Error desconocido")
            logger.error(f"Error al consultar lote {prot}: {error_msg}")
            update_lote_status(
                lote_id=lote_id,
                status=LOTE_STATUS_ERROR,
                msg_res_lot=error_msg,
            )
            return False

        # Extraer código y mensaje
        cod_res_lot = result.get("cod_res_lot")
        msg_res_lot = result.get("msg_res_lot")
        response_xml = result.get("response_xml")

        # Determinar nuevo estado basado en el código
        new_status = determine_status_from_cod_res_lot(cod_res_lot)

        # Actualizar lote
        update_lote_status(
            lote_id=lote_id,
            status=new_status,
            cod_res_lot=cod_res_lot,
            msg_res_lot=msg_res_lot,
            response_xml=response_xml,
        )

        logger.info(
            f"Lote {prot} actualizado: status={new_status}, "
            f"cod={cod_res_lot}, msg={msg_res_lot[:50] if msg_res_lot else None}"
        )

        # Si el estado es expired_window, también marcar como requires_cdc
        if new_status == LOTE_STATUS_EXPIRED_WINDOW:
            logger.warning(
                f"Lote {prot}: Ventana de 48h expirada. "
                "Requiere consulta por CDC individual."
            )

        return True

    except Exception as e:
        logger.error(f"Excepción al procesar lote {prot}: {e}", exc_info=True)
        update_lote_status(
            lote_id=lote_id,
            status=LOTE_STATUS_ERROR,
            msg_res_lot=f"Excepción: {str(e)}",
        )
        return False


def poll_lotes(
    env: str,
    max_attempts: Optional[int] = None,
    interval_seconds: int = 60,
    max_interval_seconds: int = 300,
    once: bool = False,
):
    """
    Ejecuta el polling de lotes.

    Args:
        env: Ambiente ('test' o 'prod')
        max_attempts: Máximo número de intentos por lote (opcional)
        interval_seconds: Intervalo inicial entre consultas (segundos)
        max_interval_seconds: Intervalo máximo (para backoff)
        once: Si True, ejecuta solo una vez sin loop
    """
    logger.info(f"Iniciando polling de lotes (env={env}, once={once})")

    # Verificar variables de entorno
    if not os.getenv("SIFEN_CERT_PATH") and not os.getenv("SIFEN_SIGN_P12_PATH"):
        logger.error(
            "Falta SIFEN_CERT_PATH o SIFEN_SIGN_P12_PATH. "
            "Configure las variables de entorno."
        )
        sys.exit(1)

    if not os.getenv("SIFEN_CERT_PASSWORD") and not os.getenv("SIFEN_SIGN_P12_PASSWORD"):
        logger.error(
            "Falta SIFEN_CERT_PASSWORD o SIFEN_SIGN_P12_PASSWORD. "
            "Configure las variables de entorno."
        )
        sys.exit(1)

    current_interval = interval_seconds
    iteration = 0

    while True:
        iteration += 1
        logger.info(f"--- Iteración {iteration} ---")

        # Obtener lotes pendientes
        lotes = get_lotes_pending_check(env=env, max_attempts=max_attempts)

        if not lotes:
            logger.info("No hay lotes pendientes de consulta")
            if once:
                break
            time.sleep(current_interval)
            continue

        logger.info(f"Encontrados {len(lotes)} lotes pendientes")

        # Procesar cada lote
        processed = 0
        for lote in lotes:
            if process_lote(lote, env):
                processed += 1

        logger.info(f"Procesados {processed}/{len(lotes)} lotes")

        if once:
            break

        # Esperar antes de la siguiente iteración
        # Aumentar intervalo gradualmente (backoff) hasta max_interval_seconds
        time.sleep(current_interval)
        current_interval = min(current_interval * 1.1, max_interval_seconds)


def main():
    parser = argparse.ArgumentParser(
        description="Polling automático de lotes SIFEN"
    )
    parser.add_argument(
        "--env",
        choices=["test", "prod"],
        default=os.getenv("SIFEN_ENV", "test"),
        help="Ambiente SIFEN (default: test o SIFEN_ENV)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=None,
        help="Máximo número de intentos por lote (default: sin límite)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Intervalo entre consultas en segundos (default: 60)",
    )
    parser.add_argument(
        "--max-interval",
        type=int,
        default=300,
        help="Intervalo máximo en segundos para backoff (default: 300)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Ejecutar solo una vez sin loop (útil para cron)",
    )

    args = parser.parse_args()

    try:
        poll_lotes(
            env=args.env,
            max_attempts=args.max_attempts,
            interval_seconds=args.interval,
            max_interval_seconds=args.max_interval,
            once=args.once,
        )
    except KeyboardInterrupt:
        logger.info("Polling interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error fatal en polling: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

