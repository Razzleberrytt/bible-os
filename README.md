# Bible OS

Bible OS is a verification-first platform for acquiring, preserving, normalizing, validating, aligning, and publishing biblical textual data.

## Current phase

This repository contains the **foundation bootstrap only**:

- architecture RFCs and ADRs
- canonical metadata and manifest schemas
- PostgreSQL foundation migration
- OpenAPI read contract
- one synthetic fixture set
- deterministic contract tests and CI

No complete Bible corpus is committed in this bootstrap. Real source artifacts enter only through the acquisition, licensing, hashing, and release gates defined in the RFCs.

## Engineering posture

- modular monolith in a monorepo
- PostgreSQL as the relational authority
- immutable content-addressed source artifacts
- evidence, computation, interpretation, and presentation kept distinct
- small reviewable commits and required automated checks

## Verify locally

```bash
python -m pip install -e '.[dev]'
./scripts/verify.sh
```

## Repository map

- `docs/` — architecture and decision records
- `schemas/` — JSON Schema 2020-12 contracts
- `database/` — PostgreSQL migrations
- `openapi/` — OpenAPI 3.2.0 read contract
- `examples/` — synthetic contract fixtures only
- `tests/` — deterministic validation suite

## Next milestone

Run the foundation migration in CI, then add the 100-record BSB loader fixture in a separate reviewed change before any complete corpus import.
