"""Source-adapter interfaces and implementations."""

from .base import AdapterProbe, SourceAdapter, SourceRecord
from .webp_usfm import WebpUsfmAdapter, extract_visible_text

__all__ = [
    "AdapterProbe",
    "SourceAdapter",
    "SourceRecord",
    "WebpUsfmAdapter",
    "extract_visible_text",
]
