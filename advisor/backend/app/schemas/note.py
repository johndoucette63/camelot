from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NoteCreate(BaseModel):
    target_type: Literal["device", "service", "playbook"]
    target_id: int | None = None
    title: str | None = Field(None, max_length=200)
    body: str = Field(..., min_length=1, max_length=2048)
    pinned: bool = False
    tags: list[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    body: str | None = Field(None, min_length=1, max_length=2048)
    pinned: bool | None = None
    tags: list[str] | None = None


class NoteResponse(BaseModel):
    id: int
    target_type: str
    target_id: int | None
    title: str | None
    body: str
    pinned: bool
    tags: list[str]
    created_at: datetime
    updated_at: datetime


class NoteListResponse(BaseModel):
    notes: list[NoteResponse]
    total: int


class TagListResponse(BaseModel):
    tags: list[str]


class SuggestionItem(BaseModel):
    target_type: str
    target_id: int | None
    target_label: str | None
    body: str


class SuggestionResponse(BaseModel):
    suggestions: list[SuggestionItem]
    error: str | None = None


class RejectedSuggestionCreate(BaseModel):
    body: str
    conversation_id: int | None = None


class RejectedSuggestionResponse(BaseModel):
    id: int
    content_hash: str
    created_at: datetime
