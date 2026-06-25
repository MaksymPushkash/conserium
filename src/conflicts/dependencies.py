from fastapi import Depends

from src.conflicts.service import ConflictService, conflicts
from src.kit.ai.llm_service import LLMService
from src.query.dependencies import get_llm_service


def get_conflict_llm_service(llm_service: LLMService = Depends(get_llm_service)) -> LLMService:
    return llm_service


def get_conflict_service() -> ConflictService:
    return conflicts
