"""Async Google Drive integration wrapper."""

from __future__ import annotations

import asyncio
import io

from googleapiclient.http import MediaIoBaseUpload

from vellum.integrations.google_auth import get_google_service


async def upload_file(name: str, content: bytes, mime_type: str) -> str:
    """Upload a file to Drive and return the created file id."""
    service = await get_google_service("drive", "v3")
    media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime_type, resumable=False)
    response = await asyncio.to_thread(
        service.files().create(
            body={"name": name},
            media_body=media,
            fields="id",
        ).execute
    )
    return str(response.get("id", ""))


async def upload_audit_artifact(content: bytes, filename: str) -> str:
    """Upload an artifact to Drive and return a file identifier."""
    return await upload_file(name=filename, content=content, mime_type="application/octet-stream")

