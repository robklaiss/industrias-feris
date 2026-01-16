.PHONY: bootstrap smoke-ruc test-sifen send-de-test help

# Makefile para comandos únicos de cert-ready precheck

bootstrap:
	@echo "=== Bootstrap Dev Environment ==="
	bash scripts/bootstrap_dev.sh

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

help:
	@echo "Comandos disponibles:"
	@echo "  make bootstrap    - Configura entorno de desarrollo (venv + dependencias + prechecks)"
	@echo "  make smoke-ruc    - Ejecuta smoke test de consulta RUC (requiere SIFEN_RUC_CONS)"
	@echo "  make test-sifen   - Ejecuta suite de tests SIFEN"
	@echo "  make send-de-test - Enviar DE de prueba (pendiente fixture)"
	@echo ""
	@echo "Ejemplos:"
	@echo "  make bootstrap"
	@echo "  export SIFEN_RUC_CONS=\"45547378\" && make smoke-ruc"
	@echo "  make test-sifen"
