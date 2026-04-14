"""Narrow remediation helpers for rule escalation paths.

Currently only used by the vpn_leak rule's escalation handler. Kept
intentionally narrow — generalize to a "remediation framework" only when
a second concrete use case appears.

Constitution II (Simplicity): no abstract registry, no plugin loader.
Just a function call.
"""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15


async def stop_container(host: str, container_name: str, *, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> tuple[bool, str | None]:
    """Stop a container on a remote host via SSH.

    Reuses the existing passwordless SSH trust from HOLYGRAIL → torrentbox
    (configured in scripts/ssh-config). No new credentials.

    Returns:
        (success, error_message). On success, error_message is None.
        On failure, success is False and error_message describes what went wrong.

    Never raises — exceptions are caught and surfaced as a (False, str) tuple.
    """
    cmd = ["ssh", host, "docker", "stop", container_name]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
            err = f"ssh {host} docker stop {container_name} timed out after {timeout}s"
            logger.warning("remediation.stop_container.timeout", extra={"host": host, "container": container_name, "timeout": timeout})
            return (False, err)
    except (OSError, asyncio.SubprocessError) as exc:
        err = f"failed to invoke ssh: {exc}"
        logger.warning("remediation.stop_container.subprocess_error", extra={"host": host, "container": container_name, "error": str(exc)})
        return (False, err)

    if proc.returncode != 0:
        err = (stderr.decode("utf-8", errors="replace") or stdout.decode("utf-8", errors="replace") or "unknown error").strip()
        logger.warning(
            "remediation.stop_container.nonzero_exit",
            extra={"host": host, "container": container_name, "rc": proc.returncode, "error": err},
        )
        return (False, f"ssh exit {proc.returncode}: {err}")

    logger.info(
        "remediation.stop_container.ok",
        extra={"host": host, "container": container_name},
    )
    return (True, None)
