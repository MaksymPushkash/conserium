from dishka import Provider, Scope, provide

from src.application.ports.ingestion.file_storage import IFileStorage
from src.application.ports.ingestion.task_dispatcher import ITaskDispatcher
from src.application.ports.ingestion.text_chunker import ITextChunker
from src.infrastructure.celery.dispatcher import CeleryTaskDispatcher
from src.infrastructure.storage.local_file_storage import LocalFileStorage
from src.infrastructure.text_processing import SimpleTextChunker


class IngestionProvider(Provider):
    @provide(scope=Scope.APP)
    def get_task_dispatcher(self) -> ITaskDispatcher:
        return CeleryTaskDispatcher()

    @provide(scope=Scope.APP)
    def get_file_storage(self) -> IFileStorage:
        return LocalFileStorage()

    @provide(scope=Scope.APP)
    def get_text_chunker(self) -> ITextChunker:
        return SimpleTextChunker()
