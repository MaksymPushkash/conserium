from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.topics import (
    GetTopicDetailUseCase,
    IgnoreTopicUseCase,
    ListTopicsUseCase,
    MergeTopicsUseCase,
    PinTopicUseCase,
    RenameTopicUseCase,
)


class TopicsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_list_topics_use_case(self, uow: IUnitOfWork) -> ListTopicsUseCase:
        return ListTopicsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_topic_detail_use_case(self, uow: IUnitOfWork) -> GetTopicDetailUseCase:
        return GetTopicDetailUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_rename_topic_use_case(self, uow: IUnitOfWork) -> RenameTopicUseCase:
        return RenameTopicUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_merge_topics_use_case(self, uow: IUnitOfWork) -> MergeTopicsUseCase:
        return MergeTopicsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_pin_topic_use_case(self, uow: IUnitOfWork) -> PinTopicUseCase:
        return PinTopicUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_ignore_topic_use_case(self, uow: IUnitOfWork) -> IgnoreTopicUseCase:
        return IgnoreTopicUseCase(uow)
