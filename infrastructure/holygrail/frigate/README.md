# Frigate NVR stack (HOLYGRAIL)

GPU-accelerated local NVR for the Camelot home network. Deployed from this
repo to HOLYGRAIL via rsync + `docker compose`.

**Authoritative design**: see [`specs/017-frigate-nvr/`](../../../specs/017-frigate-nvr/)
— `spec.md` for requirements, `plan.md` for architecture, `research.md` for
decisions (Frigate image pin, YOLOv9-T TensorRT engine, go2rtc bundled, ext4
at `/mnt/frigate`, Mosquitto ACL split, etc.), `quickstart.md` for the deploy
runbook, `contracts/` for MQTT + HA automation contracts.

## What's in here

- `docker-compose.yml` — Frigate + Mosquitto services, pinned images, GPU
  runtime, restart policies, volume mounts, Traefik labels.
- `config/config.yml` — Frigate runtime config (go2rtc streams, detector,
  camera pipeline, retention, MQTT).
- `mosquitto/config/` — Broker config (two listeners, ACL, passwords seed).
- `.env.example` — Secrets contract. Copy to `.env` on HOLYGRAIL before first
  deploy; fill from the real credentials. `.env` is gitignored.

## One-command deploy

From the Mac (never `git pull` on HOLYGRAIL per Camelot deploy convention):

```bash
rsync -av --delete infrastructure/holygrail/frigate/ holygrail:/opt/frigate-stack/
ssh holygrail 'cd /opt/frigate-stack && docker compose pull && docker compose up -d'
```

See `specs/017-frigate-nvr/quickstart.md` for the full runbook including
drive preparation, doorbell setup, and HA re-pointing.
