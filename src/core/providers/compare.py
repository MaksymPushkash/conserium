from dishka import Provider, Scope, provide

from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.compare import (
    CompareDocumentsUseCase,
    DeleteCompareResultUseCase,
    GetCompareResultUseCase,
    ListCompareResultsUseCase,
)
from src.application.use_cases.query.query_use_case import QueryUseCase


class CompareProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_compare_documents_use_case(
        self,
        query_use_case: QueryUseCase,
        uow: IUnitOfWork,
        llm_service: ILLMService,
    ) -> CompareDocumentsUseCase:
        return CompareDocumentsUseCase(query_use_case, uow, llm_service)

    @provide(scope=Scope.REQUEST)
    def get_list_compare_results_use_case(self, uow: IUnitOfWork) -> ListCompareResultsUseCase:
        return ListCompareResultsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_compare_result_use_case(self, uow: IUnitOfWork) -> GetCompareResultUseCase:
        return GetCompareResultUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_delete_compare_result_use_case(self, uow: IUnitOfWork) -> DeleteCompareResultUseCase:
        return DeleteCompareResultUseCase(uow)
