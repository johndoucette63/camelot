# Feature Specification: Ubuntu Migration & Base Setup

**Feature Branch**: `001-ubuntu-migration`  
**Created**: 2026-04-06  
**Status**: Draft  
**Input**: User description: "Migrate HOLYGRAIL from Windows 11 to Ubuntu Server 24.04 LTS with core OS configuration"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Install Ubuntu Server Headless (Priority: P1)

As a Camelot admin, I need to perform a clean install of Ubuntu Server 24.04 LTS on HOLYGRAIL with OpenSSH enabled and minimal packages, so that the server is ready for headless remote management immediately after installation.

**Why this priority**: This is the core deliverable of the feature. HOLYGRAIL cannot serve any downstream infrastructure purpose until the OS is installed and remotely accessible.

**Independent Test**: Can be fully tested by booting HOLYGRAIL from the installer, completing the install, then verifying SSH connectivity from the Mac workstation over the LAN.

**Acceptance Scenarios**:

1. **Given** a bootable Ubuntu Server 24.04 LTS USB drive, **When** the admin boots HOLYGRAIL from USB and completes the minimal install, **Then** Ubuntu Server 24.04 LTS is running on HOLYGRAIL.
2. **Given** Ubuntu is installed, **When** the admin attempts to SSH into HOLYGRAIL from the Mac workstation, **Then** SSH connection succeeds using the `john` user account.
3. **Given** Ubuntu is installed with OpenSSH, **When** someone attempts to log in as root via SSH, **Then** the connection is denied.
4. **Given** Ubuntu is installed, **When** the admin checks the `john` user account, **Then** the account has sudo privileges.

---

### User Story 2 - Create Bootable Ubuntu Installer (Priority: P2)

As a Camelot admin, I need to create a verified bootable Ubuntu Server 24.04 LTS USB drive from my Mac, so that I have a reliable installation medium for HOLYGRAIL.

**Why this priority**: This is a prerequisite for installation but is a straightforward, low-risk step. It supports User Story 1 but is independently completable and verifiable.

**Independent Test**: Can be fully tested by downloading the ISO, verifying its checksum, writing it to USB, and confirming HOLYGRAIL boots from it to the Ubuntu installer screen.

**Acceptance Scenarios**:

1. **Given** the admin needs to install Ubuntu, **When** the Ubuntu Server 24.04 LTS ISO is downloaded to the Mac, **Then** the ISO file's SHA256 checksum matches the official published value.
2. **Given** a verified ISO, **When** the admin writes it to a USB drive, **Then** a bootable USB drive is created.
3. **Given** a bootable USB drive, **When** HOLYGRAIL is powered on with the USB inserted, **Then** the Ubuntu Server installer loads successfully.

---

### User Story 3 - Configure Hostname, Static IP, and Timezone (Priority: P2)

As a Camelot admin, I need HOLYGRAIL to have a stable hostname, static IP address, and correct timezone configured, so that all other devices on the network can reliably discover and communicate with it.

**Why this priority**: Network stability is essential for all downstream services, but this configuration can be applied after the base install is complete. It builds on the foundation from User Story 1.

**Independent Test**: Can be fully tested by verifying hostname resolution, pinging the static IP from other devices, confirming timezone output, and checking DNS resolution through Pi-hole.

**Acceptance Scenarios**:

1. **Given** Ubuntu is installed on HOLYGRAIL, **When** the admin configures the hostname, **Then** the system hostname is set to `holygrail` and persists across reboots.
2. **Given** Ubuntu is installed, **When** the admin configures the static IP 192.168.10.129, **Then** HOLYGRAIL consistently uses that address after reboots.
3. **Given** a static IP is configured, **When** another device on the LAN pings HOLYGRAIL's IP, **Then** the device responds reliably.
4. **Given** Ubuntu is installed, **When** the admin sets the timezone, **Then** the system clock reflects the correct local time.
5. **Given** network configuration is applied, **When** HOLYGRAIL performs DNS lookups, **Then** queries are resolved through Pi-hole at 192.168.10.150.
6. **Given** the firewall is enabled, **When** a device on the LAN attempts to connect to a non-SSH port on HOLYGRAIL, **Then** the connection is rejected.

---

### Edge Cases

- What happens if the USB drive fails to boot on HOLYGRAIL? The admin should verify BIOS/UEFI boot order settings and try an alternative USB port or drive.
- What happens if HOLYGRAIL's network interface is not detected during Ubuntu install? The admin may need to select a different driver or install with a wired Ethernet connection.
- What happens if the static IP conflicts with another device on the subnet? The admin should verify the chosen IP is not already in use (via ARP scan or DHCP lease table) before assigning it.
- What happens if the BIOS requires a specific boot mode (UEFI vs Legacy)? The installer USB must be created with the correct boot mode for HOLYGRAIL's firmware.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Admin MUST download the Ubuntu Server 24.04 LTS ISO and verify its SHA256 checksum against the official published hash.
- **FR-002**: Admin MUST create a bootable USB installation medium from the verified ISO.
- **FR-003**: System MUST be installed with Ubuntu Server 24.04 LTS using the minimal install option.
- **FR-004**: System MUST have OpenSSH server enabled and accessible on the LAN immediately after installation.
- **FR-005**: System MUST have root SSH login disabled.
- **FR-006**: System MUST have a user account named `john` with sudo privileges.
- **FR-007**: System MUST accept both SSH key-based and password authentication initially. Hardening to key-only is deferred to a later phase.
- **FR-008**: System MUST have a host firewall enabled, allowing inbound SSH traffic only. Additional ports will be opened in later phases as services are deployed.
- **FR-009**: System hostname MUST be set to `holygrail` and persist across reboots.
- **FR-010**: System MUST have the static IP address 192.168.10.129 assigned on the 192.168.10.0/24 subnet, persisting across reboots.
- **FR-011**: System timezone MUST be set to the admin's local timezone.
- **FR-012**: System DNS MUST be configured to resolve through Pi-hole at 192.168.10.150.

### Key Entities

- **HOLYGRAIL**: The target server hardware (Ryzen 7800X3D / 32GB / RTX 2070S) being migrated from Windows 11 to Ubuntu Server. Central server for the Camelot home infrastructure.
- **NAS**: The Raspberry Pi 4 at 192.168.10.105 running OpenMediaVault (SMB file shares).
- **Media Server / Pi-hole**: The Raspberry Pi 5 at 192.168.10.150 running Plex, Emby, and Pi-hole (DNS provider for the network).
- **Mac Workstation**: The MacBook Pro at 192.168.10.145 used to create the bootable USB and manage the migration remotely via SSH.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Admin can establish an SSH session to HOLYGRAIL from the Mac workstation within 5 minutes of the first post-install boot.
- **SC-002**: HOLYGRAIL responds to network requests at 192.168.10.129 consistently across 3 consecutive reboots.
- **SC-003**: DNS queries from HOLYGRAIL resolve correctly through Pi-hole (verifiable by checking DNS server in use).
- **SC-004**: The `john` user can execute privileged commands via sudo without issue.
- **SC-005**: Root login via SSH is rejected 100% of the time.
- **SC-006**: The hostname `holygrail` is correctly returned by the system after reboot.
- **SC-007**: Connections to non-SSH ports on HOLYGRAIL are rejected by the host firewall.

## Clarifications

### Session 2026-04-06

- Q: What specific static IP should HOLYGRAIL use on 192.168.10.0/24? → A: 192.168.10.129 (already reserved on the network)
- Q: SSH authentication method? → A: Key-based + password initially; harden to key-only in a later phase
- Q: Should a host firewall be configured as part of base setup? → A: Yes, enable firewall allowing SSH only; additional ports opened in later phases as services are added
- Q: Is a Windows backup needed before wiping? → A: No, nothing on the Windows installation needs to be preserved

## Assumptions

- HOLYGRAIL is physically accessible for USB boot and initial BIOS/UEFI configuration during the migration.
- HOLYGRAIL's Ethernet network interface is natively supported by the Ubuntu Server 24.04 LTS kernel (no additional drivers needed).
- The admin has physical access to a keyboard and monitor for HOLYGRAIL during the initial install (headless operation begins after first boot with SSH).
- The 192.168.10.0/24 subnet is a flat LAN with no VLANs or firewall rules blocking SSH traffic between devices.
- The RTX 2070S GPU drivers and CUDA setup are out of scope for this feature (covered in a later phase).
- Docker, Portainer, and all application services are out of scope (covered in subsequent Phase 1 features).
