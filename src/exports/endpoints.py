from fastapi import Depends, Response

from src.auth.auth import CurrentUser
from src.documents.exports import (
    NotionMarkdownExporter,
    markdown_to_pdf,
    safe_filename,
)
from src.documents.schemas import ExportedFile
from src.exports.dependencies import get_notion_markdown_exporter
from src.exports.schemas import MarkdownExportRequest, NotionExportRequest, NotionExportResponse
from src.routing import APIRouter

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


def markdown_export_file(*, title: str, markdown: str, export_format: str) -> ExportedFile:
    filename_stem = safe_filename(title)
    normalized_format = export_format.lower()
    if normalized_format in {"md", "markdown"}:
        return ExportedFile(
            filename=f"{filename_stem}.md",
            media_type="text/markdown; charset=utf-8",
            content=markdown.encode("utf-8"),
        )
    return ExportedFile(
        filename=f"{filename_stem}.pdf",
        media_type="application/pdf",
        content=markdown_to_pdf(markdown),
    )


@router.post("/notion", response_model=NotionExportResponse)
async def export_notion(
    body: NotionExportRequest,
    current_user: CurrentUser,
    handler: NotionMarkdownExporter = Depends(get_notion_markdown_exporter),
) -> NotionExportResponse:
    result = await handler(
        user_id=current_user.id,
        title=body.title,
        markdown=body.markdown,
        parent_page_id=body.parent_page_id,
    )
    return NotionExportResponse(page_id=result.page_id, url=result.url)


__all__ = ["markdown_export_file", "router"]
