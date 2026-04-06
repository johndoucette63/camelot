# Network Advisor — Project Specification

## Project Overview

Build a **local-first, AI-powered home network advisor** that provides intelligent guidance, monitoring, and configuration assistance for a sophisticated home lab environment. The application runs as a web service (Docker container) on the HOLYGRAIL server and is accessible from any device on the local network — primarily a MacBook Pro.

---

## Host Environment: HOLYGRAIL

| Component | Detail |
|-----------|--------|
| Hostname | HOLYGRAIL |
| OS (current) | Windows 11 Pro — **migrating to Ubuntu Server 24.04 LTS** |
| CPU | AMD Ryzen 7 7800X3D (8c/16t, Zen 4 3D V-Cache) |
| RAM | 32 GB DDR5 |
| GPU | NVIDIA RTX 2070 Super (8 GB VRAM) |
| Storage | 1 TB NVMe SSD (~584 GB free) |
| NIC | Realtek 2.5GbE (primary, wired) |
| Network role | Headless basement server, static IP on home LAN |

HOLYGRAIL will run **Docker + Portainer** as its primary workload host. All application services should be containerized.

---

## Existing Home Network Context

The advisor must understand and account for the following pre-existing infrastructure:

### Compute
- **HOLYGRAIL** — primary server (this host)
- **Multiple Raspberry Pi devices** — lightweight edge nodes running various services
- **MacBook Pro** — primary daily driver and development machine (all-Mac transition)

### Storage
- **NAS devices** (multiple) — network-attached storage already on LAN

### Automation & IoT
- **Home Assistant** — running on a dedicated Pi, central hub for all automation
- **Apple HomeKit** — used in parallel with Home Assistant
- **Aqara ecosystem** — Zigbee/Thread devices, Aqara hub(s) as border routers
- **SmartWings motorized blinds** (18 units) — Thread-based, integrated via Home Assistant and HomeKit
- **Thread network** — multiple border routers (HomePods, Aqara hubs); fragmentation is a known recurring issue

### AI & Inference
- **Ollama** — to be deployed on HOLYGRAIL with GPU acceleration (RTX 2070 Super)
- **Local LLM API** — HOLYGRAIL will expose an OpenAI-compatible endpoint on the LAN

### Monitoring & Services (Pi-hosted, to be consolidated)
- Pi-hole / AdGuard Home (DNS-level ad blocking)
- MQTT broker (Mosquitto) for Home Assistant
- Various Docker containers across multiple Pis

---

## Application Goals

### Primary Purpose
A **conversational + dashboard advisor** that helps the owner:
1. Understand what is running on the network at any given time
2. Diagnose problems (Thread fragmentation, container failures, Pi overload, etc.)
3. Get actionable recommendations for configuration and optimization
4. Plan infrastructure changes (e.g., migrating Pi services to HOLYGRAIL Docker)
5. Ask natural language questions about the network and get grounded, accurate answers

### Secondary Goals
- Serve as a living knowledge base of the home network topology
- Track service health across all nodes (Pis, HOLYGRAIL, NAS)
- Provide AI-assisted troubleshooting using a local LLM (via Ollama on HOLYGRAIL)
- Surface alerts for anomalies (device offline, high CPU, Thread border router drop, etc.)

---

## Functional Requirements

### 1. Network Discovery & Inventory
- Scan the LAN and maintain a device inventory (hostname, IP, MAC, vendor, role)
- Identify Raspberry Pi devices, NAS units, smart home hubs, and HOLYGRAIL itself
- Allow manual annotation of devices (assign role, description, tags)
- Persist inventory to a local database

### 2. Service Registry
- Track known services and which host/container runs them
- Detect Docker containers via Docker socket or Portainer API
- Monitor service health (HTTP health checks, port probing)
- Display status dashboard: green/yellow/red per service

### 3. AI-Powered Advisor Chat
- Conversational interface backed by local LLM (Ollama on HOLYGRAIL)
- System prompt includes live network context: device list, service status, recent alerts
- Capable of answering questions like:
  - "Why is my Thread network fragmented?"
  - "Which Pi is most overloaded right now?"
  - "What services should I move from Pi to HOLYGRAIL?"
  - "Is my NAS reachable from all devices?"
- Response grounded in real-time network state, not just training data

### 4. Home Assistant Integration
- Connect to Home Assistant REST API or WebSocket API
- Display entity states relevant to the network (border router status, device connectivity)
- Surface Thread network topology if available via HA

### 5. Infrastructure Recommendations Engine
- Rule-based + LLM-assisted recommendations
- Examples:
  - "Pi-3 CPU is averaging 85% — consider migrating [service] to HOLYGRAIL"
  - "You have 3 Thread border routers but 2 are on the same VLAN — consider redistributing"
  - "Ollama is not running — local AI features are degraded"

### 6. Alerts & Notifications
- Configurable thresholds (CPU, memory, disk, ping latency)
- Alert log visible in dashboard
- Optional: push to Home Assistant as notifications

---

## Technical Architecture

### Stack
| Layer | Technology |
|-------|------------|
| Backend | Python (FastAPI) |
| Frontend | React + Tailwind CSS |
| Database | PostgreSQL (Docker container) |
| LLM | Ollama (local, GPU-accelerated) |
| Container mgmt | Docker + Portainer |
| Network scanning | nmap / python-nmap or similar |
| HA integration | `homeassistant` Python client or REST |
| Deployment | Docker Compose on HOLYGRAIL |

### Deployment
- All services run via `docker-compose` on HOLYGRAIL
- Accessible on local LAN at `http://holygrail:PORT` or a chosen hostname
- No cloud dependency — fully local and private
- Portainer used for container lifecycle management

### AI Integration
- Ollama runs as a separate Docker container with GPU passthrough (CUDA)
- Advisor backend calls Ollama via OpenAI-compatible API (`/v1/chat/completions`)
- Recommended default model: **Llama 3.1 8B** (RTX 2070 Super 8GB VRAM constraint)
- System prompt dynamically assembled from live network state at query time

---

## Non-Functional Requirements

- **Local-first**: No data leaves the home network. No cloud APIs required for core functionality.
- **Low friction**: Should be useful within 60 seconds of opening — no lengthy setup wizards.
- **Resilient**: If Ollama is down, dashboard and inventory still work; AI chat degrades gracefully.
- **Extensible**: Designed so new integrations (Proxmox, Grafana, additional Pi sensors) can be added without major refactoring.
- **Headless-friendly**: HOLYGRAIL has no monitor. All management via SSH and web UI.

---

## Out of Scope (v1)

- Cloud backup or remote access (Tailscale setup is separate)
- Mobile app (browser on iOS/macOS is sufficient)
- Multi-user authentication (single-owner household)

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM model | Llama 3.1 8B | RTX 2070 Super has 8GB VRAM; 32B models won't fit even at Q4 |
| PostgreSQL | Isolated per-project | Easy to consolidate later, painful to untangle |
| Docker socket | Mount directly | Simpler than Portainer API for local containers; Portainer API for remote |
| Network scanning | Scheduled + ARP watch | Scheduled for full inventory, ARP for real-time device arrivals |

---

*Spec-kit compatible. Part of the Camelot project.*
