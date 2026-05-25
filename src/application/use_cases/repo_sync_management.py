from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.dtos.repo_sync_dtos import CreateRepoSyncDTO, RepoSyncDTO, RepoSyncListDTO
from src.application.use_cases.repo_sync_helpers import (
    normalize_repo_path_patterns,
    parse_github_repo_url,
)
from src.domain.exceptions import ResourceNotFoundException

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


_DEFAULT_INCLUDE_PATHS = ("README.md", "docs/**/*.md", "**/*.md")
_DEFAULT_EXCLUDE_PATHS = ("node_modules/**", ".git/**", "dist/**")


class ListRepoSyncsUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, *, user_id: UUID) -> RepoSyncListDTO:
        async with self._uow:
            items = await self._uow.repo_sync_repo.list_by_user_id(user_id)
        return RepoSyncListDTO(items=items)


class CreateRepoSyncUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, dto: CreateRepoSyncDTO) -> RepoSyncDTO:
        repo_ref = parse_github_repo_url(dto.repo_url)
        branch = dto.branch.strip() or "main"
        include_paths = normalize_repo_path_patterns(dto.include_paths, _DEFAULT_INCLUDE_PATHS)
        exclude_paths = normalize_repo_path_patterns(dto.exclude_paths, _DEFAULT_EXCLUDE_PATHS)
        async with self._uow:
            collection = await self._uow.collection_repo.get_by_id(dto.collection_id)
            if collection is None or collection.user_id != dto.user_id:
                raise ResourceNotFoundException("collection not found")
            existing = await self._uow.repo_sync_repo.get_by_repo(
                user_id=dto.user_id,
                owner=repo_ref.owner,
                repo=repo_ref.repo,
                branch=branch,
            )
            if existing is not None:
                existing = await self._uow.repo_sync_repo.update_filters(
                    repo_sync_id=existing.id,
                    include_paths=include_paths,
                    exclude_paths=exclude_paths,
                )
                await self._uow.commit()
                return existing
            repo_sync = await self._uow.repo_sync_repo.create(
                id=uuid.uuid4(),
                user_id=dto.user_id,
                collection_id=dto.collection_id,
                provider="github",
                owner=repo_ref.owner,
                repo=repo_ref.repo,
                branch=branch,
                include_paths=include_paths,
                exclude_paths=exclude_paths,
            )
            await self._uow.commit()
            return repo_sync
