"""Feed ingestion: download, validate, and assign canonical identity (N-03, N-08, N-09)."""

from app.ingestion.feeds import (
    DownloadResult,
    FeedDownloadError,
    FeedMetadata,
    archive_path,
    build_metadata,
    download_feed,
    metadata_path,
    sha256_file,
)
from app.ingestion.gtfs import (
    FeedArchive,
    GtfsArchiveError,
    GtfsStation,
    ValidationReport,
    extract_stations,
    validate_feed,
)
from app.ingestion.stations import (
    StationMapping,
    build_mappings,
    find_duplicate_canonical_ids,
    read_mapping_csv,
    slugify,
    write_mapping_csv,
)

__all__ = [
    "DownloadResult",
    "FeedArchive",
    "FeedDownloadError",
    "FeedMetadata",
    "GtfsArchiveError",
    "GtfsStation",
    "StationMapping",
    "ValidationReport",
    "archive_path",
    "build_mappings",
    "build_metadata",
    "download_feed",
    "extract_stations",
    "find_duplicate_canonical_ids",
    "metadata_path",
    "read_mapping_csv",
    "sha256_file",
    "slugify",
    "validate_feed",
    "write_mapping_csv",
]
