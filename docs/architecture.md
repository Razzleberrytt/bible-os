# Bible OS Architecture

## Mission

Bible OS is a reproducible research platform for acquiring, preserving, normalizing, validating, aligning, analyzing, and publishing biblical textual data. It is not a new Bible translation. Websites, APIs, research exports, and AI tools are downstream products of the same trusted pipeline.

## Architectural style

The initial implementation is a **modular monolith in a monorepo**. Domain boundaries are explicit, but deployment remains simple until measured scaling, security, release-cadence, or ownership pressure justifies extracting a service.

## Epistemic layers

1. **Evidence** — immutable source artifacts and faithful normalized records.
2. **Computation** — deterministic, algorithm-versioned results derived from evidence.
3. **Interpretation** — human- or AI-authored explanations with citations and review state.
4. **Presentation** — rebuildable API, export, search, and interface views.

No interface may erase the distinction between these layers. AI processes have read-only access to evidence and cannot create or mutate source text.

## Pipeline

`Register → Acquire → Verify → Archive → Parse → Normalize → Validate → Align → Enrich → Analyze → Index → Publish`

Every stage consumes versioned inputs and emits new versioned artifacts. No stage overwrites an upstream artifact.

## Core modules

| Module | Responsibility |
|---|---|
| Registry | Source identity, authority, licensing status, lifecycle |
| Acquisition | Controlled retrieval and retrieval events |
| Provenance | Checksums, manifests, lineage, transformation records |
| Parsers | Format-specific syntax processing |
| Normalization | Conversion into the canonical model |
| Canon | Books, passages, canons, and versification mappings |
| Quality | Validation rules, reports, severities, and release gates |
| Alignment | Passage, segment, phrase, and token mappings |
| Variants | Readings, witnesses, and apparatus relationships |
| Linguistics | Tokens, lemmas, morphology, and senses |
| Knowledge | Sourced entities and relationships |
| Search | Derived search indexes and ranking |
| AI | Prompts, evaluations, and generated interpretations |
| Publishing | API contracts, exports, releases, and read models |

Modules may call another module's public interface. They must not mutate another module's owned tables directly.

## Identity and canon

Human references such as `John 3:16` are locators within a named versification system, not universal primary keys. Bible OS uses opaque stable identifiers for works, books, passages, text units, tokens, alignments, and releases.

The canon model supports multiple named and versioned canon systems. Passage-reference mappings may be `equivalent`, `split`, `join`, `overlap`, `omitted`, `addition`, `relocated`, or `uncertain`. Non-1:1 mappings carry method, confidence, evidence, and review state.

## Storage

- PostgreSQL is the canonical relational authority.
- Raw source artifacts use immutable content-addressed storage.
- Search and graph stores are derived, rebuildable projections.
- Workbooks are control-plane and governance artifacts, not production databases.

## Provenance and releases

Every source and output artifact requires a SHA-256 digest. Acquisition events and transformation runs are append-only. A published release binds source artifacts, schemas, pipeline revision, outputs, quality reports, licenses, and provenance attestations into one immutable manifest.

## Security

External corpora and archives are untrusted input. Parsing must be resource-bounded and path-safe. Publishing credentials are isolated from parser execution. Critical license, checksum, schema, provenance, or referential-integrity failures block publication.

## Initial milestone

The first production milestone is a reproducible multi-corpus release containing BSB, WEBP, SBLGNT, and OSHB/WLC, with complete source provenance, validation reports, canon mappings, and passage-level alignment.
