import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast

from src.application.ports.persistence.knowledge_graph_repository import (
    KnowledgeEdgeRecord,
    KnowledgeGraphConcernRecord,
    KnowledgeGraphRecord,
)
from src.application.use_cases.knowledge_graph import (
    CreateKnowledgeGraphConcernUseCase,
    GetKnowledgeGraphUseCase,
    RecomputeKnowledgeGraphUseCase,
)

if TYPE_CHECKING:
    from src.application.ports.persistence.unit_of_work import IUnitOfWork


class _FakeKnowledgeGraphRepository:
    def __init__(self) -> None:
        self.replaced_edge_count = 0
        self.concern: KnowledgeGraphConcernRecord | None = None

    async def list_topic_document_links(
        self,
        user_id: uuid.UUID,
        *,
        document_limit: int,
        topic_limit: int,
        **filters: object,
    ) -> list[KnowledgeGraphRecord]:
        assert document_limit > 0
        assert topic_limit > 0
        assert filters is not None
        return [
            KnowledgeGraphRecord(
                document_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                document_title="FastAPI Notes",
                document_type="TEXT",
                topic_name="python",
                summary="FastAPI summary",
                suggested_questions=["How does FastAPI work?"],
            ),
            KnowledgeGraphRecord(
                document_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                document_title="Django Notes",
                document_type="TEXT",
                topic_name="python",
            ),
        ]

    async def list_edges(self, user_id: uuid.UUID) -> list[KnowledgeEdgeRecord]:
        return [
            KnowledgeEdgeRecord(
                source_document_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                target_document_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
                relation_type="same_topic",
                score=0.75,
                evidence=["python"],
            )
        ]

    async def replace_edges(self, user_id: uuid.UUID, edges: list[KnowledgeEdgeRecord]) -> None:
        self.replaced_edge_count = len(edges)

    async def create_concern(
        self,
        *,
        concern_id: uuid.UUID,
        user_id: uuid.UUID,
        node_id: str | None,
        node_kind: str | None,
        node_label: str | None,
        message: str,
    ) -> KnowledgeGraphConcernRecord:
        self.concern = KnowledgeGraphConcernRecord(
            id=concern_id,
            user_id=user_id,
            node_id=node_id,
            node_kind=node_kind,
            node_label=node_label,
            message=message,
            status="open",
            created_at=datetime.now(UTC),
        )
        return self.concern


class _FakeUnitOfWork:
    def __init__(self) -> None:
        self.knowledge_graph_repo = _FakeKnowledgeGraphRepository()
        self.committed = False

    async def __aenter__(self) -> "_FakeUnitOfWork":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


async def test_get_knowledge_graph_returns_topic_document_nodes_and_edges() -> None:
    uow = _FakeUnitOfWork()
    use_case = GetKnowledgeGraphUseCase(cast("IUnitOfWork", uow))

    result = await use_case(user_id=uuid.uuid4(), document_limit=80, topic_limit=20)

    assert {node.id for node in result.nodes} == {
        "topic:python",
        "document:00000000-0000-0000-0000-000000000001",
        "document:00000000-0000-0000-0000-000000000002",
    }
    assert {edge.target_id for edge in result.edges} == {
        "document:00000000-0000-0000-0000-000000000001",
        "document:00000000-0000-0000-0000-000000000002",
    }
    assert uow.knowledge_graph_repo.replaced_edge_count == 0
    assert not uow.committed
    fastapi_node = next(node for node in result.nodes if node.id == "document:00000000-0000-0000-0000-000000000001")
    assert fastapi_node.summary == "FastAPI summary"
    assert fastapi_node.suggested_questions == ["How does FastAPI work?"]


async def test_recompute_knowledge_graph_persists_document_edges() -> None:
    uow = _FakeUnitOfWork()
    use_case = RecomputeKnowledgeGraphUseCase(cast("IUnitOfWork", uow))

    result = await use_case(user_id=uuid.uuid4(), document_limit=80, topic_limit=20)

    assert len(result.edges) == 3
    assert uow.knowledge_graph_repo.replaced_edge_count == 1
    assert uow.committed


async def test_create_knowledge_graph_concern_persists_review_item() -> None:
    uow = _FakeUnitOfWork()
    use_case = CreateKnowledgeGraphConcernUseCase(cast("IUnitOfWork", uow))
    user_id = uuid.uuid4()

    result = await use_case(
        user_id=user_id,
        node_id="topic:python",
        node_kind="topic",
        node_label="python",
        message=" stale context ",
    )

    assert result.user_id == user_id
    assert result.node_id == "topic:python"
    assert result.message == "stale context"
    assert uow.committed
