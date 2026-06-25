from fastapi import Depends

from src.query.agents.graph_runner import QueryGraphRunner
from src.query.dependencies import get_query_graph_runner


def get_public_query_graph_runner(
    graph_runner: QueryGraphRunner = Depends(get_query_graph_runner),
) -> QueryGraphRunner:
    return graph_runner
