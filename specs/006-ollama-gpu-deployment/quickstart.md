# Quickstart: Ollama LLM Deployment with GPU Acceleration

**Feature Branch**: `006-ollama-gpu-deployment`  
**Date**: 2026-04-08

## Prerequisites

- HOLYGRAIL running Ubuntu 24.04 LTS with Docker Engine + Docker Compose v2
- NVIDIA driver (570+) and nvidia-container-toolkit installed (Phase 1)
- `holygrail-proxy` Docker network exists (created in F2.2)
- Traefik running on HOLYGRAIL (deployed in F2.2)
- SSH access: `ssh john@holygrail`

## Deployment

### Step 1: Deploy Ollama

```bash
# Copy compose and configs to HOLYGRAIL
scp -r infrastructure/holygrail/ollama/ john@holygrail:~/docker/ollama/

# Create .env from example
ssh john@holygrail "cp ~/docker/ollama/.env.example ~/docker/ollama/.env"

# Start Ollama
ssh john@holygrail "cd ~/docker/ollama && docker compose up -d"
```

Verify: `ssh john@holygrail "curl -s http://localhost:11434/"` should return "Ollama is running".

### Step 2: Pull Default Model

```bash
ssh john@holygrail "docker exec ollama ollama pull llama3.1:8b"
```

This downloads ~4.5 GB. Wait for completion.

Verify: `ssh john@holygrail "docker exec ollama ollama list"` should show `llama3.1:8b`.

### Step 3: Open Firewall

```bash
ssh john@holygrail "sudo ufw allow from 192.168.10.0/24 to any port 11434 comment 'Ollama LLM API'"
```

### Step 4: Configure Mac DNS

Add `ollama.holygrail` to `/etc/hosts` (if not already there):

```bash
# Check if entry exists
grep -q "ollama.holygrail" /etc/hosts || sudo sh -c 'echo "192.168.10.129  ollama.holygrail" >> /etc/hosts'
```

### Step 5: Verify LAN Access

```bash
# Direct port
curl -s http://192.168.10.129:11434/v1/models | python3 -m json.tool

# Traefik hostname
curl -s http://ollama.holygrail/v1/models | python3 -m json.tool

# Test inference
curl -s http://ollama.holygrail/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.1:8b","messages":[{"role":"user","content":"Hello, what can you do?"}]}'
```

### Step 6: Run Benchmark

```bash
bash scripts/benchmark-ollama.sh
```

Records results to stdout. Copy key metrics to `docs/INFRASTRUCTURE.md`.

## Verification Checklist

- [ ] `curl http://ollama.holygrail/` returns "Ollama is running"
- [ ] `docker exec ollama ollama list` shows llama3.1:8b
- [ ] `nvidia-smi` shows VRAM usage during inference
- [ ] Chat completions request from Mac returns valid response
- [ ] Traefik dashboard shows `ollama@docker` route as healthy
- [ ] UFW shows port 11434 allowed from LAN

## Rollback

```bash
ssh john@holygrail "cd ~/docker/ollama && docker compose down"
ssh john@holygrail "sudo ufw delete allow from 192.168.10.0/24 to any port 11434"
```

Model data persists in the `ollama_data` volume until explicitly removed.

## Files Modified (Repository)

| Path | Change |
|------|--------|
| `infrastructure/holygrail/ollama/docker-compose.yml` | New — Ollama with GPU passthrough |
| `infrastructure/holygrail/ollama/.env.example` | New — operational config template |
| `scripts/benchmark-ollama.sh` | New — performance baseline script |
| `scripts/setup-holygrail-dns.sh` | Updated — add ollama.holygrail |
| `docs/INFRASTRUCTURE.md` | Updated — add Ollama service + benchmark results |
