#!/usr/bin/env bash
set -euo pipefail

echo "== audit_kpis (solo discrepancias) =="
python manage.py audit_kpis --threshold 0.05 --only-mismatches

echo ""
echo "== audit_logica_economica (solo discrepancias) =="
python manage.py audit_logica_economica --only-mismatches --epsilon 1

echo ""
echo "== audit_integridad_datos (solo warnings) =="
python manage.py audit_integridad_datos --only-warnings

