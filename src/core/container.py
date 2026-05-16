from dishka import make_async_container

from src.core.providers import (
    AIProvider,
    AuthProvider,
    CacheProvider,
    DatabaseProvider,
    DocumentsProvider,
    DraftsProvider,
    IngestionProvider,
    QueryProvider,
    StatsProvider,
    TopicsProvider,
)

container = make_async_container(
    DatabaseProvider(),
    CacheProvider(),
    AuthProvider(),
    IngestionProvider(),
    AIProvider(),
    DocumentsProvider(),
    QueryProvider(),
    DraftsProvider(),
    StatsProvider(),
    TopicsProvider(),
)
