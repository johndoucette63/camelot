# Data Model: Camelot Network Integration

**Branch**: `003-network-integration` | **Date**: 2026-04-07

> This feature modifies existing scripts and documentation. The "data model" describes the device definitions and script interfaces.

## Device Definitions

### pi-status.sh Device Array

| Device | Host | User | GPU Support |
| ------ | ---- | ---- | ----------- |
| HOLYGRAIL | 192.168.10.129 | john | Yes (nvidia-smi) |
| Torrentbox | 192.168.10.141 | john | No |
| NAS | 192.168.10.105 | pi | No |
| Media Server | 192.168.10.150 | pi | No |

### pi-update.sh Host Map

| Key | Name | Host | User |
| --- | ---- | ---- | ---- |
| holygrail | HOLYGRAIL | 192.168.10.129 | john |
| torrentbox | Torrentbox | 192.168.10.141 | john |
| nas | NAS | 192.168.10.105 | pi |
| mediaserver | Media Server | 192.168.10.150 | pi |

## Status Script Output Sections

Existing sections (all devices):
- `::UPTIME::` — System uptime
- `::HOSTNAME::` — Device hostname
- `::OS::` — OS version
- `::CPU_TEMP::` — CPU temperature
- `::MEMORY::` — RAM usage
- `::DISK::` — Disk usage
- `::DOCKER::` — Container status
- `::MOUNTS::` — SMB mounts
- `::UPDATES::` — Available package updates

New section (HOLYGRAIL only):
- `::GPU::` — GPU model, temperature, memory, utilization (via nvidia-smi)

## SSH Hardening Configuration

| Setting | Before (F1.1) | After (F1.3) |
| ------- | ------------- | ------------ |
| PermitRootLogin | no | no (unchanged) |
| PasswordAuthentication | yes (default) | no |
| PubkeyAuthentication | yes (default) | yes (unchanged) |
| Config file | `/etc/ssh/sshd_config.d/hardening.conf` | Same file, updated |
