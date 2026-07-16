SHELL := /bin/sh

PYTHON ?= python3
PIP := $(PYTHON) -m pip
RUFF := $(PYTHON) -m ruff
PYTEST := $(PYTHON) -m pytest
BANDIT := $(PYTHON) -m bandit
PRE_COMMIT := $(PYTHON) -m pre_commit
PIP_AUDIT := $(PYTHON) -m pip_audit

BANDIT_EXCLUDES := .git,.venv,venv,env,media,staticfiles,tests,core/tests.py,accounts/migrations,cms/migrations,core/migrations,landing/migrations

.PHONY: install install-dev run check format lint test test-cov security migrations-check precommit ci

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements.txt -r requirements-dev.txt

run:
	$(PYTHON) manage.py runserver 0.0.0.0:8000

check:
	$(PYTHON) manage.py check

format:
	$(RUFF) format .

lint:
	$(RUFF) check .
	$(RUFF) format --check .

test:
	$(PYTEST)

test-cov:
	$(PYTEST) --cov=. --cov-report=term-missing --cov-report=xml

security:
	$(BANDIT) -ll -r . -x $(BANDIT_EXCLUDES)
	$(PIP_AUDIT) -r requirements.txt
	-$(PIP_AUDIT) -r requirements-dev.txt
	detect-secrets scan --all-files --baseline .secrets.baseline

migrations-check:
	$(PYTHON) manage.py makemigrations --check --dry-run

precommit:
	$(PRE_COMMIT) run --all-files

ci:
	$(MAKE) check
	$(MAKE) migrations-check
	$(MAKE) lint
	$(MAKE) test-cov
	$(MAKE) security
