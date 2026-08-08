from __future__ import annotations

import hashlib
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from bible_os.artifacts import ArtifactStoreError, put_file, validate_sha256

CHUNK_SIZE = 1024 * 1024
MAX_SIZE_MARGIN = 1024 * 1024
USER_AGENT = "Bible-OS-Acquisition-Archive/0.1 (+https://github.com/Razzleberrytt/bible-os)"


class AcquisitionArchiveError(ValueError):
    """Raised when a registered source cannot be safely archived as evidence."""


def _required_target_identity(target: Mapping[str, Any]) -> tuple[int, str]:
    try:
        expected_bytes = int(target["expected_bytes"])
        expected_sha256 = validate_sha256(target["expected_sha256"])
    except (KeyError, TypeError, ValueError, ArtifactStoreError) as error:
        raise AcquisitionArchiveError(
            "archival requires a pinned expected_bytes value and lowercase SHA-256 identity"
        ) from error
    if expected_bytes < 0:
        raise AcquisitionArchiveError("expected_bytes cannot be negative")
    return expected_bytes, expected_sha256


def archive_registered_source(
    target: Mapping[str, Any],
    store_root: Path,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Download, strictly verify, and retain a registered source observation by digest."""
    expected_bytes, expected_sha256 = _required_target_identity(target)
    try:
        requested_url = str(target["requested_url"])
        target_id = str(target["target_id"])
        source_id = str(target["source_id"])
    except KeyError as error:
        raise AcquisitionArchiveError(f"archival target is missing required field: {error.args[0]}") from error

    request = urllib.request.Request(
        requested_url,
        headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
    )
    digest = hashlib.sha256()
    observed_bytes = 0
    response_headers: dict[str, str] = {}

    with tempfile.TemporaryDirectory(prefix="bible-os-acquisition-archive-") as temp_dir:
        download_path = Path(temp_dir) / "source-artifact"
        with opener(request, timeout=60) as response, download_path.open("wb") as output:
            response_headers = {
                "content_type": response.headers.get("Content-Type", ""),
                "content_length": response.headers.get("Content-Length", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
                "etag": response.headers.get("ETag", ""),
                "resolved_url": response.geturl(),
            }
            while chunk := response.read(CHUNK_SIZE):
                observed_bytes += len(chunk)
                if observed_bytes > expected_bytes + MAX_SIZE_MARGIN:
                    raise AcquisitionArchiveError(
                        "download exceeded the registered size safety margin"
                    )
                digest.update(chunk)
                output.write(chunk)

        observed_sha256 = digest.hexdigest()
        if observed_bytes != expected_bytes:
            raise AcquisitionArchiveError(
                f"byte count mismatch: expected {expected_bytes}, observed {observed_bytes}"
            )
        if observed_sha256 != expected_sha256:
            raise AcquisitionArchiveError(
                f"SHA-256 mismatch: expected {expected_sha256}, observed {observed_sha256}"
            )

        stored = put_file(download_path, Path(store_root))
        if stored.sha256 != expected_sha256 or stored.byte_size != expected_bytes:
            raise AcquisitionArchiveError(
                "content-addressed store returned an object inconsistent with the registered identity"
            )

    return {
        "report_version": "1.0.0",
        "target_id": target_id,
        "source_id": source_id,
        "requested_url": requested_url,
        "resolved_url": response_headers["resolved_url"],
        "archived_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "observed_sha256": observed_sha256,
        "observed_bytes": observed_bytes,
        "expected_sha256": expected_sha256,
        "expected_bytes": expected_bytes,
        "verification_status": "verified",
        "archive_uri": stored.uri,
        "archive_effect": "deduplicated-existing" if stored.already_present else "stored-new",
        "response_headers": response_headers,
        "retention": "verified bytes retained in content-addressed store",
        "source_text_reported": False,
    }
