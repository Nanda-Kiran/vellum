"""Shared Google auth and service builders for single-tenant integrations."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from vellum.settings import get_settings

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]
_CREDS: Credentials | service_account.Credentials | None = None
_SERVICES: dict[tuple[str, str], Any] = {}
_LOCK = asyncio.Lock()


def _load_credentials() -> Credentials | service_account.Credentials:
    settings = get_settings()
    credentials_path = Path(settings.google_credentials_path)
    if not settings.google_credentials_path:
        raise ValueError("GOOGLE_CREDENTIALS_PATH is not configured")
    if not credentials_path.exists():
        raise FileNotFoundError(f"Google credentials file not found: {credentials_path}")

    with credentials_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if payload.get("type") == "service_account":
        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=_SCOPES,
        )

    creds = Credentials.from_authorized_user_file(str(credentials_path), _SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


async def get_google_service(service_name: str, version: str) -> Any:
    """Return a cached google-api-python-client service instance."""
    global _CREDS
    key = (service_name, version)
    async with _LOCK:
        if key in _SERVICES:
            return _SERVICES[key]
        if _CREDS is None:
            _CREDS = await asyncio.to_thread(_load_credentials)
        service = await asyncio.to_thread(
            build,
            service_name,
            version,
            credentials=_CREDS,
            cache_discovery=False,
        )
        _SERVICES[key] = service
        return service
