"""Feed downloading with provenance recording (N-08, N-09).

Every download writes a sidecar `<feed_id>.meta.json` next to the archive
carrying source URL, licence, retrieval timestamp, SHA-256, and the feed version
the archive declares. The archives themselves are gitignored; **the metadata is
committed**, so the repo always states what data a build was made from even
though it does not carry the data.

Resumability is by checksum, not by byte range: a re-run that finds an unchanged
archive skips the download and says so. Agency GTFS endpoints are plain static
files that rarely honour `Range`, and re-downloading five megabytes is cheaper
than reasoning about a half-written zip.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

from app.regions.schema import FeedSource, TokenAuth

log = structlog.get_logger(__name__)

DOWNLOAD_TIMEOUT_SECONDS = 120.0
CHUNK_BYTES = 1024 * 256
ZIP_MAGIC = b"PK"


@dataclass(frozen=True, slots=True)
class FeedMetadata:
    """The provenance record N-09 requires. Committed; the archive is not."""

    feed_id: str
    agency_name: str
    source_url: str
    retrieved_at: str
    sha256: str
    size_bytes: int
    feed_version: str | None
    license_name: str
    license_url: str | None
    license_verified: bool
    attribution: str | None
    agency_ids: list[str]
    validation_errors: list[str]
    validation_warnings: list[str]

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(asdict(self), indent=2) + "\n", encoding="utf-8")
        return target

    @classmethod
    def read(cls, path: str | Path) -> FeedMetadata:
        return cls(**json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class DownloadResult:
    feed_id: str
    path: Path
    sha256: str
    size_bytes: int
    changed: bool
    """False when the freshly downloaded bytes match what was already on disk."""


class FeedDownloadError(RuntimeError):
    pass


def archive_path(feed: FeedSource, gtfs_dir: Path) -> Path:
    return gtfs_dir / f"{feed.feed_id}.zip"


def metadata_path(feed: FeedSource, gtfs_dir: Path) -> Path:
    return gtfs_dir / f"{feed.feed_id}.meta.json"


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_feed(
    feed: FeedSource,
    gtfs_dir: str | Path,
    *,
    client: httpx.Client | None = None,
    force: bool = False,
    env: Mapping[str, str] | None = None,
) -> DownloadResult:
    """Fetch one feed into `gtfs_dir`, replacing the previous archive atomically.

    Raises rather than guessing when a feed is blocked, credentialed, or has no
    URL — a half-configured feed must not look like a successful ingest.
    Credentials are read from `env` (default: the process environment) and are
    never logged or written to the provenance record.
    """
    env = os.environ if env is None else env
    if feed.blocked_reason:
        raise FeedDownloadError(f"{feed.feed_id}: blocked — {feed.blocked_reason.strip()}")
    if feed.requires_credentials:
        if not feed.auth:
            raise FeedDownloadError(
                f"{feed.feed_id}: requires credentials but declares no auth block"
            )
        if not feed.has_credentials(env):
            raise FeedDownloadError(
                f"{feed.feed_id}: set {', '.join(feed.credential_env)} in .env first"
            )
    if not feed.url:
        raise FeedDownloadError(f"{feed.feed_id}: no url configured")

    directory = Path(gtfs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    target = archive_path(feed, directory)
    previous_hash = sha256_file(target) if target.exists() else None

    owns_client = client is None
    client = client or httpx.Client(timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        log.info("feed_download_start", feed_id=feed.feed_id, url=feed.url)
        if feed.auth:
            token = _fetch_token(feed.feed_id, feed.auth, feed.credential_env, env, client)
            request = client.build_request(
                "POST", feed.url, files={feed.auth.token_form_field: (None, token)}
            )
        else:
            request = client.build_request("GET", feed.url)
        # Download to a temp file in the same directory so a failure mid-stream
        # never leaves a truncated archive where a valid one used to be.
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                response = client.send(request, stream=True)
                try:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(CHUNK_BYTES):
                        tmp.write(chunk)
                finally:
                    response.close()
            except httpx.HTTPError as exc:
                tmp_path.unlink(missing_ok=True)
                raise FeedDownloadError(f"{feed.feed_id}: download failed — {exc}") from exc
    finally:
        if owns_client:
            client.close()

    # An API that answers 200 with a JSON error must not replace a good archive.
    with tmp_path.open("rb") as handle:
        if handle.read(len(ZIP_MAGIC)) != ZIP_MAGIC:
            tmp_path.unlink(missing_ok=True)
            raise FeedDownloadError(f"{feed.feed_id}: response is not a zip archive")

    new_hash = sha256_file(tmp_path)
    size = tmp_path.stat().st_size
    changed = force or previous_hash != new_hash

    if changed:
        shutil.move(str(tmp_path), target)
    else:
        tmp_path.unlink(missing_ok=True)

    log.info(
        "feed_download_done",
        feed_id=feed.feed_id,
        size_bytes=size,
        changed=changed,
        sha256=new_hash[:16],
    )
    return DownloadResult(
        feed_id=feed.feed_id,
        path=target,
        sha256=new_hash,
        size_bytes=size,
        changed=changed,
    )


def _fetch_token(
    feed_id: str,
    auth: TokenAuth,
    credential_env: tuple[str, ...],
    env: Mapping[str, str],
    client: httpx.Client,
) -> str:
    """Exchange portal credentials for a short-lived download token."""
    username_var, password_var = credential_env
    form = {
        auth.username_field: (None, env[username_var].strip()),
        auth.password_field: (None, env[password_var].strip()),
    }
    try:
        response = client.post(auth.token_url, files=form)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise FeedDownloadError(f"{feed_id}: token request failed — {exc}") from exc
    token = payload.get(auth.token_response_field) if isinstance(payload, dict) else None
    if not token:
        # The payload carries no secret when authentication fails; keys only, to be safe.
        keys = sorted(payload) if isinstance(payload, dict) else type(payload).__name__
        raise FeedDownloadError(f"{feed_id}: portal returned no token (response keys: {keys})")
    return str(token)


def build_metadata(
    feed: FeedSource,
    result: DownloadResult,
    *,
    feed_version: str | None,
    agency_ids: list[str],
    errors: list[str],
    warnings: list[str],
    retrieved_at: datetime | None = None,
) -> FeedMetadata:
    return FeedMetadata(
        feed_id=feed.feed_id,
        agency_name=feed.agency_name,
        source_url=feed.url or "",
        retrieved_at=(retrieved_at or datetime.now(UTC)).isoformat(),
        sha256=result.sha256,
        size_bytes=result.size_bytes,
        feed_version=feed_version,
        license_name=feed.license.name,
        license_url=feed.license.url,
        license_verified=feed.license.verified,
        attribution=feed.license.attribution,
        agency_ids=agency_ids,
        validation_errors=errors,
        validation_warnings=warnings,
    )
