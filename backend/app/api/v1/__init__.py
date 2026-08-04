"""Version 1 of the public API — the surface defined by docs/api-spec.yaml."""

from app.api.v1.router import api_router

__all__ = ["api_router"]
