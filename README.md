# web-inversure

Plataforma Django 4.2 para gestión inmobiliaria, estudios de viabilidad, proyectos, clientes, inversores, comunicaciones y generación de PDF.

La arquitectura actual combina:

- `core` para la lógica principal de negocio, cálculos financieros y PDF.
- `landing` para la web pública, noticias y captación de leads.
- `accounts` para login, roles, permisos, sesiones y notificaciones.
- `cms` para modelos Wagtail y administración editorial.
- `config` para settings, URLs, middleware y despliegue.

## Requisitos

- Python 3.11.
- PostgreSQL en producción.
- SQLite en local por defecto.
- Gunicorn, WhiteNoise, Wagtail y WeasyPrint.
- Dependencias del sistema para PDF cuando se ejecute la ruta real de generación.

En Linux y macOS, el entorno de PDF suele necesitar paquetes como `libcairo`, `pango`, `gdk-pixbuf`, `poppler` y fuentes básicas. El `Dockerfile` ya documenta el conjunto mínimo usado en despliegue.

## Instalación Local

Crear y activar un entorno virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Instalar producción:

```bash
python -m pip install -r requirements.txt
```

Instalar desarrollo:

```bash
python -m pip install -r requirements.txt -r requirements-dev.txt
```

## Variables De Entorno

Parte de la configuración vive en `config/settings.py` y se documenta en [.env.example](./.env.example).

Variables clave:

- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DATABASE_URL`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `SENTRY_DSN`
- `SENSITIVE_DATA_KEY`
- `SENSITIVE_DATA_HMAC_KEY`
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_STORAGE_BUCKET_NAME`
- `AWS_S3_REGION_NAME`
- `AWS_S3_CUSTOM_DOMAIN`
- `EMAIL_BACKEND`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS`
- `EMAIL_USE_SSL`
- `DEFAULT_FROM_EMAIL`
- `LANDING_LEAD_NOTIFY_EMAILS`
- `VAPID_PUBLIC_KEY`
- `VAPID_PRIVATE_KEY`
- `VAPID_SUBJECT`
- `MAINTENANCE_MODE`
- `AUTO_ADMIN_NOTIFICATIONS`
- `PDF_MESSAGE_SANITIZE`
- `MAX_UPLOAD_MB`
- `MAX_UPLOAD_FILES`
- `INVERSOR_RETENCION_PCT`
- `INVERSOR_RETENCION_PCT_F`
- `INVERSOR_RETENCION_PCT_J`
- `CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL`
- `MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION`
- `WAGTAILADMIN_BASE_URL`
- `DJANGO_DEBUG_TOOLBAR`
- `DJANGO_DEV_APPS`

## Base De Datos

- Producción: PostgreSQL vía `DATABASE_URL`.
- Local: SQLite en `db.sqlite3` si no se define `DATABASE_URL`.

## Migraciones

Crear migraciones nuevas:

```bash
python manage.py makemigrations
```

Comprobar que no hay cambios pendientes:

```bash
python manage.py makemigrations --check --dry-run
```

Aplicarlas:

```bash
python manage.py migrate
```

No se deben editar migraciones existentes salvo necesidad muy justificada.

## Ejecución Local

```bash
python manage.py runserver
```

Rutas principales:

- `/` landing pública.
- `/app/` aplicación interna.
- `/app/login/` entrada de autenticación.
- `/cms/` administración Wagtail.
- `/documents/` documentos de Wagtail.
- `/healthz/` comprobación de salud.

## Tests

```bash
pytest
```

Con cobertura:

```bash
pytest --cov=. --cov-report=term-missing --cov-report=xml
```

## Calidad De Código

```bash
ruff check .
ruff format --check .
```

Formatear:

```bash
ruff format .
```

## Seguridad

```bash
bandit -r .
pip-audit
pre-commit run --all-files
```

Los datos sensibles se gestionan con `SENSITIVE_DATA_KEY` y `SENSITIVE_DATA_HMAC_KEY` en `core/security.py`. No deben añadirse secretos reales al repositorio.

## Pre-Commit

Instalación:

```bash
pre-commit install
```

Ejecución manual:

```bash
pre-commit run --all-files
```

## Flujo De Ramas

- Trabaja en ramas de funcionalidad.
- Abre pull requests contra `main`.
- No mezcles cambios de lógica con refactors masivos.
- Mantén las migraciones nuevas separadas y revisables.

## Despliegue En Render

El despliegue actual está orientado a Render con Docker.

Flujo general:

1. Render construye la imagen con `Dockerfile`.
2. Se instalan dependencias de producción.
3. Se ejecuta `collectstatic`.
4. Se aplican migraciones.
5. Gunicorn arranca `config.wsgi:application`.

Variables sensibles deben configurarse en Render, no en el repositorio.

## Resolución De Problemas

- Si falla `manage.py check`, revisa variables de entorno y `ALLOWED_HOSTS`.
- Si fallan los PDF, verifica librerías del sistema de WeasyPrint.
- Si `pytest` no encuentra la base de datos, comprueba `DATABASE_URL`.
- Si el login redirige a two-factor, revisa `django-otp` y `two_factor`.
- Si Wagtail genera enlaces incorrectos, revisa `WAGTAILADMIN_BASE_URL`.
