from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.stats import GetStatsOverviewUseCase, GetStatsTimelineUseCase


class StatsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_stats_overview_use_case(self, uow: IUnitOfWork) -> GetStatsOverviewUseCase:
        return GetStatsOverviewUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_stats_timeline_use_case(self, uow: IUnitOfWork) -> GetStatsTimelineUseCase:
        return GetStatsTimelineUseCase(uow)
