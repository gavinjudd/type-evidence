"""Offline family discovery metadata, deliberately separate from exact local faces.

This module does not download fonts, inspect installed fonts, grant rights, or
resolve directory identifiers to bytes. All results are declared source metadata.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path
import re
import unicodedata
from typing import Any


DIRECTORY_PATH = Path(__file__).with_name("font_directory.json")
EVIDENCE_SCOPE = (
    "Family discovery metadata from a dated source snapshot; not exact local font "
    "identities, verified glyph coverage, rendered appearance, or usage permission. "
    "Local availability has not been checked."
)
CATEGORIES = {"sans-serif", "serif", "display", "handwriting", "monospace", "unknown"}
LICENSE_KINDS = {"open", "commercial", "unknown"}
ACCESS_KINDS = {"open-download", "commercial-license", "unknown"}


def _fold(value: str) -> str:
    """Case/diacritic-insensitive words, without speculative semantic aliases."""
    return " ".join(re.findall(r"\w+", "".join(
        char for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )))


@lru_cache(maxsize=1)
def _load() -> dict[str, Any]:
    data = json.loads(DIRECTORY_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("families"), list):
        raise ValueError("Unsupported font directory schema")
    identifiers = [row["id"] for row in data["families"]]
    if len(set(identifiers)) != len(identifiers) or any(
        not identifier.startswith("directory:") for identifier in identifiers
    ):
        raise ValueError("Font directory identifiers must be unique and directory-prefixed")
    return data


def _text(value: Any, name: str, *, maximum: int = 240, empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise ValueError(f"{name} must be at most {maximum} characters without control characters")
    value = value.strip()
    if not value and not empty:
        raise ValueError(f"{name} must not be empty")
    return value


def _enum(value: Any, name: str, choices: set[str]) -> str | None:
    if value is None:
        return None
    value = _text(value, name).casefold()
    if value not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(sorted(choices))}")
    return value


def _facets(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Counts cover the complete match set, never merely the returned page."""
    result: dict[str, Any] = {}
    truncated: dict[str, int] = {}
    for field in ("category", "provider", "vendor", "license_kind", "access", "variable", "tags", "subsets"):
        counts: Counter[str] = Counter()
        for row in rows:
            value = row.get(field)
            if field == "variable":
                values = ["unknown" if value is None else str(value).lower()]
            elif isinstance(value, list):
                values = set(value)
            else:
                values = [value or "unknown"]
            counts.update(values)
        # Designer/vendor and script lists can be large. Bound context explicitly.
        limit = 50 if field in {"vendor", "tags", "subsets"} else len(counts)
        ordered = sorted(counts.items(), key=lambda pair: (-pair[1], _fold(pair[0]), pair[0]))
        result[field] = {name: count for name, count in ordered[:limit]}
        if len(ordered) > limit:
            truncated[field] = len(ordered) - limit
    result["truncated_values"] = truncated
    result["scope"] = "all matching families before pagination; counts overlap for tags and subsets"
    return result


def directory_stats() -> dict[str, Any]:
    """Return bounded counts and the provenance of the packaged offline snapshot."""
    data = _load()
    rows = data["families"]
    return {
        "schema_version": data["schema_version"],
        "total_families": len(rows),
        "open_families": sum(row["license_kind"] == "open" for row in rows),
        "commercial_families": sum(row["license_kind"] == "commercial" for row in rows),
        "providers": len({row["provider"] for row in rows}),
        "variable_families": sum(row["variable"] is True for row in rows),
        "variable_unknown": sum(row["variable"] is None for row in rows),
        "facets": _facets(rows),
        "snapshot": deepcopy(data["snapshot"]),
        "evidence_scope": EVIDENCE_SCOPE,
        "local_availability": "not-checked",
    }


def directory_detail(identifier: str) -> dict[str, Any]:
    """Look up one directory ID; never accept or produce an exact face ID."""
    identifier = _text(identifier, "identifier")
    if not identifier.startswith("directory:"):
        raise ValueError("Expected a directory: identifier, not an exact local face ID")
    for row in _load()["families"]:
        if row["id"] == identifier:
            result = deepcopy(row)
            result["evidence_scope"] = EVIDENCE_SCOPE
            return result
    raise ValueError(f"Unknown directory identifier: {identifier}")


def search_directory(
    query: str = "",
    *,
    category: str | None = None,
    provider: str | None = None,
    vendor: str | None = None,
    license_kind: str | None = None,
    access: str | None = None,
    tags: str | list[str] | tuple[str, ...] | None = None,
    variable: bool | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """Search literal family/designer/tag metadata with deterministic paging.

    Query words use AND semantics. Provider/vendor filters are exact after
    Unicode case/diacritic normalization. Tags use AND semantics. There is no
    popularity ranking, semantic appearance inference, or hidden online request.
    """
    query = _text(query, "query", empty=True)
    category = _enum(category, "category", CATEGORIES)
    license_kind = _enum(license_kind, "license_kind", LICENSE_KINDS)
    access = _enum(access, "access", ACCESS_KINDS)
    provider = _fold(_text(provider, "provider")) if provider is not None else None
    vendor = _fold(_text(vendor, "vendor")) if vendor is not None else None
    if variable is not None and not isinstance(variable, bool):
        raise ValueError("variable must be true, false, or null")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer from 1 to 100")
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 1_000_000:
        raise ValueError("offset must be an integer from 0 to 1000000")
    if tags is None:
        tag_values: list[str] = []
    elif isinstance(tags, str):
        tag_values = [tags]
    elif isinstance(tags, (list, tuple)):
        tag_values = list(tags)
    else:
        raise ValueError("tags must be a string or a list of strings")
    if len(tag_values) > 16:
        raise ValueError("At most 16 tags may be supplied")
    required_tags = {_fold(_text(tag, "tag", maximum=80)) for tag in tag_values}
    folded_query = _fold(query)
    words = folded_query.split()
    if query and not words:
        raise ValueError("query must contain at least one letter or number")
    matched: list[dict[str, Any]] = []
    for row in _load()["families"]:
        if category is not None and row["category"] != category:
            continue
        if license_kind is not None and row["license_kind"] != license_kind:
            continue
        if access is not None and row["access"] != access:
            continue
        if variable is not None and row["variable"] is not variable:
            continue
        if provider is not None and _fold(row["provider"]) != provider:
            continue
        if vendor is not None and _fold(row.get("vendor") or "unknown") != vendor:
            continue
        if not required_tags.issubset({_fold(tag) for tag in row["tags"]}):
            continue
        haystack = _fold(" ".join([
            row["family"], row["provider"], row.get("vendor") or "", row["category"],
            *row["tags"], *row["subsets"], *row.get("designers", []),
        ]))
        if all(word in haystack for word in words):
            matched.append(row)

    def order(row: dict[str, Any]) -> tuple[int, str, str]:
        family = _fold(row["family"])
        relevance = 0 if family == folded_query else 1 if folded_query and family.startswith(folded_query) else 2
        return relevance, family, row["id"]

    matched.sort(key=order)
    page = matched[offset:offset + limit]
    next_offset = offset + len(page) if offset + len(page) < len(matched) else None
    return {
        "results": deepcopy(page),
        "pagination": {
            "offset": offset, "limit": limit, "total": len(matched),
            "has_more": next_offset is not None, "next_offset": next_offset,
        },
        "facets": _facets(matched),
        "snapshot": {key: deepcopy(value) for key, value in _load()["snapshot"].items() if key != "sources"},
        "evidence_scope": EVIDENCE_SCOPE,
        "query_interpretation": "Literal metadata terms; all words and requested tags must match. No visual ranking.",
        "local_availability": "not-checked",
    }
