"""Arabic crisis-keyword detection for reflections.

Matched against the raw input_text (NOT the PII-cleaned text) so signals that
include names/places — e.g. "أريد أن أنتحر بسبب أحمد" — still trigger.
"""

import re
import unicodedata

# Ordered roughly by severity. Order matters only for which keyword is
# reported first when multiple match.
CRITICAL_KEYWORDS: list[str] = [
    # Suicide / self-harm intent
    "بنتحر", "أنتحر", "انتحر", "سأنتحر", "راح أنتحر", "حانتحر", "حنتحر",
    "انتحار", "بقتل نفسي", "راح أقتل نفسي", "حقتل نفسي", "أقتل نفسي",
    "اقتل نفسي", "أنهي حياتي", "بنهي حياتي", "أؤذي نفسي", "اؤذي نفسي",
    "إيذاء نفسي", "ايذاء نفسي", "أجرح نفسي", "اجرح نفسي", "أقطع نفسي",
    "اقطع نفسي",
    # Death wish
    "أتمنى الموت", "اتمنى الموت", "أتمنى أموت", "اتمنى اموت", "بتمنى أموت",
    "بتمنى اموت", "ليتني أموت", "ليتني اموت", "يا ريتني أموت",
    "يا ريتني اموت", "أفضل لو مت", "افضل لو مت", "أريد الموت", "اريد الموت",
    "بدي أموت", "بدي اموت", "ما بدي أعيش", "ما بدي اعيش",
    "لا أريد أن أعيش", "لا اريد ان اعيش", "لا أستحق الحياة", "لا استحق الحياة",
    # Severe hopelessness / collapse
    "لا أمل", "لا امل", "ميؤوس مني", "لا فائدة من حياتي", "حياتي لا قيمة لها",
    "لا أحد يهتم بي", "لا احد يهتم بي", "لا أحد يحبني", "لا احد يحبني",
    "خلاص تعبت من الحياة", "لم أعد أتحمل", "لم اعد اتحمل", "ما عاد أتحمل",
    "ما عاد اتحمل", "منهار", "اكتئاب شديد", "أكره حياتي", "اكره حياتي",
    "أكره نفسي", "اكره نفسي",
]


# Arabic diacritics range (tashkeel) — strip before matching so
# "أَنْتَحِر" matches "أنتحر".
_DIACRITICS_RE = re.compile(r"[ً-ٰٟۖ-ۭ]")

# Normalization map for letter variants that users frequently swap.
_NORMALIZE_TABLE = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ئ": "ي",
    "ؤ": "و",
    "ة": "ه",
})


def _normalize(text: str) -> str:
    """Lowercase-equivalent for Arabic: strip diacritics + unify letter shapes."""
    text = unicodedata.normalize("NFKC", text)
    text = _DIACRITICS_RE.sub("", text)
    text = text.translate(_NORMALIZE_TABLE)
    # Collapse runs of whitespace so "أنا   أنتحر" still matches.
    text = re.sub(r"\s+", " ", text)
    return text


# Dedupe by normalized form — the human-readable list intentionally includes
# hamza variants ("أنتحر" / "انتحر") for clarity, but they collapse to the
# same canonical string after _normalize, so we must not fire twice for one
# occurrence in the text. First occurrence wins as the displayed keyword.
def _build_keyword_index() -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for k in CRITICAL_KEYWORDS:
        norm = _normalize(k)
        if norm in seen:
            continue
        seen.add(norm)
        out.append((norm, k))
    return out


_NORMALIZED_KEYWORDS: list[tuple[str, str]] = _build_keyword_index()


def detect_keywords(text: str) -> list[tuple[str, str]]:
    """Return list of (original_keyword, snippet) pairs found in `text`.

    snippet is a small window around the first occurrence, useful for the
    HR-facing alert payload.
    """
    if not text:
        return []
    normalized = _normalize(text)
    hits: list[tuple[str, str]] = []
    seen: set[str] = set()
    for norm_kw, original_kw in _NORMALIZED_KEYWORDS:
        if norm_kw in normalized and original_kw not in seen:
            seen.add(original_kw)
            # Pull a snippet from the ORIGINAL text by locating the keyword's
            # approximate position in the normalized text. We can't map indices
            # 1:1 (diacritics may have been removed), so fall back to a
            # bounded substring of the original.
            idx = normalized.find(norm_kw)
            start = max(0, idx - 30)
            end = min(len(text), idx + len(norm_kw) + 30)
            snippet = text[start:end].strip()
            hits.append((original_kw, snippet))
    return hits
