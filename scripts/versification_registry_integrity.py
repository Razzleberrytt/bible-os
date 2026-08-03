from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from bible_os.governance import audit_registry


def run(repository_root: Path) -> dict[str, object]:
    report = audit_registry(repository_root)
    return {
        "schema_version": "1.0.0",
        "status": "passed" if report.clean else "failed",
        "read_only": True,
        "registry_mutation": "not-performed",
        "materialization_authority": "none",
        "execution_eligible": False,
        "publication_eligible": False,
        "audit": asdict(report),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit versification governance registry integrity without mutation"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)

    result = run(args.root)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
