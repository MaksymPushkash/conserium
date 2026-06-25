from fastapi import Depends

from src.compare.service import CompareService, compare
from src.kit.ai.llm_service import LLMService
from src.query.dependencies import get_llm_service, get_query_executor
from src.query.service import QueryExecutor


def get_compare_query_executor(query_executor: QueryExecutor = Depends(get_query_executor)) -> QueryExecutor:
    return query_executor


def get_compare_llm_service(llm_service: LLMService = Depends(get_llm_service)) -> LLMService:
    return llm_service


def get_compare_service() -> CompareService:
    return compare
