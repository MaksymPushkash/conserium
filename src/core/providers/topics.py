from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.topics import GetTopicDetailUseCase, ListTopicsUseCase


class TopicsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_list_topics_use_case(self, uow: IUnitOfWork) -> ListTopicsUseCase:
        return ListTopicsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_topic_detail_use_case(self, uow: IUnitOfWork) -> GetTopicDetailUseCase:
        return GetTopicDetailUseCase(uow)
