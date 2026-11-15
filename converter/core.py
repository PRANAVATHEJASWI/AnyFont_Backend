# converter/core.py
"""
Core conversion engine for Nudi ↔ Unicode Kannada.

Key challenges handled here
----------------------------
1. **Pre-base i-matra reordering**: In Nudi the i-matra ('{') and ii-matra
   ('|') are stored *before* the consonant they modify, but Unicode requires
   the combining mark to follow the base letter.  We detect and swap these
   pairs after the basic character substitution.

2. **Longest-match substitution**: NUDI_SPECIAL_SEQUENCES are tried first
   (longest first) before falling back to single-char NUDI_TO_UNICODE so
   that conjuncts and compound forms are handled correctly.

3. **Mixed-encoding documents**: `convert_mixed_text` segments the input,
   identifies each segment's encoding, and converts only the portions that
   need it.
"""

from __future__ import annotations

import re
from typing import Any

from .nudi_mappings import (
    NUDI_TO_UNICODE,
    UNICODE_TO_NUDI,
    NUDI_SPECIAL_SEQUENCES,
    KANNADA_UNICODE_START,
    KANNADA_UNICODE_END,
)
from .detection import detect_encoding_type, segment_by_encoding

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# Characters that are pre-base in Nudi (appear before the consonant in the
# byte stream but after it in Unicode).
_PRE_BASE_NUDI = frozenset(["{", "|"])

# Unicode equivalents of the pre-base matras
_I_MATRA  = "ಿ"   # U+0CBF
_II_MATRA = "ೀ"   # U+0CC0

# Regex that matches a pre-base matra immediately followed by a Kannada
# Unicode consonant (after the first substitution pass).
# Consonants land in U+0C95–U+0CB9 / U+0CDE / U+0CE0–U+0CE1
_PREBASE_REORDER_RE = re.compile(
    r"([ಿೀ])([\u0C95-\u0CB9\u0CDE\u0CE0\u0CE1])"
)


def _apply_longest_match(text: str, mapping: dict[str, str], specials: list[tuple[str, str]]) -> str:
    """
    Substitute all occurrences of keys in *mapping* (and *specials*) in
    *text* using longest-first greedy matching.
    """
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched = False
        # Try special sequences first (already sorted longest-first)
        for nudi_seq, uni_str in specials:
            seq_len = len(nudi_seq)
            if text[i:i + seq_len] == nudi_seq:
                result.append(uni_str)
                i += seq_len
                matched = True
                break
        if not matched:
            ch = text[i]
            result.append(mapping.get(ch, ch))
            i += 1
    return "".join(result)


def _reorder_pre_base_matras(text: str) -> str:
    """
    After the initial character substitution, fix pre-base matra ordering.
    Pattern: <i-matra or ii-matra><consonant>  →  <consonant><matra>
    """
    return _PREBASE_REORDER_RE.sub(r"\2\1", text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def nudi_to_unicode(text: str) -> str:
    """
    Convert Nudi-encoded *text* to Unicode Kannada.

    Steps:
    1. Apply longest-match substitution using NUDI_SPECIAL_SEQUENCES +
       NUDI_TO_UNICODE character map.
    2. Reorder any pre-base matras that ended up before their base consonant.
    """
    if not text:
        return text

    # Step 1 – character substitution
    converted = _apply_longest_match(text, NUDI_TO_UNICODE, NUDI_SPECIAL_SEQUENCES)

    # Step 2 – pre-base matra reordering
    converted = _reorder_pre_base_matras(converted)

    return converted


def unicode_to_nudi(text: str) -> str:
    """
    Convert Unicode Kannada *text* to Nudi encoding.

    For multi-character Unicode entries (e.g. 'ಅಂ') we try the longest
    Unicode key first so that combined forms are translated as a unit.
    """
    if not text:
        return text

    # Build reverse special sequences (unicode → nudi) sorted longest-first
    rev_specials: list[tuple[str, str]] = sorted(
        [(uni, nudi) for nudi, uni in NUDI_SPECIAL_SEQUENCES],
        key=lambda t: -len(t[0]),
    )

    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched = False
        # Try special sequences
        for uni_seq, nudi_str in rev_specials:
            seq_len = len(uni_seq)
            if text[i:i + seq_len] == uni_seq:
                result.append(nudi_str)
                i += seq_len
                matched = True
                break
        if not matched:
            ch = text[i]
            # Also handle the two-char Unicode entries in UNICODE_TO_NUDI
            # (e.g. 'ಅಂ') by checking two-char window first
            two = text[i:i + 2]
            if two in UNICODE_TO_NUDI:
                result.append(UNICODE_TO_NUDI[two])
                i += 2
            else:
                result.append(UNICODE_TO_NUDI.get(ch, ch))
                i += 1
    return "".join(result)


def auto_convert_to_nudi(text: str) -> dict[str, Any]:
    """
    Auto-detect *text* encoding and convert to Nudi.

    Returns
    -------
    dict:
        converted   : str   – the Nudi-encoded result
        source_type : str   – detected source encoding
        confidence  : float – detection confidence
        segments    : list  – per-segment details
    """
    detection = detect_encoding_type(text)
    source_type = detection["type"]
    confidence  = detection["confidence"]

    if source_type == "nudi":
        return {
            "converted":   text,
            "source_type": "nudi",
            "confidence":  confidence,
            "segments":    [{"text": text, "type": "nudi", "converted": text}],
        }

    if source_type == "unicode":
        converted = unicode_to_nudi(text)
        return {
            "converted":   converted,
            "source_type": "unicode",
            "confidence":  confidence,
            "segments":    [{"text": text, "type": "unicode", "converted": converted}],
        }

    if source_type == "mixed":
        mixed = convert_mixed_text(text, target="nudi")
        return {
            "converted":   mixed["result"],
            "source_type": "mixed",
            "confidence":  confidence,
            "segments":    mixed["segments"],
        }

    # Latin / other – return as-is
    return {
        "converted":   text,
        "source_type": "latin",
        "confidence":  confidence,
        "segments":    [{"text": text, "type": "latin", "converted": text}],
    }


def convert_mixed_text(text: str, target: str = "nudi") -> dict[str, Any]:
    """
    Handle text that contains a mixture of Nudi and Unicode Kannada.

    The function segments the input by encoding, converts each segment as
    appropriate, then rejoins the result.

    Parameters
    ----------
    text   : Input text (may mix Nudi, Unicode Kannada, and Latin).
    target : "nudi" to convert everything to Nudi, or "unicode" to convert
             everything to Unicode Kannada.

    Returns
    -------
    dict:
        result   : str  – fully converted text
        segments : list of {"text", "type", "converted"}
    """
    if not text:
        return {"result": "", "segments": []}

    if target not in ("nudi", "unicode"):
        raise ValueError(f"target must be 'nudi' or 'unicode', got {target!r}")

    segs = segment_by_encoding(text)
    output_parts: list[str] = []
    segment_details: list[dict] = []

    for seg in segs:
        seg_text = seg["text"]
        seg_type = seg["type"]

        if target == "nudi":
            if seg_type == "unicode":
                converted = unicode_to_nudi(seg_text)
            elif seg_type == "nudi":
                converted = seg_text          # already Nudi
            else:
                converted = seg_text          # Latin/other – leave unchanged
        else:  # target == "unicode"
            if seg_type == "nudi":
                converted = nudi_to_unicode(seg_text)
            elif seg_type == "unicode":
                converted = seg_text          # already Unicode
            else:
                converted = seg_text          # Latin/other – leave unchanged

        output_parts.append(converted)
        segment_details.append({
            "text":      seg_text,
            "type":      seg_type,
            "converted": converted,
        })

    return {
        "result":   "".join(output_parts),
        "segments": segment_details,
    }


def auto_convert_to_unicode(text: str) -> dict[str, Any]:
    """
    Auto-detect *text* encoding and convert to Unicode Kannada.

    Returns
    -------
    dict with the same shape as `auto_convert_to_nudi`.
    """
    detection = detect_encoding_type(text)
    source_type = detection["type"]
    confidence  = detection["confidence"]

    if source_type == "unicode":
        return {
            "converted":   text,
            "source_type": "unicode",
            "confidence":  confidence,
            "segments":    [{"text": text, "type": "unicode", "converted": text}],
        }

    if source_type == "nudi":
        converted = nudi_to_unicode(text)
        return {
            "converted":   converted,
            "source_type": "nudi",
            "confidence":  confidence,
            "segments":    [{"text": text, "type": "nudi", "converted": converted}],
        }

    if source_type == "mixed":
        mixed = convert_mixed_text(text, target="unicode")
        return {
            "converted":   mixed["result"],
            "source_type": "mixed",
            "confidence":  confidence,
            "segments":    mixed["segments"],
        }

    return {
        "converted":   text,
        "source_type": "latin",
        "confidence":  confidence,
        "segments":    [{"text": text, "type": "latin", "converted": text}],
    }
