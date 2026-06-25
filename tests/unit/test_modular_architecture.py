import ast
from pathlib import Path

MIGRATED_ENDPOINT_MODULES = (
    "api_keys",
    "auth",
    "chats",
    "collections",
    "compare",
    "conflicts",
    "documents",
    "drafts",
    "exports",
    "ingestion",
    "integrations",
    "knowledge_gaps",
    "knowledge_graph",
    "learning_goals",
    "observability",
    "public_api",
    "public_shares",
    "query",
    "repo_syncs",
    "review",
    "stats",
    "topics",
    "users",
    "webhooks",
    "workspaces",
)


def test_feature_modules_do_not_contain_convention_placeholders() -> None:
    placeholder_sources = {
        "__all__: list[str] = []",
        "from src.auth.auth import CurrentUser, get_current_user\n\n__all__ = [\"CurrentUser\", \"get_current_user\"]",
    }

    for path in Path("src").glob("*/*.py"):
        if path.name == "__init__.py":
            continue
        assert path.read_text().strip() not in placeholder_sources, str(path)


def test_central_api_router_owns_v1_prefix() -> None:
    from src.api import router

    assert router.prefix == "/api/v1"
    assert router.routes


def test_worker_registry_exposes_feature_task_modules() -> None:
    from src.worker.registry import TASK_MODULES

    assert "src.documents.tasks" in TASK_MODULES
    assert "src.notifications.tasks" in TASK_MODULES
    assert "src.repo_syncs.tasks" in TASK_MODULES
    assert not Path("src/worker/composition.py").exists()


def test_global_document_repository_session_is_not_reintroduced() -> None:
    assert not Path("src/kit/ports/persistence").exists()
    assert not Path("src/kit/unit_of_work.py").exists()
    assert not Path("src/kit/sqlalchemy_unit_of_work.py").exists()

    old_session_name = "Unit" + "OfWork"
    old_document_session_name = "Document" + "RepositorySession"
    for path in Path("src").rglob("*.py"):
        source = path.read_text()
        assert "src.kit.unit_of_work" not in source, str(path)
        assert "SQLAlchemy" + old_session_name not in source, str(path)
        assert old_session_name not in source, str(path)
        assert old_document_session_name not in source, str(path)

    document_repository_source = Path("src/documents/document_repository.py").read_text()
    assert "self.session" not in document_repository_source
    for path in Path("src/documents").rglob("*.py"):
        assert "document_repo.session" not in path.read_text(), str(path)


def test_single_implementation_document_interfaces_are_not_reintroduced() -> None:
    forbidden_names = (
        "I" + "DocumentTagSync",
        "I" + "DocumentTopicSync",
        "I" + "TextChunker",
    )
    for root in (Path("src"), Path("tests")):
        for path in root.rglob("*.py"):
            source = path.read_text()
            for name in forbidden_names:
                assert name not in source, str(path)


def test_collection_does_not_reintroduce_parallel_entity_model() -> None:
    assert not Path("src/collections/entity.py").exists()
    repository_source = Path("src/collections/repository.py").read_text()
    assert "_to_entity" not in repository_source
    assert "_to_model" not in repository_source


def test_documents_do_not_reintroduce_parallel_entity_models() -> None:
    assert not Path("src/documents/entity.py").exists()
    assert not Path("src/documents/chunk_entity.py").exists()
    for repository_path in (
        Path("src/documents/document_repository.py"),
        Path("src/documents/chunk_repository.py"),
    ):
        source = repository_path.read_text()
        assert "_to_entity" not in source
        assert "_to_model" not in source


def test_users_do_not_reintroduce_parallel_entity_or_email_value_object() -> None:
    assert not Path("src/users/entity.py").exists()
    assert not Path("src/users/email.py").exists()
    repository_source = Path("src/users/repository.py").read_text()
    assert "_to_entity" not in repository_source
    assert "_to_model" not in repository_source


def test_external_client_contracts_stay_with_client_modules() -> None:
    assert not Path("src/auth/repository.py").exists()
    assert not Path("src/integrations/clients.py").exists()
    repository_source = Path("src/integrations/repository.py").read_text()
    forbidden_names = (
        "I" + "GitHubRepositoryClient",
        "I" + "NotionExportClient",
        "I" + "NotionOAuthClient",
        "I" + "NotionWorkspaceClient",
        "I" + "WebResourceFetcher",
    )
    for name in forbidden_names:
        assert name not in repository_source


def test_clean_architecture_ports_are_not_reintroduced() -> None:
    assert not Path("src/kit/ports").exists()
    forbidden_names = {
        "I" + "Cache",
        "I" + "ConversationStore",
        "I" + "DocumentStatusCache",
        "I" + "NotificationSender",
        "I" + "QueryTracer",
        "I" + "TaskDispatcher",
        "I" + "TokenCipher",
        "JWTService" + "Protocol",
    }
    for path in Path("src").rglob("*.py"):
        source = path.read_text()
        assert "src.kit.ports" not in source, str(path)
        for name in forbidden_names:
            assert name not in source, f"{path}: {name}"


def test_dto_layer_is_not_reintroduced() -> None:
    for path in Path("src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert not node.name.endswith("DTO"), f"DTO reintroduced: {path}:{node.lineno}"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert "_dto" not in node.name, f"DTO mapper reintroduced: {path}:{node.lineno}"


def test_command_mapping_layer_is_not_reintroduced() -> None:
    for path in Path("src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert not node.name.endswith("Command"), f"command payload reintroduced: {path}:{node.lineno}"
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert not node.name.startswith("to_") or not node.name.endswith("_command"), (
                    f"command mapper reintroduced: {path}:{node.lineno}"
                )


def test_business_services_are_framework_independent() -> None:
    service_paths = list(Path("src").rglob("service.py"))
    service_paths.extend(
        (
            Path("src/documents/exports.py"),
            Path("src/documents/ingestion.py"),
            Path("src/documents/notes.py"),
        )
    )
    for path in service_paths:
        source = path.read_text()
        assert "from fastapi" not in source, str(path)
        assert "import fastapi" not in source, str(path)
        assert "Depends(" not in source, str(path)


def test_collapsed_response_contracts_are_not_duplicated_as_dtos() -> None:
    forbidden_names = (
        "Flashcard" + "DTO",
        "Quiz" + "DTO",
        "LearningPath" + "DTO",
        "CollectionWorkspace" + "DTO",
        "DocumentChunk" + "DTO",
        "DocumentQuestionHistory" + "DTO",
        "NoteVersion" + "DTO",
    )
    for path in Path("src").rglob("schemas.py"):
        source = path.read_text()
        for name in forbidden_names:
            assert f"class {name}" not in source, str(path)


def test_repository_bundles_are_not_reintroduced() -> None:
    for path in Path("src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                assert not node.name.endswith("Repositories"), f"repository bundle was reintroduced: {path}:{node.lineno}"


def test_request_services_do_not_commit_transactions() -> None:
    commit_boundaries = {
        "src/postgres.py:get_db_session",
        "src/documents/processing.py:DocumentProcessingService.acknowledge",
        "src/documents/processing.py:DocumentProcessingService._claim_outbox",
        "src/documents/processing.py:DocumentProcessingService._dispatch_outbox_item",
        "src/documents/processing.py:DocumentProcessingService._mark_outbox_dispatched",
        "src/documents/processing.py:DocumentProcessingService._mark_outbox_failed",
        "src/documents/processing.py:DocumentProcessingService._mark_document_failed",
        "src/documents/processing.py:DocumentIngestionProcessor._mark_processing",
        "src/documents/processing.py:DocumentEmbeddingProcessor.__call__",
        "src/documents/processing.py:ImageDocumentProcessor.__call__",
        "src/documents/services/enrichment/enrichment_service.py:EnrichmentService.enrich_document",
        "src/notifications/service.py:_TelegramDeliveryRunner._create_delivery",
        "src/notifications/service.py:_TelegramDeliveryRunner._mark_sent",
        "src/notifications/service.py:_TelegramDeliveryRunner._mark_skipped",
        "src/notifications/service.py:_TelegramDeliveryRunner._mark_failed",
        "src/public_shares/service.py:PublicAskLedger.reserve",
        "src/public_shares/service.py:PublicAskLedger.complete",
        "src/public_shares/service.py:PublicAskLedger.fail",
        "src/repo_syncs/service.py:RepoSyncRunner._sync_files",
        "src/repo_syncs/service.py:RepoSyncRunner._set_repo_sync_state",
        "src/repo_syncs/service.py:RepoSyncOutboxDrainer._claim_outbox",
        "src/repo_syncs/service.py:RepoSyncOutboxDrainer._dispatch_outbox_item",
        "src/repo_syncs/service.py:RepoSyncOutboxDrainer._mark_outbox_dispatched",
        "src/repo_syncs/service.py:RepoSyncOutboxDrainer._mark_outbox_failed",
        "src/repo_syncs/service.py:RepoSyncOutboxDrainer._mark_repo_sync_failed",
        "src/worker/document_failure.py:_mark_document_status",
    }

    for path in Path("src").rglob("*.py"):
        tree = ast.parse(path.read_text())
        parents: dict[ast.AST, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != "commit":
                continue

            scopes: list[str] = []
            current = parents.get(node)
            while current is not None:
                if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    scopes.append(current.name)
                current = parents.get(current)
            qualified_name = ".".join(reversed(scopes))
            boundary = f"{path}:{qualified_name}"
            assert boundary in commit_boundaries, f"request transaction committed outside an approved boundary: {boundary}"


def test_documents_service_does_not_own_collection_services() -> None:
    source = Path("src/documents/service.py").read_text()
    forbidden_fragments = (
        "CreateCollection" + "UseCase",
        "ListCollections" + "UseCase",
        "GetCollectionWorkspace" + "UseCase",
        "UpdateCollection" + "UseCase",
        "DeleteCollection" + "UseCase",
        "get_list_collections_" + "use_case",
    )
    for fragment in forbidden_fragments:
        assert fragment not in source


def test_migrated_endpoint_modules_do_not_use_removed_injection_or_presentation_layers() -> None:
    for module in MIGRATED_ENDPOINT_MODULES:
        source = Path("src", module, "endpoints.py").read_text()
        assert "src." + "presentation" not in source
        assert "FromDishka" not in source
        assert "@inject" not in source


def test_removed_layers_have_been_removed() -> None:
    assert not Path("src/application").exists()
    assert not Path("src/presentation").exists()
    assert not Path("src/core").exists()
    assert not Path("src/domain").exists()
    assert not Path("src/infrastructure").exists()
    assert not Path("src/dependencies.py").exists()

    removed_imports = (
        "src." + "application",
        "src." + "presentation",
        "src." + "core",
        "src." + "domain",
        "src." + "infrastructure",
        "src." + "dependencies",
    )
    for root in (Path("src"), Path("tests"), Path("scripts"), Path("alembic")):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            source = "\n".join(
                line
                for line in path.read_text().splitlines()
                if line.startswith("from src.") or line.startswith("import src.")
            )
            for removed_import in removed_imports:
                assert removed_import not in source, str(path)


def test_feature_local_layer_folders_are_not_reintroduced() -> None:
    forbidden_names = {"dtos", "ports", "use" + "_cases"}

    for path in Path("src").rglob("*"):
        if not path.is_dir():
            continue
        if path.name in forbidden_names:
            raise AssertionError(f"feature-local layer folder was reintroduced: {path}")


def test_feature_local_layer_imports_are_not_reintroduced() -> None:
    forbidden_import_fragments = (".dtos.", ".ports.", ".use" + "_cases.")

    for root in (Path("src"), Path("tests"), Path("scripts")):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            import_lines = [
                line
                for line in path.read_text().splitlines()
                if line.startswith("from src.") or line.startswith("import src.")
            ]
            for line in import_lines:
                for fragment in forbidden_import_fragments:
                    assert fragment not in line, f"{path}: {line}"


def test_endpoint_modules_keep_persistence_logic_out_of_routes() -> None:
    forbidden_fragments = (
        "from sqlalchemy",
        "import sqlalchemy",
        ".execute(",
        "Redis.from_url",
        "FernetTokenCipher",
        "NotionExportClient",
    )

    for module in MIGRATED_ENDPOINT_MODULES:
        path = Path("src", module, "endpoints.py")
        source = path.read_text()
        for fragment in forbidden_fragments:
            assert fragment not in source, f"{path}: {fragment}"


def test_http_redis_lifecycle_is_owned_by_shared_kit() -> None:
    lifecycle_source = Path("src/lifecycle.py").read_text()
    assert "from src.kit.cache.redis import dispose_redis" in lifecycle_source
    assert "src.auth" not in lifecycle_source
    assert "src.documents" not in lifecycle_source
    assert "src.query" not in lifecycle_source

    redis_factories = []
    for path in Path("src").rglob("*.py"):
        if "def get_redis(" in path.read_text():
            redis_factories.append(path)
    assert redis_factories == [Path("src/kit/cache/redis.py")]


def test_dependency_override_container_layer_has_been_removed_from_production_code() -> None:
    assert not Path("src/core/container.py").exists()
    assert not Path("src/core/providers").exists()

    forbidden_fragments = (
        "from dishka",
        "import dishka",
        "setup_dishka",
        "dishka" + "_container",
        "FromDishka",
        "@inject",
    )
    for path in Path("src").rglob("*.py"):
        source = path.read_text()
        for fragment in forbidden_fragments:
            assert fragment not in source, f"{path}: {fragment}"

    test_container_state = "dependency_override_" + "container"
    for path in Path("tests").rglob("*.py"):
        if path.resolve() == Path(__file__).resolve():
            continue
        assert test_container_state not in path.read_text(), str(path)


def test_feature_services_do_not_reintroduce_old_service_layer_names() -> None:
    old_factory_fragment = "use" + "_case"
    old_class_fragment = "Use" + "Case"
    forbidden_kit_ports = (
        Path("src/kit/ports/cache/document_status_cache.py"),
        Path("src/kit/ports/ingestion/task_dispatcher.py"),
        Path("src/kit/ports/ingestion/text_chunker.py"),
    )
    for path in forbidden_kit_ports:
        assert not path.exists(), str(path)

    for path in Path("src").rglob("*.py"):
        source = path.read_text()
        assert "src." + "infrastructure" not in source, str(path)
        assert old_factory_fragment not in source, str(path)
        for line in source.splitlines():
            stripped = line.strip()
            assert not (stripped.startswith("class ") and old_class_fragment in stripped), (
                f"{path}: old service class declaration remains"
            )
            assert not (old_class_fragment in stripped and "=" in stripped), f"{path}: old service alias remains"
