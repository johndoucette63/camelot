#!/bin/sh
# Backend entrypoint — normalizes SSH keys mounted from the host.
#
# The vpn_leak rule needs to invoke `ssh torrentbox ...` to probe Deluge's
# external IP and (on escalation) to stop the deluge container. We mount
# /etc/ssh-keys read-only from the host. OpenSSH refuses to use key files
# whose owner UID doesn't match the running process, so we copy the key into
# /root/.ssh with correct ownership and perms before exec'ing the real CMD.
#
# Idempotent — safe across container restarts.

set -eu

if [ -d /etc/ssh-keys ]; then
    mkdir -p /root/.ssh
    chmod 700 /root/.ssh

    if [ -f /etc/ssh-keys/id_ed25519 ]; then
        cp -L /etc/ssh-keys/id_ed25519 /root/.ssh/id_ed25519
        chmod 600 /root/.ssh/id_ed25519
    fi

    if [ -f /etc/ssh-keys/known_hosts ]; then
        cp -L /etc/ssh-keys/known_hosts /root/.ssh/known_hosts
        chmod 600 /root/.ssh/known_hosts
    fi

    # SSH config alias for the watchdog target. Hardcoded — we own this image
    # and the target is fixed by the network topology (Torrentbox at .141).
    cat > /root/.ssh/config <<'EOF'
Host torrentbox
    HostName 192.168.10.141
    User john
    IdentityFile /root/.ssh/id_ed25519
    StrictHostKeyChecking accept-new
    UserKnownHostsFile /root/.ssh/known_hosts
EOF
    chmod 600 /root/.ssh/config
fi

exec "$@"
