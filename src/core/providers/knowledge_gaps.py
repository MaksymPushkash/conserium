from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.knowledge_gaps import GetKnowledgeGapsUseCase


class KnowledgeGapsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_knowledge_gaps_use_case(self, uow: IUnitOfWork) -> GetKnowledgeGapsUseCase:
        return GetKnowledgeGapsUseCase(uow)
