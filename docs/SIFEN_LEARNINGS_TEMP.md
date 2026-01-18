## [2026-01-18] Error 0160 "XML Mal Formado" - XML idéntico a TIPS

**Síntoma:** SIFEN devuelve error 0160 "XML Mal Formado" pero el XML es idéntico al de TIPS.

**Contexto/archivo:** `tesaka-cv/tools/send_sirecepde.py`

**Causa real encontrada:** El XML generado es 100% idéntico al de TIPS (después de limpiar whitespace), pero SIFEN sigue devolviendo 0160.

**Fix aplicado:**
1. Removido XML declaration del lote.xml para match con TIPS
2. Mantenido namespace XMLDSig estándar en Signature (match con TIPS)
3. Preservado dDesTrib en gCamFuFD (match con TIPS)
4. Verificado que el XML es idéntico a TIPS byte por byte

**Comandos de verificación:**
```bash
# Extraer y comparar con TIPS
cd tesaka-cv/artifacts
python3 - <<'PY'
# Extract lote from SOAP
# (ver código completo arriba)
# Resultado: XMLs are IDENTICAL after cleaning!

# Verificar firma
xmlsec1 --verify --insecure --id-attr:Id DE lote_current.xml
# Verification status: OK
```

**Resultado esperado:** El XML debe ser idéntico al de TIPS y la firma debe verificar OK.

**Estado actual:** 
- XML idéntico a TIPS ✅
- Firma válida ✅
- SIFEN devuelve 0160 ❌

**Conclusiones:**
Si el XML es idéntico al de TIPS y la firma es válida, pero SIFEN devuelve 0160, las causas posibles son:
1. **Certificado diferente:** TIPS usa un certificado de producción válido
2. **Ambiente TEST:** SIFEN test podría tener validaciones adicionales
3. **RUC no habilitado:** El RUC 4554737 podría no estar habilitado para facturación electrónica en TEST
4. **Validación interna:** SIFEN podría tener validaciones no visibles en el XSD

**Recomendación:** Contactar a SIFEN soporte con el XML exacto que se está enviando (ya validado contra TIPS) para solicitar detalles específicos del error 0160.
