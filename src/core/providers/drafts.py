from dishka import Provider, Scope, provide

from src.application.use_cases.drafts import GenerateDraftUseCase
from src.application.use_cases.query.query_use_case import QueryUseCase


class DraftsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_generate_draft_use_case(self, query_use_case: QueryUseCase) -> GenerateDraftUseCase:
        return GenerateDraftUseCase(query_use_case)
