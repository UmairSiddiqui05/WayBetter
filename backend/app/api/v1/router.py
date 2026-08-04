"""Aggregate router for the versioned public API.

Intentionally empty in the A1 scaffold: every path in this router must exist in
docs/api-spec.yaml, and the endpoints themselves belong to A3 (Backend API &
Models). Adding a route here that the contract does not define will fail
tests/test_openapi_parity.py.

A3 wires its modules in as:

    from app.api.v1 import session, trip, stations, parking, feedback, providers

    api_router.include_router(session.router)
    ...
"""

from __future__ import annotations

from fastapi import APIRouter

api_router = APIRouter()
