# Research: Ubuntu Migration & Base Setup

**Branch**: `001-ubuntu-migration` | **Date**: 2026-04-06

## Decision 1: Manual Install vs Autoinstall

**Decision**: Manual interactive install via Subiquity installer.

**Rationale**: Autoinstall (cloud-init) is designed for fleet provisioning — it requires creating a YAML config, serving it via HTTP or embedding in a custom ISO, and debugging when things go wrong. For a single server, this complexity has no payoff. The Subiquity installer completes in under 10 minutes interactively, and all choices are documented in the repo. YAGNI applies.

**Alternatives considered**: Autoinstall with cloud-init YAML — rejected because this is a one-time install on one machine with no reproducibility requirement.

## Decision 2: Netplan Static IP Configuration

**Decision**: Use Netplan 1.0 YAML with the `routes` block (not deprecated `gateway4`).

**Rationale**: Ubuntu 24.04 ships Netplan 1.0 which deprecated the `gateway4` key. The correct approach is a `routes` block with `to: default` and `via: <gateway>`. The config file created by the installer will be in `/etc/netplan/` — the post-install script will write or replace it with the static IP configuration. Interface name must be verified with `ip link` (Ryzen AM5 systems typically use `enp`-prefixed names).

**Alternatives considered**: NetworkManager CLI (`nmcli`) — rejected because Netplan is the default and preferred network configuration layer on Ubuntu Server.

## Decision 3: Firewall (UFW) Configuration

**Decision**: Use UFW with default-deny incoming, allow outgoing, and explicit SSH allow rule.

**Rationale**: UFW is pre-installed on Ubuntu Server 24.04. The commands are: `ufw default deny incoming`, `ufw default allow outgoing`, `ufw allow ssh`, `ufw enable`. Critical safety note: always run `ufw allow ssh` before `ufw enable` to avoid locking yourself out. Physical console access should remain available during initial setup as a recovery path.

**Alternatives considered**: iptables/nftables directly — rejected as unnecessarily complex for a simple SSH-only rule set. UFW wraps these cleanly.

## Decision 4: SSH Hardening Approach

**Decision**: Set `PermitRootLogin no` in `/etc/ssh/sshd_config.d/hardening.conf`. Leave password and key-based auth at defaults (both enabled).

**Rationale**: On a fresh Ubuntu Server 24.04 install with OpenSSH selected, the defaults are: `PermitRootLogin prohibit-password`, `PasswordAuthentication yes`, `PubkeyAuthentication yes`, and the root account is locked (no password set). Root SSH is effectively already disabled, but setting it explicitly to `no` makes the intent clear and guards against accidental root password creation. Using the `sshd_config.d/` drop-in directory keeps customizations separate from the default config, making future upgrades cleaner. Service name on Ubuntu 24.04 is `ssh` (not `sshd`).

**Alternatives considered**: Disabling password auth immediately (key-only) — rejected per clarification; hardening to key-only is deferred to a later phase to simplify initial setup.

## Decision 5: Boot Mode and Partitioning

**Decision**: UEFI boot mode. Let the Subiquity installer handle GPT partitioning and EFI System Partition creation automatically.

**Rationale**: AM5 motherboards (B650/X670) for Ryzen 7800X3D are UEFI-only; legacy BIOS/CSM is absent or disabled by default. The Ubuntu Server ISO supports UEFI and Secure Boot out of the box. The installer will create a GPT partition table with an EFI System Partition automatically. Manual partitioning is unnecessary — the default layout (single root partition + EFI + swap) is sufficient for a base OS install, and Docker will use overlay2 on the root filesystem.

**Alternatives considered**: Custom LVM/separate /home partition — rejected as premature. Docker volumes and bind mounts will handle data separation in later phases. Can be revisited if disk management becomes a concern.
