from src.application.dtos.export_dtos import NotionExportDTO, NotionExportResultDTO
from src.application.ports.integrations.notion_export_client import INotionExportClient
from src.application.ports.persistence.unit_of_work import IUnitOfWork
from src.application.ports.security.token_cipher import ITokenCipher
from src.domain.exceptions import IntegrationConfigurationException


class ExportMarkdownToNotionUseCase:
    def __init__(self, uow: IUnitOfWork, notion_client: INotionExportClient, token_cipher: ITokenCipher) -> None:
        self._uow = uow
        self._notion_client = notion_client
        self._token_cipher = token_cipher

    async def __call__(self, dto: NotionExportDTO) -> NotionExportResultDTO:
        access_token = None
        async with self._uow:
            connection = await self._uow.external_connection_repo.get_by_provider(user_id=dto.user_id, provider="notion")
        parent_page_id = dto.parent_page_id
        if connection is not None:
            try:
                access_token = self._token_cipher.decrypt(connection.access_token_encrypted)
            except ValueError as exc:
                raise IntegrationConfigurationException("reconnect Notion before exporting") from exc
            parent_page_id = parent_page_id or connection.default_parent_page_id
            if not parent_page_id:
                raise IntegrationConfigurationException("set a default Notion parent page before exporting")

        page_id, url = await self._notion_client.create_markdown_page(
            title=dto.title,
            markdown=dto.markdown,
            parent_page_id=parent_page_id,
            access_token=access_token,
        )
        return NotionExportResultDTO(page_id=page_id, url=url)
