from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.knowledge_graph import (
    CreateKnowledgeGraphConcernUseCase,
    GetKnowledgeGraphInsightsUseCase,
    GetKnowledgeGraphUseCase,
    RecomputeKnowledgeGraphUseCase,
)


class KnowledgeGraphProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_knowledge_graph_use_case(self, uow: IUnitOfWork) -> GetKnowledgeGraphUseCase:
        return GetKnowledgeGraphUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_knowledge_graph_insights_use_case(self, uow: IUnitOfWork) -> GetKnowledgeGraphInsightsUseCase:
        return GetKnowledgeGraphInsightsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_recompute_knowledge_graph_use_case(self, uow: IUnitOfWork) -> RecomputeKnowledgeGraphUseCase:
        return RecomputeKnowledgeGraphUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_create_knowledge_graph_concern_use_case(self, uow: IUnitOfWork) -> CreateKnowledgeGraphConcernUseCase:
        return CreateKnowledgeGraphConcernUseCase(uow)
