from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ARTIFACT_URI_PREFIX = "artifact+sha256://"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CHUNK_SIZE = 1024 * 1024


class ArtifactStoreError(ValueError):
    """Raised when an artifact store contract is violated."""


@dataclass(frozen=True)
class StoredArtifact:
    sha256: str
    byte_size: int
    uri: str
    path: Path
    already_present: bool


def validate_sha256(value: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ArtifactStoreError("SHA-256 must be 64 lowercase hexadecimal characters")
    return value


def artifact_uri(sha256: str) -> str:
    return f"{ARTIFACT_URI_PREFIX}{validate_sha256(sha256)}"


def parse_artifact_uri(uri: str) -> str:
    if not isinstance(uri, str) or not uri.startswith(ARTIFACT_URI_PREFIX):
        raise ArtifactStoreError(f"unsupported artifact URI: {uri!r}")
    return validate_sha256(uri.removeprefix(ARTIFACT_URI_PREFIX))


def object_path(root: Path, sha256: str) -> Path:
    digest = validate_sha256(sha256)
    return Path(root) / "sha256" / digest[:2] / digest[2:4] / digest


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_size = 0
    with Path(path).open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            digest.update(chunk)
            byte_size += len(chunk)
    return digest.hexdigest(), byte_size


def _verify_object(path: Path, expected_sha256: str, expected_bytes: int | None = None) -> int:
    if not path.is_file():
        raise ArtifactStoreError(f"artifact object is missing: {path}")
    observed_sha256, observed_bytes = hash_file(path)
    if observed_sha256 != expected_sha256:
        raise ArtifactStoreError(
            f"artifact digest mismatch: expected {expected_sha256}, observed {observed_sha256}"
        )
    if expected_bytes is not None and observed_bytes != expected_bytes:
        raise ArtifactStoreError(
            f"artifact byte-size mismatch: expected {expected_bytes}, observed {observed_bytes}"
        )
    return observed_bytes


def put_file(source: Path, root: Path) -> StoredArtifact:
    """Copy a file into the immutable local CAS without changing the source file."""
    source = Path(source)
    root = Path(root)
    if not source.is_file():
        raise ArtifactStoreError(f"source artifact is not a file: {source}")

    sha256, byte_size = hash_file(source)
    destination = object_path(root, sha256)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if destination.exists():
        _verify_object(destination, sha256, byte_size)
        return StoredArtifact(
            sha256=sha256,
            byte_size=byte_size,
            uri=artifact_uri(sha256),
            path=destination,
            already_present=True,
        )

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".{sha256}.", suffix=".tmp", dir=destination.parent, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            with source.open("rb") as input_handle:
                shutil.copyfileobj(input_handle, temporary, length=CHUNK_SIZE)
            temporary.flush()
            os.fsync(temporary.fileno())
        _verify_object(temporary_path, sha256, byte_size)
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    _verify_object(destination, sha256, byte_size)
    return StoredArtifact(
        sha256=sha256,
        byte_size=byte_size,
        uri=artifact_uri(sha256),
        path=destination,
        already_present=False,
    )


def resolve_uri(uri: str, root: Path, *, expected_bytes: int | None = None) -> Path:
    sha256 = parse_artifact_uri(uri)
    path = object_path(Path(root), sha256)
    _verify_object(path, sha256, expected_bytes)
    return path


def verify_manifest(manifest: Mapping[str, Any], root: Path) -> Path:
    """Resolve and verify an artifact manifest against the local CAS."""
    try:
        sha256 = validate_sha256(manifest["sha256"])
        byte_size = int(manifest["byte_size"])
        uri = manifest["archive_uri"]
    except (KeyError, TypeError, ValueError) as error:
        raise ArtifactStoreError("artifact manifest is missing a valid sha256, byte_size, or archive_uri") from error

    uri_sha256 = parse_artifact_uri(uri)
    if uri_sha256 != sha256:
        raise ArtifactStoreError(
            f"manifest URI digest {uri_sha256} does not match manifest SHA-256 {sha256}"
        )
    return resolve_uri(uri, Path(root), expected_bytes=byte_size)
