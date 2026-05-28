from uuid import UUID

from src.application.dtos.stats_dtos import WeeklyReportDTO
from src.application.ports.persistence.unit_of_work import IUnitOfWork


class GetWeeklyReportUseCase:
    def __init__(self, uow: IUnitOfWork) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID) -> WeeklyReportDTO:
        async with self._uow:
            report = await self._uow.stats_repo.get_weekly_report(user_id=user_id)

        recommended_actions = _recommended_actions(
            stale_documents=report.stale_documents,
            failed_documents=report.failed_documents,
            query_count=report.query_count,
            saved_documents=report.saved_documents,
        )
        return WeeklyReportDTO(
            saved_documents=report.saved_documents,
            active_documents=report.active_documents,
            query_count=report.query_count,
            citation_count=report.citation_count,
            ready_documents=report.ready_documents,
            failed_documents=report.failed_documents,
            stale_documents=report.stale_documents,
            summary=_summary(report.saved_documents, report.active_documents, report.query_count),
            recommended_actions=recommended_actions,
        )


def _summary(saved_documents: int, active_documents: int, query_count: int) -> str:
    if saved_documents == 0 and query_count == 0:
        return "No meaningful workspace activity in the last 7 days."
    return f"{saved_documents} sources saved, {active_documents} sources revisited, {query_count} queries asked in the last 7 days."


def _recommended_actions(
    *,
    stale_documents: int,
    failed_documents: int,
    query_count: int,
    saved_documents: int,
) -> list[str]:
    actions: list[str] = []
    if failed_documents:
        actions.append("Retry failed processing jobs.")
    if stale_documents:
        actions.append("Review stale documents with the daily digest.")
    if saved_documents and query_count == 0:
        actions.append("Ask a scoped question about recently saved sources.")
    if not actions:
        actions.append("Keep adding sources and use gaps to decide what to study next.")
    return actions
