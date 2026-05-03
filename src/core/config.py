from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    JWT_SECRET: str
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    JWT_ALGORITHM: str = "HS256"
    DEBUG: bool = False

    DATABASE_URL: str
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    REDIS_URL: str
    REDIS_EMBEDDING_CACHE_TTL: int = 3600
    REDIS_DOC_STATUS_TTL: int = 3600
    REDIS_CONVERSATION_TTL: int = 604800

    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

    RABBITMQ_URL: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_EMBEDDING_DIMENSIONS: int = 1536
    OPENAI_LLM_MODEL: str = "gpt-4o-mini"

    FILE_STORAGE_TYPE: str = "local"
    LOCAL_STORAGE_PATH: str = "./storage"
    AWS_REGION: str = "eu-central-1"
    AWS_S3_BUCKET: str = ""
    AWS_S3_PREFIX: str = "uploads"

    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    FRONTEND_URL: str

    # OCR / Image preprocessing tuning
    OCR_TESSERACT_PSM: str = "3"
    OCR_TESSERACT_OEM: str = "3"
    OCR_TESSERACT_LANG: str = "eng"
    OCR_PREPROCESS_MIN_DIMENSION: int = 800
    OCR_PREPROCESS_AUTOCONTRAST: bool = True
    OCR_PREPROCESS_DENOISE: bool = True
    OCR_PREPROCESS_SHARPEN: bool = True
    OCR_PREPROCESS_DESKEW: bool = False
    OCR_PREPROCESS_THRESHOLD: bool = False

    # Retrieval reranker
    RERANKER_ENABLED: bool = True
    RERANKER_TOP_K: int = 10

    # Evaluation
    EVAL_SCORER: str = "heuristic"

    # Deduplication threshold (cosine similarity)
    DEDUPLICATION_SIMILARITY_THRESHOLD: float = 0.95


settings = Settings()  # pyright: ignore[reportCallIssue]
