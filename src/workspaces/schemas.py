from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class CollectionMemberDTO:
    id: UUID
    collection_id: UUID
    user_id: UUID | None
    email: str
    role: str
    invited_by_user_id: UUID
    created_at: datetime
    updated_at: datetime | None


@dataclass(frozen=True)
class CollectionMemberListDTO:
    items: list[CollectionMemberDTO]


@dataclass(frozen=True)
class CollectionAuditEventDTO:
    id: UUID
    collection_id: UUID
    actor_user_id: UUID
    event_type: str
    metadata: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class CollectionAuditEventListDTO:
    items: list[CollectionAuditEventDTO]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class InviteCollectionMemberDTO:
    collection_id: UUID
    actor_user_id: UUID
    email: str
    role: str


@dataclass(frozen=True)
class UpdateCollectionMemberRoleDTO:
    collection_id: UUID
    member_id: UUID
    actor_user_id: UUID
    role: str


@dataclass(frozen=True)
class RemoveCollectionMemberDTO:
    collection_id: UUID
    member_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True)
class WorkspaceDTO:
    id: UUID
    user_id: UUID
    name: str
    description: str | None
    access_role: str
    created_at: datetime
    updated_at: datetime | None
    archived_at: datetime | None = None


@dataclass(frozen=True)
class WorkspaceListDTO:
    items: list[WorkspaceDTO]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class WorkspaceMemberDTO:
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
class WorkspaceMemberListDTO:
    items: list[WorkspaceMemberDTO]


@dataclass(frozen=True)
class WorkspaceAuditEventDTO:
    id: UUID
    workspace_id: UUID
    actor_user_id: UUID
    event_type: str
    metadata: dict[str, object]
    created_at: datetime


@dataclass(frozen=True)
class WorkspaceAuditEventListDTO:
    items: list[WorkspaceAuditEventDTO]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class CreateWorkspaceDTO:
    user_id: UUID
    name: str
    description: str | None = None


@dataclass(frozen=True)
class UpdateWorkspaceDTO:
    workspace_id: UUID
    actor_user_id: UUID
    name: str
    description: str | None = None


@dataclass(frozen=True)
class DeleteWorkspaceDTO:
    workspace_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True)
class InviteWorkspaceMemberDTO:
    workspace_id: UUID
    actor_user_id: UUID
    email: str
    role: str


@dataclass(frozen=True)
class UpdateWorkspaceMemberRoleDTO:
    workspace_id: UUID
    member_id: UUID
    actor_user_id: UUID
    role: str


@dataclass(frozen=True)
class RemoveWorkspaceMemberDTO:
    workspace_id: UUID
    member_id: UUID
    actor_user_id: UUID


@dataclass(frozen=True)
class TransferWorkspaceOwnershipDTO:
    workspace_id: UUID
    actor_user_id: UUID
    member_id: UUID


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
