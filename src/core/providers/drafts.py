from dishka import Provider, Scope, provide

from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.drafts import (
    DeleteDraftUseCase,
    GenerateDraftOutlineUseCase,
    GenerateDraftUseCase,
    GetDraftUseCase,
    ListDraftsUseCase,
    ListDraftTemplatesUseCase,
    ListDraftVersionsUseCase,
    RestoreDraftVersionUseCase,
)
from src.application.use_cases.query.query_use_case import QueryUseCase


class DraftsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_list_draft_templates_use_case(self) -> ListDraftTemplatesUseCase:
        return ListDraftTemplatesUseCase()

    @provide(scope=Scope.REQUEST)
    def get_generate_draft_outline_use_case(self) -> GenerateDraftOutlineUseCase:
        return GenerateDraftOutlineUseCase()

    @provide(scope=Scope.REQUEST)
    def get_list_drafts_use_case(self, uow: IUnitOfWork) -> ListDraftsUseCase:
        return ListDraftsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_draft_use_case(self, uow: IUnitOfWork) -> GetDraftUseCase:
        return GetDraftUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_draft_versions_use_case(self, uow: IUnitOfWork) -> ListDraftVersionsUseCase:
        return ListDraftVersionsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_restore_draft_version_use_case(self, uow: IUnitOfWork) -> RestoreDraftVersionUseCase:
        return RestoreDraftVersionUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_delete_draft_use_case(self, uow: IUnitOfWork) -> DeleteDraftUseCase:
        return DeleteDraftUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_generate_draft_use_case(
        self,
        query_use_case: QueryUseCase,
        uow: IUnitOfWork,
        llm_service: ILLMService,
    ) -> GenerateDraftUseCase:
        return GenerateDraftUseCase(query_use_case, uow, llm_service)
