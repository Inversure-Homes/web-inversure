# Recuperación rápida (Render)

Este documento resume cómo volver atrás si un deploy rompe producción.

## Servicios detectados

- Producción (Docker): `Inversure home` (URL `web-inversure-1.onrender.com`)
- Servicio legacy (Python runtime, suspendido): `web-inversure` (URL `web-inversure.onrender.com`)

## Plan de rollback recomendado

1. **Revertir commit** en GitHub (o hacer un commit nuevo que deshaga cambios) y dejar que Render auto-deploye.
2. Si necesitas restauración inmediata:
   - En Render, abre el servicio `Inversure home` → pestaña Deploys.
   - Redeploy del último deploy “verde” (o redeploy de un commit anterior).
3. Si el problema es de configuración:
   - Verifica `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DATABASE_URL`, y credenciales AWS/Email.
   - Para aislar, puedes poner temporalmente `MAINTENANCE_MODE=1`.

## Señales típicas de fallo

- 502/503 tras deploy: suele ser `gunicorn` no arranca o error de import.
- 500 en rutas específicas: revisar logs de aplicación y migraciones.
- Fallos en PDF/imagenes: revisar dependencias del sistema (ej. `poppler-utils` para `pdf2image`).

