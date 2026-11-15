# converter/__init__.py
"""Nudi ↔ Unicode Kannada conversion package."""

from .core import (
    nudi_to_unicode,
    unicode_to_nudi,
    auto_convert_to_nudi,
    auto_convert_to_unicode,
    convert_mixed_text,
)
from .detection import detect_encoding_type, segment_by_encoding
from .document_processor import process_file

__all__ = [
    "nudi_to_unicode",
    "unicode_to_nudi",
    "auto_convert_to_nudi",
    "auto_convert_to_unicode",
    "convert_mixed_text",
    "detect_encoding_type",
    "segment_by_encoding",
    "process_file",
]
