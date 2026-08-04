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
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog

from app.regions.schema import FeedSource

log = structlog.get_logger(__name__)

DOWNLOAD_TIMEOUT_SECONDS = 120.0
CHUNK_BYTES = 1024 * 256


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
) -> DownloadResult:
    """Fetch one feed into `gtfs_dir`, replacing the previous archive atomically.

    Raises rather than guessing when a feed is blocked, credentialed, or has no
    URL — a half-configured feed must not look like a successful ingest.
    """
    if feed.blocked_reason:
        raise FeedDownloadError(f"{feed.feed_id}: blocked — {feed.blocked_reason.strip()}")
    if feed.requires_credentials:
        raise FeedDownloadError(
            f"{feed.feed_id}: needs credentials from {', '.join(feed.credential_env)}; "
            "credentialed downloads are not implemented (no portal account exists yet)"
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
        # Download to a temp file in the same directory so a failure mid-stream
        # never leaves a truncated archive where a valid one used to be.
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                with client.stream("GET", feed.url) as response:
                    response.raise_for_status()
                    for chunk in response.iter_bytes(CHUNK_BYTES):
                        tmp.write(chunk)
            except httpx.HTTPError as exc:
                tmp_path.unlink(missing_ok=True)
                raise FeedDownloadError(f"{feed.feed_id}: download failed — {exc}") from exc
    finally:
        if owns_client:
            client.close()

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
