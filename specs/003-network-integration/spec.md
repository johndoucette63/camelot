# Feature Specification: Camelot Network Integration

**Feature Branch**: `003-network-integration`  
**Created**: 2026-04-07  
**Status**: Draft  
**Input**: User description: "Integrate HOLYGRAIL into Camelot management scripts, SSH config, and documentation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Add HOLYGRAIL to Management Scripts (Priority: P1)

As a Camelot admin, I need HOLYGRAIL included in the existing status and update management scripts, so that I can monitor and maintain it with the same tools I use for the Pis — including GPU temperature and container status in the output.

**Why this priority**: Without management script integration, HOLYGRAIL is a blind spot — the admin must SSH in manually to check its health. This is the core value of F1.3: unified management from the Mac.

**Independent Test**: Run the status script from the Mac targeting HOLYGRAIL and confirm it reports uptime, disk usage, Docker containers, GPU temperature, and available updates.

**Acceptance Scenarios**:

1. **Given** the status script is updated, **When** the admin runs it targeting HOLYGRAIL, **Then** output includes uptime, disk usage, CPU/memory, Docker container count and status, GPU temperature, and GPU memory usage.
2. **Given** the status script is updated, **When** the admin runs it targeting all devices, **Then** HOLYGRAIL appears alongside the Pis in the combined output.
3. **Given** the update script is updated, **When** the admin runs it targeting HOLYGRAIL, **Then** it performs OS package updates and Docker image updates with interactive confirmation.
4. **Given** HOLYGRAIL is offline, **When** the admin runs the status script targeting all devices, **Then** HOLYGRAIL is reported as unreachable without blocking status checks for other devices.

---

### User Story 2 - Harden SSH to Key-Only Authentication (Priority: P1)

As a Camelot admin, I need password authentication disabled on HOLYGRAIL's SSH server, so that only key-based authentication is accepted — completing the SSH hardening deferred from F1.1.

**Why this priority**: Co-equal with management scripts. SSH key auth is already working (set up during F1.1/F1.2), so disabling password auth is a low-risk security improvement that should be done before the server runs production services.

**Independent Test**: Attempt to SSH into HOLYGRAIL using a password (no key) and confirm the connection is rejected.

**Acceptance Scenarios**:

1. **Given** SSH key authentication is already working, **When** the admin disables password authentication on HOLYGRAIL, **Then** SSH connections using keys continue to work.
2. **Given** password authentication is disabled, **When** someone attempts to SSH with only a password (no key), **Then** the connection is rejected.
3. **Given** password authentication is disabled, **When** HOLYGRAIL is rebooted, **Then** the key-only SSH configuration persists.
4. **Given** the hardening script runs, **When** key-based authentication cannot be confirmed for the current session, **Then** the script aborts without making changes and prints a warning.

---

### User Story 3 - Update Infrastructure Documentation (Priority: P2)

As a Camelot admin, I need the infrastructure documentation updated to reflect HOLYGRAIL's live configuration, so that the docs accurately represent the current state of the network.

**Why this priority**: Documentation drift causes confusion and wastes time. Now that HOLYGRAIL is fully configured, the docs should reflect reality before more services are added.

**Independent Test**: Read the infrastructure documentation and verify every HOLYGRAIL detail (IP, OS, services, ports) matches what's actually running on the server.

**Acceptance Scenarios**:

1. **Given** HOLYGRAIL is fully configured, **When** the admin reads the infrastructure documentation, **Then** HOLYGRAIL's IP (192.168.10.129), OS (Ubuntu Server 24.04 LTS), and all deployed services with ports are accurately listed.
2. **Given** the documentation includes a network diagram, **When** the admin views it, **Then** HOLYGRAIL appears with its correct IP, role, and connections to other devices.
3. **Given** the documentation is updated, **When** compared against live system state, **Then** there are zero discrepancies for HOLYGRAIL.

---

### User Story 4 - Create HOLYGRAIL Setup Guide (Priority: P3)

As a Camelot admin, I need a comprehensive setup guide documenting everything done to configure HOLYGRAIL in Phase 1, so that the build is fully reproducible from a bare machine if needed.

**Why this priority**: Disaster recovery documentation. Lower priority because the server is already running, but valuable insurance against hardware failure or needing to rebuild.

**Independent Test**: A knowledgeable admin could follow the guide from a blank machine to a fully configured HOLYGRAIL matching the current state, without needing to reference any other documents.

**Acceptance Scenarios**:

1. **Given** a bare Ryzen 7800X3D machine, **When** an admin follows the setup guide step by step, **Then** the result is a fully configured HOLYGRAIL matching the current production state.
2. **Given** the setup guide is written, **When** the admin reviews every command in the guide, **Then** each command is copy-pasteable and produces the expected result.
3. **Given** the setup guide is complete, **When** it references hardware-specific settings (BIOS, boot order, interface names), **Then** those details are documented with the actual values used on this machine.

---

### Edge Cases

- What happens if HOLYGRAIL is unreachable when running the status script? The script must handle timeouts gracefully and continue checking other devices.
- What happens if the GPU driver is not loaded when the status script runs? The script should report "GPU: unavailable" rather than erroring out.
- What happens if Docker is stopped when the status script checks container status? The script should report "Docker: not running" gracefully.
- What happens if the admin accidentally disables SSH keys AND passwords? The setup guide should warn about this and note that physical console access is the recovery path.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The status management script MUST report HOLYGRAIL's uptime, disk usage, CPU load, memory usage, Docker container count and status, GPU temperature, and GPU memory usage.
- **FR-002**: The status script MUST handle HOLYGRAIL being unreachable with a timeout, reporting it as offline without blocking other device checks.
- **FR-003**: The update management script MUST support HOLYGRAIL for OS package updates and Docker image updates with interactive confirmation.
- **FR-004**: The status and update scripts MUST include HOLYGRAIL in the "all devices" target alongside the existing Pis.
- **FR-005**: SSH password authentication MUST be disabled on HOLYGRAIL, allowing only key-based authentication.
- **FR-006**: SSH key-only configuration MUST persist across reboots.
- **FR-007**: Infrastructure documentation MUST list HOLYGRAIL with its actual IP (192.168.10.129), OS (Ubuntu Server 24.04 LTS), and all deployed services with their ports.
- **FR-008**: The infrastructure documentation network diagram MUST include HOLYGRAIL with correct details.
- **FR-009**: A HOLYGRAIL setup guide MUST document the complete Phase 1 build process with copy-pasteable commands.
- **FR-010**: The setup guide MUST include hardware-specific details (BIOS settings, boot order, network interface name, GPU model).

### Key Entities

- **HOLYGRAIL**: The central server at 192.168.10.129 running Ubuntu Server 24.04 LTS, Docker 29.4.0, NVIDIA driver 570, Portainer CE.
- **Management Scripts**: `pi-status.sh` (remote health checker) and `pi-update.sh` (remote OS/Docker updater) in `scripts/`.
- **Infrastructure Documentation**: `docs/INFRASTRUCTURE.md` — the authoritative reference for network topology, device configs, and service inventory.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Running the status script from the Mac returns HOLYGRAIL health data (including GPU info) within 15 seconds.
- **SC-002**: Running the status script with HOLYGRAIL offline completes for all other devices without hanging.
- **SC-003**: SSH password-only login attempts to HOLYGRAIL are rejected 100% of the time after hardening.
- **SC-004**: Every HOLYGRAIL detail in the infrastructure documentation matches the live server state with zero discrepancies.
- **SC-005**: The setup guide contains all commands needed to reproduce the current HOLYGRAIL configuration from a bare machine.

## Assumptions

- F1.1 and F1.2 are complete — HOLYGRAIL is running Ubuntu Server 24.04 LTS with Docker, NVIDIA drivers, and Portainer.
- SSH key authentication from Mac to HOLYGRAIL is already working (configured during F1.1/F1.2).
- The `scripts/ssh-config` already has a `Host holygrail` entry at 192.168.10.129 (added in F1.1).
- The existing `pi-status.sh` and `pi-update.sh` scripts are structured to support adding new devices.
- HOLYGRAIL is an x86_64 server, not a Raspberry Pi — the management scripts may need adjustments for architecture-specific commands (e.g., GPU temp, no `vcgencmd`).
