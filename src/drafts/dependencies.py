from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.documents.document_repository import DocumentRepository
from src.drafts.repository import DraftRepository
from src.drafts.service import DraftService
from src.kit.ai.llm_service import LLMService
from src.postgres import get_db_session
from src.query.dependencies import get_llm_service, get_query_executor
from src.query.service import QueryExecutor


def get_query_executor_for_drafts(query_executor: QueryExecutor = Depends(get_query_executor)) -> QueryExecutor:
    return query_executor


def get_llm_service_for_drafts(llm_service: LLMService = Depends(get_llm_service)) -> LLMService:
    return llm_service


def get_draft_service(
    session: AsyncSession = Depends(get_db_session),
    query_executor: QueryExecutor = Depends(get_query_executor_for_drafts),
    llm_service: LLMService = Depends(get_llm_service_for_drafts),
) -> DraftService:
    return DraftService(
        session,
        DraftRepository(session),
        DocumentRepository.from_session(session),
        query_executor,
        llm_service,
    )
