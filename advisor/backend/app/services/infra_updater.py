"""Stack updater — SSH + `docker compose pull && up -d && image prune`.

Surfaces the existing manual upgrade workflow (per
`infrastructure/torrentbox/README.md` and the HOLYGRAIL compose dirs at
`/home/john/docker/{plex,ollama,monitoring,traefik}`) as buttons on the
Services page. Reuses the SSH key already mounted into the backend
container for the vpn_leak watchdog (see docker-compose.yml).

Design notes:
  - Excluded from the registry: `advisor` (self-update would kill the
    running process mid-request) and stacks not yet deployed to HOLYGRAIL
    (frigate, vaultwarden — repo has compose files but they aren't in
    `/home/john/docker/` yet).
  - Per-stack concurrency lock: one in-flight run per stack. Different
    stacks may update in parallel.
  - Output truncated to OUTPUT_MAX_BYTES (most of `docker compose pull`
    is layer-progress lines we don't need).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.database import async_session
from app.models.infra_update import InfraUpdate

logger = logging.getLogger(__name__)

UPDATE_TIMEOUT_SECONDS = 15 * 60  # 15 min — Plex/Ollama image pulls can be slow
OUTPUT_MAX_BYTES = 64 * 1024


@dataclass(frozen=True)
class StackDef:
    key: str
    label: str
    host: str  # display label ("HOLYGRAIL" / "Torrentbox")
    ssh_target: str  # passed to `ssh <target>` — must be in known_hosts
    compose_dir: str
    warning: str | None = None  # shown in the confirm dialog


STACKS: dict[str, StackDef] = {
    "torrentbox": StackDef(
        key="torrentbox",
        label="Torrentbox stack (Sonarr/Radarr/Prowlarr/Deluge/…)",
        host="Torrentbox",
        ssh_target="john@192.168.10.141",
        compose_dir="/home/john/docker",
        warning="gluetun is pinned to v3.40.0 and will not move. Other services will pull :latest.",
    ),
    "holygrail-plex": StackDef(
        key="holygrail-plex",
        label="Plex",
        host="HOLYGRAIL",
        ssh_target="john@192.168.10.129",
        compose_dir="/home/john/docker/plex",
        warning="Plex may run a database migration on first launch after a major version bump. Give it a few minutes before declaring failure.",
    ),
    "holygrail-ollama": StackDef(
        key="holygrail-ollama",
        label="Ollama",
        host="HOLYGRAIL",
        ssh_target="john@192.168.10.129",
        compose_dir="/home/john/docker/ollama",
    ),
    "holygrail-monitoring": StackDef(
        key="holygrail-monitoring",
        label="Monitoring (Grafana / InfluxDB / Smokeping)",
        host="HOLYGRAIL",
        ssh_target="john@192.168.10.129",
        compose_dir="/home/john/docker/monitoring",
    ),
    "holygrail-traefik": StackDef(
        key="holygrail-traefik",
        label="Traefik",
        host="HOLYGRAIL",
        ssh_target="john@192.168.10.129",
        compose_dir="/home/john/docker/traefik",
        warning="Traefik fronts advisor.holygrail. The Advisor UI may briefly drop while Traefik restarts — the update continues in the background and the result will appear here when you reload.",
    ),
}

# In-process per-stack lock — prevents double-clicking "Update" from
# kicking off two concurrent runs. Process-local; if the backend has
# multiple workers this would need to move to the DB. Single-worker
# uvicorn is the current deploy.
_LOCKS: dict[str, asyncio.Lock] = {key: asyncio.Lock() for key in STACKS}


def is_running(stack_key: str) -> bool:
    """True if an update for this stack is currently in flight."""
    lock = _LOCKS.get(stack_key)
    return lock is not None and lock.locked()


async def start_update(stack_key: str) -> InfraUpdate:
    """Insert a 'running' row and spawn the background task. Returns the row.

    Raises KeyError if the stack is unknown. Caller should check
    is_running() first to surface a 409 to the client; this function
    will still attempt to acquire the lock and may block briefly.
    """
    stack = STACKS[stack_key]

    async with async_session() as session:
        run = InfraUpdate(stack_key=stack_key, status="running")
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    asyncio.create_task(_run(stack, run_id))

    async with async_session() as session:
        result = await session.execute(select(InfraUpdate).where(InfraUpdate.id == run_id))
        return result.scalar_one()


async def _run(stack: StackDef, run_id: int) -> None:
    """Background task — SSH, run compose pull/up/prune, record result."""
    lock = _LOCKS[stack.key]
    if lock.locked():
        # Another run is in flight — record this one as failed and bail.
        await _finalize(run_id, status="failed", output="", error="another update is already running for this stack")
        return

    async with lock:
        # Combined &&-chained command — short-circuits on the first
        # non-zero exit. `image prune -f` removes only dangling images
        # (the layers superseded by the pull); it does not touch
        # in-use images.
        remote_cmd = (
            f"cd {stack.compose_dir} && "
            "docker compose pull && "
            "docker compose up -d && "
            "docker image prune -f"
        )
        cmd = ["ssh", "-o", "BatchMode=yes", stack.ssh_target, remote_cmd]

        logger.info(
            "infra_update.start", extra={"stack": stack.key, "run_id": run_id, "ssh": stack.ssh_target}
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # combined
            )
        except (OSError, asyncio.SubprocessError) as exc:
            await _finalize(run_id, status="failed", output="", error=f"failed to invoke ssh: {exc}")
            logger.warning(
                "infra_update.spawn_error", extra={"stack": stack.key, "run_id": run_id, "error": str(exc)}
            )
            return

        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=UPDATE_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            await _finalize(
                run_id,
                status="timeout",
                output="",
                error=f"update timed out after {UPDATE_TIMEOUT_SECONDS}s",
            )
            logger.warning(
                "infra_update.timeout", extra={"stack": stack.key, "run_id": run_id}
            )
            return

        output = _truncate(stdout.decode("utf-8", errors="replace"))
        rc = proc.returncode or 0
        status = "success" if rc == 0 else "failed"
        error = None if rc == 0 else f"ssh exit {rc}"

        await _finalize(run_id, status=status, output=output, error=error, exit_code=rc)
        logger.info(
            "infra_update.done",
            extra={"stack": stack.key, "run_id": run_id, "status": status, "rc": rc},
        )


def _truncate(text: str) -> str:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= OUTPUT_MAX_BYTES:
        return text
    head = encoded[: OUTPUT_MAX_BYTES // 2].decode("utf-8", errors="replace")
    tail = encoded[-OUTPUT_MAX_BYTES // 2 :].decode("utf-8", errors="replace")
    return f"{head}\n\n…[truncated {len(encoded) - OUTPUT_MAX_BYTES} bytes]…\n\n{tail}"


async def _finalize(
    run_id: int,
    *,
    status: str,
    output: str,
    error: str | None = None,
    exit_code: int | None = None,
) -> None:
    async with async_session() as session:
        result = await session.execute(select(InfraUpdate).where(InfraUpdate.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            return
        run.status = status
        run.output = output
        run.error = error
        run.exit_code = exit_code
        run.finished_at = datetime.utcnow()
        await session.commit()
