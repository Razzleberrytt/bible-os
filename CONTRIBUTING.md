# Contributing to Bible OS

Bible OS treats data correctness and provenance as product requirements.

## Before implementation

1. Check whether the change needs an RFC or ADR.
2. Identify the owning module and its public interface.
3. Define the evidence, computation, interpretation, or presentation layer involved.
4. Add or update fixtures before changing pipeline behavior.

## Pull-request requirements

- Keep changes narrow and reviewable.
- Link the relevant RFC, ADR, or issue.
- Include tests appropriate to the change.
- Do not hand-edit immutable source artifacts.
- Do not place AI-generated content in evidence records.
- Update schemas, migrations, documentation, and examples together when contracts change.
- Explain licensing or attribution consequences for new datasets.

## Local verification

```bash
bash scripts/verify.sh
```

## Commit style

Use concise conventional prefixes when practical:

- `feat:` new capability
- `fix:` correctness repair
- `docs:` documentation or governance
- `test:` test-only change
- `refactor:` behavior-preserving restructuring
- `chore:` repository or tooling maintenance
