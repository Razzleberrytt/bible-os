# CI and Source-Integrity Boundaries

## Why this boundary exists

Bible OS works with evidence controlled by external publishers. A live URL can begin serving different bytes even when no Bible OS code changed.

That event is scientifically important, but it is not the same failure class as a broken parser, invalid schema, failing migration, or regression in repository code.

Bible OS therefore separates three execution lanes.

## Lane 1 — Deterministic pull-request CI

Purpose: answer **“Did this repository change break Bible OS?”**

Trigger:

- every pull request;
- pushes to `main`.

Allowed dependencies:

- repository source code;
- committed metadata and fixtures;
- deterministic database services;
- immutable evidence objects once they are resolvable by pinned content identity.

Not allowed:

- treating a live publisher URL as the bytes required for a historical baseline;
- failing a pull request merely because an external publisher revised an artifact.

The generic workflow is `.github/workflows/ci.yml`.

## Lane 2 — Live source-integrity watch

Purpose: answer **“Does the publisher still serve the exact artifact Bible OS registered?”**

Trigger:

- scheduled monitoring;
- explicit manual execution.

The workflow performs strict hash/size verification against registered acquisition targets. A mismatch is expected to fail the workflow loudly.

That failure means **upstream provenance drift was detected**. It does not, by itself, mean Bible OS code regressed.

The generic workflow is `.github/workflows/source-integrity.yml`.

## Lane 3 — Frozen research reproduction

Purpose: answer **“Can a specific historical experiment still be reproduced under its declared source assumptions?”**

Some current experiments still retrieve source bytes from live publisher URLs because the durable content-addressed artifact backend is not yet fully available. Those workflows are manual research tools, not pull-request gates.

A strict failure is preserved. The workflow is not weakened merely to accommodate a changed upstream artifact.

Once the immutable artifact store has a durable, resolvable replica backend, historical reproductions should read their exact `artifact+sha256://` evidence objects instead of relying on a live URL. At that point, many can become deterministic regression tests.

## Failure semantics

| Failure | Meaning | Blocks ordinary PRs? |
|---|---|---:|
| Unit/contract test failure | Repository regression | Yes |
| Migration/integrity failure | Repository or schema regression | Yes |
| Registered source hash mismatch | External evidence changed | No |
| Frozen live research reproduction mismatch | Historical live-source assumption no longer holds | No |
| Pinned immutable artifact reproduction mismatch | Deterministic reproducibility regression | Yes |

## Non-negotiable rule

Separating the lanes must never weaken evidence verification.

Bible OS should move a check to the execution context that matches its epistemic meaning; it should not turn a strict mismatch into a warning merely to obtain a green checkmark.
