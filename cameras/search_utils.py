"""Natural-language style search for detection events (synonyms + fuzzy spelling)."""

from __future__ import annotations

from django.db.models import Q, QuerySet

# Related terms — typing any member matches the whole group.
_SYNONYM_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"smog", "smoog", "smoke", "fog", "haze", "mist", "fire", "flame"}),
    frozenset({"person", "people", "human", "man", "woman", "pedestrian", "staff", "worker"}),
    frozenset({"car", "vehicle", "truck", "van", "bus", "motorcycle", "bike", "bicycle"}),
    frozenset({"gun", "weapon", "knife", "pistol", "rifle"}),
    frozenset({"box", "package", "parcel", "carton", "container"}),
    frozenset({"dog", "cat", "animal", "pet"}),
    frozenset({"alert", "warning", "danger", "alarm"}),
    frozenset({"unknown", "stranger", "unidentified"}),
)

_NLP_SEARCH_FIELDS = ("label", "class_name", "employee_name", "personal_number")


def levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + cost))
        prev = curr
    return prev[-1]


def expand_search_terms(query: str, *, max_fuzzy_distance: int = 1) -> list[str]:
    """Expand a user query into synonym + fuzzy spelling variants."""
    raw = (query or "").strip().lower()
    if not raw:
        return []

    terms: set[str] = {raw}
    matched_groups: list[frozenset[str]] = []

    for group in _SYNONYM_GROUPS:
        for word in group:
            if raw == word or (len(raw) >= 3 and (raw in word or word in raw)):
                matched_groups.append(group)
                break
            if len(raw) >= 4 and levenshtein_distance(raw, word) <= max_fuzzy_distance:
                matched_groups.append(group)
                break
            if len(raw) == 4 and levenshtein_distance(raw, word) <= max_fuzzy_distance:
                matched_groups.append(group)
                break

    for group in matched_groups:
        terms |= group

    return sorted(terms)


def apply_detection_search(qs: QuerySet, query: str) -> QuerySet:
    """NLP-style search on detection class and label only (synonyms + fuzzy spelling)."""
    terms = expand_search_terms(query)
    if not terms:
        return qs

    combined = Q()
    for term in terms:
        term_filter = Q()
        for field in _NLP_SEARCH_FIELDS:
            term_filter |= Q(**{f"{field}__icontains": term})
        combined |= term_filter

    return qs.filter(combined).distinct()
