from src.api_keys.endpoints import router as api_key_router
from src.auth.endpoints import router as auth_router
from src.chats.endpoints import router as chat_router
from src.collections.endpoints import router as collection_router
from src.compare.endpoints import router as compare_router
from src.conflicts.endpoints import router as conflict_router
from src.documents.endpoints import router as document_router
from src.drafts.endpoints import router as draft_router
from src.exports.endpoints import router as export_router
from src.ingestion.endpoints import router as ingestion_router
from src.integrations.endpoints import router as integration_router
from src.knowledge_gaps.endpoints import router as knowledge_gap_router
from src.knowledge_graph.endpoints import router as knowledge_graph_router
from src.learning_goals.endpoints import router as learning_goal_router
from src.observability.endpoints import router as observability_router
from src.public_api.endpoints import router as public_api_router
from src.public_shares.endpoints import router as public_share_router
from src.query.endpoints import router as query_router
from src.repo_syncs.endpoints import router as repo_sync_router
from src.review.endpoints import router as review_router
from src.routing import APIRouter
from src.stats.endpoints import router as stats_router
from src.topics.endpoints import router as topic_router
from src.users.endpoints import router as user_router
from src.webhooks.endpoints import router as webhook_router
from src.workspaces.endpoints import router as workspace_router

router = APIRouter(prefix="/api/v1")

router.include_router(auth_router)
router.include_router(api_key_router)
router.include_router(public_share_router)
router.include_router(user_router)
router.include_router(collection_router)
router.include_router(workspace_router)
router.include_router(compare_router)
router.include_router(conflict_router)
router.include_router(document_router)
router.include_router(draft_router)
router.include_router(export_router)
router.include_router(ingestion_router)
router.include_router(integration_router)
router.include_router(repo_sync_router)
router.include_router(webhook_router)
router.include_router(knowledge_gap_router)
router.include_router(knowledge_graph_router)
router.include_router(learning_goal_router)
router.include_router(chat_router)
router.include_router(query_router)
router.include_router(review_router)
router.include_router(stats_router)
router.include_router(topic_router)
router.include_router(observability_router)
router.include_router(public_api_router)

__all__ = ["router"]
