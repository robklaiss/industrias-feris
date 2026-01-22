import os
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(REPO_ROOT / ".venv" / "bin" / "python")
CLI = str(REPO_ROOT / "tools" / "consulta_lote_de.py")

TEST_POST_URL_RE = re.compile(
    r"\[SIFEN DEBUG\]\s*POST URL \(consulta_ruc\):\s*(https://sifen-test\.set\.gov\.py/\S+)",
    re.IGNORECASE,
)

def _run_cli_contaminated_env():
    # Ambiente "contaminado" a propósito: SIFEN_ENV=prod
    env = os.environ.copy()
    env["SIFEN_ENV"] = "prod"

    cmd = [
        PYTHON,
        CLI,
        "--env", "test",
        "--ruc", "4554737-8",
        "--dump-http",
        "--debug",
    ]

    cp = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    return cp.returncode, cp.stdout

def test_consulta_ruc_cli_env_override():
    rc, out = _run_cli_contaminated_env()

    # 1) El proceso no debe fallar
    assert rc == 0, f"CLI returned non-zero={rc}\n--- OUTPUT ---\n{out}\n--- END ---"

    # 2) Guardrail REAL: aunque SIFEN_ENV=prod en el shell,
    #    el CLI con --env test debe POSTear SIEMPRE al endpoint de TEST
    m = TEST_POST_URL_RE.search(out)
    assert m, (
        "No encontré evidencia del POST URL de TEST en el stdout.\n"
        "Se esperaba una línea tipo:\n"
        "[SIFEN DEBUG] POST URL (consulta_ruc): https://sifen-test.set.gov.py/...\n"
        f"--- OUTPUT ---\n{out}\n--- END ---"
    )

    # 3) Resultado: ideal 200/0502, pero aceptamos 400/0160 por intermitencia del ambiente TEST
    #    (siempre que el endpoint sea el de TEST, que ya verificamos arriba).
    if "HTTP Status: 200" in out and re.search(r"\bCódigo:\s*0502\b", out):
        return

    if "HTTP Status: 400" in out and re.search(r"\bCódigo:\s*0160\b", out):
        # Intermitencia conocida del test env: OK para este guardrail
        return

    assert False, (
        "Respuesta inesperada: no fue 200/0502 ni 400/0160.\n"
        f"--- OUTPUT ---\n{out}\n--- END ---"
    )
