from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.knowledge_graph.repository import KnowledgeGraphRepository
from src.knowledge_graph.service import KnowledgeGraphService
from src.postgres import get_db_session
from src.topics.repository import TopicRepository


def get_knowledge_graph_service(session: AsyncSession = Depends(get_db_session)) -> KnowledgeGraphService:
    return KnowledgeGraphService(
        session,
        KnowledgeGraphRepository.from_session(session),
        TopicRepository.from_session(session),
    )
