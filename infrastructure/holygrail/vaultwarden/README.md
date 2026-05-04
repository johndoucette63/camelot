# Vaultwarden — HOLYGRAIL

Self-hosted, Bitwarden-compatible password vault. LAN-only at
`https://vault.holygrail`; reach it from outside the house via the existing VPN.

| Item | Value |
| --- | --- |
| Image | `vaultwarden/server` (pinned in `.env`) |
| URL | `https://vault.holygrail` (HTTP redirects to HTTPS) |
| Admin panel | `https://vault.holygrail/admin` |
| TLS | Self-signed cert with SAN `*.holygrail`, served by Traefik (see `../traefik/`) |
| Network | `holygrail-proxy` (Traefik) |
| Data | Docker volume `vaultwarden_data` on NVMe |
| Backups | `/var/backups/vaultwarden/` (NVMe), 7 daily / 4 weekly / 6 monthly |
| Clients | All official Bitwarden apps — set "Self-hosted" server URL to the URL above |

The browser will warn on first visit because the cert is self-signed. Click
**Advanced → Proceed to vault.holygrail** to accept it. To silence the warning
on every device, import `holygrail.crt` from HOLYGRAIL into the system trust
store — on macOS:

```bash
scp holygrail:/home/john/docker/traefik/certs/holygrail.crt /tmp/
sudo security add-trusted-cert -d -r trustRoot \
    -k /Library/Keychains/System.keychain /tmp/holygrail.crt
```

---

## First-time setup

1. **Generate the admin token** (Argon2 hash):

   ```bash
   docker run --rm -it vaultwarden/server /vaultwarden hash
   ```

   Paste the resulting `$argon2id$...` string into `ADMIN_TOKEN=` in `.env`.
   When the value contains `$`, double them (`$` → `$$`) so Compose doesn't
   try to interpolate.

2. **Add the DNS entry** on Pi-hole (192.168.10.150) — Local DNS Records:

   ```text
   vault.holygrail  ->  192.168.10.129
   ```

   Skip if `*.holygrail` is already wildcarded.

3. **Deploy from the Mac:**

   ```bash
   rsync -av --exclude='.env' infrastructure/holygrail/vaultwarden/ \
         holygrail:/home/john/docker/vaultwarden/
   ssh holygrail "cd /home/john/docker/vaultwarden && docker compose up -d"
   ```

   The first run fetches the image and seeds `/data` (DB + RSA keypair).

4. **Register your account.** Open `http://vault.holygrail`, click *Create
   account*, and register your one user. Then in `.env` set
   `SIGNUPS_ALLOWED=false` and `docker compose up -d` to lock down further
   self-registration. Future users go through the admin panel's invite flow.

5. **Install the backup cron** (see below).

6. **Smoke test.** Verify in this order:
   - `curl -fsS http://vault.holygrail/alive` → returns a timestamp.
   - Web vault loads, you can log in.
   - Browser extension / mobile app connects with server URL
     `http://vault.holygrail` and syncs.
   - `http://vault.holygrail/admin` accepts the token.

---

## Backups & snapshots

NVMe doesn't have ZFS, so snapshots are application-level: `backup.sh`
invokes vaultwarden's built-in `backup` subcommand (safe while the container
is live — it does an online SQLite snapshot via the linked-in libsqlite3),
then copies out the resulting DB plus attachments, sends, and the RSA key,
and tars + rotates them.

Install on HOLYGRAIL:

```bash
sudo install -m 0755 backup.sh /usr/local/sbin/vaultwarden-backup
sudo install -d -o root -g root -m 0750 /var/backups/vaultwarden
sudo tee /etc/cron.d/vaultwarden-backup > /dev/null <<'EOF'
30 3 * * *  root  /usr/local/sbin/vaultwarden-backup >> /var/log/vaultwarden-backup.log 2>&1
EOF
```

Daily at 03:30 local. Sunday backups are promoted to the weekly tier; the
1st-of-month backup is promoted to monthly. Retention matches the tank ZFS
policy (7 / 4 / 6).

**Once the `tank` ZFS pool is online** (specs/020-storage-evolution), add a
follow-up cron to mirror `/var/backups/vaultwarden/` onto `tank/archive/` so
the vault survives an NVMe loss:

```bash
# /etc/cron.d/vaultwarden-backup-mirror
45 3 * * *  root  rsync -a --delete /var/backups/vaultwarden/ /tank/archive/vaultwarden/
```

### Restore

```bash
# Pick a tarball
ls /var/backups/vaultwarden/{daily,weekly,monthly}

# Stop the container and restore /data wholesale
docker compose -f /home/john/docker/vaultwarden/docker-compose.yml stop
docker run --rm -v vaultwarden_data:/data -v /var/backups/vaultwarden:/b \
    alpine sh -c 'rm -rf /data/* && tar -xzf /b/daily/vaultwarden-XXXX.tar.gz -C /data'
docker compose -f /home/john/docker/vaultwarden/docker-compose.yml start
```

---

## Operations

```bash
# Logs
ssh holygrail "docker logs -f vaultwarden"

# Restart after .env edits
ssh holygrail "cd /home/john/docker/vaultwarden && docker compose up -d"

# Upgrade (bump VAULTWARDEN_IMAGE_TAG in .env first)
ssh holygrail "cd /home/john/docker/vaultwarden && docker compose pull && docker compose up -d"

# One-off backup outside cron
ssh holygrail "sudo /usr/local/sbin/vaultwarden-backup"
```

---

## Notes

- **Why no HTTPS?** Vaultwarden requires HTTPS for browser extensions to
  treat the origin as secure — *except* for `localhost` and IPs/hosts on the
  LAN that clients consider trusted. Bitwarden mobile and desktop apps are
  fine with plain HTTP. If browser-extension warnings ever bite, terminate
  TLS on Traefik with a self-signed or internal CA cert and switch `DOMAIN`
  to `https://`.
- **Admin panel stays on** by design (per setup decision). Anyone with the
  admin token can manage users — keep it long, keep it secret, keep it in
  the vault itself once you've registered.
- **Single user expected.** Set `SIGNUPS_ALLOWED=false` after registering.
  Add more users from `/admin` → *Users* → *Invite User*.
