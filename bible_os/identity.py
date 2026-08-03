from __future__ import annotations

import base64
import hashlib


def stable_id(prefix: str, namespace: str, key: str, *, length: int = 20) -> str:
    """Create a deterministic opaque identifier from a versioned namespace and key."""

    if not prefix or not namespace or not key:
        raise ValueError("prefix, namespace, and key are required")
    if length < 12:
        raise ValueError("stable identifier tokens must contain at least 12 characters")
    canonical = f"{namespace}\x1f{key}".encode("utf-8")
    digest = hashlib.sha256(canonical).digest()
    token = base64.b32encode(digest).decode("ascii").lower().rstrip("=")[:length]
    return f"{prefix}_{token}"
