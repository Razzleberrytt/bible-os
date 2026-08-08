# Content-Addressed Artifact Store

## Purpose

Bible OS source manifests already identify immutable source observations with URIs such as:

```text
artifact+sha256://<64-lowercase-hex-digest>
```

This document defines the executable contract behind that identifier.

The store exists to preserve the exact evidence bytes used by a research result so a later upstream revision can be compared against the original observation rather than only against aggregate fingerprints.

## Local object layout

The default local root is `artifacts/raw/`, which is excluded from Git history.

Objects are placed at:

```text
<root>/sha256/<first-2>/<next-2>/<full-sha256>
```

The object filename is the digest. Original upstream filenames are metadata, not object identity.

## Invariants

1. The SHA-256 digest is the object identity.
2. A stored object is never overwritten with different bytes.
3. Re-storing identical bytes deduplicates to the same path.
4. Every resolve operation re-verifies the digest.
5. Manifest verification binds `archive_uri`, `sha256`, and `byte_size` together.
6. Raw corpus bytes remain outside Git history.
7. A local CAS copy is a cache/preservation layer, not by itself a complete durability strategy.
8. Acquisition bytes enter the evidence store only after their registered byte count and SHA-256 both verify exactly.

## CLI

Store an already available source observation:

```bash
python -m scripts.artifact_store --root artifacts/raw put /path/to/source.zip
```

Resolve and verify a URI:

```bash
python -m scripts.artifact_store --root artifacts/raw resolve \
  artifact+sha256://<digest>
```

Verify an existing artifact manifest:

```bash
python -m scripts.artifact_store --root artifacts/raw verify \
  registry/artifacts/engwebp-usfm.artifact.json
```

`BIBLE_OS_ARTIFACT_ROOT` may be used to change the default root.

## Acquire, verify, and archive in one operation

For a registered acquisition target with a pinned byte count and SHA-256:

```bash
python -m scripts.archive_acquisition \
  registry/acquisitions/eng-asv-usfm.json \
  --store-root artifacts/raw \
  --report archive-acquisition-report.json
```

The command follows this order:

```text
Download to temporary file
  -> enforce size safety margin
  -> verify exact registered byte count
  -> verify exact registered SHA-256
  -> copy into content-addressed storage
  -> verify stored object again
  -> delete temporary download
```

A byte-count or hash mismatch aborts before the changed bytes enter the evidence store. Repeating the operation for the same verified bytes deduplicates to the existing content object.

Unpinned source observations cannot use this archival path. They must first acquire an explicit evidence identity rather than silently turning a transient live response into canonical raw evidence.

## Durability boundary

The filesystem CAS implemented in the repository makes `artifact+sha256://` executable and testable, but it does not claim that a developer workstation is durable archival storage.

Production preservation requires at least one immutable remote mirror with independent integrity verification. A future backend may use object storage, release assets, institutional archival storage, or another immutable blob service. The logical URI must remain independent of whichever physical backend stores the bytes.

## Why logical and physical locations are separated

A URL can change, disappear, or begin serving different bytes. A digest cannot silently change without becoming a different object.

Therefore:

```text
upstream URL = where an observation was acquired
artifact+sha256 URI = what exact observation Bible OS used
physical mirror = where those exact bytes can currently be retrieved
```

These are separate provenance facts.

## Cross-format revision state

The 2026-08 WEBP drift investigation showed that official delivery surfaces can be temporally out of sync. Bible OS must not assume that USFM, HTML, OSIS, EPUB, or other formats are synchronized merely because they carry the same translation/edition label.

Future acquisition records should fingerprint each delivery artifact independently and relate them to an edition/revision observation explicitly.

## Next storage milestone

Add a pluggable remote mirror backend and a registry of physical replicas:

```text
artifact+sha256://digest
  -> local CAS replica
  -> remote immutable replica A
  -> optional remote immutable replica B
```

Replica metadata should record verification time, backend, object locator, byte size, digest, and availability without changing the logical artifact identity.
