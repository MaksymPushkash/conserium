from dishka import Provider, Scope, provide

from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.application.ports.integrations.github_repository_client import IGitHubRepositoryClient
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.repo_syncs import CreateRepoSyncUseCase, ListRepoSyncsUseCase, RunRepoSyncUseCase
from src.infrastructure.integrations.github_repository_client import GitHubRepositoryClient


class RepoSyncsProvider(Provider):
    @provide(scope=Scope.APP)
    def get_github_repository_client(self) -> IGitHubRepositoryClient:
        return GitHubRepositoryClient()

    @provide(scope=Scope.REQUEST)
    def get_list_repo_syncs_use_case(self, uow: IUnitOfWork) -> ListRepoSyncsUseCase:
        return ListRepoSyncsUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_create_repo_sync_use_case(self, uow: IUnitOfWork) -> CreateRepoSyncUseCase:
        return CreateRepoSyncUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_run_repo_sync_use_case(
        self,
        uow: IUnitOfWork,
        github_client: IGitHubRepositoryClient,
        task_dispatcher: ITaskDispatcher,
    ) -> RunRepoSyncUseCase:
        return RunRepoSyncUseCase(uow, github_client, task_dispatcher)
