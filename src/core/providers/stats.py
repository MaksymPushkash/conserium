from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.stats import (
    GetDailyDigestUseCase,
    GetStatsOverviewUseCase,
    GetStatsTimelineUseCase,
    GetWeeklyReportUseCase,
)


class StatsProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_stats_overview_use_case(self, uow: IUnitOfWork) -> GetStatsOverviewUseCase:
        return GetStatsOverviewUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_stats_timeline_use_case(self, uow: IUnitOfWork) -> GetStatsTimelineUseCase:
        return GetStatsTimelineUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_daily_digest_use_case(self, uow: IUnitOfWork) -> GetDailyDigestUseCase:
        return GetDailyDigestUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_weekly_report_use_case(self, uow: IUnitOfWork) -> GetWeeklyReportUseCase:
        return GetWeeklyReportUseCase(uow)
