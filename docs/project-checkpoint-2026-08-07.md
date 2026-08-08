# Bible OS Project Checkpoint — 2026-08-07

## Purpose

This checkpoint supersedes the **planning state** recorded in `project-checkpoint-2026-08-03.md` while preserving that document as historical evidence. It records the actual merged baseline after PR #39, the active draft research/infrastructure stack, and the next highest-ROI milestone.

Bible OS remains a **Biblical Intelligence Engine**: a provenance-first computational research platform for detecting structure across translations. The objective is not another reading app and not a machine-generated theological authority. The objective is to make translation relationships, uncertainty, drift, invariants, clusters, and higher-order structure measurable.

---

## Stable merged baseline

The default branch is stable through **PR #39** (`8202e32e4e893d1bc4fd2ed22e0d63b7f67c44f1`).

### Foundation and execution controls

Bible OS has already proven:

- foundational relational schema and migrations;
- explicit cross-versification reference relations;
- registry-driven materializers;
- synthetic split/join semantics with production/synthetic execution separation;
- deterministic identities and reproducible normalized-export fingerprints;
- contract, migration, registry-integrity, and evidence-package test gates.

### Human-governed versification review

The review-governance chain is no longer a future task. Merged PRs #17–#24 provide:

- inert review queue records;
- append-only reviewer attestations;
- non-authoritative aggregation;
- human decision records;
- append-only queue transitions;
- deterministic effective-state reduction;
- read-only registry audit;
- named CI integrity gate.

Merged PRs #29–#34 extend this with a real ASV/WEBP Romans proposal, provisional review, human evidence requirements, evidence-package manifests, consistency checking, and a dedicated evidence-package integrity gate.

### Real corpora

Two real English corpora are fully represented in the current research baseline:

1. **American Standard Version (ASV 1901)**
2. **World English Bible — Protestant edition (WEBP)**

ASV onboarding and comparison work in PRs #25–#28 proved:

- public-domain source registration and cryptographic acquisition verification;
- source-specific structural parsing over the generic USFM parser;
- reproducible full PostgreSQL loading with source-owned identities;
- pinned normalized export;
- combined ASV+WEBP ephemeral load;
- 31,083 shared text-to-text source locators;
- inert exceptional-locator candidate generation;
- zero automatic cross-translation passage identities or semantic mappings.

### First cross-translation lexical research stack

PRs #35–#39 delivered the first text-private lexical research sequence:

- deterministic ASV↔WEBP normalized lexical fingerprints;
- corpus- and book-level distance summaries;
- Gospel source-structure diagnostic;
- exact character-style marker attribution;
- `wj` record-shape accounting;
- opening-`wj` versus non-`wj` token-ratio stratification.

This sequence demonstrated an important lab behavior: an initially striking corpus-level signal was progressively localized to source structure without being misreported as semantic or theological drift.

---

## Active draft stack after PR #39

The following work is **draft / unmerged** and must not be treated as part of the stable main-branch contract until reviewed and merged.

### Marker semantics and upstream-revision research

- **#40** — metadata-only `wj` marker semantics/provenance.
- **#41** — observe-first handling for an upstream WEBP artifact revision; changed live bytes are quarantined rather than silently accepted.
- **#42** — measures downstream impact of that revision and records evidence limits. The current evidence supports a tiny normalized lexical perturbation and strongly suggests localization to `MIC 3:11`, but direct old-USFM/new-USFM proof is impossible because the old source bytes were not retained.

### General provenance infrastructure exposed by the incident

- **#43** — executable `artifact+sha256://` content-addressed artifact store.
- **#44** — separates deterministic PR CI from live publisher/source-integrity monitoring.
- **#45** — `Acquire → Verify → Archive` path that admits bytes to evidence storage only after exact registered identity verification.

### Falsified / bounded WEBP sub-hypotheses

- **#46** — cross-format package timing. The stronger different-release-date hypothesis was not supported; all seven observed WEBP packages were modified on 2026-08-06, compatible with a staggered same-day build/publish batch.
- **#47** — current USFM and downloadable HTML agree under normalization at all four official 2026-08-05 correction loci.
- **#48** — current served `engwebp/MIC03.htm` and the downloadable HTML member differ in wrapper bytes but have identical normalized visible text at observation time. Current page/package text-state divergence was not supported.

### Incident-level conclusion

Stop spending the current sprint on the single-page WEBP synchronization hypothesis unless a future independently fingerprinted observation reproduces a divergence.

The incident was valuable because it exposed reusable provenance requirements; the next work should generalize those lessons rather than continue source-specific archaeology.

---

## Current bottlenecks

### 1. Only two fully ingested real corpora

ASV and WEBP permit pairwise comparison, but two observations do not support the geometry needed for the project's central research goals.

With only two corpora, Bible OS cannot meaningfully begin to distinguish:

- lineage-specific effects from broader translation invariants;
- center-of-gravity behavior from a pairwise midpoint;
- clusters from a single pair;
- translation-specific feature signatures from binary contrast;
- robust outliers from pairwise disagreement.

### 2. ASV and WEBP are methodologically/genealogically related

Their relationship makes them valuable for controlled historical comparison, but it also means the current research field is narrow. The next corpus should expand the translation-method and stylistic basis rather than merely add another close WEB-family observation.

### 3. Historical source-byte retention was incomplete

The 2026-08 WEBP revision proved that fingerprints alone cannot replace the exact prior artifact when a byte/field-level source revision must be reconstructed.

Draft PRs #43 and #45 address this for future legally retainable observations. Until those contracts land, new source work on `main` must preserve the existing no-retention safety model rather than silently depend on unmerged infrastructure.

---

# Current Sprint — Third Real Corpus

## Sprint objective

Onboard **Young's Literal Translation (YLT / eBible `engylt`)** as Bible OS's third verified real English corpus.

### Why YLT

YLT is a high-information third observation because it broadens the translation-method and stylistic basis substantially more than another WEB-family variant would. Its literal and historically distinctive English makes it useful for testing whether ASV↔WEBP signals are lineage-specific or persist under a different rendering strategy.

The selection is methodological, not theological. YLT is not treated as more authoritative than ASV, WEBP, or any future source.

## Sprint principles

1. Provenance before analysis.
2. Source-owned identities remain disjoint.
3. Matching locators do not imply semantic equivalence.
4. No automatic cross-translation passage mappings.
5. No Scripture text is committed to the repository or research reports.
6. Live source bytes remain ephemeral unless an approved immutable-retention path is available.
7. Every observed profile becomes reproducible before higher-order analysis consumes it.

## YLT done criteria

### Phase A — Source and acquisition

- register the official YLT source authority and public-domain evidence;
- identify the official eBible USFM artifact;
- bounded observation of byte size, SHA-256, HTTP provenance headers, ZIP integrity, and USFM-like entry counts;
- pin exact artifact identity;
- reproduce strict acquisition verification from a fresh run;
- no source text retained in Git.

### Phase B — Structural adapter profile

- use the generic deterministic eBible/USFM parsing contract rather than creating a bespoke parser unless source evidence demands it;
- pin canonical book count, source-locus count, text/placeholder counts, special labels, and structural exceptions;
- identify structural differences without promoting them to mappings.

### Phase C — Reproducible corpus load

- deterministic YLT work, corpus, passage, reference, and text-unit identities;
- full ephemeral PostgreSQL load;
- zero cross-translation passage identity sharing;
- zero automatic reference relations or alignments;
- pinned normalized-export SHA-256, byte size, and record count.

### Phase D — Three-corpus structural field

Produce the first ASV/WEBP/YLT structural comparison with:

- three-way locator intersection count;
- pairwise-only and corpus-specific locator counts;
- realization-type disagreement counts;
- exceptional loci only in text-private reports;
- no automatic semantic correspondence or mapping authority.

---

## Next research milestone after YLT ingestion

### Translation DNA v0 / three-way lexical geometry

Once YLT is reproducibly loaded, the next highest-value experiment is the first genuinely multi-observation lexical feature field.

Candidate initial features per translation/book or translation/corpus include:

- normalized token density;
- lexical distance distributions;
- type/token characteristics;
- punctuation-independent length profile;
- source-marker structural signature;
- per-book deviation from the three-corpus centroid;
- pairwise distance triangle structure.

This is **Translation DNA v0**, not a final theological or semantic fingerprint. The first goal is to determine which measurable features are stable, discriminative, reproducible, and resistant to source-format artifacts.

With three corpora, Bible OS can finally ask whether a signal is:

- shared by all three;
- unique to one corpus;
- specific to the ASV↔WEBP lineage;
- an outlier relative to a third observation;
- a candidate invariant worthy of expansion to more translations.

---

## Open infrastructure priority

The provenance drafts remain high-value parallel work:

1. merge-quality review of deterministic-CI/source-monitor separation (#44);
2. content-addressed artifact identity/store (#43);
3. verified-acquisition archival path (#45).

These should mature without blocking YLT's provenance-first onboarding on the stable main-branch contracts.

---

## Change-control rule

Continue with narrow, reviewable draft PRs. Do not automatically merge research or provenance changes. A later checkpoint should supersede this document only after the third corpus is reproducibly loaded or the sprint objective materially changes.

---

# Next Highest ROI Task

**Register and cryptographically observe the official YLT (`engylt`) USFM source as Bible OS's third real corpus candidate, then pin and reproduce its exact artifact identity.**

That task increases the dimensionality of the research field and directly unlocks the first three-translation geometry, Translation DNA v0, and more meaningful tests of invariants versus lineage-specific artifacts.
