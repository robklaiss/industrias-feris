---
name: sifen-docs-knowledge-base
description: A brief description, shown to the model to help it understand when to use this skill
---

# sifen-docs-knowledge-base (Skill)

## Cuándo usar esta skill
Usá esta skill **siempre** que el usuario pregunte sobre **SIFEN / e-Kuatia (SET Paraguay)** dentro de este repo: estructura del **DE**, campos del XML, validaciones, errores (ej. **0160**, “CDC no correspondiente”), firma, XSDs, ejemplos y procedimientos internos documentados.

## Fuente de verdad (paths)
Base principal:
- /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/docs/knowledge-base-sifen/SIFEN_knowledge_base.md

Documentos adicionales (si existen y aportan):
- /Users/robinklaiss/Dev/industrias-feris-facturacion-electronica-simplificado/docs/knowledge-base-sifen/KB_SIFEN.md

## Reglas de uso
1) **Primero buscar** en los .md de esta carpeta antes de inventar o suponer.
2) Al responder, **citar el encabezado/sección** (H1/H2/H3) de donde se sacó la info.
3) Si hay conflicto entre documentos, **priorizar `SIFEN_knowledge_base.md`** y mencionar la discrepancia.
4) Si la respuesta no está en la KB, decir explícitamente: **“No está documentado en la KB”** y sugerir qué sección conviene agregar.
5) Mantener respuestas **prácticas**: pasos concretos, ejemplos de campos, y checks de validación (CDC/firma/XSD) cuando aplique.
6) No modificar archivos fuera de `docs/knowledge-base-sifen/` a menos que el usuario lo pida.

## Output esperado
- Respuestas en español (LATAM), directas y accionables.
- Cuando aplique: checklist de verificación + fragmentos de ejemplo (cortos).
- Si se pide un “aprendizaje/anti-regresión”, proponer texto listo para pegar en el .md correspondiente.