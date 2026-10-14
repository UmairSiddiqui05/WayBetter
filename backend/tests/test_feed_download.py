"""Credentialed feed downloads (N-09): token exchange, zip guard, no secret leakage."""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import asdict
from pathlib import Path

import httpx
import pytest

from app.ingestion.feeds import FeedDownloadError, build_metadata, download_feed
from app.regions.schema import FeedSource

TOKEN_URL = "https://feeds.example.test/getToken"
FEED_URL = "https://feeds.example.test/getGTFS"
ENV = {"FEED_USER": "someone", "FEED_PASS": "s3cret-pass"}


def _feed() -> FeedSource:
    return FeedSource.model_validate(
        {
            "feed_id": "example_rail",
            "agency_name": "Example Rail",
            "modes": ["commuter_rail"],
            "url": FEED_URL,
            "requires_credentials": True,
            "credential_env": ["FEED_USER", "FEED_PASS"],
            "auth": {
                "token_url": TOKEN_URL,
                "username_field": "username",
                "password_field": "password",
                "token_response_field": "UserToken",
                "token_form_field": "token",
            },
            "license": {"name": "Example terms"},
        }
    )


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agency.txt", "agency_id,agency_name\n1,Example\n")
    return buffer.getvalue()


def _client(feed_body: bytes, token_payload: dict[str, str] | None = None) -> httpx.Client:
    seen: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[str(request.url)] = request.read()
        if str(request.url) == TOKEN_URL:
            return httpx.Response(200, json=token_payload or {"UserToken": "tok-123"})
        if str(request.url) == FEED_URL:
            assert b"tok-123" in request.read(), "feed request must carry the token"
            return httpx.Response(200, content=feed_body)
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.seen = seen  # type: ignore[attr-defined]
    return client


def test_token_is_exchanged_then_used_for_the_archive(tmp_path: Path) -> None:
    client = _client(_zip_bytes())

    result = download_feed(_feed(), tmp_path, client=client, env=ENV)

    assert result.path.read_bytes().startswith(b"PK")
    assert b"s3cret-pass" in client.seen[TOKEN_URL]  # type: ignore[attr-defined]


def test_missing_credentials_fail_before_any_request(tmp_path: Path) -> None:
    client = _client(_zip_bytes())

    with pytest.raises(FeedDownloadError, match="FEED_USER"):
        download_feed(_feed(), tmp_path, client=client, env={})
    assert client.seen == {}  # type: ignore[attr-defined]


def test_rejected_login_is_an_error(tmp_path: Path) -> None:
    client = _client(_zip_bytes(), token_payload={"Authenticated": "False"})

    with pytest.raises(FeedDownloadError, match="no token"):
        download_feed(_feed(), tmp_path, client=client, env=ENV)


def test_non_zip_response_never_replaces_a_good_archive(tmp_path: Path) -> None:
    good = _zip_bytes()
    (tmp_path / "example_rail.zip").write_bytes(good)
    client = _client(b'{"errorMessage": "Daily limit reached"}')

    with pytest.raises(FeedDownloadError, match="not a zip"):
        download_feed(_feed(), tmp_path, client=client, env=ENV)
    assert (tmp_path / "example_rail.zip").read_bytes() == good
    assert not list(tmp_path.glob("*.part"))


def test_provenance_record_carries_no_credentials(tmp_path: Path) -> None:
    feed = _feed()
    result = download_feed(feed, tmp_path, client=_client(_zip_bytes()), env=ENV)

    meta = build_metadata(feed, result, feed_version=None, agency_ids=[], errors=[], warnings=[])
    written = json.dumps(asdict(meta))

    for secret in ("s3cret-pass", "someone", "tok-123"):
        assert secret not in written
