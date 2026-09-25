"""Street-name normalisation and fuzzy comparison.

Indian street names come in many spellings: "Nolambur Phase Ii 4th  Cross Street", "N.S.K.Salai",
"VIIth Cross St". normalize_name() folds the common variations so they compare equal;
name_similarity() scores what is left (0-100).
"""
import re
import unicodedata

from rapidfuzz import fuzz

# Whole-word abbreviations -> full word. Applied after lower-casing and punctuation removal.
ABBREVIATIONS = {
    "st": "street", "str": "street", "rd": "road", "ave": "avenue", "av": "avenue",
    "ln": "lane", "extn": "extension", "ext": "extension", "nr": "near", "opp": "opposite",
    "mn": "main", "sal": "salai", "hwy": "highway", "blvd": "boulevard", "cr": "cross",
}
NUMBER_WORDS = {"first": "1st", "second": "2nd", "third": "3rd", "fourth": "4th", "fifth": "5th",
                "sixth": "6th", "seventh": "7th", "eighth": "8th", "ninth": "9th", "tenth": "10th",
                "eleventh": "11th", "twelfth": "12th"}
# Words that say what kind of road it is, not which one. A name made only of these ("1st Street")
# is too generic to match on its own.
GENERIC_WORDS = {"street", "road", "main", "cross", "avenue", "lane", "salai", "high", "link", "extension",
                 "new", "old", "north", "south", "east", "west", "service", "nagar", "colony", "and"}
# Single letters are NOT expanded: initials are common in Indian street names ("N.S.K. Salai").
ROMAN = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
         "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15, "xvi": 16, "xvii": 17, "xviii": 18,
         "xix": 19, "xx": 20}
# Words after which a roman numeral / bare number is an ordinal ("phase ii", "sector iv").
ORDINAL_CONTEXT = {"cross", "street", "main", "avenue", "lane", "road", "phase", "sector", "block", "stage"}


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }".replace(" ", "")


def normalize_name(name: str | None) -> str:
    """Lower-case, strip accents/punctuation, expand abbreviations, unify ordinals."""
    if not name:
        return ""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = s.split()
    out: list[str] = []
    for i, w in enumerate(words):
        nxt = words[i + 1] if i + 1 < len(words) else ""
        prev = out[-1] if out else ""
        # "viith" / "vii" (+ cross/street...) or "phase ii" -> "7th"
        m = re.fullmatch(r"([ivx]+)(st|nd|rd|th)?", w)
        if m and m.group(1) in ROMAN and (m.group(2) or nxt in ORDINAL_CONTEXT or prev in ORDINAL_CONTEXT):
            out.append(_ordinal(ROMAN[m.group(1)]))
            continue
        # "4" before cross/street -> "4th"; "4 th" -> "4th"
        if w.isdigit() and nxt in ("st", "nd", "rd", "th"):
            out.append(_ordinal(int(w)))
            words[i + 1] = ""
            continue
        if w.isdigit() and nxt in ORDINAL_CONTEXT:
            out.append(_ordinal(int(w)))
            continue
        if w == "":
            continue
        out.append(NUMBER_WORDS.get(w) or ABBREVIATIONS.get(w, w))
    # Join runs of initials: "n s k salai" -> "nsk salai".
    return re.sub(r"\b(?:[a-z] )+[a-z]\b", lambda m: m.group(0).replace(" ", ""), " ".join(out))


def is_distinctive(normalized: str) -> bool:
    """True if the name has a word that identifies the road (not just '1st street')."""
    return any(not re.fullmatch(r"\d+(st|nd|rd|th)?", w) and w not in GENERIC_WORDS
               for w in normalized.split())


def name_similarity(a: str | None, b: str | None) -> float:
    """0-100. Compares normalised names; token order and small typos matter little.
    One name containing the other ("Anna Street" / "Anna Street Padi") scores high,
    but only if the shorter one is distinctive."""
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    score = max(fuzz.ratio(na, nb), fuzz.token_sort_ratio(na, nb))
    shorter = na if len(na) <= len(nb) else nb
    if is_distinctive(shorter):
        score = max(score, fuzz.token_set_ratio(na, nb) - 5)
    return score


def compare_names(a: str | None, b: str | None, similar_at: float = 85.0) -> str:
    """same | similar | different | only_a | only_b | none."""
    a = a if isinstance(a, str) and a.strip() else None  # NaN / None / "" all mean "no name"
    b = b if isinstance(b, str) and b.strip() else None
    if not a and not b:
        return "none"
    if not b:
        return "only_a"
    if not a:
        return "only_b"
    score = name_similarity(a, b)
    if score == 100:
        return "same"
    return "similar" if score >= similar_at else "different"
