"""Bounded, evidence-led font discovery with optional content-based visual evidence.

Scores are deliberately simple preferences, not typography-quality measurements.
Exact-file constraints are applied before ranking. Inspect/render finalists with
the project's actual text before choosing a typeface.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import bisect
import math
import os
import re
import unicodedata


ROLES = {"ui", "body", "display", "code", "brand", "game", "document"}
CATEGORIES = {"sans", "serif", "mono", "script", "display", "unknown"}
_BRIEF_FIELDS = {"role", "text", "query", "family", "limit", "weight", "italic", "min_styles", "required_styles",
                 "category", "require_open_evidence", "exclude", "existing_id", "style",
                 "offset", "exclude_families", "similar_to", "avoid_like", "audience",
                 "medium", "tone", "language", "hierarchy", "surroundings", "density", "size"}
_SPACE = re.compile(r"\s+")
_ALIASES = {
    "sans": "category:sans", "sans-serif": "category:sans",
    "serif": "category:serif", "editorial": "category:serif",
    "mono": "measured:mono", "monospace": "measured:mono",
    "monospaced": "measured:mono", "code": "measured:mono",
    "script": "category:script", "handwriting": "category:script",
    "display": "category:display", "condensed": "metadata:condensed",
    "narrow": "metadata:condensed", "wide": "metadata:wide",
    "expanded": "metadata:wide", "compact": "measured:compact",
    "tabular": "measured:tabular", "numeric": "measured:tabular",
    "numbers": "measured:tabular", "italic": "metadata:italic",
    "bold": "metadata:bold", "light": "metadata:light",
}
_GENERIC_FAMILIES = {
    "serif", "sans-serif", "monospace", "cursive", "fantasy", "system-ui",
    "ui-serif", "ui-sans-serif", "ui-monospace", "ui-rounded", "emoji",
    "math", "fangsong", "inherit", "initial", "unset", "revert", "revert-layer",
    "-apple-system", "blinkmacsystemfont",
}


def _clean(value, limit=100):
    """Avoid oversized or control-bearing font metadata in agent responses."""
    value = "".join(c if not unicodedata.category(c).startswith("C") else " "
                    for c in str(value or ""))
    return _SPACE.sub(" ", value).strip()[:limit]


def _key(value):
    return _SPACE.sub(" ", str(value or "")).strip().casefold()


def _family_key(font):
    # A missing family is not one enormous "unknown" family.
    return font.get("family_key") or _key(font.get("family")) or font["id"]


def _shortlist_family(font):
    return _key(font.get('family')) or _family_key(font)


def _axis(font, tag):
    for axis in font.get("axes", []):
        if axis.get("tag") == tag:
            return axis
    return None


def _style_words(font):
    """Read explicit style words, excluding a literal family-name prefix.

    Names are conflict evidence only, never a replacement for numeric metadata.
    Camel-case splitting recognizes CondItalic without matching arbitrary
    substrings such as an unrelated family named Blackbird.
    """
    family = _SPACE.sub(" ", str(font.get("family") or "")).strip()
    words = set()
    for field in ("style", "full_name"):
        name = _SPACE.sub(" ", str(font.get(field) or "")).strip()
        if family and name.casefold().startswith(family.casefold()):
            suffix = name[len(family):]
            if not suffix or not suffix[0].isalnum():
                name = suffix
        name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
        name = re.sub(r"([A-Z])([A-Z][a-z])", r"\1 \2", name)
        words.update(re.findall(r"[a-z]+", name.casefold()))
    return words


def _weight_name_conflict(words, requested):
    # Deliberately broad bands: naming conventions cannot establish an exact
    # weight, but an explicit heavy style is incompatible with regular 400.
    if words & {"bold", "semibold", "demibold", "extrabold", "ultrabold"} and requested < 600:
        return True
    if words & {"black", "heavy"} and requested < 700:
        return True
    if words & {"thin", "hairline", "light", "extralight", "ultralight"} and requested > 350:
        return True
    return False


def _covers(font, codepoints):
    ranges = sorted((int(a), int(b)) for a, b in font.get("coverage", []))
    starts = [a for a, _ in ranges]
    for cp in codepoints:
        ix = bisect.bisect_right(starts, cp) - 1
        if ix < 0 or cp > ranges[ix][1]:
            return False
    return True


def _style_signature(font):
    return (_key(font.get("style")), font.get("weight"), bool(font.get("italic")))


def _styles(fonts):
    by_style = {}
    for font in fonts:
        signature = _style_signature(font)
        by_style.setdefault(signature, {
            "style": _clean(font.get("style"), 60),
            "weight": font.get("weight"), "italic": bool(font.get("italic")),
        })
    ordered = sorted(by_style.values(), key=lambda s: (
        s["weight"] if isinstance(s["weight"], (float, int)) else 0,
        s["italic"], s["style"].casefold()))
    return {
        "count": len(ordered), "styles": ordered[:12],
        "truncated": len(ordered) > 12,
        "meaning": "Observed distinct face styles in this catalog; not proof of a complete family. Variable instances are not counted as additional faces.",
    }


def _validate_brief(brief):
    if not isinstance(brief, dict):
        raise ValueError("brief must be a JSON object")
    role = brief.get("role", "ui")
    if role not in ROLES:
        raise ValueError("role must be one of " + ", ".join(sorted(ROLES)))
    limit = brief.get("limit", 6)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
        raise ValueError("limit must be an integer between 1 and 20")
    offset = brief.get("offset", 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 5000:
        raise ValueError("offset must be an integer between 0 and 5000")
    if "size" in brief and (isinstance(brief["size"], bool) or not isinstance(brief["size"], (int, float)) or not 6 <= brief["size"] <= 300):
        raise ValueError("size must be a number between 6 and 300 CSS pixels")
    if "density" in brief and brief["density"] not in {"comfortable", "balanced", "dense"}:
        raise ValueError("density must be comfortable, balanced, or dense")
    minimum = brief.get("min_styles", 1)
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= 1000:
        raise ValueError("min_styles must be an integer between 1 and 1000")
    if "weight" in brief:
        weight = brief["weight"]
        if isinstance(weight, bool) or not isinstance(weight, (int, float)) or not 1 <= weight <= 1000:
            raise ValueError("weight must be a number between 1 and 1000")
    if "italic" in brief and not isinstance(brief["italic"], bool):
        raise ValueError("italic must be boolean")
    if "require_open_evidence" in brief and not isinstance(brief["require_open_evidence"], bool):
        raise ValueError("require_open_evidence must be boolean")
    required = brief.get('required_styles', [])
    if not isinstance(required, list) or len(required) > 8:
        raise ValueError('required_styles must be a list of at most 8 weight/italic objects')
    for style in required:
        if not isinstance(style, dict) or set(style) != {'weight', 'italic'} or not isinstance(style['italic'], bool) or isinstance(style['weight'], bool) or not isinstance(style['weight'], int) or not 1 <= style['weight'] <= 1000:
            raise ValueError('Each required style needs integer weight 1..1000 and boolean italic')
    for field, maximum in (("text", 20000), ("query", 300), ("family", 300), ("style", 100), ("existing_id", 100),
                           ("similar_to", 100), ("avoid_like", 100),
                           ("audience", 300), ("medium", 100), ("tone", 300),
                           ("language", 100), ("hierarchy", 300), ("surroundings", 500)):
        if field in brief and (not isinstance(brief[field], str) or len(brief[field]) > maximum):
            raise ValueError(f"{field} must be a string of at most {maximum} characters")
    if "category" in brief and brief["category"] not in CATEGORIES:
        raise ValueError("category must be one of " + ", ".join(sorted(CATEGORIES)))
    excluded = brief.get("exclude", [])
    if not isinstance(excluded, list) or len(excluded) > 1000 or not all(isinstance(x, str) for x in excluded):
        raise ValueError("exclude must be a list of at most 1000 exact IDs")
    excluded_families = brief.get("exclude_families", [])
    if not isinstance(excluded_families, list) or len(excluded_families) > 100 or not all(isinstance(x, str) and len(x) <= 300 for x in excluded_families):
        raise ValueError("exclude_families must be a list of at most 100 literal family names")
    return role, limit, minimum


def _hard_constraints(font, brief, codepoints, family_styles):
    failures = []
    axes = {}
    if _key(font.get('family')) == '(unnamed)':
        failures.append('missing_family_identity')
    if not font.get('coverage'):
        failures.append('no_usable_unicode_cmap')
    if 'family' in brief and _key(font.get('family')) != _key(brief['family']):
        failures.append('exact_family_name_mismatch')
    style_words = _style_words(font) if 'weight' in brief or 'italic' in brief else set()
    if font["id"] in brief.get("exclude", []):
        failures.append("explicitly_excluded")
    if _key(font.get("family")) in {_key(value) for value in brief.get("exclude_families", [])}:
        failures.append("explicitly_excluded_family")
    if codepoints and not _covers(font, codepoints):
        failures.append("missing_requested_characters")
    if "weight" in brief:
        requested = brief["weight"]
        variable = _axis(font, "wght")
        if variable:
            if variable["min"] <= requested <= variable["max"]:
                axes["wght"] = requested
            else:
                failures.append("requested_weight_unavailable")
        else:
            if font.get("weight") != requested:
                failures.append("requested_weight_unavailable")
            if _weight_name_conflict(style_words, requested):
                failures.append("weight_metadata_conflict")
    if "italic" in brief:
        requested = brief["italic"]
        variable = _axis(font, "ital")
        if variable:
            if variable["min"] <= int(requested) <= variable["max"]:
                axes["ital"] = int(requested)
            else:
                failures.append("requested_italic_state_unavailable")
        else:
            if bool(font.get("italic")) != requested:
                failures.append("requested_italic_state_unavailable")
            if style_words & {'italic', 'oblique', 'slanted', 'obl'} and not font.get('italic'):
                failures.append('style_metadata_conflict')
    if "style" in brief and _key(font.get("style")) != _key(brief["style"]):
        failures.append("requested_style_name_unavailable")
    if "category" in brief and font.get("category", "unknown") != brief["category"]:
        failures.append("category_metadata_mismatch")
    if family_styles["count"] < brief.get("min_styles", 1):
        failures.append("insufficient_observed_family_styles")
    if brief.get("require_open_evidence") and font.get("rights", {}).get("status") != "embedded-open-license":
        failures.append("open_license_evidence_not_present")
    if font.get("render_probe") is False:
        failures.append("render_probe_failed")
    return failures, axes


# Keep language interpretation deliberately inspectable. Negation scopes across
# coordinated terms, including comma lists, but resets at a clause boundary or
# explicit positive transition. It is
# not silently discarded before aliases or visual-semantic retrieval.
_NEGATORS = {"not", "no", "without", "avoid", "avoiding", "neither", "less", "exclude", "excluding"}
_CONTRAST = {"but", "however", "yet", "instead", "except"}
_AFFIRMERS = {"prefer", "preferring", "want", "use", "include", "including"}
_GRAMMAR = _NEGATORS | _CONTRAST | _AFFIRMERS | {"and", "or", "nor", "a", "an", "the", "too", "very", "rather"}


def interpret_query(query):
    """Return positive/negative terms for transparent ranking and visual adapters.

    Unknown words are retained with their polarity so a content-based adapter
    can interpret 'not playful' without accidentally rewarding playfulness.
    """
    tokens = re.findall(r"[\w-]+|[,;.!?:]", _key(query))
    positive, negative, unknown_positive, unknown_negative = {}, {}, [], []
    negated = False
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == ",":
            i += 1
            continue
        if token in {";", ".", "!", "?", ":"} or token in _CONTRAST:
            negated = False
            i += 1
            continue
        if token in _AFFIRMERS:
            # "do not use X" stays negative; a new comma-led clause such as
            # "avoid X, prefer Y" explicitly switches back to positive.
            if i and tokens[i - 1] == ",":
                negated = False
            i += 1
            continue
        if token in _NEGATORS:
            if token == 'without' and i + 1 < len(tokens) and tokens[i + 1] == 'losing':
                i += 2
                continue
            # 'not only X but also Y' is additive, not a request to avoid X.
            if token == "not" and i + 1 < len(tokens) and tokens[i + 1] == "only":
                i += 2
                continue
            negated = True
            i += 1
            continue
        local_negative = negated
        term = token
        if token.startswith("non-") and len(token) > 4:
            term = token[4:]
            local_negative = True
        if term == "sans" and i + 1 < len(tokens) and tokens[i + 1] == "serif":
            term = "sans-serif"
            i += 1
        elif term in {'high','low'} and i + 1 < len(tokens) and tokens[i + 1] == 'contrast':
            term += ' contrast'
            i += 1
        if term in {"high", "large"} and i + 1 < len(tokens) and tokens[i + 1] == "x-height":
            term += " x-height"
            i += 1
        preference = "measured:high-x-height" if term in {"high x-height", "large x-height"} else _ALIASES.get(term)
        if preference:
            (negative if local_negative else positive)[term] = preference
        elif term not in _GRAMMAR and term not in {"only", "also"}:
            destination = unknown_negative if local_negative else unknown_positive
            if term not in destination:
                destination.append(term)
        i += 1
    return {"positive": positive, "negative": negative,
            "unmodeled_positive": unknown_positive, "unmodeled_negative": unknown_negative}


def interpret_brief(brief):
    """Query and tone are independent clauses, shared by every ranker."""
    result = {"positive": {}, "negative": {}, "unmodeled_positive": [], "unmodeled_negative": []}
    for field in ("query", "tone"):
        terms = interpret_query(brief.get(field, ""))
        for polarity in ("positive", "negative"):
            result[polarity].update(terms[polarity])
            unknown = "unmodeled_" + polarity
            result[unknown].extend(term for term in terms[unknown] if term not in result[unknown])
    return result


def _preference_match(font, preference, weight, italic):
    metrics = font.get("metrics") or {}
    category = font.get("category", "unknown")
    if preference.startswith("category:"):
        return category == preference.split(":", 1)[1], "metadata"
    if preference in {"measured:mono", "measured:tabular"}:
        key = "mono_measured" if preference.endswith("mono") else "digit_tabular_default"
        return metrics.get(key) is True, "measured"
    if preference == "measured:compact":
        value = metrics.get("average_advance_em")
        return isinstance(value, (int, float)) and 0 < value <= 0.52, "measured+heuristic"
    if preference == "measured:high-x-height":
        value = metrics.get("x_height_em")
        return isinstance(value, (int, float)) and value >= 0.5, "measured+heuristic"
    if preference == "metadata:condensed":
        return 1 <= (font.get("width_class") or 5) <= 4, "metadata"
    if preference == "metadata:wide":
        return (font.get("width_class") or 5) >= 6, "metadata"
    if preference == "metadata:bold":
        return weight >= 700, "metadata"
    if preference == "metadata:light":
        return weight <= 300, "metadata"
    if preference == "metadata:italic":
        return italic, "metadata"
    return False, "metadata"


def _similarity(font, reference):
    """Low-dimensional shape proximity, explicitly distinct from visual judgment."""
    left, right = font.get("metrics") or {}, reference.get("metrics") or {}
    distances, fields = [], []
    for key, scale in (("x_height_em", .3), ("cap_height_em", .3), ("average_advance_em", .5)):
        a, b = left.get(key), right.get(key)
        if isinstance(a, (float, int)) and isinstance(b, (float, int)) and math.isfinite(a) and math.isfinite(b):
            distances.append(min(1, abs(a - b) / scale))
            fields.append(key)
    # One isolated metric is too little evidence for a similarity claim.
    if len(distances) < 2:
        return None, fields
    return 1 - sum(distances) / len(distances), fields


def _visual_record(value):
    if not isinstance(value, dict):
        return None
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        return None
    matches = value.get("matches", [])
    result = {"score": round(max(-20, min(20, score)), 4),
            "description": _clean(value.get("description"), 400),
            "basis": _clean(value.get("basis", "visual-adapter"), 80),
            "matches": [_clean(x, 80) for x in matches[:12]] if isinstance(matches, list) else []}
    similarity = value.get("raw_similarity")
    if isinstance(similarity, (int, float)) and not isinstance(similarity, bool) and math.isfinite(similarity):
        result["raw_similarity"] = round(similarity, 6)
    if "sample_script" in value:
        result["sample_script"] = _clean(value["sample_script"], 40)
    if "sample_language" in value:
        result["sample_language"] = _clean(value["sample_language"], 40)
    axes = value.get("sample_axes")
    if isinstance(axes, dict):
        result["sample_axes"] = {str(tag)[:4]: number for tag, number in list(axes.items())[:16]
                                 if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number)}
    return result


def _rank(font, brief, role, family_styles, interpretation, references, visual=None):
    score = 0
    reasons = []
    category = font.get("category", "unknown")
    metrics = font.get("metrics") or {}
    weight = brief.get("weight", font.get("weight", 400))
    italic = brief.get("italic", bool(font.get("italic")))

    def add(points, basis, reason):
        nonlocal score
        score += points
        reasons.append({"basis": basis, "points": round(points, 4), "reason": reason})

    if role == "code":
        if metrics.get("mono_measured") is True:
            add(6, "measured", "Sampled glyph advances are equal; useful evidence for aligned code.")
        elif category == "mono":
            add(2, "metadata", "Metadata labels this as monospaced; inspect alignment in the actual text.")
    elif role in {"ui", "body", "document"}:
        if category in {"sans", "serif"}:
            add(2, "heuristic", f"{category.title()} metadata is a starting point for this text role, not a readability verdict.")
        xheight = metrics.get("x_height_em")
        if isinstance(xheight, (int, float)) and 0.45 <= xheight <= 0.65:
            add(1, "measured+heuristic", "Measured x-height is 0.45–0.65 em; this modest preference needs a size-specific preview.")
        if family_styles["count"] >= 3:
            add(1, "metadata", "At least three distinct face styles are present for hierarchy.")
    elif role in {"display", "brand"} and category in {"display", "script", "serif", "sans"}:
        add(1, "heuristic", "This role permits multiple categories; compare its actual letterforms.")

    if "weight" not in brief and 350 <= weight <= 500:
        add(1, "heuristic", "A regular-weight starting point keeps the first comparison useful.")
    if "italic" not in brief and not italic:
        add(1, "heuristic", "Upright is the default starting point when no slant is requested.")

    query = _key(brief.get("query"))
    family = _key(font.get("family"))
    if query and query in {family, _key(font.get("full_name")), _key(font.get("postscript_name"))}:
        add(20, "metadata", "Exact font or family-name query match.")
    elif query and len(query) >= 3 and query in family:
        add(5, "metadata", "The query occurs in the family name; this is a text match, not visual evidence.")

    negative_preferences = set(interpretation["negative"].values())
    for preference in sorted(set(interpretation["positive"].values()) | negative_preferences):
        match, basis = _preference_match(font, preference, weight, italic)
        if match:
            # In a contradictory brief an explicit avoidance wins. A preference
            # is still soft; known matching candidates can be explored later.
            if preference in negative_preferences:
                add(-6, basis, f"Negated query preference matched and penalized: {preference}.")
            else:
                add(3, basis, f"Transparent query preference matched: {preference}.")

    xheight = metrics.get("x_height_em")
    size = brief.get("size")
    if size is not None and size <= 16 and isinstance(xheight, (int, float)):
        if .5 <= xheight <= .7:
            add(2, "measured+context", "At the requested small size, x-height 0.50–0.70 em is a useful starting point; inspect counters and spacing in context.")
        elif xheight < .42:
            add(-2, "measured+context", "Small measured x-height may make this requested small size harder to use; inspect the composition.")
    audience = _key(brief.get("audience"))
    if re.search(r"\b(children|child|seniors|older|early readers)\b", audience) and isinstance(xheight, (int, float)) and .5 <= xheight <= .7:
        add(1, "measured+context", "Larger lowercase proportions are a starting preference for this audience; they do not establish accessibility.")
    advance = metrics.get("average_advance_em")
    density = brief.get("density")
    if density == "dense" and isinstance(advance, (int, float)) and 0 < advance <= .55:
        add(2, "measured+context", "Sampled average advances support the requested dense layout; verify actual line breaks and readable spacing.")
    if density == "comfortable" and isinstance(advance, (int, float)) and .5 <= advance <= .7:
        add(1, "measured+context", "Moderate sampled advances are a starting point for the requested comfortable density.")
    if metrics.get("digit_tabular_default") is True and (sum(c.isdigit() for c in brief.get("text", "")) >= 6 or re.search(r"\b(table|dashboard|data|numeric|schedule)\b", _key(brief.get("medium")))):
        add(1, "measured+context", "Equal default digit advances support the numeric content or medium supplied.")
    if brief.get("hierarchy") and family_styles["count"] >= 3:
        add(1, "metadata+context", "Several observed styles are available for the requested hierarchy; use required_styles to guarantee exact companions.")

    if visual is not None:
        add(visual["score"], visual["basis"], "Content-based visual retrieval: " + (visual["description"] or "adapter similarity score"))
    else:
        for key, polarity in (("similar_to", 1), ("avoid_like", -1)):
            if key not in references:
                continue
            similarity, fields = _similarity(font, references[key])
            if similarity is not None:
                add(round(5 * similarity * polarity, 4), "measured-similarity", f"{'Similarity to' if polarity > 0 else 'Avoidance of'} reference proportions across {', '.join(fields)}; this does not measure letterform personality.")
    return round(score, 4), reasons


def _compact(font, score, reasons, axes, styles, baseline=False):
    rights = font.get("rights") or {}
    metric_keys = ("x_height_em", "cap_height_em", "average_advance_em", "mono_measured", "digit_tabular_default")
    return {
        "id": font["id"], "family": _clean(font.get("family")),
        "style": _clean(font.get("style"), 60), "weight": font.get("weight"),
        "italic": bool(font.get("italic")), "category": font.get("category", "unknown"),
        "score": score, "score_meaning": "Heuristic preference points; not a quality or readability score.",
        "reasons": sorted(reasons, key=lambda item: -abs(item["points"]))[:12], "required_axes": axes,
        "metrics": {k: (font.get("metrics") or {}).get(k) for k in metric_keys},
        "family_available_styles": styles,
        "rights": {"status": rights.get("status", "unknown"), "review_required": True},
        "warnings": [_clean(x, 140) for x in font.get("warnings", [])[:4]],
        "existing_baseline": baseline,
    }


def _diversity_signature(font):
    metrics = font.get("metrics") or {}

    def bin_metric(key):
        value = metrics.get(key)
        return int(value * 10) if isinstance(value, (int, float)) else None

    category = font.get("category")
    return (category if category != "unknown" else None, font.get("width_class"),
            metrics.get("mono_measured"), bin_metric("x_height_em"),
            bin_metric("average_advance_em"))


def _distance(left, right):
    # Absence of evidence does not itself earn a diversity bonus.
    return sum(weight for a, b, weight in zip(left, right, (3, 1, 2, 1, 1))
               if a is not None and b is not None and a != b)


def search(catalog, brief: dict, visual_index=None) -> dict:
    """Return at most 20 exact-face candidates, one per family plus baseline.

    ``catalog`` implements ``all()``; a list of font dicts is also accepted for
    composition/tests. ``existing_id`` is always reserved a result slot when it
    satisfies constraints, otherwise its concrete rejection is reported. Name,
    foundry, provenance, and popularity never determine preference except when
    the user explicitly supplies a font-name query.
    """
    role, limit, _ = _validate_brief(brief)
    originals = catalog if isinstance(catalog, list) else catalog.all()
    if visual_index is not None and not isinstance(visual_index, dict):
        raise ValueError("visual_index must map exact IDs to visual evidence objects")
    fonts = []
    for original in originals:
        font = dict(original)
        font['metrics'] = dict(original.get('metrics') or {})
        for field in ['x_height_em', 'cap_height_em', 'average_advance_em']:
            value = font['metrics'].get(field)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                font['metrics'][field] = None
        fonts.append(font)
    families = defaultdict(list)
    by_id = {}
    for font in fonts:
        families[_family_key(font)].append(font)
        by_id[font["id"]] = font
    references = {}
    for field in ("similar_to", "avoid_like"):
        if brief.get(field):
            if brief[field] not in by_id:
                raise ValueError(f"{field} ID is not in this catalog")
            references[field] = by_id[brief[field]]
    visual_records = {ident: record for ident, raw in (visual_index or {}).items()
                      if ident in by_id and (record := _visual_record(raw)) is not None}
    family_styles = {key: _styles([font for font in items if font.get("render_probe") is not False])
                     for key, items in families.items()}
    # Newline, tab, and carriage return are layout controls, not font glyphs.
    codepoints = sorted({ord(c) for c in brief.get("text", "") if c not in "\n\r\t"})
    # Resolve each requested hierarchy style against the same version group and
    # actual project characters; a count of files is not a regular/bold guarantee.
    family_resolutions = {}
    for family_key, group in families.items():
        resolutions = []
        for requested in brief.get('required_styles', []):
            matches = []
            for face in group:
                constraints = dict(requested, require_open_evidence=brief.get('require_open_evidence', False), exclude=brief.get('exclude', []))
                failures, required_axes = _hard_constraints(face, constraints, codepoints, family_styles[family_key])
                if not failures:
                    matches.append((bool(required_axes), face['id'], required_axes))
            if not matches:
                resolutions = None
                break
            _, ident, applied = sorted(matches, key=lambda x:(x[0],x[1]))[0]
            resolutions.append(dict(requested, id=ident, required_axes=applied))
        family_resolutions[family_key] = resolutions
    query = _key(brief.get("query"))
    interpretation = interpret_brief(brief)
    query_terms = interpretation["positive"]
    eligible = []
    rejected = Counter()
    reject_by_id = {}
    existing_id = brief.get("existing_id")
    for font in fonts:
        styles = family_styles[_family_key(font)]
        failures, axes = _hard_constraints(font, brief, codepoints, styles)
        if family_resolutions[_family_key(font)] is None:
            failures.append('required_family_style_unavailable')
        if failures:
            rejected.update(failures)
            if font["id"] == existing_id:
                reject_by_id[font["id"]] = failures
            continue
        score, reasons = _rank(font, brief, role, styles, interpretation, references, visual_records.get(font["id"]))
        eligible.append((score, font, reasons, axes, styles))
    # Content digest breaks equal-score ties without familiarity/name favoritism.
    eligible.sort(key=lambda entry: (-entry[0], entry[1].get("canonical_hash") or entry[1]["id"], entry[1]["id"]))
    selected = []
    seen_families = set()
    seen_content = set()
    baseline = {"requested_id": existing_id, "status": "not_supplied"}
    if existing_id:
        baseline["status"] = "rejected"
        if existing_id not in by_id:
            baseline["reasons"] = ["id_not_in_catalog"]
        elif existing_id in reject_by_id:
            baseline["reasons"] = reject_by_id[existing_id]
        else:
            baseline["status"] = "retained"
            entry = next(entry for entry in eligible if entry[1]["id"] == existing_id)
            selected.append(entry)
            seen_families.add(_shortlist_family(entry[1]))
            seen_content.add(entry[1].get("canonical_hash") or entry[1]["id"])
    # Pick the strongest exact face per family before pagination. This prevents
    # another style of a seen family from filling every next page.
    representatives = []
    for entry in eligible:
        family = _shortlist_family(entry[1])
        content = entry[1].get("canonical_hash") or entry[1]["id"]
        if family in seen_families or content in seen_content:
            continue
        representatives.append(entry)
        seen_families.add(family)
        seen_content.add(content)
    offset = brief.get("offset", 0)
    capacity = limit - len(selected)
    wanted = min(len(representatives), offset + capacity)
    # Greedy diversity only breaks equal score ties. Incremental minimum
    # distances keep later pages bounded rather than recomputing all pairs.
    signatures = [_diversity_signature(entry[1]) for entry in representatives]
    baseline_signatures = [_diversity_signature(entry[1]) for entry in selected]
    novelty = [min((_distance(sig, other) for other in baseline_signatures), default=0)
               for sig in signatures]
    used = set()
    ordered = []
    while len(ordered) < wanted:
        remaining = [i for i in range(len(representatives)) if i not in used]
        if not remaining:
            break
        best = max(remaining, key=lambda i: (representatives[i][0], novelty[i], -i))
        used.add(best)
        ordered.append(representatives[best])
        for i in remaining:
            if i == best:
                continue
            distance = _distance(signatures[i], signatures[best])
            novelty[i] = min(novelty[i], distance) if baseline_signatures or len(ordered) > 1 else distance
    selected.extend(ordered[offset:offset + capacity])
    candidates = [_compact(font, score, reasons, axes, styles, font["id"] == existing_id)
                  for score, font, reasons, axes, styles in selected]
    for candidate, entry in zip(candidates, selected):
        resolutions = []
        for chosen in family_resolutions[_family_key(entry[1])]:
            requested = {'weight':chosen['weight'], 'italic':chosen['italic']}
            failures, applied = _hard_constraints(entry[1], requested, codepoints, entry[4])
            resolutions.append(dict(requested, id=candidate['id'], required_axes=applied) if not failures else chosen)
        candidate['family_style_resolutions'] = resolutions
        if candidate['id'] in visual_records:
            candidate['visual_evidence'] = visual_records[candidate['id']]
        candidate['evidence_gaps'] = (["visual_category_unknown"] if candidate['category'] == 'unknown' else []) + ([] if candidate['id'] in visual_records else ["no_visual_index_evidence"])
    alternatives = [
        {"option": "single_family", "advice": "Compare a single family's observed styles before adding a second typeface; additional fonts are not inherently an improvement."},
        {"option": "keep_existing", "advice": "Keeping the current typography is a valid outcome. Supply existing_id to include an exact catalog face as the comparison baseline."},
    ]
    return {
        "schema_version": 1, "status": "candidates" if candidates else "no_matches",
        "role": role, "candidates": candidates, "baseline": baseline,
        "counts": {"catalog_faces": len(fonts), "eligible_faces": len(eligible),
                   "returned_faces": len(candidates),
                   "eligible_distinct_alternatives": len(representatives),
                   "visual_scored_faces": sum(entry[1]["id"] in visual_records for entry in eligible)},
        "pagination": {"offset": offset, "limit": limit,
                       "next_offset": offset + max(0, len(candidates) - len(baseline_signatures)) if capacity and offset + capacity < len(representatives) else None,
                       "has_more": offset + capacity < len(representatives),
                       "meaning": "Offset counts distinct alternatives, excluding the reserved baseline. Keep the brief and catalog fixed between pages; changing either starts a new exploration."},
        "constraint_rejections": dict(sorted(rejected.items())),
        "query_interpretation": {
            "exact_name_match_count": sum(query in {_key(f.get('family')), _key(f.get('full_name')), _key(f.get('postscript_name'))} for f in fonts) if query else 0,
            "name_lookup_advice": "query ranks preferences and can return alternatives when a name is absent. Use family for a hard exact family-name lookup.",
            "aliases": query_terms,
            "negated_aliases": interpretation["negative"],
            "unmodeled_terms": sorted(set(interpretation["unmodeled_positive"] + interpretation["unmodeled_negative"]))[:20],
            "unmodeled_terms_meaning": "Terms not interpreted by deterministic aliases. The active visual adapter may interpret their appearance; inspect its evidence and render finalists." if visual_records else "Terms not interpreted by deterministic aliases; only literal name matching can use them without a visual adapter.",
            "negation_scope": "Query and tone are interpreted independently. Negation extends across comma-coordinated terms until a sentence/semicolon/colon boundary, an explicit contrast such as but, or a comma-led positive clause such as prefer or use. Check the reported polarity for ambiguous prose.",
            "unmodeled_positive": interpretation["unmodeled_positive"][:20],
            "unmodeled_negative": interpretation["unmodeled_negative"][:20],
            "visual_scoring_active": bool(visual_records),
            "unrecognized_brief_fields": [_clean(field, 60) for field in sorted(set(brief) - _BRIEF_FIELDS)[:20]],
            "method": "Negation-aware aliases, literal name matches, measured context preferences, and optional content-based visual evidence. Unmodeled terms are not interpreted by metadata ranking; a visual adapter may interpret them. unrecognized brief fields have no effect.",
        },
        "refinement": {"similar_to": brief.get("similar_to"), "avoid_like": brief.get("avoid_like"),
                       "method": "Content-based visual evidence when supplied for a face; otherwise proximity in at least two measured proportions. Reference IDs remain eligible unless excluded."},
        "context_interpretation": {"supplied_fields": [field for field in ("audience", "medium", "tone", "language", "hierarchy", "surroundings", "density", "size") if field in brief],
                                   "measurement_rules": ["small-size lowercase proportions", "audience lowercase proportions", "density sampled advances", "numeric alignment", "observed hierarchy styles"],
                                   "handoff_fields": [field for field in ("language", "surroundings") if field in brief],
                                   "advice": "Use the actual language, size, text, hierarchy and surrounding design in a contextual composition. Context fields guide preferences; none proves aesthetic fit."},
        "constraints": {"coverage": "Requested non-layout characters must occur in cmap; this does not prove shaping correctness.",
                        "text_codepoint_count": len(codepoints),
                        "text_supplied": bool(brief.get("text")),
                        "family_diversity": "At most one face per family; equivalent canonical content is also deduplicated. Equal-score ties favor differences in known category, width, monospace measurement, x-height, and advance-width bands; this is not proof of visual distinction.",
                        "open_evidence_requested": bool(brief.get("require_open_evidence"))},
        "alternatives": alternatives,
        "limitations": [
            "Rankings combine explicitly labeled evidence. Visual adapter scores are interpretations, not quality or readability measurements; missing visual evidence remains eligible.",
            "Render the selected exact faces on project text at intended sizes. Coverage alone cannot establish legibility, shaping, personality, or good pairing.",
            "Metadata categories and family groupings may be imperfect. Available styles describe this collection, not a complete upstream family.",
            "Unknown rights remain unknown. Embedded open-license evidence is not legal clearance; review source and license evidence before distribution.",
        ],
    }


_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "vendor", ".venv", "venv",
    "__pycache__", "dist", "build", ".next", ".cache", "coverage", "target",
}
_PROJECT_EXTENSIONS = {".css", ".scss", ".sass", ".less", ".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".json", ".vue", ".svelte"}


def _font_declarations(text):
    """Extract literal declarations only; never execute project configuration."""
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    # CSS, inline HTML styles, and CSS-in-JS with literal strings.
    pattern = r"(?<![\w-])font-family\s*:\s*([^;}\n]{1,500})"
    for match in re.finditer(pattern, text, re.I):
        value = match.group(1).strip()
        # An HTML attribute quote is not part of the font stack.
        value = value.split(">", 1)[0].rstrip("\"' ")
        yield value
    pattern = r"\bfontFamily\s*[\"']?\s*:\s*(\[[^\]\n]{1,500}\]|[\"'][^\n]{1,500}?[\"'])"
    for match in re.finditer(pattern, text):
        yield match.group(1).strip("[] ").strip("\"'")
    # Common Tailwind/theme fontFamily literal maps. Nested/functional values
    # are intentionally unsupported; the configuration is never evaluated.
    for block in re.finditer(r"\bfontFamily\s*[\"']?\s*:\s*\{([^{}]{1,2000})\}", text):
        for match in re.finditer(r"[\w\"'-]+\s*:\s*(\[[^\]\n]{1,500}\]|[\"'][^\n]{1,500}?[\"'])", block.group(1)):
            yield match.group(1).strip("[] ").strip("\"'")
    # Common CSS shorthand with explicit size and optional line height.
    for match in re.finditer(r"(?<![\w-])font\s*:\s*[^;{}\n]{0,100}?\d+(?:\.\d+)?(?:px|pt|rem|em|%)\s*(?:/\s*[\d.]+(?:px|pt|rem|em|%)?\s*)?\s+([^;}\n]{1,500})", text, re.I):
        yield match.group(1)
    # CSS custom properties named as font tokens; sizes/weights are excluded.
    pattern = r"--(?:font-family|font-(?!size|weight|style|stretch|variant|feature)[\w-]+)\s*:\s*([^;}\n]{1,500})"
    for match in re.finditer(pattern, text, re.I):
        yield match.group(1).strip()


def _parse_stack(value):
    result = []
    for raw in value.split(",")[:12]:
        name = _clean(raw.strip().strip("\"'"), 100)
        # Permit literal names, CSS generics, and local var() references only.
        # Anything expression-like or URL-like stays out of the context output.
        if not name or not re.fullmatch(r"[\w \-]+|var\(--[\w-]+\)", name):
            continue
        if re.match(r"^(?:\d|true$|false$|null$)", name):
            continue
        result.append(name)
    return result


def project_context(root) -> dict:
    """Read a bounded local project snapshot and return font declarations only.

    No source code, document prose, environment files, network calls, recursive
    symlink traversal, dependency execution, or inferred audience is included.
    This is a hint collector, not a CSS cascade/browser computed-style engine.
    """
    root = Path(root).expanduser()
    if root.is_symlink():
        raise ValueError("project root must not be a symlink")
    if not root.is_dir():
        raise ValueError("project root must be an existing directory")
    root = root.resolve()
    max_files, max_bytes, per_file_bytes, max_depth = 300, 2_000_000, 65_536, 6
    files_read = total_bytes = symlinks_skipped = unreadable = oversized = 0
    counts = Counter()
    locations = defaultdict(set)
    stacks = Counter()
    truncated = False
    examined = 0
    max_entries = 6000
    pending = [(root, 0)]
    while pending:
        directory, depth = pending.pop()
        try:
            # Avoid an unbounded directory listing as well as unbounded reads.
            with os.scandir(directory) as iterator:
                entries = []
                for item in iterator:
                    examined += 1
                    if examined > max_entries:
                        truncated = True
                        break
                    entries.append(item)
            entries.sort(key=lambda item: item.name)
        except OSError:
            unreadable += 1
            continue
        for entry in entries:
            if files_read >= max_files or total_bytes >= max_bytes:
                truncated = True
                break
            try:
                if entry.is_symlink():
                    symlinks_skipped += 1
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                        continue
                    if depth < max_depth:
                        pending.append((Path(entry.path), depth + 1))
                    else:
                        truncated = True
                    continue
                path = Path(entry.path)
                if not entry.is_file(follow_symlinks=False) or path.suffix.lower() not in _PROJECT_EXTENSIONS or entry.name.startswith("."):
                    continue
                if entry.name.endswith((".min.js", ".min.css", "-lock.json")):
                    continue
                size = entry.stat(follow_symlinks=False).st_size
                if size > per_file_bytes:
                    oversized += 1
                    # Skipping rather than partial extraction avoids suggesting
                    # that a half-read configuration represents a project.
                    continue
                if total_bytes + size > max_bytes:
                    truncated = True
                    break
                # O_NOFOLLOW prevents a last-moment file symlink substitution.
                descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(descriptor, "rb") as handle:
                    data = handle.read(per_file_bytes + 1)
                if len(data) > per_file_bytes:
                    oversized += 1
                    continue
                total_bytes += len(data)
                files_read += 1
                source = _clean(str(path.relative_to(root)).replace(os.sep, "/"), 240)
                for declaration in _font_declarations(data.decode("utf-8", errors="replace")):
                    stack = _parse_stack(declaration)
                    if not stack:
                        continue
                    stacks[tuple(stack)] += 1
                    for name in stack:
                        counts[name] += 1
                        if len(locations[name]) < 4:
                            locations[name].add(source)
            except OSError:
                unreadable += 1
        if truncated and (files_read >= max_files or total_bytes >= max_bytes or examined > max_entries):
            break
    ordered = sorted(counts, key=lambda name: (-counts[name], name.casefold()))[:40]
    return {
        "schema_version": 1,
        "font_families": [{"name": name, "declarations": counts[name],
                           "kind": "css_variable" if name.startswith("var(") else "generic" if name.casefold() in _GENERIC_FAMILIES else "literal_family",
                           "sources": sorted(locations[name])}
                          for name in ordered],
        "font_stacks": [{"families": list(stack), "declarations": count}
                        for stack, count in sorted(stacks.items(), key=lambda item: (-item[1], item[0]))[:12]],
        "scan": {"files_read": files_read, "bytes_read": total_bytes,
                 "symlinks_skipped": symlinks_skipped, "unreadable": unreadable,
                 "oversized_files_skipped": oversized,
                 "truncated": truncated or len(counts) > 40 or len(stacks) > 12,
                 "limits": {"files": max_files, "bytes": max_bytes,
                            "per_file_bytes": per_file_bytes, "depth": max_depth,
                            "directory_entries": max_entries}},
        "next_step": "Resolve literal families to exact catalog IDs, supply existing_id and real project text to search, and compare before replacing the current typography.",
        "limitations": [
            "Literal declarations only; not computed styles. CSS inheritance, runtime values, fallback availability, remote fonts, and configuration execution are not evaluated.",
            "No audience, brand personality, or design quality is inferred from filenames or source text. Supply those requirements in the brief.",
            "Dependency/build/hidden directories and symlinks are skipped; large files and scan limits may omit declarations.",
        ],
    }
