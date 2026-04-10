"""GET /containers — Docker container inventory from HOLYGRAIL."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("")
async def list_containers(request: Request):
    return request.app.state.container_state
