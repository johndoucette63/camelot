#!/usr/bin/env bash
# Deploy and validate the advisor app on HOLYGRAIL
# Syncs source from Mac, builds containers remotely, runs migration, smoke-tests
# Usage: bash scripts/deploy-advisor.sh
set -euo pipefail

REMOTE="holygrail"
REMOTE_USER="john"
REMOTE_HOST="192.168.10.129"
LOCAL_ADVISOR="$(cd "$(dirname "$0")/../advisor" && pwd)"
REMOTE_DIR="~/advisor"
# Curl backend from inside the frontend container (on the advisor bridge network)
REMOTE_CURL="cd $REMOTE_DIR && docker compose exec -T frontend curl -sf http://backend:8000"

echo "=== Deploying advisor to HOLYGRAIL ==="

echo ""
echo "--- Step 1: Sync advisor directory to HOLYGRAIL ---"
rsync -avz --delete \
    --exclude='node_modules/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='.pytest_cache/' \
    --exclude='dist/' \
    --exclude='.env' \
    "$LOCAL_ADVISOR/" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

echo ""
echo "--- Step 2: Build and start containers ---"
ssh "$REMOTE" "cd $REMOTE_DIR && docker compose build backend frontend scanner"
ssh "$REMOTE" "cd $REMOTE_DIR && docker compose up -d"

echo ""
echo "--- Step 3: Wait for backend to be ready ---"
for i in $(seq 1 15); do
    if ssh "$REMOTE" "$REMOTE_CURL/health" >/dev/null 2>&1; then
        echo "  Backend is ready."
        break
    fi
    echo "  Waiting for backend... (attempt $i/15)"
    sleep 1
done

echo ""
echo "--- Step 4: Run database migration ---"
ssh "$REMOTE" "cd $REMOTE_DIR && docker compose exec -T backend alembic upgrade head"

echo ""
echo "--- Step 5: Verify containers are running ---"
ssh "$REMOTE" "cd $REMOTE_DIR && docker compose ps"

echo ""
echo "--- Step 6: Smoke-test API endpoints ---"

echo ""
echo "  GET /health"
ssh "$REMOTE" "$REMOTE_CURL/health" | python3 -m json.tool

echo ""
echo "  GET /dashboard/summary"
ssh "$REMOTE" "$REMOTE_CURL/dashboard/summary" | python3 -m json.tool

echo ""
echo "  GET /services (first 2)"
ssh "$REMOTE" "$REMOTE_CURL/services" | python3 -c "import sys,json; [print(json.dumps(s,indent=2)) for s in json.load(sys.stdin)[:2]]"

echo ""
echo "  GET /containers (counts)"
ssh "$REMOTE" "$REMOTE_CURL/containers" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Running: {len(d[\"running\"])}, Stopped: {len(d[\"stopped\"])}, Socket error: {d[\"socket_error\"]}')"

echo ""
echo "  GET /services/1/history"
ssh "$REMOTE" "$REMOTE_CURL/services/1/history?hours=1" | python3 -m json.tool

echo ""
echo "=== Deployment complete ==="
echo "Dashboard: http://advisor.holygrail"
