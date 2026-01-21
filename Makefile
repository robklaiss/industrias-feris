.PHONY: bootstrap venv ssl-preflight smoke-ruc test-sifen send-de-test send-test send-prod send-test-cv send-prod-cv help

# Makefile para comandos útiles del proyecto

# Usar siempre .venv/bin/python
PYTHON := .venv/bin/python

bootstrap:
	@echo "=== Bootstrap Dev Environment ==="
	bash scripts/bootstrap_venv.sh

venv:
	@echo "=== Creating Virtual Environment ==="
	python3 -m venv .venv
	source .venv/bin/activate && pip install --upgrade pip
	source .venv/bin/activate && pip install -r requirements.txt
	@echo "Virtual environment ready in .venv/"

ssl-preflight:
	@echo "=== SSL Preflight Check ==="
	@if [ ! -f "$(PYTHON)" ]; then \
		echo "Error: Virtual environment not found. Run 'make venv' first"; \
		exit 1; \
	fi
	$(PYTHON) tools/ssl_preflight.py

smoke-ruc:
	@echo "=== Smoke Test: Consulta RUC ==="
	@if [ -z "$$SIFEN_RUC_CONS" ]; then \
		echo "ERROR: SIFEN_RUC_CONS no está configurado"; \
		echo "Uso: export SIFEN_RUC_CONS=\"45547378\" && make smoke-ruc"; \
		exit 1; \
	fi
	bash scripts/sifen_smoke_consulta_ruc.sh

test-sifen:
	@echo "=== Running SIFEN Tests ==="
	cd tesaka-cv && python3 -m pytest -q -k "sifen" -vv

send-de-test:
	@echo "=== Send DE Test ==="
	@echo "ERROR: Fixture pendiente para send-de-test"
	@echo "Por ahora, usar endpoint POST /api/facturas/{id}/enviar-sifen directamente"
	@exit 1

send-test:
	@echo "=== Send DE to Test Environment ==="
	@if [ ! -f "$(PYTHON)" ]; then \
		echo "Error: Virtual environment not found. Run 'make venv' first"; \
		exit 1; \
	fi
	$(PYTHON) -m tools.send_sirecepde --env test --xml latest --dump-http

send-prod:
	@echo "=== Send DE to Production Environment ==="
	@if [ ! -f "$(PYTHON)" ]; then \
		echo "Error: Virtual environment not found. Run 'make venv' first"; \
		exit 1; \
	fi
	@echo "WARNING: This will send to PRODUCTION!"
	@read -p "Are you sure? (y/N) " confirm && [ "$$confirm" = "y" ]
	$(PYTHON) -m tools.send_sirecepde --env prod --xml latest --dump-http

send-test-cv:
	@echo "=== Send DE to Test Environment (tesaka-cv) ==="
	@if [ ! -f "$(PYTHON)" ]; then \
		echo "Error: Virtual environment not found. Run 'make venv' first"; \
		exit 1; \
	fi
	cd tesaka-cv && ../scripts/run.sh -m tools.send_sirecepde --env test --xml latest --dump-http

send-prod-cv:
	@echo "=== Send DE to Production Environment (tesaka-cv) ==="
	@if [ ! -f "$(PYTHON)" ]; then \
		echo "Error: Virtual environment not found. Run 'make venv' first"; \
		exit 1; \
	fi
	@echo "WARNING: This will send to PRODUCTION!"
	@read -p "Are you sure? (y/N) " confirm && [ "$$confirm" = "y" ]
	cd tesaka-cv && ../scripts/run.sh -m tools.send_sirecepde --env prod --xml latest --dump-http

help:
	@echo "Comandos disponibles:"
	@echo "  make bootstrap      - Configura entorno (venv + deps + SSL preflight)"
	@echo "  make venv           - Crea virtual environment en .venv"
	@echo "  make ssl-preflight  - Ejecuta verificación SSL"
	@echo "  make smoke-ruc      - Ejecuta smoke test de consulta RUC (requiere SIFEN_RUC_CONS)"
	@echo "  make test-sifen     - Ejecuta suite de tests SIFEN"
	@echo "  make send-test      - Enviar DE a test environment"
	@echo "  make send-prod      - Enviar DE a producción (CONFIRMAR)"
	@echo "  make send-test-cv   - Enviar DE a test (desde tesaka-cv)"
	@echo "  make send-prod-cv   - Enviar DE a producción (desde tesaka-cv, CONFIRMAR)"
	@echo "  make send-de-test   - Enviar DE de prueba (pendiente fixture)"
	@echo ""
	@echo "Ejemplos:"
	@echo "  make bootstrap"
	@echo "  make ssl-preflight"
	@echo "  export SIFEN_RUC_CONS=\"45547378\" && make smoke-ruc"
	@echo "  make send-test"
	@echo "  make send-test-cv"
	@echo ""
	@echo "Para ejecutar comandos personalizados:"
	@echo "  ./scripts/run.sh <command> [args]"
	@echo "  ./scripts/run.sh --cwd <dir> <command> [args]"
