# converter/detection.py
"""
Encoding detection for Nudi vs Unicode Kannada text.

Heuristics
----------
* Unicode Kannada characters live in U+0C80–U+0CFF.
* Nudi-encoded text uses a specific set of ASCII/ANSI code points that are
  extremely unlikely to co-occur in natural English/Latin text in the same
  patterns (e.g. lone backslash, control chars \x80–\x8e, etc.).
* The detector looks at character-level ratios and returns a confidence
  breakdown so the caller can decide what to do with mixed content.
"""

from __future__ import annotations

import unicodedata
from .nudi_mappings import NUDI_INDICATOR_CHARS, KANNADA_UNICODE_START, KANNADA_UNICODE_END

# Characters that are strong Nudi indicators (non-printable / repurposed)
_STRONG_NUDI: frozenset[str] = frozenset(
    c for c in NUDI_INDICATOR_CHARS
    if ord(c) > 0x7E or ord(c) < 0x41  # outside A-Z / a-z printable range
)

# Nudi consonant / vowel ASCII chars (A-Z, a-s, plus punctuation subset)
_NUDI_PRINTABLE: frozenset[str] = frozenset(NUDI_INDICATOR_CHARS) - _STRONG_NUDI


def _is_kannada_unicode(ch: str) -> bool:
    """Return True if *ch* is a Unicode Kannada character."""
    cp = ord(ch)
    return KANNADA_UNICODE_START <= cp <= KANNADA_UNICODE_END


def _is_strong_nudi(ch: str) -> bool:
    """Return True for characters that only appear in Nudi-encoded streams."""
    return ch in _STRONG_NUDI


def _is_latin(ch: str) -> bool:
    """Return True for plain Latin/ASCII printable characters."""
    return ch.isascii() and (ch.isalpha() or ch.isdigit() or ch.isspace() or ch in '.,;:!?-()\'\"')


def detect_encoding_type(text: str) -> dict:
    """
    Analyse *text* and return an encoding classification.

    Returns
    -------
    dict with keys:
        type         : "nudi" | "unicode" | "mixed" | "latin"
        nudi_ratio   : float  – fraction of significant chars that are Nudi
        unicode_ratio: float  – fraction of significant chars that are Unicode Kannada
        confidence   : float  – 0.0–1.0 confidence in the primary classification
        details      : str    – human-readable explanation
    """
    if not text:
        return {
            "type": "latin",
            "nudi_ratio": 0.0,
            "unicode_ratio": 0.0,
            "confidence": 1.0,
            "details": "Empty input",
        }

    total = len(text)
    nudi_strong = 0    # \x80-\x8e range chars → definitely Nudi
    nudi_ascii  = 0    # ASCII chars used as Nudi consonants/vowels
    unicode_kan = 0    # U+0C80–U+0CFF chars
    latin_chars = 0
    whitespace  = 0
    other       = 0

    for ch in text:
        if ch in ('\n', '\r', '\t', ' '):
            whitespace += 1
        elif _is_kannada_unicode(ch):
            unicode_kan += 1
        elif _is_strong_nudi(ch):
            nudi_strong += 1
        elif ch in _NUDI_PRINTABLE:
            nudi_ascii += 1
        elif _is_latin(ch):
            latin_chars += 1
        else:
            other += 1

    significant = total - whitespace
    if significant == 0:
        return {
            "type": "latin",
            "nudi_ratio": 0.0,
            "unicode_ratio": 0.0,
            "confidence": 1.0,
            "details": "Only whitespace",
        }

    # Weight strong Nudi chars more heavily than printable re-used ASCII
    nudi_weight   = nudi_strong + nudi_ascii * 0.6
    unicode_weight = unicode_kan

    nudi_ratio    = nudi_weight   / significant
    unicode_ratio = unicode_weight / significant

    # --- Classification logic ---
    if nudi_strong > 0 and unicode_kan > 0:
        enc_type    = "mixed"
        confidence  = min(nudi_ratio, unicode_ratio) * 2  # symmetric measure
        details     = (
            f"Mixed content: {nudi_strong} strong-Nudi chars, "
            f"{unicode_kan} Unicode Kannada chars out of {significant} significant chars."
        )
    elif nudi_strong > 0 and unicode_kan == 0:
        enc_type    = "nudi"
        confidence  = min(1.0, nudi_ratio * 1.5)
        details     = (
            f"Nudi encoding detected: {nudi_strong} control/special chars "
            f"(\\x80–\\x8e range) and {nudi_ascii} printable Nudi chars."
        )
    elif unicode_kan > 0 and nudi_strong == 0:
        enc_type    = "unicode"
        confidence  = min(1.0, unicode_ratio * 1.5)
        details     = (
            f"Unicode Kannada detected: {unicode_kan} Kannada code points "
            f"out of {significant} significant chars."
        )
    elif nudi_ascii > latin_chars and nudi_ascii > 0:
        # Possibly Nudi without control chars (pure-ASCII Nudi is ambiguous)
        enc_type    = "nudi"
        confidence  = 0.5
        details     = (
            f"Possibly Nudi (ASCII only): {nudi_ascii} chars match Nudi printable "
            f"map vs {latin_chars} plain Latin chars. Low confidence."
        )
    else:
        enc_type    = "latin"
        confidence  = 1.0 - nudi_ratio - unicode_ratio
        confidence  = max(0.0, min(1.0, confidence))
        details     = f"Latin/other text: {latin_chars} Latin chars, {other} other chars."

    return {
        "type":          enc_type,
        "nudi_ratio":    round(nudi_ratio,    4),
        "unicode_ratio": round(unicode_ratio, 4),
        "confidence":    round(confidence,    4),
        "details":       details,
    }


def segment_by_encoding(text: str, min_segment_length: int = 3) -> list[dict]:
    """
    Split *text* into contiguous runs of the same encoding type.

    Returns a list of dicts::

        [{"text": str, "type": "nudi"|"unicode"|"latin", "start": int, "end": int}, ...]

    Short ambiguous runs are merged into the preceding segment.
    """
    if not text:
        return []

    segments: list[dict] = []
    current_chars: list[str] = []
    current_type: str | None = None
    current_start: int = 0

    def _char_type(ch: str) -> str:
        if _is_kannada_unicode(ch):
            return "unicode"
        if ch in NUDI_INDICATOR_CHARS:
            return "nudi"
        return "latin"

    for idx, ch in enumerate(text):
        if ch in ('\n', '\r', '\t', ' '):
            # Whitespace: attach to current segment
            current_chars.append(ch)
            continue

        ctype = _char_type(ch)
        if current_type is None:
            current_type = ctype
            current_start = idx

        if ctype != current_type:
            # Flush current segment
            seg_text = "".join(current_chars)
            if len(seg_text.strip()) >= min_segment_length:
                segments.append({"text": seg_text, "type": current_type, "start": current_start, "end": idx - 1})
            elif segments:
                # Merge short segment into previous
                segments[-1]["text"] += seg_text
                segments[-1]["end"] = idx - 1
            current_chars = [ch]
            current_type  = ctype
            current_start = idx
        else:
            current_chars.append(ch)

    # Flush final segment
    if current_chars:
        seg_text = "".join(current_chars)
        if segments and len(seg_text.strip()) < min_segment_length:
            segments[-1]["text"] += seg_text
            segments[-1]["end"]   = len(text) - 1
        else:
            segments.append({
                "text":  seg_text,
                "type":  current_type or "latin",
                "start": current_start,
                "end":   len(text) - 1,
            })

    return segments
