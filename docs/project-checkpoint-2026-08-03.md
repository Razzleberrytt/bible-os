# Bible OS Project Checkpoint — 2026-08-03

## Stable baseline

The repository is currently restored to the exact file tree produced by PR #13. PR #14 was reverted completely by PR #15; the add/revert pair remains in history, but no PR #14 files remain on `main`.

Current stable commit:

- `a82713a2e870b5fbc7d16b07144d0b59dfe74c5d`

## Proven capabilities

1. Verification-first architecture, contracts, PostgreSQL migrations, OpenAPI, synthetic fixtures, and CI.
2. Deterministic 100-reference relational loader proof.
3. Machine-enforced canon relation types.
4. Official WEBP artifact registration and pinned SHA-256 verification.
5. WEBP USFM parser with pinned structural profile.
6. Disposable full WEBP PostgreSQL load with no corpus retention.
7. Reproducible normalized WEBP fingerprint.
8. Evidence-reviewed WEBP ↔ BSB Romans doxology relocation.
9. First-class reference-relation records.
10. Registry-driven one-to-one materialization.
11. Synthetic-only split and join planning semantics.
12. Explicit execution boundary preventing synthetic split/join profiles from running as production materializers.

## Current safety boundaries

- No complete Bible corpus is stored in Git.
- No dataset release is created by the provisional loaders.
- WEBP source artifacts are downloaded, verified, processed, and discarded in CI.
- Evidence-reviewed mappings are not represented as completed human scholarly review.
- Split and join semantics are synthetic-only.
- Production materialization supports one-to-one ordered mappings only.
- No production source text may be split or joined without a separately reviewed text-boundary policy.

## Current sprint

**Goal:** strengthen research and review infrastructure before introducing another production mapping shape.

### Next highest-ROI task

Create a review-queue contract for proposed versification observations. The queue should capture:

- observation identity and affected reference systems,
- relation type and candidate loci,
- evidence citations,
- machine-detected structural differences,
- review state and reviewer identity,
- explicit publication eligibility,
- deterministic resolution into an accepted, rejected, or deferred decision.

This task should initially be schema-and-fixture only. It must not mutate corpus text, canonical passage identities, mappings, or database records.

## Change-control rule

Until this checkpoint is deliberately revised:

1. One narrow pull request at a time.
2. No automatic merge.
3. Stop after CI and inspect the exact changed-file list.
4. Any unexpected merge is immediately reverted before new work begins.
5. Runtime changes require a synthetic fixture and a regression proving all existing WEBP and Romans results remain unchanged.
