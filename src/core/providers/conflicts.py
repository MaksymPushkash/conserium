from dishka import Provider, Scope, provide

from src.application.ports.ai.llm_service import ILLMService
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.conflicts import DetectConflictsUseCase


class ConflictsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_detect_conflicts_use_case(self, uow: IUnitOfWork, llm_service: ILLMService) -> DetectConflictsUseCase:
        return DetectConflictsUseCase(uow, llm_service)
