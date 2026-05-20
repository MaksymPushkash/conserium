from dishka import Provider, Scope, provide

from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.drafts import GenerateDraftUseCase
from src.application.use_cases.query.query_use_case import QueryUseCase


class DraftsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_generate_draft_use_case(
        self,
        query_use_case: QueryUseCase,
        uow: IUnitOfWork,
        llm_service: ILLMService,
    ) -> GenerateDraftUseCase:
        return GenerateDraftUseCase(query_use_case, uow, llm_service)
