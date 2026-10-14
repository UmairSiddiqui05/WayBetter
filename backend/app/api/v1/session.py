"""POST /session — anonymous, server-issued session tokens (N-06, D-15).

Minimal for the demo sprint: a random id signed with SESSION_TOKEN_SECRET. No storage;
a token is valid if its signature checks out. Rate limiting per token comes later (N-05).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

router = APIRouter()


class SessionResponse(BaseModel):
    session_token: str


def _sign(request: Request, session_id: str) -> str:
    secret = request.app.state.settings.session_token_secret.get_secret_value().encode()
    return hmac.new(secret, session_id.encode(), hashlib.sha256).hexdigest()[:32]


@router.post("/session", status_code=status.HTTP_201_CREATED, response_model=SessionResponse)
def create_session(request: Request) -> SessionResponse:
    session_id = secrets.token_urlsafe(16)
    return SessionResponse(session_token=f"{session_id}.{_sign(request, session_id)}")


def require_session(
    request: Request, x_session_token: Annotated[str | None, Header()] = None
) -> str:
    """Dependency for endpoints the contract marks with the sessionToken scheme."""
    if x_session_token and "." in x_session_token:
        session_id, signature = x_session_token.rsplit(".", 1)
        if hmac.compare_digest(signature, _sign(request, session_id)):
            return session_id
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or invalid X-Session-Token")
