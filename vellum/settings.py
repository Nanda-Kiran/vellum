"""Pydantic settings loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class VellumSettings(BaseSettings):
    """Runtime configuration for Vellum services and integrations."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    groq_api_key: str = ""
    slack_bot_token: str = ""
    slack_app_token: str = ""
    plaid_client_id: str = ""
    plaid_secret: str = ""
    plaid_env: str = "sandbox"
    stripe_api_key: str = ""
    google_credentials_path: str = ""
    vellum_db_path: str = "./vellum.db"
    vellum_policy_path: str = "./data/policy.md"


@lru_cache(maxsize=1)
def get_settings() -> VellumSettings:
    """Return a cached settings instance."""
    return VellumSettings()

