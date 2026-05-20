from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, Response

from src.application.dtos.export_dtos import ExportedFileDTO, NotionExportDTO
from src.application.use_cases.documents.export_document_use_case import markdown_to_pdf, safe_filename
from src.application.use_cases.documents.export_markdown_to_notion_use_case import ExportMarkdownToNotionUseCase
from src.presentation.dependencies.auth import CurrentUser
from src.presentation.schemas.export import MarkdownExportRequest, NotionExportRequest, NotionExportResponse

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("/markdown")
async def export_markdown(body: MarkdownExportRequest, current_user: CurrentUser) -> Response:
    _ = current_user
    result = markdown_export_file(title=body.title, markdown=body.markdown, export_format=body.format)
    return Response(
        content=result.content,
        media_type=result.media_type,
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


def markdown_export_file(*, title: str, markdown: str, export_format: str) -> ExportedFileDTO:
    filename_stem = safe_filename(title)
    normalized_format = export_format.lower()
    if normalized_format in {"md", "markdown"}:
        return ExportedFileDTO(
            filename=f"{filename_stem}.md",
            media_type="text/markdown; charset=utf-8",
            content=markdown.encode("utf-8"),
        )
    return ExportedFileDTO(
        filename=f"{filename_stem}.pdf",
        media_type="application/pdf",
        content=markdown_to_pdf(markdown),
    )


@router.post("/notion", response_model=NotionExportResponse)
@inject
async def export_notion(
    body: NotionExportRequest,
    current_user: CurrentUser,
    use_case: FromDishka[ExportMarkdownToNotionUseCase],
) -> NotionExportResponse:
    _ = current_user
    result = await use_case(
        NotionExportDTO(
            user_id=current_user.id,
            title=body.title,
            markdown=body.markdown,
            parent_page_id=body.parent_page_id,
        )
    )
    return NotionExportResponse(page_id=result.page_id, url=result.url)
