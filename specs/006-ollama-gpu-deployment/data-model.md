# Data Model: Ollama LLM Deployment with GPU Acceleration

**Feature Branch**: `006-ollama-gpu-deployment`  
**Date**: 2026-04-08

## Overview

This feature is infrastructure-focused. There is no traditional application data model. The "data model" consists of the LLM server configuration, API contracts, and benchmark output format.

## Configuration Entities

### Ollama Server

| Property | Value | Notes |
|----------|-------|-------|
| Host binding | `0.0.0.0` | Listen on all interfaces for LAN access |
| API port | 11434 | Ollama default |
| GPU | RTX 2070 Super (8 GB VRAM) | Full GPU passthrough via NVIDIA runtime |
| Model storage | Docker volume (`ollama_data`) | Persists models across restarts |
| Restart policy | `unless-stopped` | Auto-recovery after reboot |

### Default Model

| Property | Value | Notes |
|----------|-------|-------|
| Model name | `llama3.1:8b` | Ollama model tag |
| Parameter count | ~8 billion | General-purpose LLM |
| Quantization | Q4_K_M (default) | ~4.5 GB VRAM footprint |
| VRAM budget | 8 GB max | RTX 2070 Super limit |
| Context window | 8192 tokens (default) | Expandable if VRAM allows |

### Traefik Route

| Hostname | Backend | Network | Discovery |
|----------|---------|---------|-----------|
| `ollama.holygrail` | ollama:11434 | Bridge (holygrail-proxy) | Docker labels |

### Docker Networks

Ollama joins the existing `holygrail-proxy` external network for Traefik routing. No additional internal network needed (single container, no inter-service communication).

## API Contract (OpenAI-Compatible)

### Chat Completions

```
POST /v1/chat/completions
Host: ollama.holygrail

{
  "model": "llama3.1:8b",
  "messages": [
    {"role": "user", "content": "..."}
  ]
}
```

Response: Standard OpenAI chat completions JSON format.

### Models Listing

```
GET /v1/models
Host: ollama.holygrail
```

Response: List of available models in OpenAI-compatible format.

### Health Check

```
GET /
Host: ollama.holygrail
```

Response: `200 OK` — "Ollama is running"

## Benchmark Output

| Metric | Unit | Source |
|--------|------|--------|
| Prompt eval rate | tokens/sec | `eval_count / eval_duration` from `/api/generate` response |
| Generation rate | tokens/sec | `eval_count / eval_duration` from generation phase |
| Response latency (short) | seconds | Wall-clock time for <50 word prompt |
| Response latency (medium) | seconds | Wall-clock time for ~200 word prompt |
| Response latency (advisor) | seconds | Wall-clock time for ~500 word prompt (simulating Network Advisor use case) |
| VRAM usage | MB | `nvidia-smi` during inference |
| Model size on disk | GB | Volume usage |

Results stored in `docs/INFRASTRUCTURE.md` under HOLYGRAIL's deployed services section.
