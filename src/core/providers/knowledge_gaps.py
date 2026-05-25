from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.documents.note_use_cases import CreateNoteUseCase
from src.application.use_cases.knowledge_gaps import (
    CreateKnowledgeGapNoteUseCase,
    GetKnowledgeGapsUseCase,
    ListKnowledgeGapsUseCase,
)


class KnowledgeGapsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_knowledge_gaps_use_case(self, uow: IUnitOfWork) -> GetKnowledgeGapsUseCase:
        return GetKnowledgeGapsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_knowledge_gaps_use_case(self, uow: IUnitOfWork) -> ListKnowledgeGapsUseCase:
        return ListKnowledgeGapsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_create_knowledge_gap_note_use_case(self, create_note: CreateNoteUseCase) -> CreateKnowledgeGapNoteUseCase:
        return CreateKnowledgeGapNoteUseCase(create_note)
