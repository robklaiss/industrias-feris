#!/usr/bin/env bash
set -euo pipefail

RUN_ID="final_test_$(date +%Y%m%d_%H%M%S)"
XML="../artifacts/04554737-820260125_014406/siRecepDE.xml"

SIFEN_CERT_PATH="/Users/robinklaiss/.sifen/certs/_normalized/cert.pem" \
SIFEN_KEY_PATH="/Users/robinklaiss/.sifen/certs/_normalized/key.pem" \
SIFEN_CERT_PASSWORD="x" \
SIFEN_SIGN_P12_PATH="/Users/robinklaiss/.sifen/certs/F1T_65478.p12" \
SIFEN_SIGN_P12_PASSWORD="bH1%T7EP" \
SIFEN_DEBUG_SOAP=1 \
SIFEN_SKIP_RUC_GATE=1 \
../.venv/bin/python -m tools.send_sirecepde \
  --env test \
  --xml "$XML" \
  --run-id "$RUN_ID" \
  --dump-http
