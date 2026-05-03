"""Infra updates — stack list, kick-off, status.

UI surfaces this on the Services page so the user can run the equivalent
of `ssh <host> 'cd <dir> && docker compose pull && up -d && image prune -f'`
without dropping to a terminal. Excluded: the advisor stack itself
(self-update would kill the running process) and stacks not yet deployed
on HOLYGRAIL (frigate/vaultwarden).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.infra_update import InfraUpdate
from app.services.infra_updater import STACKS, is_running, start_update

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/infra", tags=["infra"])


async def get_db():
    async with async_session() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


class StackInfo(BaseModel):
    key: str
    label: str
    host: str
    warning: str | None = None
    running: bool
    last_status: str | None
    last_started_at: datetime | None
    last_finished_at: datetime | None


class StackListResponse(BaseModel):
    stacks: list[StackInfo]


class UpdateRunResponse(BaseModel):
    id: int
    stack_key: str
    status: str
    output: str
    exit_code: int | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None


@router.get("/stacks", response_model=StackListResponse)
async def list_stacks(db: DbDep) -> StackListResponse:
    # Latest run per stack — single query using DISTINCT ON.
    result = await db.execute(
        select(InfraUpdate)
        .where(InfraUpdate.stack_key.in_(list(STACKS.keys())))
        .order_by(InfraUpdate.stack_key, InfraUpdate.started_at.desc())
        .distinct(InfraUpdate.stack_key)
    )
    latest_by_stack: dict[str, InfraUpdate] = {row.stack_key: row for row in result.scalars().all()}

    items: list[StackInfo] = []
    for key, stack in STACKS.items():
        last = latest_by_stack.get(key)
        items.append(
            StackInfo(
                key=key,
                label=stack.label,
                host=stack.host,
                warning=stack.warning,
                running=is_running(key),
                last_status=last.status if last else None,
                last_started_at=last.started_at if last else None,
                last_finished_at=last.finished_at if last else None,
            )
        )
    return StackListResponse(stacks=items)


@router.post("/stacks/{stack_key}/update", response_model=UpdateRunResponse, status_code=202)
async def trigger_update(stack_key: str) -> UpdateRunResponse:
    if stack_key not in STACKS:
        raise HTTPException(404, f"Unknown stack: {stack_key}")
    if is_running(stack_key):
        raise HTTPException(409, f"An update for {stack_key} is already running")

    run = await start_update(stack_key)
    return UpdateRunResponse(
        id=run.id,
        stack_key=run.stack_key,
        status=run.status,
        output=run.output,
        exit_code=run.exit_code,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/stacks/{stack_key}/runs/latest", response_model=UpdateRunResponse | None)
async def latest_run(stack_key: str, db: DbDep) -> UpdateRunResponse | None:
    if stack_key not in STACKS:
        raise HTTPException(404, f"Unknown stack: {stack_key}")
    result = await db.execute(
        select(InfraUpdate)
        .where(InfraUpdate.stack_key == stack_key)
        .order_by(InfraUpdate.started_at.desc())
        .limit(1)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None
    return UpdateRunResponse(
        id=run.id,
        stack_key=run.stack_key,
        status=run.status,
        output=run.output,
        exit_code=run.exit_code,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
