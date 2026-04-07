# Feature Specification: Docker & GPU Infrastructure

**Feature Branch**: `002-docker-gpu-infra`  
**Created**: 2026-04-07  
**Status**: Draft  
**Input**: User description: "Install Docker, NVIDIA drivers, CUDA, container toolkit, and Portainer on HOLYGRAIL"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install GPU Drivers for Hardware Acceleration (Priority: P1)

As a Camelot admin, I need the RTX 2070 Super GPU recognized and hardware-accelerated under Ubuntu on HOLYGRAIL, so that downstream workloads like media transcoding and LLM inference can use the GPU.

**Why this priority**: GPU acceleration is the primary reason HOLYGRAIL exists as the central server. Without working drivers, the GPU is unused hardware and all GPU-dependent features (Plex transcoding, Ollama inference) are blocked.

**Independent Test**: Can be fully tested by querying the GPU status from the command line and confirming the GPU model, driver version, and available memory are reported correctly.

**Acceptance Scenarios**:

1. **Given** HOLYGRAIL is running Ubuntu Server 24.04 LTS, **When** the admin installs the GPU driver, **Then** the system recognizes the RTX 2070 Super and reports the driver version and available GPU memory.
2. **Given** GPU drivers are installed, **When** the admin queries GPU status from the command line, **Then** the GPU model, driver version, temperature, and memory usage are displayed.
3. **Given** GPU drivers are installed, **When** the admin checks the system, **Then** no desktop environment or display server is running (headless operation preserved).
4. **Given** GPU drivers are installed, **When** HOLYGRAIL is rebooted, **Then** the GPU driver loads automatically and the GPU is recognized without manual intervention.

---

### User Story 2 - Install Container Runtime with Compose (Priority: P1)

As a Camelot admin, I need a container runtime with orchestration support installed on HOLYGRAIL, so that all services can run as isolated containers managed through declarative configuration files.

**Why this priority**: Co-equal with GPU drivers — the container runtime is the foundation for every service in the Camelot infrastructure. Without it, no services can be deployed. The constitution mandates all long-running services run as containers.

**Independent Test**: Can be fully tested by running a basic container image, verifying it starts and stops cleanly, and confirming the `john` user can manage containers without elevated privileges.

**Acceptance Scenarios**:

1. **Given** HOLYGRAIL is running Ubuntu, **When** the admin installs the container runtime, **Then** the runtime is available and running as a system service.
2. **Given** the container runtime is installed, **When** the admin runs a test container, **Then** the container starts, executes, and outputs a success message.
3. **Given** the runtime is installed, **When** the `john` user runs container commands, **Then** no elevated privileges are required.
4. **Given** the runtime is installed, **When** the admin uses the orchestration tool to define and start a multi-container stack, **Then** all containers in the stack start and communicate correctly.
5. **Given** the runtime is installed, **When** HOLYGRAIL is rebooted, **Then** the container runtime starts automatically and restarts previously running containers.

---

### User Story 3 - Enable GPU Access Inside Containers (Priority: P2)

As a Camelot admin, I need containers running on HOLYGRAIL to access the GPU for hardware-accelerated workloads, so that services like media transcoding and LLM inference can leverage the RTX 2070 Super from within their containers.

**Why this priority**: Bridges the gap between GPU drivers (US1) and the container runtime (US2). Without GPU passthrough, containers can't use the GPU, making the hardware acceleration useless for containerized services.

**Independent Test**: Can be fully tested by running a GPU-enabled test container that queries the GPU and reports its model and memory — confirming the GPU is visible and usable inside the container.

**Acceptance Scenarios**:

1. **Given** GPU drivers and the container runtime are installed, **When** the admin installs the GPU container integration, **Then** the runtime is configured to support GPU passthrough.
2. **Given** GPU container integration is configured, **When** the admin runs a GPU-enabled test container, **Then** the container sees the RTX 2070 Super and reports its model, driver version, and memory.
3. **Given** GPU passthrough is working, **When** a container requests all available GPUs, **Then** the full GPU is accessible inside the container.
4. **Given** GPU passthrough is configured, **When** HOLYGRAIL is rebooted, **Then** GPU access inside containers works without manual reconfiguration.

---

### User Story 4 - Deploy Container Management Web UI (Priority: P3)

As a Camelot admin, I need a web-based UI for managing containers on HOLYGRAIL, so that I can monitor, start, stop, and inspect containers from my Mac browser without needing SSH.

**Why this priority**: A convenience layer on top of the core infrastructure. Not blocking any downstream services, but significantly improves day-to-day management experience. All services can be managed via CLI if this is deferred.

**Independent Test**: Can be fully tested by opening the management UI in a browser from the Mac workstation, logging in, and verifying the list of running containers matches what the CLI reports.

**Acceptance Scenarios**:

1. **Given** the container runtime is installed, **When** the admin deploys the management UI as a container, **Then** the UI is accessible via HTTPS from the Mac workstation's browser.
2. **Given** the management UI is running, **When** the admin logs in and views the dashboard, **Then** all locally running containers are listed with their status.
3. **Given** the management UI is running, **When** the admin starts or stops a container through the UI, **Then** the action is reflected in both the UI and the CLI.
4. **Given** the management UI container is deployed, **When** HOLYGRAIL is rebooted, **Then** the management UI restarts automatically and is accessible again without manual intervention.

---

### Edge Cases

- What happens if the GPU driver installation fails due to a kernel mismatch? The admin should verify the kernel version is compatible and may need to install kernel headers first.
- What happens if the container runtime conflicts with a pre-installed package (e.g., a Snap-based version)? The admin must remove conflicting packages before installing the official version.
- What happens if the GPU container toolkit cannot detect the GPU? The admin should verify the base GPU driver is working first (via command-line GPU query) before troubleshooting container integration.
- What happens if the management UI port conflicts with another service? The admin should verify port availability or choose an alternative port during deployment.
- What happens if the firewall blocks access to the management UI from the Mac? The firewall must be updated to allow the management UI port from the LAN.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST have GPU drivers installed that recognize the RTX 2070 Super and report driver version, GPU model, temperature, and memory usage.
- **FR-002**: GPU drivers MUST load automatically on boot without manual intervention.
- **FR-003**: System MUST NOT have a desktop environment or display server installed (headless operation preserved).
- **FR-004**: System MUST have a container runtime installed and running as a system service, enabled on boot.
- **FR-005**: The `john` user MUST be able to manage containers without elevated privileges.
- **FR-006**: Container orchestration MUST be available for defining and running multi-container stacks from declarative configuration files.
- **FR-007**: System MUST have GPU container integration installed, enabling containers to access the RTX 2070 Super via GPU passthrough.
- **FR-008**: A GPU-enabled test container MUST be able to query and report the GPU model, driver version, and memory from inside the container.
- **FR-009**: A container management web UI MUST be deployed and accessible via HTTPS from the Mac workstation on the LAN.
- **FR-010**: The management UI MUST display all locally running containers and allow starting/stopping them.
- **FR-011**: The management UI container MUST restart automatically after a HOLYGRAIL reboot.
- **FR-012**: The host firewall MUST be updated to allow the management UI port from the LAN.

### Key Entities

- **HOLYGRAIL**: The central server (Ryzen 7800X3D / 32GB / RTX 2070S) running Ubuntu Server 24.04 LTS at 192.168.10.129. Target for all installations in this feature.
- **RTX 2070 Super**: The GPU that must be recognized by the OS, accessible to the container runtime, and available for hardware-accelerated workloads inside containers.
- **Container Management UI**: A web-based dashboard for managing containers, accessible from the Mac workstation's browser over HTTPS.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: GPU is recognized by the system and reports model, driver version, and memory within 60 seconds of boot.
- **SC-002**: Admin can run a test container that starts and completes successfully within 30 seconds of the first container runtime install.
- **SC-003**: The `john` user can manage containers without elevated privileges immediately after setup.
- **SC-004**: A GPU-enabled test container reports the correct GPU model and available memory from inside the container.
- **SC-005**: The container management UI is accessible from the Mac browser within 60 seconds of HOLYGRAIL boot.
- **SC-006**: All components (GPU driver, container runtime, GPU container integration, management UI) survive a reboot and function without manual intervention.
- **SC-007**: The admin can start and stop containers from the management UI and see the results reflected in the CLI.

## Assumptions

- F1.1 (Ubuntu migration) is complete — HOLYGRAIL is running Ubuntu Server 24.04 LTS at 192.168.10.129 with SSH access and UFW firewall configured.
- The RTX 2070 Super is physically installed and connected to a PCIe slot with adequate power.
- HOLYGRAIL has internet access for downloading packages (DNS via Pi-hole at 192.168.10.150 with 8.8.8.8 fallback).
- No desktop environment or X server is currently installed (minimal server install from F1.1).
- The container runtime will be installed from official upstream repositories, not from Ubuntu's default package sources or Snap.
- Specific service deployments (Plex, Ollama, monitoring) are out of scope — this feature only sets up the infrastructure they will run on.
- The management UI only needs to manage containers on HOLYGRAIL (single-host, no cluster/swarm).
