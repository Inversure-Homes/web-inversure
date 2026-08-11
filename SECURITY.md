# Security Policy

## How To Report A Vulnerability

If you find a security issue, report it privately to the project maintainers or through the platform-specific private vulnerability channel if one is available.

Include:

- A short summary.
- Steps to reproduce.
- The affected URL, command, or module.
- Expected vs actual behavior.
- The impact and scope.

Do not open a public issue for a vulnerability until the fix is available.

## What Not To Include In Public Reports

Do not include:

- Real secrets, API keys, tokens, passwords, or session cookies.
- Customer or investor personal data.
- Database dumps.
- Full PDF exports that contain personal or financial information.
- Internal hostnames or private network details unless strictly needed for reproduction.

## Secrets And Environment Variables

- Store runtime configuration in environment variables.
- Keep `.env` local and out of version control.
- Use `.env.example` only as a template with fictitious values.
- Rotate secrets if they may have been exposed.
- Prefer separate keys for encryption and HMAC when the code expects them.

## Dependency Updates

Recommended routine:

1. Update pinned or ranged dependencies in `requirements.txt` and `requirements-dev.txt`.
2. Run `pip-audit` against the installed environment.
3. Run `pytest`, `ruff check .`, and `ruff format --check .`.
4. Run `pre-commit run --all-files`.
5. Review release notes for Django, Wagtail, WeasyPrint, and any security-sensitive dependency before upgrading.

If a vulnerable dependency cannot be upgraded immediately without breaking compatibility, document the issue and the mitigation instead of disabling the audit.
