from dishka import Provider, Scope, provide

from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.use_cases.collection_shares import (
    CreateCollectionShareUseCase,
    GetCollectionShareUseCase,
    GetPublicCollectionUseCase,
    QueryPublicCollectionUseCase,
    RevokeCollectionShareUseCase,
)
from src.application.use_cases.query.query_use_case import QueryUseCase


class CollectionSharesProvider(Provider):
    @provide(scope=Scope.REQUEST)
    def get_collection_share_use_case(self, uow: IUnitOfWork) -> GetCollectionShareUseCase:
        return GetCollectionShareUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_create_collection_share_use_case(self, uow: IUnitOfWork) -> CreateCollectionShareUseCase:
        return CreateCollectionShareUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_revoke_collection_share_use_case(self, uow: IUnitOfWork) -> RevokeCollectionShareUseCase:
        return RevokeCollectionShareUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_public_collection_use_case(self, uow: IUnitOfWork) -> GetPublicCollectionUseCase:
        return GetPublicCollectionUseCase(uow)

    @provide(scope=Scope.REQUEST)
    def get_query_public_collection_use_case(
        self,
        uow: IUnitOfWork,
        query_use_case: QueryUseCase,
    ) -> QueryPublicCollectionUseCase:
        return QueryPublicCollectionUseCase(uow, query_use_case)
