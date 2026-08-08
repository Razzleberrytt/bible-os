# Bible OS Architecture Decisions

## ADR-0001 — Monorepo initially

**Status:** Accepted  
Keep specifications, schemas, migrations, pipeline modules, API contracts, and product consumers in one repository. This supports atomic changes and one CI graph while the project has a small team and tightly coupled contracts.

## ADR-0002 — Modular monolith before microservices

**Status:** Accepted  
Deploy the initial platform as one application/process family with strict internal module boundaries. Service extraction requires measured operational, security, ownership, or release-cadence pressure.

## ADR-0003 — PostgreSQL as relational authority

**Status:** Proposed  
Use PostgreSQL for canonical records, constraints, migrations, provenance, alignment, and release metadata. Search and graph systems remain derived projections.

## ADR-0004 — Immutable raw artifacts

**Status:** Accepted  
Archive source downloads by content digest. Never overwrite or hand-edit acquired bytes. Corrections create new artifacts and lineage records.

**Implementation note (2026-08-08):** `artifact+sha256://<digest>` is the logical artifact identity. The repository provides a local content-addressed filesystem implementation with atomic writes, deduplication, digest verification, and manifest binding. Raw bytes remain outside Git history. Durable production preservation still requires at least one independently verified remote immutable replica.

## ADR-0005 — Opaque stable identifiers

**Status:** Accepted  
Use stable internal IDs for passages and text objects. Human references remain mapped attributes because canons and versification systems contain splits, joins, omissions, additions, and relocations.

## ADR-0006 — REST and OpenAPI first

**Status:** Accepted  
Define the first public HTTP interface as versioned REST endpoints documented with OpenAPI 3.2.0. GraphQL may be added only for demonstrated research use cases.

## ADR-0007 — Separate evidence, computation, interpretation, and presentation

**Status:** Accepted  
Store and label these categories separately with distinct provenance and mutation policies. AI-authored records can never be typed as evidence.

## ADR-0008 — Standards baseline

**Status:** Accepted  
Use JSON Schema 2020-12 for contracts, OpenAPI 3.2.0 for the HTTP API, in-toto Statement v1 with SLSA 1.2-compatible provenance structures, and SPDX-compatible license metadata while preserving exact publisher evidence.

## ADR-0009 — Project license remains undecided

**Status:** Proposed  
Do not imply an open-source license until the contribution, patent, and redistribution posture is deliberately selected and recorded.

## ADR-0010 — Artifact identity is independent of storage backend

**Status:** Accepted  
Treat the SHA-256 content identity as the stable logical reference and physical storage locations as replaceable replicas. Upstream URLs record acquisition provenance; `artifact+sha256://` records the exact evidence object; local or remote storage backends record where verified replicas can currently be retrieved. No backend-specific URL becomes the primary identity of an evidence artifact.
