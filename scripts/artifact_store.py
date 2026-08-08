from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Sequence

from bible_os.artifacts import ArtifactStoreError, put_file, resolve_uri, verify_manifest

DEFAULT_ROOT = Path(os.environ.get("BIBLE_OS_ARTIFACT_ROOT", "artifacts/raw"))


def load_manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage Bible OS content-addressed source artifacts")
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Local content-addressed store root (default: BIBLE_OS_ARTIFACT_ROOT or artifacts/raw)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    put_parser = subparsers.add_parser("put", help="Store a file by SHA-256")
    put_parser.add_argument("source", type=Path)

    resolve_parser = subparsers.add_parser("resolve", help="Resolve and verify an artifact URI")
    resolve_parser.add_argument("uri")
    resolve_parser.add_argument("--expected-bytes", type=int)

    verify_parser = subparsers.add_parser("verify", help="Verify an artifact manifest against the local store")
    verify_parser.add_argument("manifest", type=Path)

    args = parser.parse_args(argv)

    try:
        if args.command == "put":
            result = put_file(args.source, args.root)
            output = {
                "status": "stored" if not result.already_present else "already-present",
                "sha256": result.sha256,
                "byte_size": result.byte_size,
                "archive_uri": result.uri,
                "local_path": str(result.path),
            }
        elif args.command == "resolve":
            path = resolve_uri(args.uri, args.root, expected_bytes=args.expected_bytes)
            output = {"status": "verified", "archive_uri": args.uri, "local_path": str(path)}
        else:
            manifest = load_manifest(args.manifest)
            path = verify_manifest(manifest, args.root)
            output = {
                "status": "verified",
                "artifact_id": manifest.get("artifact_id"),
                "archive_uri": manifest["archive_uri"],
                "local_path": str(path),
            }
    except (ArtifactStoreError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
