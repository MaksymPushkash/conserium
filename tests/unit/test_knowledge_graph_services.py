import uuid
from datetime import UTC, datetime

from src.knowledge_graph.repository import (
    KnowledgeEdgeRecord,
    KnowledgeGraphConcernRecord,
    KnowledgeGraphRecord,
)
from src.knowledge_graph.schemas import KnowledgeGraphConcernCreateRequest
from src.knowledge_graph.service import (
    KnowledgeGraphFilters,
    KnowledgeGraphService,
)
from src.topics.repository import TopicOverrideRecord


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


class _FakeTopicRepository:
    def __init__(self) -> None:
        self.overrides: list[TopicOverrideRecord] = []

    async def list_overrides(self, user_id: uuid.UUID) -> list[TopicOverrideRecord]:
        return self.overrides


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False

    async def flush(self) -> None:
        self.committed = True


def _service() -> tuple[KnowledgeGraphService, _FakeSession, _FakeKnowledgeGraphRepository, _FakeTopicRepository]:
    session = _FakeSession()
    knowledge_graph_repo = _FakeKnowledgeGraphRepository()
    topic_repo = _FakeTopicRepository()
    return KnowledgeGraphService(session, knowledge_graph_repo, topic_repo), session, knowledge_graph_repo, topic_repo


def _filters(*, topic_name: str | None = None) -> KnowledgeGraphFilters:
    return KnowledgeGraphFilters(
        document_limit=80,
        topic_limit=20,
        collection_id=None,
        tag_name=None,
        topic_name=topic_name,
        document_type=None,
        recency_days=None,
    )


async def test_get_knowledge_graph_returns_topic_document_nodes_and_edges() -> None:
    service, session, knowledge_graph_repo, _topic_repo = _service()

    result = await service.get_graph(user_id=uuid.uuid4(), filters=_filters())

    assert {node.id for node in result.nodes} == {
        "topic:python",
        "document:00000000-0000-0000-0000-000000000001",
        "document:00000000-0000-0000-0000-000000000002",
    }
    assert {edge.target_id for edge in result.edges} == {
        "document:00000000-0000-0000-0000-000000000001",
        "document:00000000-0000-0000-0000-000000000002",
    }
    assert knowledge_graph_repo.replaced_edge_count == 0
    assert not session.committed
    fastapi_node = next(node for node in result.nodes if node.id == "document:00000000-0000-0000-0000-000000000001")
    assert fastapi_node.summary == "FastAPI summary"
    assert fastapi_node.suggested_questions == ["How does FastAPI work?"]


async def test_get_knowledge_graph_applies_topic_overrides() -> None:
    service, _session, _knowledge_graph_repo, topic_repo = _service()
    topic_repo.overrides = [
        TopicOverrideRecord(source_name="python", display_name="Backend", pinned=True, ignored=False),
    ]

    result = await service.get_graph(user_id=uuid.uuid4(), filters=_filters())

    topic_node = next(node for node in result.nodes if node.kind == "topic")
    assert topic_node.id == "topic:Backend"
    assert topic_node.label == "Backend"
    assert topic_node.source_names == ["python"]
    assert topic_node.is_pinned is True


async def test_get_knowledge_graph_filters_by_effective_topic_name() -> None:
    service, _session, _knowledge_graph_repo, topic_repo = _service()
    topic_repo.overrides = [
        TopicOverrideRecord(source_name="python", display_name="Backend", pinned=False, ignored=False),
    ]

    result = await service.get_graph(user_id=uuid.uuid4(), filters=_filters(topic_name="Backend"))

    assert {node.id for node in result.nodes} == {
        "topic:Backend",
        "document:00000000-0000-0000-0000-000000000001",
        "document:00000000-0000-0000-0000-000000000002",
    }


async def test_get_knowledge_graph_insights_uses_overrides_and_graph_signals() -> None:
    service, _session, _knowledge_graph_repo, topic_repo = _service()
    topic_repo.overrides = [
        TopicOverrideRecord(source_name="python", display_name="Backend", pinned=True, ignored=False),
        TopicOverrideRecord(source_name="legacy", display_name="Legacy", pinned=False, ignored=True),
    ]

    result = await service.get_insights(user_id=uuid.uuid4(), filters=_filters())

    insights = {item.kind: item for item in result.items}
    assert insights["pinned_topics"].count == 1
    assert insights["pinned_topics"].nodes[0].label == "Backend"
    assert insights["ignored_topics"].count == 1
    assert insights["ignored_topics"].nodes[0].label == "Legacy"


async def test_recompute_knowledge_graph_persists_document_edges() -> None:
    service, session, knowledge_graph_repo, _topic_repo = _service()

    result = await service.recompute(user_id=uuid.uuid4(), filters=_filters())

    assert len(result.edges) == 3
    assert knowledge_graph_repo.replaced_edge_count == 1
    assert session.committed


async def test_create_knowledge_graph_concern_persists_review_item() -> None:
    service, session, _knowledge_graph_repo, _topic_repo = _service()
    user_id = uuid.uuid4()

    result = await service.create_concern(
        user_id=user_id,
        payload=KnowledgeGraphConcernCreateRequest(
            node_id="topic:python",
            node_kind="topic",
            node_label="python",
            message=" stale context ",
        ),
    )

    assert result.node_id == "topic:python"
    assert result.message == "stale context"
    assert session.committed
