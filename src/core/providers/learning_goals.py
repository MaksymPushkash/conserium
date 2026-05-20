from dishka import Provider, Scope, provide

from src.application.ports.integrations.web_resource_fetcher import IWebResourceFetcher
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.learning_goals import (
    CreateLearningGoalUseCase,
    DeleteLearningGoalUseCase,
    ListLearningGoalRemindersUseCase,
    ListLearningGoalsUseCase,
    RankLearningGoalResourcesUseCase,
    UpdateLearningGoalUseCase,
)
from src.infrastructure.integrations.web_resource_fetcher import HTTPWebResourceFetcher


class LearningGoalsProvider(Provider):
    @provide(scope=Scope.APP)
    def get_web_resource_fetcher(self) -> IWebResourceFetcher:
        return HTTPWebResourceFetcher()

    @provide(scope=Scope.REQUEST)
    def get_list_learning_goals_use_case(self, uow: IUnitOfWork) -> ListLearningGoalsUseCase:
        return ListLearningGoalsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_list_learning_goal_reminders_use_case(
        self,
        list_goals: ListLearningGoalsUseCase,
    ) -> ListLearningGoalRemindersUseCase:
        return ListLearningGoalRemindersUseCase(list_goals)

    @provide(scope=Scope.REQUEST)
    def get_create_learning_goal_use_case(self, uow: IUnitOfWork) -> CreateLearningGoalUseCase:
        return CreateLearningGoalUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_update_learning_goal_use_case(self, uow: IUnitOfWork) -> UpdateLearningGoalUseCase:
        return UpdateLearningGoalUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_delete_learning_goal_use_case(self, uow: IUnitOfWork) -> DeleteLearningGoalUseCase:
        return DeleteLearningGoalUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_rank_learning_goal_resources_use_case(
        self,
        uow: IUnitOfWork,
        web_resource_fetcher: IWebResourceFetcher,
    ) -> RankLearningGoalResourcesUseCase:
        return RankLearningGoalResourcesUseCase(uow, web_resource_fetcher)
