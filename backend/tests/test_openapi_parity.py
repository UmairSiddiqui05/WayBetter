"""OpenAPI parity with docs/api-spec.yaml — the API contract (CLAUDE.md precedence #2).

The generated schema must stay a *subset* of the contract: every path the app
serves has to be defined in the contract with the same methods. It is a subset
rather than an exact match because endpoints land incrementally (A1 ships zero
contract endpoints, A3 ships them all). `test_contract_coverage_report` prints
what is still missing so the gap is visible without failing the build; A3 flips
the subset assertion into an equality assertion when it finishes wiring.
"""

from __future__ import annotations

from fastapi import FastAPI

from app import __version__
from app.config import API_V1_PREFIX
from app.main import API_DESCRIPTION, API_TITLE

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "options", "head", "patch", "trace"})


def _contract_operations(contract: dict) -> set[tuple[str, str]]:
    """Contract paths are relative to `servers[0].url`; the app serves absolute paths."""
    prefix = contract["servers"][0]["url"].rstrip("/")
    return {
        (f"{prefix}{path}", method.upper())
        for path, item in contract["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def _app_operations(app: FastAPI) -> set[tuple[str, str]]:
    return {
        (path, method.upper())
        for path, item in app.openapi()["paths"].items()
        for method in item
        if method in HTTP_METHODS
    }


def test_contract_server_prefix_matches_code(api_contract: dict) -> None:
    assert api_contract["servers"][0]["url"] == API_V1_PREFIX


def test_openapi_info_mirrors_the_contract(app: FastAPI, api_contract: dict) -> None:
    info = app.openapi()["info"]

    assert info["title"] == api_contract["info"]["title"] == API_TITLE
    assert info["version"] == api_contract["info"]["version"] == __version__
    assert " ".join(api_contract["info"]["description"].split()) == API_DESCRIPTION


def test_app_serves_no_path_outside_the_contract(app: FastAPI, api_contract: dict) -> None:
    undeclared = _app_operations(app) - _contract_operations(api_contract)

    assert not undeclared, (
        "These operations are not in docs/api-spec.yaml. The contract governs: "
        f"add them there (with a version bump + PROGRESS.md entry) or remove them. {undeclared}"
    )


def test_ops_endpoints_stay_off_the_versioned_surface(app: FastAPI) -> None:
    """Health checks are ops, not contract — see app/api/health.py."""
    served = {path for path, _ in _app_operations(app)}

    assert "/healthz" not in served
    assert "/readyz" not in served


def test_contract_coverage_report(app: FastAPI, api_contract: dict) -> None:
    implemented = _app_operations(app)
    declared = _contract_operations(api_contract)
    missing = sorted(declared - implemented)

    print(f"\nContract coverage: {len(implemented)}/{len(declared)} operations implemented.")
    for path, method in missing:
        print(f"  not yet implemented (A3): {method} {path}")

    assert implemented <= declared
