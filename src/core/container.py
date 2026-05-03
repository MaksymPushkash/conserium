from dishka import make_async_container

from src.core.providers import (
    AIProvider,
    AuthProvider,
    CacheProvider,
    DatabaseProvider,
    DocumentsProvider,
    IngestionProvider,
    QueryProvider,
)

container = make_async_container(
    DatabaseProvider(),
    CacheProvider(),
    AuthProvider(),
    IngestionProvider(),
    AIProvider(),
    DocumentsProvider(),
    QueryProvider(),
)
