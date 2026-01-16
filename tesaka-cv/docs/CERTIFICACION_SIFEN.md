# Guía de Certificación SIFEN

## 📋 Requisitos Previos

### 1. **Documentación Requerida**
- [ ] Manual de Integración SIFEN (PDF)
- [ ] Esquemas XSD oficiales
- [ ] Certificado digital válido
- [ ] Credenciales de ambiente TEST y PROD

### 2. **Ambientes**
- **TEST**: `https://sifen-test.set.gov.py/`
- **PROD**: `https://sifen.set.gov.py/`

## 🏆 Proceso de Certificación

### Fase 1: Preparación y Validación Local

#### 1.1 Validación XSD
```bash
# Validar XML contra esquemas oficiales
.venv/bin/python tools/validate_sifen_xml.py --xml mi_factura.xml
```

**Validaciones requeridas:**
- ✅ Estructura XML según XSD v150
- ✅ Todos los campos obligatorios
- ✅ Formatos de fecha y número
- ✅ Códigos de catálogo válidos

#### 1.2 Prevalidador SIFEN
```bash
# Subir a: https://sifen.set.gov.py/prevalidador/
```

**Validaciones del Prevalidador:**
- ✅ CDC coincidente
- ✅ Firma válida
- ✅ XML bien formado
- ✅ Esquema válido

### Fase 2: Pruebas en Ambiente TEST

#### 2.1 Envío de Documentos
```bash
# Enviar a TEST
.venv/bin/python tools/send_sirecepde.py \
  --xml mi_factura.xml \
  --env test \
  --artifacts-dir artifacts/cert_test
```

#### 2.2 Consulta de RUC
```bash
# Probar servicio de consulta
.venv/bin/python tools/smoke_test_ruc.py --env test
```

#### 2.3 Pruebas de Contingencia
- Simular caída de servicios
- Probar reintentos automáticos
- Verificar modo offline

### Fase 3: Pruebas de Límites y Casos Especiales

#### 3.1 Límites Técnicos
- **Tamaño máximo XML**: 1MB
- **Máximo items**: 100 por documento
- **Lote máximo**: 500 documentos
- **Decimales**: Hasta 10 decimales

#### 3.2 Casos Especiales
- Caracteres especiales (ñ, á, é, í, ó, ú)
- Notas de crédito y débito
- Exportación y exportación simplificada
- Servicios y bienes

#### 3.3 Escenarios de Error
- RUC inválido
- Timbrado vencido
- Número duplicado
- Firma inválida

### Fase 4: Certificación en Producción

#### 4.1 Solicitud de Acceso
1. Completar formulario de SIFEN
2. Presentar documentación
3. Esperar aprobación

#### 4.2 Pruebas en PROD
```bash
# Enviar a producción (solo con aprobación)
.venv/bin/python tools/send_sirecepde.py \
  --xml mi_factura.xml \
  --env prod \
  --artifacts-dir artifacts/cert_prod
```

## 📊 Checklist de Certificación

### Validaciones Técnicas
- [ ] XML valida contra XSD
- [ ] CDC calculado correctamente
- [ ] Firma digital válida
- [ ] QR generado correctamente
- [ ] PDF representación impresa

### Servicios SIFEN
- [ ] Autenticación mTLS
- [ ] Envío de lote
- [ ] Consulta de estado
- [ ] Consulta de RUC
- [ ] Recepción de eventos

### Casos de Prueba
- [ ] Factura electrónica normal
- [ ] Nota de crédito
- [ ] Nota de débito
- [ ] Exportación
- [ ] Contingencia

## 🛠️ Herramientas de Certificación

### Scripts Disponibles
```bash
# Validación
tools/validate_sifen_xml.py
tools/debug_cdc.py
tools/sifen_inspect_signature.py

# Envío
tools/send_sirecepde.py
tools/smoke_test_ruc.py

# Generación
tools/generar_pdf_sifen.py
tools/adaptar_xml_ruc.py

# Certificación
tools/sifen_certificacion.py
```

### Flujo Automatizado
```bash
# Ejecutar todo el flujo
.venv/bin/python tools/sifen_certificacion.py --paso all --xml mi_factura.xml
```

## 📝 Documentación a Presentar

1. **Memoria Técnica**
   - Arquitectura del sistema
   - Flujo de procesamiento
   - Manejo de errores

2. **Manual de Operación**
   - Procedimientos de emisión
   - Manejo de contingencia
   - Soporte técnico

3. **Casos de Prueba**
   - XMLs de prueba
   - Respuestas SIFEN
   - Logs de auditoría

## ⚠️ Consideraciones Importantes

### Seguridad
- Usar siempre HTTPS
- Validar certificados SSL
- Proteger claves privadas
- Auditoría de accesos

### Performance
- Timeout de conexiones: 30 segundos
- Reintentos: 3 intentos
- Pool de conexiones: 10
- Cache de RUC: 24 horas

### Errores Comunes
- **0160**: XML mal formado
- **0301**: CDC no corresponde
- **0901**: Error de autenticación
- **0999**: Error genérico

## 🚀 Pasos para Empezar

1. **Preparar ambiente TEST**
   ```bash
   export SIFEN_CERT_PATH=/path/to/cert.p12
   export SIFEN_SIGN_P12_PASSWORD=password
   ```

2. **Ejecutar primer paso**
   ```bash
   .venv/bin/python tools/sifen_certificacion.py --paso 1 --xml test.xml
   ```

3. **Seguir la secuencia**
   ```bash
   .venv/bin/python tools/sifen_certificacion.py --listar
   ```

## 📞 Soporte

- **Email**: soporte@sifen.gov.py
- **Teléfono**: (521) 420 820
- **Web**: https://www.sifen.gov.py

---

*Última actualización: Enero 2026*
