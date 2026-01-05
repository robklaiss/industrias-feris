.PHONY: help env-check send-de consulta-lote extract-lote mtls-mock-test mtls-mock-server mtls-mock-certs mtls-mock-test mtls-mock-server mtls-mock-certs

# Default target
help:
	@echo "SIFEN Task Runner - Comandos disponibles:"
	@echo ""
	@echo "  make env-check                    - Verifica configuración (venv, certificados, env vars)"
	@echo "  make send-de XML=... ENV=test     - Envía DE a SIFEN"
	@echo "  make consulta-lote PROT=... ENV=test - Consulta estado de lote"
	@echo "  make extract-lote IN=... OUT=...  - Extrae ZIP del SOAP y guarda XML"
	@echo ""
	@echo "  make mtls-mock-certs              - Genera certificados DEV para mock server"
	@echo "  make mtls-mock-server             - Levanta el mock server mTLS"
	@echo "  make mtls-mock-test               - Test automático completo (levanta server, prueba, baja)"
	@echo ""
	@echo "Ejemplos:"
	@echo "  make env-check"
	@echo "  make send-de XML=artifacts/sirecepde_rebuild.xml ENV=test"
	@echo "  make send-de XML=artifacts/sirecepde_rebuild.xml ENV=test DEBUG=1"
	@echo "  make consulta-lote PROT=47353168697315928 ENV=test"
	@echo "  make extract-lote IN=artifacts/soap_last_sent_lote.xml OUT=artifacts/lote_extracted.xml"
	@echo ""
	@echo "Variables:"
	@echo "  XML     - Path al archivo XML a enviar (requerido para send-de)"
	@echo "  PROT    - dProtConsLote (requerido para consulta-lote)"
	@echo "  ENV     - Ambiente SIFEN: test o prod (default: test)"
	@echo "  DEBUG   - Si está definido, activa SIFEN_DEBUG_SOAP=1"
	@echo "  IN      - Archivo SOAP de entrada (requerido para extract-lote)"
	@echo "  OUT     - Archivo XML de salida (requerido para extract-lote)"

# Verificar configuración del entorno
env-check:
	@echo "🔍 Verificando configuración del entorno..."
	@echo ""
	@echo "Python:"
	@which python || echo "  ⚠️  'python' no encontrado en PATH"
	@python --version 2>/dev/null || echo "  ⚠️  No se pudo obtener versión de Python"
	@if [ -n "$$VIRTUAL_ENV" ]; then \
		echo "  ✓ Virtualenv activo: $$VIRTUAL_ENV"; \
	else \
		echo "  ⚠️  No hay virtualenv activo (usando Python del sistema)"; \
	fi
	@echo ""
	@echo "Certificado:"
	@if [ -z "$$SIFEN_CERT_PATH" ]; then \
		echo "  ❌ SIFEN_CERT_PATH no está configurado"; \
	else \
		echo "  ✓ SIFEN_CERT_PATH=$$SIFEN_CERT_PATH"; \
		if [ -f "$$SIFEN_CERT_PATH" ]; then \
			echo "  ✓ Archivo existe"; \
		else \
			echo "  ❌ Archivo no existe: $$SIFEN_CERT_PATH"; \
		fi; \
	fi
	@echo ""
	@echo "Password:"
	@if [ -z "$$SIFEN_CERT_PASSWORD" ]; then \
		echo "  ⚠️  SIFEN_CERT_PASSWORD no está configurado (se pedirá interactivamente)"; \
	else \
		PASS_LEN=$$(echo -n "$$SIFEN_CERT_PASSWORD" | wc -c | tr -d ' '); \
		echo "  ✓ SIFEN_CERT_PASSWORD está configurado (longitud: $$PASS_LEN)"; \
	fi
	@echo ""
	@echo "Ambiente:"
	@if [ -z "$$SIFEN_ENV" ]; then \
		echo "  ⚠️  SIFEN_ENV no está configurado (default: test)"; \
	else \
		echo "  ✓ SIFEN_ENV=$$SIFEN_ENV"; \
	fi

# Enviar DE a SIFEN
send-de:
	@if [ -z "$(XML)" ]; then \
		echo "❌ Error: XML no especificado. Uso: make send-de XML=archivo.xml ENV=test"; \
		exit 1; \
	fi
	@if [ ! -f "$(XML)" ]; then \
		echo "❌ Error: Archivo XML no encontrado: $(XML)"; \
		exit 1; \
	fi
	@ENV=$${ENV:-test}; \
	export PYTHONUNBUFFERED=1; \
	if [ -n "$(DEBUG)" ]; then \
		export SIFEN_DEBUG_SOAP=1; \
	fi; \
	echo "📤 Enviando DE a SIFEN (ambiente: $$ENV)..."; \
	python -m tools.send_sirecepde --env $$ENV --xml "$(XML)"

# Consultar estado de lote
consulta-lote:
	@if [ -z "$(PROT)" ]; then \
		echo "❌ Error: PROT no especificado. Uso: make consulta-lote PROT=123456 ENV=test"; \
		exit 1; \
	fi
	@ENV=$${ENV:-test}; \
	export PYTHONUNBUFFERED=1; \
	echo "🔎 Consultando lote $(PROT) en ambiente $$ENV..."; \
	python -m tools.consulta_lote_de --env $$ENV --prot "$(PROT)"

# Extraer lote del SOAP
extract-lote:
	@if [ -z "$(IN)" ]; then \
		echo "❌ Error: IN no especificado. Uso: make extract-lote IN=soap.xml OUT=output.xml"; \
		exit 1; \
	fi
	@if [ -z "$(OUT)" ]; then \
		echo "❌ Error: OUT no especificado. Uso: make extract-lote IN=soap.xml OUT=output.xml"; \
		exit 1; \
	fi
	@if [ ! -f "$(IN)" ]; then \
		echo "❌ Error: Archivo de entrada no encontrado: $(IN)"; \
		exit 1; \
	fi
	@export PYTHONUNBUFFERED=1; \
	echo "📦 Extrayendo lote de $(IN) a $(OUT)..."; \
	python scripts/extract_lote_from_soap.py "$(IN)" "$(OUT)"

# Mock Server mTLS (dev-only)
mtls-mock-certs:
	@echo "🔐 Generando certificados DEV para mock server..."
	@tools/mtls_mock/generate_dev_certs.sh

mtls-mock-server:
	@echo "🚀 Levantando mock server mTLS..."
	@echo "   Servidor escuchará en https://127.0.0.1:9443"
	@echo "   Presione Ctrl+C para detener"
	@export PYTHONUNBUFFERED=1; \
	python tools/mtls_mock/mock_server.py

mtls-mock-test:
	@echo "🧪 Ejecutando test automático del mock server..."
	@export PYTHONUNBUFFERED=1; \
	python tools/mtls_mock/test_mtls_mock.py

