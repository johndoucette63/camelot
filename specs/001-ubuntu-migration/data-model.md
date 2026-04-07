# Data Model: Ubuntu Migration & Base Setup

**Branch**: `001-ubuntu-migration` | **Date**: 2026-04-06

> This feature is an infrastructure migration, not an application. Instead of database entities, this document describes the configuration entities — the discrete pieces of system state that must be set and verified.

## Configuration Entities

### Server Identity

| Attribute | Value | Persistence |
| --------- | ----- | ----------- |
| Hostname | `holygrail` | `/etc/hostname` + `/etc/hosts` |
| Static IP | `192.168.10.129/24` | Netplan config in `/etc/netplan/` |
| Gateway | `192.168.10.1` (assumed) | Netplan config |
| DNS Server | `192.168.10.150` (Pi-hole) | Netplan config |
| Timezone | Admin's local timezone | `timedatectl` |

### User Account

| Attribute | Value | Persistence |
| --------- | ----- | ----------- |
| Username | `john` | Created during install |
| Sudo access | Yes | `/etc/sudoers.d/` or `sudo` group membership |
| SSH key auth | Enabled (default) | `/etc/ssh/sshd_config` |
| SSH password auth | Enabled (default, harden later) | `/etc/ssh/sshd_config` |

### Security Configuration

| Component | State | Config Location |
| --------- | ----- | --------------- |
| Root SSH login | Disabled (`PermitRootLogin no`) | `/etc/ssh/sshd_config.d/hardening.conf` |
| Firewall (UFW) | Enabled, SSH-only inbound | UFW rules (`ufw status`) |
| Default inbound policy | Deny | UFW default |
| Default outbound policy | Allow | UFW default |

## Relationships

```text
Mac Workstation (192.168.10.145)
    │
    │ SSH (port 22)
    ▼
HOLYGRAIL (192.168.10.129)
    │
    │ DNS queries (port 53)
    ▼
NAS / Pi-hole (192.168.10.150)
```

## State Transitions

This feature has a linear, one-way migration flow:

```text
[Windows 11 Running] → [USB Boot] → [Ubuntu Installing] → [Ubuntu Installed (DHCP)]
    → [Post-Install Config Applied] → [Static IP + SSH + Firewall Active] → [Verified & Complete]
```

There is no rollback path once the Windows disk is wiped. The "Verified & Complete" state is confirmed by the verification script checking all acceptance criteria.
