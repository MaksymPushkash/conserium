from src.application.dtos.external_connection_dtos import NotionConnectionDTO, NotionPageDTO
from src.presentation.schemas.integration import NotionConnectionResponse, NotionPageResponse


def to_notion_connection_response(dto: NotionConnectionDTO) -> NotionConnectionResponse:
    return NotionConnectionResponse(
        connected=dto.connected,
        workspace_id=dto.workspace_id,
        workspace_name=dto.workspace_name,
        bot_id=dto.bot_id,
        default_parent_page_id=dto.default_parent_page_id,
        default_parent_page_title=dto.default_parent_page_title,
    )


def to_notion_page_response(dto: NotionPageDTO) -> NotionPageResponse:
    return NotionPageResponse(id=dto.id, title=dto.title)
