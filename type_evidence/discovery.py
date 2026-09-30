"""Bounded, evidence-led font discovery. No model, network, or visual claims.

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
                 "category", "require_open_evidence", "exclude", "existing_id", "style"}
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
    for field, maximum in (("text", 20000), ("query", 300), ("family", 300), ("style", 100), ("existing_id", 100)):
        if field in brief and (not isinstance(brief[field], str) or len(brief[field]) > maximum):
            raise ValueError(f"{field} must be a string of at most {maximum} characters")
    if "category" in brief and brief["category"] not in CATEGORIES:
        raise ValueError("category must be one of " + ", ".join(sorted(CATEGORIES)))
    excluded = brief.get("exclude", [])
    if not isinstance(excluded, list) or len(excluded) > 1000 or not all(isinstance(x, str) for x in excluded):
        raise ValueError("exclude must be a list of at most 1000 exact IDs")
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
    name_slanted = bool(re.search(r'\b(italic|oblique|slanted)\b', str(font.get('style', '')), re.I))
    if 'italic' in brief and name_slanted and not font.get('italic'):
        failures.append('style_metadata_conflict')
    if font["id"] in brief.get("exclude", []):
        failures.append("explicitly_excluded")
    if codepoints and not _covers(font, codepoints):
        failures.append("missing_requested_characters")
    if "weight" in brief:
        requested = brief["weight"]
        variable = _axis(font, "wght")
        if variable and variable["min"] <= requested <= variable["max"]:
            axes["wght"] = requested
        elif font.get("weight") != requested:
            failures.append("requested_weight_unavailable")
    if "italic" in brief:
        requested = brief["italic"]
        variable = _axis(font, "ital")
        if variable and variable["min"] <= int(requested) <= variable["max"]:
            axes["ital"] = int(requested)
        elif bool(font.get("italic")) != requested:
            failures.append("requested_italic_state_unavailable")
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


def _rank(font, brief, role, family_styles, query_terms):
    score = 0
    reasons = []
    category = font.get("category", "unknown")
    metrics = font.get("metrics") or {}
    weight = brief.get("weight", font.get("weight", 400))
    italic = brief.get("italic", bool(font.get("italic")))

    def add(points, basis, reason):
        nonlocal score
        score += points
        reasons.append({"basis": basis, "points": points, "reason": reason})

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
        # All these categories remain equal: role alone is not a style brief.
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

    preferences = set(query_terms.values())
    for preference in sorted(preferences):
        match = False
        basis = "metadata"
        if preference.startswith("category:"):
            match = category == preference.split(":", 1)[1]
        elif preference == "measured:mono":
            match = metrics.get("mono_measured") is True
            basis = "measured"
        elif preference == "measured:tabular":
            match = metrics.get("digit_tabular_default") is True
            basis = "measured"
        elif preference == "measured:compact":
            advance = metrics.get("average_advance_em")
            match = isinstance(advance, (int, float)) and 0 < advance <= 0.52
            basis = "measured+heuristic"
        elif preference == "metadata:condensed":
            match = 1 <= font.get("width_class", 5) <= 4
        elif preference == "metadata:wide":
            match = font.get("width_class", 5) >= 6
        elif preference == "metadata:bold":
            match = weight >= 700
        elif preference == "metadata:light":
            match = weight <= 300
        elif preference == "metadata:italic":
            match = italic
        if match:
            add(3, basis, f"Transparent query preference matched: {preference}.")

    if "high x-height" in query or "large x-height" in query:
        xheight = metrics.get("x_height_em")
        if isinstance(xheight, (int, float)) and xheight >= 0.5:
            add(3, "measured+heuristic", "Query preference: measured x-height is at least 0.5 em.")
    return score, reasons


def _compact(font, score, reasons, axes, styles, baseline=False):
    rights = font.get("rights") or {}
    metric_keys = ("x_height_em", "cap_height_em", "average_advance_em", "mono_measured", "digit_tabular_default")
    return {
        "id": font["id"], "family": _clean(font.get("family")),
        "style": _clean(font.get("style"), 60), "weight": font.get("weight"),
        "italic": bool(font.get("italic")), "category": font.get("category", "unknown"),
        "score": score, "score_meaning": "Heuristic preference points; not a quality or readability score.",
        "reasons": reasons[:8], "required_axes": axes,
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


def search(catalog, brief: dict) -> dict:
    """Return at most 20 exact-face candidates, one per family plus baseline.

    ``catalog`` implements ``all()``; a list of font dicts is also accepted for
    composition/tests. ``existing_id`` is always reserved a result slot when it
    satisfies constraints, otherwise its concrete rejection is reported. Name,
    foundry, provenance, and popularity never determine preference except when
    the user explicitly supplies a font-name query.
    """
    role, limit, _ = _validate_brief(brief)
    originals = catalog if isinstance(catalog, list) else catalog.all()
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
    tokens = set(re.findall(r"[\w-]+", query))
    query_terms = {token: _ALIASES[token] for token in sorted(tokens) if token in _ALIASES}
    for phrase in ("high x-height", "large x-height"):
        if phrase in query:
            query_terms[phrase] = "measured:high-x-height"
    modeled_words = {word for term in query_terms for word in term.split()}
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
        score, reasons = _rank(font, brief, role, styles, query_terms)
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
    signatures = {entry[1]["id"]: _diversity_signature(entry[1]) for entry in eligible}
    while len(selected) < limit:
        best = None
        best_key = None
        for entry in eligible:
            font = entry[1]
            family = _shortlist_family(font)
            content = font.get("canonical_hash") or font["id"]
            if family in seen_families or content in seen_content:
                continue
            novelty = min((_distance(signatures[font["id"]], signatures[previous[1]["id"]])
                           for previous in selected), default=0)
            key = (entry[0], novelty)
            # Equal evidence keeps the earlier content-hash ordering.
            if best_key is None or key > best_key:
                best, best_key = entry, key
        if best is None:
            break
        selected.append(best)
        seen_families.add(_shortlist_family(best[1]))
        seen_content.add(best[1].get("canonical_hash") or best[1]["id"])
    candidates = [_compact(font, score, reasons, axes, styles, font["id"] == existing_id)
                  for score, font, reasons, axes, styles in selected]
    for candidate, entry in zip(candidates, selected):
        resolutions = []
        for chosen in family_resolutions[_family_key(entry[1])]:
            requested = {'weight':chosen['weight'], 'italic':chosen['italic']}
            failures, applied = _hard_constraints(entry[1], requested, codepoints, entry[4])
            resolutions.append(dict(requested, id=candidate['id'], required_axes=applied) if not failures else chosen)
        candidate['family_style_resolutions'] = resolutions
    alternatives = [
        {"option": "single_family", "advice": "Compare a single family's observed styles before adding a second typeface; additional fonts are not inherently an improvement."},
        {"option": "keep_existing", "advice": "Keeping the current typography is a valid outcome. Supply existing_id to include an exact catalog face as the comparison baseline."},
    ]
    return {
        "schema_version": 1, "status": "candidates" if candidates else "no_matches",
        "role": role, "candidates": candidates, "baseline": baseline,
        "counts": {"catalog_faces": len(fonts), "eligible_faces": len(eligible),
                   "returned_faces": len(candidates)},
        "constraint_rejections": dict(sorted(rejected.items())),
        "query_interpretation": {
            "exact_name_match_count": sum(query in {_key(f.get('family')), _key(f.get('full_name')), _key(f.get('postscript_name'))} for f in fonts) if query else 0,
            "name_lookup_advice": "query ranks preferences and can return alternatives when a name is absent. Use family for a hard exact family-name lookup.",
            "aliases": query_terms,
            "unmodeled_terms": sorted(tokens - modeled_words)[:20],
            "unrecognized_brief_fields": [_clean(field, 60) for field in sorted(set(brief) - _BRIEF_FIELDS)[:20]],
            "method": "Small explicit aliases, metadata name matches, measured properties. Unmodeled terms affect only literal name matches; unrecognized brief fields have no effect. No embedding or image-based similarity is claimed.",
        },
        "constraints": {"coverage": "Requested non-layout characters must occur in cmap; this does not prove shaping correctness.",
                        "text_codepoint_count": len(codepoints),
                        "text_supplied": bool(brief.get("text")),
                        "family_diversity": "At most one face per family; equivalent canonical content is also deduplicated. Equal-score ties favor differences in known category, width, monospace measurement, x-height, and advance-width bands; this is not proof of visual distinction.",
                        "open_evidence_requested": bool(brief.get("require_open_evidence"))},
        "alternatives": alternatives,
        "limitations": [
            "Rankings are transparent starting preferences. No font was visually judged by this search.",
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
