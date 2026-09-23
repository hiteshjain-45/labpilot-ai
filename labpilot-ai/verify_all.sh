#!/usr/bin/env bash
# One-command verification of LabPilot AI.
#   ./verify_all.sh            backend tests + live integration verifier + frontend build + frontend tests
#   ./verify_all.sh backend    only the backend tests and the live integration verifier
#   ./verify_all.sh frontend   only the frontend build, the frontend tests (against a live scratch API) and the dev-proxy check
# Nothing here touches your demo database: every live check runs on a temporary scratch database.
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
PY="$ROOT/backend/.venv/bin/python"
[ -x "$PY" ] || PY="$(command -v python3)"
MODE="${1:-all}"
FAILED=0
step() { printf '\n\033[1m=== %s\033[0m\n' "$1"; }
run()  { "$@" || { FAILED=1; echo ">>> FAILED: $*"; }; }

if [ "$MODE" = all ] || [ "$MODE" = backend ]; then
  step "Backend unit and integration tests (pytest)"
  (cd "$ROOT/backend" && run "$PY" -m pytest)
  step "Live end-to-end verifier (real server, scratch database, SQL cross-checks)"
  (cd "$ROOT/backend" && run "$PY" scripts/verify_integration.py | grep -E "^(OK|FAIL|TOTAL| - |==)" )
  [ "${PIPESTATUS[0]}" = 0 ] || FAILED=1
fi

if [ "$MODE" = all ] || [ "$MODE" = frontend ]; then
  step "Frontend production build"
  (cd "$ROOT/frontend" && run npm run build --silent)

  step "Frontend tests against a live, freshly seeded scratch API"
  TMP="$(mktemp -d)"; PORT=8012
  export DATABASE_URL="sqlite:///$TMP/frontend-check.db" SECRET_KEY="frontend-check-secret-key-long-enough-for-hs256" AI_PROVIDER=mock
  (cd "$ROOT/backend" && run "$PY" -m app.seed --reset | grep Seeded)
  (cd "$ROOT/backend" && exec "$PY" -m uvicorn app.main:app --port $PORT --log-level warning) > "$TMP/api.log" 2>&1 &
  API_PID=$!
  for _ in $(seq 1 60); do curl -s "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 0.5; done
  (cd "$ROOT/frontend" && SMOKE_API_URL="http://127.0.0.1:$PORT" run npx vitest run 2>&1 | sed 's/\x1b\[[0-9;]*m//g' | grep -E "✓|✗|×|FAIL|Tests|Test Files|Error")
  [ "${PIPESTATUS[0]}" = 0 ] || FAILED=1

  step "Vite dev server proxies /api to the backend (the way you run it in VS Code)"
  (cd "$ROOT/frontend" && VITE_BACKEND_URL="http://127.0.0.1:$PORT" exec npx vite --port 5199 --strictPort) > "$TMP/vite.log" 2>&1 &
  VITE_PID=$!
  for _ in $(seq 1 40); do curl -s "http://127.0.0.1:5199/" >/dev/null && break; sleep 0.5; done
  H=$(curl -s "http://127.0.0.1:5199/api/health")
  L=$(curl -s -X POST "http://127.0.0.1:5199/api/auth/login" -H 'content-type: application/json' -d '{"email":"student@labpilot.demo","password":"Student@123"}')
  P=$(curl -s "http://127.0.0.1:5199/")
  echo "GET  /api/health via :5199   -> $H"
  echo "POST /api/auth/login via :5199 -> $(echo "$L" | head -c 80)..."
  echo "GET  /  via :5199            -> $(echo "$P" | grep -o '<title>[^<]*</title>')"
  echo "$H" | grep -q '"status":"ok"' || { FAILED=1; echo ">>> FAILED: proxy health"; }
  echo "$L" | grep -q access_token || { FAILED=1; echo ">>> FAILED: proxy login"; }
  echo "$P" | grep -q 'id="root"' || { FAILED=1; echo ">>> FAILED: index page"; }
  kill $VITE_PID $API_PID 2>/dev/null; wait $VITE_PID $API_PID 2>/dev/null
fi

echo
[ "$FAILED" = 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $FAILED
