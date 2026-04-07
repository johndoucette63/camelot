# Research: Docker & GPU Infrastructure

**Branch**: `002-docker-gpu-infra` | **Date**: 2026-04-07

## Decision 1: NVIDIA Driver Installation Method

**Decision**: Use `ubuntu-drivers install` with the `-server` driver variant (e.g., `nvidia-driver-560-server`).

**Rationale**: The `-server` variant installs `nvidia-headless-560-server` which excludes X11 and desktop dependencies, preserving headless operation. `ubuntu-drivers` handles DKMS kernel module building and updates cleanly. Run `ubuntu-drivers devices` first to confirm the recommended driver version for the RTX 2070 Super (Turing architecture, expects 550 or 560 series).

**Alternatives considered**: NVIDIA `.run` installer — rejected because it bypasses apt, complicates kernel upgrades, and can break DKMS. NVIDIA PPA — unnecessary since Ubuntu's shipped drivers are sufficient for a Turing-era card.

## Decision 2: CUDA Toolkit on Host

**Decision**: Do NOT install CUDA toolkit on the host. Driver-only install.

**Rationale**: All CUDA workloads (Ollama, Plex NVENC) run inside containers. The NVIDIA Container Toolkit passes through `/dev/nvidia*` devices and driver libraries into containers; container images bundle their own CUDA runtime. Installing `cuda-toolkit` on the host wastes ~5GB and serves no purpose for a container-only workflow.

**Alternatives considered**: Full CUDA toolkit install — rejected per YAGNI. Only needed if compiling CUDA code directly on the host, which is not the use case.

## Decision 3: Docker Engine Installation Source

**Decision**: Install from the official Docker apt repository (`download.docker.com`). Remove any conflicting packages first (docker.io, podman-docker, containerd, runc).

**Rationale**: Ubuntu's `docker.io` Snap package and apt package are outdated and have known compatibility issues with nvidia-container-toolkit. The official repo provides Docker CE, CLI, containerd, buildx, and the Compose plugin as a single coordinated install. The `john` user is added to the `docker` group for rootless management.

**Alternatives considered**: Ubuntu's docker.io package — rejected for compatibility reasons. Snap — explicitly prohibited (constitution: simplicity, and the input spec requires official upstream repos).

## Decision 4: NVIDIA Runtime — Default vs Opt-In

**Decision**: NVIDIA runtime as opt-in per container/service, NOT the default runtime.

**Rationale**: Setting nvidia as the default runtime loads GPU libraries into every container, wasting memory and causing issues with containers that don't expect GPU devices. GPU-needing services (Plex, Ollama) will use the `deploy.resources.reservations.devices` Compose syntax to request GPU access. This is the standard Docker Compose approach for GPU workloads.

**Alternatives considered**: Set nvidia as default runtime — rejected because it adds unnecessary overhead to all containers and can cause compatibility issues.

## Decision 5: UFW and Docker Port Exposure

**Decision**: Bind container ports to `127.0.0.1` (localhost) by default. Expose Portainer's port 9443 via UFW rule restricted to the LAN subnet (192.168.10.0/24).

**Rationale**: Docker manipulates iptables directly, bypassing UFW. Publishing a port as `8080:80` exposes it to the entire network regardless of firewall rules. Binding to `127.0.0.1:8080:80` restricts access to local processes only. Portainer is the exception — it needs LAN access for browser management, so it gets a dedicated UFW rule. Future services will be accessed through Traefik (Phase 2), which will be the only other externally-exposed port.

**Alternatives considered**: `"iptables": false` in daemon.json — rejected because it breaks inter-container communication, DNS resolution, and outbound connectivity. `ufw-docker` utility — unnecessary complexity when localhost-binding + Traefik handles the same concern more cleanly.

## Decision 6: Portainer CE Deployment

**Decision**: Deploy as a standalone Docker container with `--restart=always`, HTTPS on port 9443, Docker socket mounted for local management.

**Rationale**: Portainer CE is the standard single-host container management UI. Port 9443 serves HTTPS with a self-signed certificate (acceptable for LAN). Port 8000 (Edge Agent) is not needed for single-host and will be omitted. Data persisted in a named Docker volume (`portainer_data`). `--restart=always` ensures it starts on boot even if manually stopped.

**Alternatives considered**: Portainer via Docker Compose — acceptable but a single `docker run` is simpler for a management tool that manages other Compose stacks. Yacht/Lazydocker — less mature, smaller community.
