from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    JWT_SECRET: str
    DEBUG: bool = False
    
    DATABASE_URL: str

    REDIS_URL: str

    RABBITMQ_URL: str

    OPENAI_API_KEY: str

    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""

    FRONTEND_URL: str

settings = Settings()
