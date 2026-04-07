# Data Model: Docker & GPU Infrastructure

**Branch**: `002-docker-gpu-infra` | **Date**: 2026-04-07

> This feature is infrastructure setup. Instead of database entities, this document describes the configuration entities and their relationships.

## Configuration Entities

### GPU Driver

| Attribute | Value | Persistence |
| --------- | ----- | ----------- |
| Driver package | `nvidia-driver-560-server` (or recommended version) | apt package, DKMS kernel module |
| GPU model | RTX 2070 Super | Hardware (PCIe) |
| Verification command | `nvidia-smi` | Binary in PATH |
| Desktop environment | None (headless) | Installer variant enforced |

### Docker Engine

| Attribute | Value | Persistence |
| --------- | ----- | ----------- |
| Source | Official Docker apt repo (`download.docker.com`) | `/etc/apt/sources.list.d/docker.list` |
| Packages | docker-ce, docker-ce-cli, containerd.io, docker-buildx-plugin, docker-compose-plugin | apt |
| User access | `john` in `docker` group | `/etc/group` |
| Service | Enabled on boot | systemd (`docker.service`) |
| Daemon config | nvidia runtime registered | `/etc/docker/daemon.json` |
| Port binding default | `127.0.0.1` (localhost only) | Convention enforced in Compose files |

### NVIDIA Container Toolkit

| Attribute | Value | Persistence |
| --------- | ----- | ----------- |
| Package | `nvidia-container-toolkit` | apt (NVIDIA repo) |
| Runtime mode | Opt-in per container (not default) | `/etc/docker/daemon.json` |
| Compose syntax | `deploy.resources.reservations.devices` | Per-service in compose files |
| Test command | `docker run --rm --runtime=nvidia --gpus all nvidia/cuda:12.x-base nvidia-smi` | N/A |

### Portainer CE

| Attribute | Value | Persistence |
| --------- | ----- | ----------- |
| Image | `portainer/portainer-ce:latest` | Docker image |
| HTTPS port | 9443 | Container port mapping |
| Certificate | Self-signed (default) | Internal to container |
| Data volume | `portainer_data` | Docker named volume |
| Socket mount | `/var/run/docker.sock` | Bind mount (read/write) |
| Restart policy | `always` | Container config |
| Firewall rule | UFW allow 9443/tcp from 192.168.10.0/24 | UFW rules |

## Relationships

```text
Mac Workstation (192.168.10.145)
    │
    │ HTTPS (port 9443)
    ▼
Portainer CE ──────► Docker Socket ──────► Docker Engine
                                               │
                                               │ nvidia runtime
                                               ▼
                                          NVIDIA Container Toolkit
                                               │
                                               │ /dev/nvidia*
                                               ▼
                                          NVIDIA Driver ──► RTX 2070 Super
```

## Installation Order (Dependencies)

```text
[NVIDIA Driver] ──► [Docker Engine] ──► [NVIDIA Container Toolkit] ──► [Portainer CE]
      │                    │                       │                         │
      │                    │                       │                         └─ Requires Docker
      │                    │                       └─ Requires Docker + NVIDIA driver
      │                    └─ Independent of GPU driver (can install in parallel)
      └─ Requires reboot after install
```

Note: NVIDIA driver and Docker Engine are independent — they can be installed in parallel. But NVIDIA Container Toolkit requires both, and Portainer requires Docker.
