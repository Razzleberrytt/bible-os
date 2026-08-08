from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from bible_os.acquisition import AcquisitionArchiveError, archive_registered_source
from bible_os.artifacts import ArtifactStoreError

DEFAULT_STORE_ROOT = Path(os.environ.get("BIBLE_OS_ARTIFACT_ROOT", "artifacts/raw"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download, strictly verify, and archive a registered source observation"
    )
    parser.add_argument("target", type=Path)
    parser.add_argument("--store-root", type=Path, default=DEFAULT_STORE_ROOT)
    parser.add_argument("--report", type=Path, default=Path("archive-acquisition-report.json"))
    args = parser.parse_args()

    try:
        target = json.loads(args.target.read_text(encoding="utf-8"))
        report = archive_registered_source(target, args.store_root)
    except (OSError, json.JSONDecodeError, AcquisitionArchiveError, ArtifactStoreError) as error:
        parser.error(str(error))

    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"ARCHIVE_URI={report['archive_uri']}")
    print(f"OBSERVED_SHA256={report['observed_sha256']}")
    print(f"OBSERVED_BYTES={report['observed_bytes']}")
    print(f"ARCHIVE_EFFECT={report['archive_effect']}")
    print(f"VERIFICATION_STATUS={report['verification_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
