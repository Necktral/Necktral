# Paquete de contexto para análisis ChatGPT (solo referencia, no para producción)

Este paquete está diseñado para que ChatGPT pueda analizar la arquitectura, dependencias y estado del proyecto Necktral ERP/CRM, y así sugerir nuevos módulos o mejoras. **No contiene secretos ni datos sensibles.**

> **IMPORTANTE:** Este paquete es solo para referencia de ChatGPT y no debe usarse en producción ni compartirse fuera del equipo autorizado.

## Contenido sugerido

1. **Árbol de carpetas y archivos**
   - Estructura generada con `tree -L 3` o similar.
2. **README y documentación clave**
   - `README.md` principal y docs de módulos relevantes.
3. **Archivos de configuración**
   - `compose.yaml`, `compose.prod.yaml`, `package.json`, `requirements/base.txt`, `.env.example` (sin secretos).
4. **Ejemplo de módulo backend y frontend**
   - Un módulo representativo de cada lado (ej: `modulos/facturacion/`, `frontend/src/pages/SyncOfflinePage.vue`).
5. **Convenciones y linters**
   - `mypy.ini`, `ruff.toml`, `eslint.config.js`.
6. **Estado de TODOs/issues**
   - Bloque de TODOs del README o archivo de issues.
7. **Tests de ejemplo**
   - Un test de backend y uno de frontend si existen.
8. **Notas de arquitectura**
   - Convención de rutas, estructura de permisos, patrones relevantes.

---

**Este paquete NO incluye datos sensibles ni secretos.**

Si necesitas ayuda para armar el zip o el texto estructurado, indícalo y se puede automatizar la recolección de estos archivos.
