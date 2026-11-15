# converter/nudi_mappings.py
"""
Nudi 5.0 font encoding mappings.

Nudi is a legacy ASCII/ANSI-based Kannada font where specific byte values
in the Windows-1252 / ISO-8859-1 range represent Kannada glyphs visually.
This module provides the lookup tables needed to convert between Nudi
encoded text and Unicode Kannada (U+0C80–U+0CFF).

IMPORTANT ordering note
-----------------------
In the Nudi byte stream some dependent vowel signs (matras) for the *i*
family appear *before* the consonant character they modify, but in Unicode
the combining mark must come *after* the base letter.  The conversion
engine in core.py handles this reordering; the raw character maps here are
intentionally simple 1-to-1 substitutions.
"""

# ---------------------------------------------------------------------------
# Primary character map  NUDI_ASCII_CHAR -> UNICODE_KANNADA_STRING
# ---------------------------------------------------------------------------

NUDI_TO_UNICODE: dict[str, str] = {
    # ── Independent vowels ─────────────────────────────────────────────────
    "C": "ಅ",   # a
    "D": "ಆ",   # aa
    "E": "ಇ",   # i
    "F": "ಈ",   # ii
    "G": "ಉ",   # u
    "H": "ಊ",   # uu
    "I": "ಋ",   # ru / vocalic r
    "J": "ಎ",   # e (short)
    "K": "ಏ",   # ee (long)
    "L": "ಐ",   # ai
    "M": "ಒ",   # o (short)
    "N": "ಓ",   # oo (long)
    "O": "ಔ",   # au
    "A": "ಅಂ",  # am  – a + anusvara
    "B": "ಅಃ",  # aha – a + visarga

    # ── Consonants ─────────────────────────────────────────────────────────
    "P": "ಕ",   # ka
    "Q": "ಖ",   # kha
    "R": "ಗ",   # ga
    "S": "ಘ",   # gha
    "T": "ಙ",   # nga
    "U": "ಚ",   # cha
    "V": "ಛ",   # chha
    "W": "ಜ",   # ja
    "X": "ಝ",   # jha
    "Y": "ಞ",   # nya
    "Z": "ಟ",   # tta (retroflex t)
    "[": "ಠ",   # ttha
    "\\": "ಡ",  # dda
    "]": "ಢ",   # ddha
    "^": "ಣ",   # nna
    "_": "ತ",   # ta (dental)
    "`": "ಥ",   # tha
    "a": "ದ",   # da
    "b": "ಧ",   # dha
    "c": "ನ",   # na
    "d": "ಪ",   # pa
    "e": "ಫ",   # pha
    "f": "ಬ",   # ba
    "g": "ಭ",   # bha
    "h": "ಮ",   # ma
    "i": "ಯ",   # ya
    "j": "ರ",   # ra
    "k": "ಲ",   # la
    "l": "ವ",   # va / wa
    "m": "ಶ",   # sha
    "n": "ಷ",   # ssa (retroflex sh)
    "o": "ಸ",   # sa
    "p": "ಹ",   # ha
    "q": "ಳ",   # lla (retroflex l)
    "r": "ೞ",   # rra (obsolete)
    "s": "ಱ",   # rra2 (obsolete)

    # ── Dependent vowel signs (matras) ─────────────────────────────────────
    # Note: 'z' (aa-matra), '}' (u), '~' (uu) appear AFTER the consonant in
    # Nudi stream, same position as Unicode → no reordering needed.
    # '{' (i-matra) and '|' (ii-matra) appear BEFORE the consonant in Nudi
    # and must be reordered by the conversion engine.
    "z": "ಾ",          # aa-matra
    "{": "ಿ",          # i-matra  (pre-base in Nudi)
    "|": "ೀ",          # ii-matra (pre-base in Nudi)
    "}": "ು",          # u-matra
    "~": "ೂ",          # uu-matra
    "\x80": "ೃ",       # ru-matra (Windows-1252 € → ೃ)
    "\x81": "ೆ",       # e-matra
    "\x82": "ೇ",       # ee-matra
    "\x83": "ೈ",       # ai-matra
    "\x84": "ೊ",       # o-matra
    "\x85": "ೋ",       # oo-matra
    "\x86": "ೌ",       # au-matra
    "\x87": "ಂ",       # anusvara / bindu
    "\x88": "ಃ",       # visarga
    "\x89": "್",       # virama / halant
    "\x8a": "ಙ",       # nga (special position)
    "\x8b": "ಞ",       # nya (special position)

    # ── Special characters ──────────────────────────────────────────────────
    "\x8c": "ೲ",       # ji special
    "\x8d": "|",        # pipe / danda stand-in
    "\x8e": "ೱ",       # rra special
}

# ---------------------------------------------------------------------------
# Reverse map  UNICODE_KANNADA -> NUDI_ASCII
# ---------------------------------------------------------------------------
# Multi-Unicode entries (like 'ಅಂ') are intentionally included so round-trip
# conversion stays consistent.

UNICODE_TO_NUDI: dict[str, str] = {v: k for k, v in NUDI_TO_UNICODE.items()}

# ---------------------------------------------------------------------------
# Special multi-character sequences
# Sorted longest-first so the engine can greedily match the longest prefix.
# Each tuple is (nudi_sequence, unicode_string).
# ---------------------------------------------------------------------------

NUDI_SPECIAL_SEQUENCES: list[tuple[str, str]] = sorted(
    [
        # Conjuncts involving virama (\x89 = ್)
        # ka + virama + ka  → ಕ್ಕ
        ("P\x89P", "ಕ್ಕ"),
        # ka + virama + ta  → ಕ್ತ
        ("P\x89_", "ಕ್ತ"),
        # ka + virama + sha → ಕ್ಶ
        ("P\x89m", "ಕ್ಶ"),
        # ka + virama + ssa → ಕ್ಷ  (ksha)
        ("P\x89n", "ಕ್ಷ"),
        # na + virama + ka  → ನ್ಕ
        ("c\x89P", "ನ್ಕ"),
        # na + virama + ga  → ನ್ಗ
        ("c\x89R", "ನ್ಗ"),
        # na + virama + da  → ನ್ದ
        ("c\x89a", "ನ್ದ"),
        # na + virama + na  → ನ್ನ
        ("c\x89c", "ನ್ನ"),
        # ta + virama + ta  → ತ್ತ
        ("_\x89_", "ತ್ತ"),
        # ta + virama + ra  → ತ್ರ
        ("_\x89j", "ತ್ರ"),
        # da + virama + da  → ದ್ದ
        ("a\x89a", "ದ್ದ"),
        # da + virama + dha → ದ್ಧ
        ("a\x89b", "ದ್ಧ"),
        # pa + virama + pa  → ಪ್ಪ
        ("d\x89d", "ಪ್ಪ"),
        # sha + virama + cha → ಶ್ಚ  (common in transliteration)
        ("m\x89U", "ಶ್ಚ"),
        # ra + virama (ra-phala, appears as curved form)
        ("j\x89", "ರ್"),
        # Anusvara combinations (bindu after matra)
        ("\x81\x87", "ೆಂ"),   # e-matra + anusvara
        ("\x82\x87", "ೇಂ"),   # ee-matra + anusvara
        ("\x85\x87", "ೋಂ"),   # oo-matra + anusvara
        # i-matra + consonant reordering helpers (pre-base i)
        # These are handled procedurally in core.py; listed here for reference.
        # au-matra as two-part sequence (some Nudi variants)
        ("\x84\x86", "ೌ"),    # o-matra + au-part → au-matra
        # Halant at end of word (explicit virama)
        ("\x89 ", "್ "),
        # Double anusvara / chandrabindu equivalents
        ("\x87\x87", "ಂಂ"),
        # Special: visarga + vowel start sequences
        ("\x88C", "ಃಅ"),
        # Independent vowels preceded by vowel (sandhi hints)
        ("DC", "ಆಅ"),
    ],
    key=lambda t: -len(t[0]),   # longest first
)

# ---------------------------------------------------------------------------
# Helper sets for detection
# ---------------------------------------------------------------------------

# All Nudi-encoded indicator characters (non-ASCII or punctuation repurposed)
NUDI_INDICATOR_CHARS: frozenset[str] = frozenset(NUDI_TO_UNICODE.keys())

# Unicode Kannada block range
KANNADA_UNICODE_START = 0x0C80
KANNADA_UNICODE_END   = 0x0CFF
