# Future Improvements

These are intentionally not integrated yet.

## Docker

Useful when the team needs a fully reproducible local environment with the same system libraries required by WeasyPrint, Poppler, and related PDF tooling.

## PostgreSQL Local

Useful when local development needs to match production query planning, indexes, constraints, and JSON behavior more closely than SQLite can provide.

## Redis

Useful once there is a real need for shared caching, background job coordination, or task queues that outgrow the current synchronous execution model.

## Celery

Useful for sending emails, generating PDFs, rebuilding dossiers, or processing notifications asynchronously when those actions start affecting request latency.

## Playwright

Useful for end-to-end browser coverage of the landing page, login flow, role-based access, and PDF entry points once the UI is stable enough to justify browser automation.

## Locust

Useful when the project needs load testing around login, dashboards, PDF endpoints, or landing lead capture under realistic traffic.

## MkDocs

Useful when the documentation set grows enough that a versioned technical documentation site is more maintainable than standalone markdown files.

## Advanced Observability

Useful when logs, traces, error monitoring, and operational metrics need to be correlated across Django, Render, Sentry, and any future background workers.
