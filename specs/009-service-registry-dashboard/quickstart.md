# Quickstart: Service Registry & Health Dashboard

**Branch**: `009-service-registry-dashboard`  
**Date**: 2026-04-09  
**Prerequisites**: Feature 4.1 (advisor app) deployed and running on HOLYGRAIL.

---

## Local Development Setup

### 1. Start services

```bash
cd advisor
docker compose up -d postgres
```

### 2. Run the database migration

```bash
docker compose run --rm backend alembic upgrade head
```

This runs migration `002_service_registry` which creates `service_definitions` and `health_check_results` tables and seeds the 12 known services.

### 3. Start the backend with Docker socket access

```bash
docker compose up -d backend
```

The backend service requires `/var/run/docker.sock` mounted (added in this feature). Verify the mount is present:

```bash
docker compose exec backend ls -la /var/run/docker.sock
```

### 4. Start the frontend dev server

```bash
cd advisor/frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. The Vite proxy forwards `/api` to `http://localhost:8000`.

---

## Verify Health Checks Are Running

After the backend starts, the health checker begins its first cycle within 5 seconds. Confirm:

```bash
# Watch backend logs for health check activity
docker compose logs -f backend | grep health_checker
```

Expected output (after first cycle):
```
{"event": "health_check_complete", "checked": 12, "duration_ms": 450}
```

### Check via API

```bash
# Summary
curl http://localhost:8000/dashboard/summary | python3 -m json.tool

# All services with latest status
curl http://localhost:8000/services | python3 -m json.tool

# Container inventory
curl http://localhost:8000/containers | python3 -m json.tool

# History for service ID 1 (Plex)
curl "http://localhost:8000/services/1/history?hours=1" | python3 -m json.tool
```

---

## Verify Dashboard in Browser

1. Open `http://localhost:5173` (or `http://advisor.holygrail` on HOLYGRAIL)
2. Navigate to the **Services** tab
3. Confirm:
   - Summary banner shows total and healthy count
   - Services are grouped by host (HOLYGRAIL, Torrentbox, NAS, Pi-hole DNS)
   - Each row shows name, port, status dot, and last check time
   - Clicking a row opens the detail modal with health history

---

## Simulating Failure States

### Test red status (bring a service down)

```bash
# Stop Plex temporarily
docker stop plex

# Wait 60 seconds, then check
curl http://localhost:8000/services | python3 -m json.tool | grep -A5 '"name": "Plex"'
# Expect: "status": "red"

# Restore
docker start plex
```

### Test yellow status (slow HTTP response)

Yellow status requires an HTTP service to respond in > 2000ms. This is difficult to simulate directly; use the integration test instead:

```bash
cd advisor/backend
pytest tests/test_health_checker.py::test_degraded_response -v
```

### Test Docker socket unavailability

```bash
# Temporarily rename the socket mount to simulate unavailability
# (or test via the unit test that mocks DockerException)
cd advisor/backend
pytest tests/test_containers_api.py::test_socket_error_returns_stale_data -v
```

---

## Running Tests

```bash
cd advisor/backend
pytest tests/ -v

cd advisor/frontend
npm run test
```

---

## Deployment to HOLYGRAIL

```bash
# On HOLYGRAIL (or from Mac via SSH)
cd ~/camelot/advisor
git pull
docker compose pull
docker compose up -d --build backend frontend
docker compose exec backend alembic upgrade head
```

The Docker socket is already accessible to containers running on HOLYGRAIL. The `docker.sock` volume mount in `docker-compose.yml` handles this automatically.
