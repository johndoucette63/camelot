# Quickstart: Network Advisor Application Scaffold

**Feature**: 007-advisor-app-scaffold
**Date**: 2026-04-08

## Prerequisites

- HOLYGRAIL accessible via SSH (`ssh john@holygrail`)
- Docker Engine and Docker Compose v2 installed on HOLYGRAIL
- `holygrail-proxy` Docker network exists (`docker network create holygrail-proxy`)
- Mac `/etc/hosts` includes `advisor.holygrail` → `192.168.10.129` (run `sudo bash scripts/setup-holygrail-dns.sh` or add manually)

## Deploy

```bash
# 1. Copy the advisor directory to HOLYGRAIL (from Mac)
scp -r advisor/ john@holygrail:~/advisor/

# 2. SSH into HOLYGRAIL
ssh john@holygrail

# 3. Create .env from template
cd ~/advisor
cp .env.example .env
# Edit .env with actual database password

# 4. Start the stack
docker compose up -d

# 5. Verify health
curl http://advisor.holygrail/api/health
# Expected: {"status":"ok","database":"connected"}
```

## Local Development (Frontend)

```bash
# From Mac workstation
cd advisor/frontend
npm install
npm run dev
# Vite dev server starts at http://localhost:5173
# API requests proxy to backend on HOLYGRAIL
```

## Local Development (Backend)

```bash
# From Mac workstation (requires Python 3.12+ and running PostgreSQL)
cd advisor/backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Verify

| Check | Command | Expected |
| ----- | ------- | -------- |
| Stack running | `docker compose ps` | 3 services: backend, frontend, postgres (all "Up") |
| Health endpoint | `curl http://advisor.holygrail/api/health` | `{"status":"ok","database":"connected"}` |
| Frontend loads | Browse `http://advisor.holygrail` | Styled landing page renders |
| Data persists | `docker compose down && docker compose up -d` | Seed devices still in database |
| Seed data | `docker compose exec postgres psql -U john -d advisor -c "SELECT hostname FROM devices;"` | 5 rows: HOLYGRAIL, Torrentbox, NAS, Pi-hole DNS, Mac Workstation |

## Environment Variables

| Variable | Description | Default |
| -------- | ----------- | ------- |
| `POSTGRES_DB` | Database name | `advisor` |
| `POSTGRES_USER` | Database user | `john` |
| `POSTGRES_PASSWORD` | Database password | *(required, no default)* |
| `DATABASE_URL` | Full connection string for backend | `postgresql+asyncpg://john:{password}@postgres:5432/advisor` |
| `OLLAMA_URL` | Ollama LLM endpoint | `http://ollama.holygrail` |
| `TZ` | Timezone | `America/Denver` |
