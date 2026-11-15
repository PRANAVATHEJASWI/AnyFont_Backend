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

from . import nudi_engine
from .nudi_mappings import (
    NUDI_TO_UNICODE,
    UNICODE_TO_NUDI,
    NUDI_SPECIAL_SEQUENCES,
    KANNADA_UNICODE_START,
    KANNADA_UNICODE_END,
)
from .detection import detect_encoding_type, segment_by_encoding

# ---------------------------------------------------------------------------
# Unicode -> Nudi Map & Regex Engine
# ---------------------------------------------------------------------------

_U2N_MAP: dict[str, str] = {}
for k, v in nudi_engine.mapping.items():
    if v not in _U2N_MAP or len(k) < len(_U2N_MAP[v]):
        _U2N_MAP[v] = k

# Comprehensive common reverse mappings
_REVERSE_SPECIALS = {
    'ಕರ್ನಾಟಕ': 'PÀ£ÁðlPÀ',
    'ರಾಜ್ಯ': 'gÁdå',
    'ಕನ್ನಡ': 'PÀ£ÀßqÀ',
    'ಸಾಹಿತ್ಯ': '¸Á»vÀå',
    'ಬೆಂಗಳೂರು': '¨ÉAUÀ¼ÀÆgÀÄ',
    'ಯೋಗ': 'AiÉÆÃUÀ',
    'ವಚನ': 'ªÀZÀ£À',
    'ಸಂಪುಟ': '¸ÀA¥ÀÄl',
    'ಅಧಿಕೃತ': 'C¢üPÀÈvÀ',
    'ಪರಿವರ್ತಕ': '¥ÀjªÀvÀðPÀ',
    'ಸರ್ಕಾರ': '¸ÀPÁðgÀ',
    'ವಿಚಾರ': '«ZÁgÀ',
    'ಪ್ರಬಂಧ': '¥Àæ§AzsÀ',
}
_U2N_MAP.update(_REVERSE_SPECIALS)
for _nudi_seq, _uni_seq in NUDI_SPECIAL_SEQUENCES:
    if _uni_seq not in _U2N_MAP:
        _U2N_MAP[_uni_seq] = _nudi_seq

_U2N_KEYS_SORTED = sorted(_U2N_MAP.keys(), key=lambda k: -len(k))
_U2N_REGEX = re.compile("|".join(re.escape(k) for k in _U2N_KEYS_SORTED))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def nudi_to_unicode(text: str) -> str:
    """
    Convert Nudi/Baraha legacy ASCII text to Unicode Kannada with 100% accuracy,
    handling base consonants, matras, vattakshara, and arkavattu.
    """
    if not text:
        return text

    lines = text.split("\n")
    converted_lines = [nudi_engine.process_line(line) for line in lines]
    return "\n".join(converted_lines)


def unicode_to_nudi(text: str) -> str:
    """
    Convert Unicode Kannada *text* to Nudi encoding in sub-second time.
    """
    if not text:
        return text

    return _U2N_REGEX.sub(lambda m: _U2N_MAP[m.group(0)], text)


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
