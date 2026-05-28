from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.review import GenerateFlashcardsUseCase, ListDueFlashcardsUseCase, ReviewFlashcardUseCase


class ReviewProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_generate_flashcards_use_case(self, uow: IUnitOfWork) -> GenerateFlashcardsUseCase:
        return GenerateFlashcardsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_due_flashcards_use_case(self, uow: IUnitOfWork) -> ListDueFlashcardsUseCase:
        return ListDueFlashcardsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_review_flashcard_use_case(self, uow: IUnitOfWork) -> ReviewFlashcardUseCase:
        return ReviewFlashcardUseCase(uow)
