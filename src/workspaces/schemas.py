from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class CollectionMemberRecord:
    id: UUID
    collection_id: UUID
    user_id: UUID | None
    email: str
    role: str
    invited_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True)
class CollectionAuditEventRecord:
    id: UUID
    collection_id: UUID
    actor_user_id: UUID
    event_type: str
    metadata: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class WorkspaceRecord:
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    access_role: str
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None = None


@dataclass(frozen=True)
class WorkspaceMemberRecord:
    id: UUID
    workspace_id: UUID
    user_id: UUID | None
    email: str
    role: str
    invite_status: str
    invited_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True)
class WorkspaceAuditEventRecord:
    id: UUID
    workspace_id: UUID
    actor_user_id: UUID
    event_type: str
    metadata: dict[str, object]
    created_at: datetime


class WorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class WorkspaceResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    access_role: str
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None = None


class WorkspaceListResponse(BaseModel):
    items: list[WorkspaceResponse]
    total: int
    limit: int
    offset: int


class WorkspaceMemberRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(pattern=r"^(viewer|editor)$")


class WorkspaceMemberRoleRequest(BaseModel):
    role: str = Field(pattern=r"^(viewer|editor)$")


class WorkspaceOwnershipTransferRequest(BaseModel):
    member_id: UUID


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID | None
    email: str
    role: str
    invite_status: str
    invited_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None


class WorkspaceMemberListResponse(BaseModel):
    items: list[WorkspaceMemberResponse]


class WorkspaceAuditEventResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    actor_user_id: UUID
    event_type: str
    metadata: dict[str, object]
    created_at: datetime


class WorkspaceAuditEventListResponse(BaseModel):
    items: list[WorkspaceAuditEventResponse]
    total: int
    limit: int
    offset: int
