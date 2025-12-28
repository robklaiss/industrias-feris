# Datos de Prueba SIFEN - Cómo Obtenerlos

## 📋 Resumen

Los datos de prueba oficiales para el ambiente de pruebas de SIFEN deben ser proporcionados por la **SET (Subsecretaría de Estado de Tributación)** cuando se habilita tu empresa en el ambiente de pruebas.

## 🔑 Variables Requeridas

Para el ambiente de pruebas necesitas:

1. **SIFEN_TEST_RUC**: RUC de prueba
2. **SIFEN_TEST_TIMBRADO**: Número de timbrado de prueba
3. **SIFEN_TEST_CSC**: Código de Seguridad del Contribuyente de prueba

## 📝 Valores de Ejemplo (Solo para Desarrollo)

Para desarrollo y smoke testing básico, puedes usar estos valores de ejemplo:

```env
SIFEN_TEST_RUC=80012345
SIFEN_TEST_TIMBRADO=12345678
SIFEN_TEST_CSC=
```

**⚠️ IMPORTANTE**: Estos valores son solo para generar XML válido localmente. NO permiten enviar documentos al ambiente de pruebas real.

## 🏛️ Cómo Obtener Valores Oficiales

### Paso 1: Contactar a la SET

- **Email**: consultas@set.gov.py
- **Portal**: https://ekuatia.set.gov.py
- **Teléfono**: Consultar en portal oficial

### Paso 2: Solicitar Habilitación en Ambiente de Pruebas

Debes solicitar:
- Habilitación de tu empresa en el ambiente de pruebas de SIFEN
- RUC de prueba asignado
- Número de timbrado de prueba
- CSC (Código de Seguridad del Contribuyente) de prueba

### Paso 3: Obtener Certificado Digital (Opcional para Pruebas)

Para envío real de documentos, también necesitarás:
- Certificado digital (.p12/.pfx) expedido por una PSC habilitada en Paraguay
- Password del certificado

## 📄 Fuentes de Información

### Documentación Oficial

1. **Guía de Pruebas del SIFEN**
   - Disponible en: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica
   - PDF: "Guía de Pruebas del SIFEN - Fase de Voluntariedad Abierta"

2. **Portal e-Kuatia**
   - URL: https://ekuatia.set.gov.py
   - Sección: Documentación Técnica
   - Contiene: Manuales técnicos, esquemas XSD, guías de integración

3. **Guía de Mejores Prácticas**
   - Documento: "Recomendaciones y mejores prácticas para SIFEN - Guía para el desarrollador" (Octubre 2024)
   - Disponible en: Portal e-Kuatia

### Información Adicional

- **Prevalidador SIFEN**: https://ekuatia.set.gov.py/prevalidador/
  - Herramienta web para validar XML antes de envío
  
- **Esquemas XSD**: http://ekuatia.set.gov.py/sifen/xsd
  - Esquemas oficiales para validación

## 🔧 Configuración en el Proyecto

### Archivo .env

1. Copiar `.env.example` a `.env`:
   ```bash
   cp .env.example .env
   ```

2. Editar `.env` y reemplazar valores de ejemplo con los oficiales:
   ```env
   SIFEN_TEST_RUC=TU_RUC_OFICIAL_AQUI
   SIFEN_TEST_TIMBRADO=TU_TIMBRADO_OFICIAL_AQUI
   SIFEN_TEST_CSC=TU_CSC_OFICIAL_AQUI
   ```

3. El sistema cargará estos valores automáticamente desde el `.env`

### Verificación

Puedes verificar que los valores se cargan correctamente ejecutando:

```python
from app.sifen_client.config import get_sifen_config

config = get_sifen_config(env='test')
print(f"RUC: {config.test_ruc}")
print(f"Timbrado: {config.test_timbrado}")
print(f"CSC: {config.test_csc}")
```

## ⚠️ Limitaciones sin Valores Oficiales

Sin valores oficiales de la SET, puedes:

✅ Generar XML válido según XSD  
✅ Validar XML localmente  
✅ Usar el Prevalidador web para validar XML  
✅ Ejecutar smoke tests básicos  

❌ NO puedes:
- Enviar documentos reales al ambiente de pruebas
- Obtener respuestas del servidor SIFEN
- Validar integración completa end-to-end

## 📞 Contacto y Soporte

- **SET - Consultas**: consultas@set.gov.py
- **Portal e-Kuatia**: https://ekuatia.set.gov.py
- **Documentación Técnica**: https://www.dnit.gov.py/web/e-kuatia/documentacion-tecnica

---

**Última actualización**: Basado en Guía de Mejores Prácticas SIFEN (Octubre 2024)

