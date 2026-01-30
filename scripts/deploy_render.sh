#!/usr/bin/env bash
set -euo pipefail

if ! command -v render >/dev/null 2>&1; then
  echo "render CLI not found. Install it first: brew install render"
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install it or adjust the script to use another JSON parser."
  exit 1
fi

if [[ ! -t 0 ]]; then
  echo "This command needs a TTY. Run it from a normal terminal (not a non-interactive runner)."
  exit 1
fi

SERVICE_INPUT="${1:-web-inversure-1}"
MIGRATE_CMD="${2:-python manage.py migrate}"
HEALTH_URL="${HEALTH_URL:-}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree is dirty. Commit your changes before deploying."
  exit 1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "Pushing ${BRANCH}..."
git push origin "${BRANCH}"

COMMIT_SHA="$(git rev-parse HEAD)"

if [[ "${SERVICE_INPUT}" == srv-* ]]; then
  SERVICE_ID="${SERVICE_INPUT}"
else
  SERVICES_JSON="$(render services -o json)"
  SERVICE_ID="$(
    SERVICE_INPUT="${SERVICE_INPUT}" SERVICES_JSON="${SERVICES_JSON}" python3 - <<'PY'
import json, os, sys
name = os.environ.get("SERVICE_INPUT", "")
data = json.loads(os.environ["SERVICES_JSON"])
matches = [s["id"] for s in data if s.get("name") == name]
if len(matches) == 1:
  print(matches[0])
  sys.exit(0)
if len(matches) == 0:
  sys.stderr.write(f"No service found with name '{name}'. Use the service ID instead.\n")
else:
  sys.stderr.write(f"Multiple services found with name '{name}'. Use the service ID instead.\n")
sys.exit(1)
PY
  )"
fi

echo "Triggering deploy for ${SERVICE_INPUT} (${SERVICE_ID}) at commit ${COMMIT_SHA}..."
render deploys create "${SERVICE_ID}" --commit "${COMMIT_SHA}" --wait --confirm -o text

echo "Running migrations..."
render ssh "${SERVICE_INPUT}" -- ${MIGRATE_CMD}

if [[ -n "${HEALTH_URL}" ]]; then
  echo "Health check: ${HEALTH_URL}"
  curl -fsS "${HEALTH_URL}"
  echo
fi
