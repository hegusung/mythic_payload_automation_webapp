from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = 'Mythic Payload WebApp'
    api_prefix: str = '/api'
    database_url: str = 'sqlite:///./mythic_payloads.db'
    mythic_url: str | None = None
    mythic_username: str | None = None
    mythic_password: str | None = None
    cors_origins: list[str] = ['*']
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')


settings = Settings()
