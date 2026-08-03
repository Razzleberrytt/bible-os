#!/usr/bin/env bash
set -euo pipefail

python -m pytest -q
python -m json.tool schemas/foundation.schema.json >/dev/null
python -c 'from pathlib import Path; import yaml; spec=yaml.safe_load(Path("openapi/openapi.yaml").read_text(encoding="utf-8")); assert spec["openapi"] == "3.2.0"'

echo "Bible OS foundation verification passed."
