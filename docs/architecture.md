# Architecture

## Overview

This repository is a monolithic Django application split into a small set of domain-focused apps.

## Django Apps

### `accounts`

Responsibility:

- Login redirection and logout.
- User access model with roles and custom permissions.
- Session tracking and connection logs.
- Web push subscriptions and notification helpers.

Important detail:

- The project uses Django's built-in `User` model, not a custom user model.

### `core`

Responsibility:

- Internal application routes under `/app/`.
- Financial calculations and business rules.
- Estudio, proyecto, cliente, participacion, ingreso y gasto persistence.
- PDF generation and PDF-related helpers.
- Investor portal and document workflows.

### `landing`

Responsibility:

- Public homepage.
- Public news listing and news detail pages.
- Legal pages.
- Lead capture from the public site.

### `cms`

Responsibility:

- Wagtail page models used in the editorial backend.
- The Wagtail admin and documents endpoints exposed in the URL config.

### `config`

Responsibility:

- Global settings.
- Middleware registration.
- Root URL routing.
- WSGI and ASGI entrypoints.
- Security headers, cookies, storage, email and external service configuration.

## Request Flow

1. Requests enter `config.urls`.
2. Public URLs are served by `landing` or authentication routes.
3. Internal URLs under `/app/` are filtered by `accounts.middleware.RoleAccessMiddleware`.
4. Authenticated users are sent through two-factor verification before private access is granted.
5. Business views in `core` render HTML or build PDF documents as needed.

## Authentication

- Login is exposed through `/app/login/`, which redirects to the two-factor auth flow.
- Django OTP and `django-two-factor-auth` are enabled.
- `AdminSiteOTPRequired` protects the Django admin.

## Roles And Permissions

Roles are stored in `accounts.UserAccess`:

- `administracion`
- `direccion`
- `comercial`
- `marketing`
- `moderators`

The permission resolver in `accounts.utils` maps roles to capabilities such as:

- `can_simulador`
- `can_estudios`
- `can_proyectos`
- `can_clientes`
- `can_inversores`
- `can_usuarios`
- `can_cms`
- `can_facturas_preview`

Custom permissions override the role when `use_custom_perms` is enabled.

## Database

- PostgreSQL is used in production via `DATABASE_URL`.
- SQLite is the local default when `DATABASE_URL` is not set.
- Models use standard Django ORM relations and multiple historical migrations.

## PDF Generation

PDF output is centered in `core.views`:

- WeasyPrint renders HTML templates into PDF bytes.
- Some PDF flows use `pdf2image` and PyMuPDF for image previews or fallbacks.
- `pypdf` is used to merge cover pages and annexes.
- `PDF_MESSAGE_SANITIZE` can harden message HTML before rendering.

## Wagtail

- Wagtail is installed and configured.
- The project exposes Wagtail admin pages and document URLs.
- Public content pages in this repository are currently served by the `landing` app rather than Wagtail page serving.

## Static Files And Media

- Static files are served by WhiteNoise in production.
- Static assets live under app-level `static/` directories.
- User-uploaded and generated files go to `MEDIA_ROOT` locally or S3 when AWS storage settings are enabled.

## External Services

The code currently integrates with:

- Sentry for error reporting.
- AWS S3-compatible storage when AWS credentials are present.
- SMTP or console email backends.
- Web push subscriptions via VAPID keys.
- The Spanish Catastro service for property data and maps.

## Deployment

- Production deployment is oriented to Render.
- `Dockerfile` installs the system dependencies needed by the PDF stack.
- The container runs `collectstatic`, applies migrations, and starts Gunicorn.
- Environment variables control secrets, hosts, storage, email, Sentry, and PDF behavior.
