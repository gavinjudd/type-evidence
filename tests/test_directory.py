"""The family directory must never masquerade as an exact, installed font."""
from collections import Counter
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urlparse

import pytest

from type_evidence.directory import (
    DIRECTORY_PATH, directory_detail, directory_stats, search_directory,
)


def all_rows():
    return json.loads(DIRECTORY_PATH.read_text(encoding="utf-8"))["families"]


def test_snapshot_breadth_provenance_and_exact_identity_boundary():
    data = json.loads(DIRECTORY_PATH.read_text(encoding="utf-8"))
    rows = data["families"]
    counts = Counter(row["license_kind"] for row in rows)
    assert counts["open"] >= 1900
    assert counts["commercial"] >= 200
    assert len({row["provider"] for row in rows if row["license_kind"] == "commercial"}) >= 7
    assert len({row["id"] for row in rows}) == len(rows)
    source_ids = {source["id"] for source in data["snapshot"]["sources"]}
    for row in rows:
        assert row["id"].startswith("directory:")
        assert not re.fullmatch(r"[0-9a-f]{64}:\d+", row["id"])
        assert row["indexed"] is False and row["renderable"] is False
        assert row["local_availability"] == "not-checked"
        assert row["provenance"]["source_id"] in source_ids
        for field in ("source_url", "acquisition_url", "specimen_url"):
            assert urlparse(row[field]).scheme == "https"
        assert row["family"] and row["provider"]
        assert row["variable"] in (True, False, None)
        assert row["provenance"]["retrieved_at"]
        if row["license_kind"] == "commercial":
            assert row["preview"]["type"] == "provider-only"
            assert row["acquisition"]["available"] is False
            assert row["styles"] == []
    assert len([r for r in rows if r["provider"] == "Google Fonts"]) == data["snapshot"]["google_served_families"]


def test_stats_counts_are_families_and_bounded_facets():
    stats = directory_stats()
    assert stats["total_families"] == len(all_rows())
    assert stats["open_families"] + stats["commercial_families"] == stats["total_families"]
    assert sum(stats["facets"]["category"].values()) == stats["total_families"]
    assert len(stats["facets"]["vendor"]) <= 50
    assert stats["facets"]["truncated_values"]["vendor"] > 0
    assert "local" in stats["evidence_scope"]


def test_exact_name_ranks_first_and_accents_are_searchable():
    assert search_directory("Inter")["results"][0]["family"] == "Inter"
    assert search_directory("SOHNE")["results"][0]["family"] == "Söhne"
    assert search_directory("manuka", provider="klim type foundry")["results"][0]["family"] == "Mānuka"
    assert search_directory("sohne nonexistentword")["results"] == []


def test_filters_are_intersected_without_treating_unknown_as_false():
    result = search_directory(category="sans-serif", provider="Google Fonts", license_kind="open",
                              access="open-download", tags=["variable", "sans-serif"], variable=True,
                              limit=100)
    assert result["pagination"]["total"] > 100
    for row in result["results"]:
        assert row["provider"] == "Google Fonts"
        assert row["variable"] is True and row["category"] == "sans-serif"
    assert search_directory("Inter", vendor="Rasmus Andersson")["results"][0]["family"] == "Inter"
    assert search_directory(provider="Klim Type Foundry", variable=False)["results"] == []
    assert search_directory(provider="not a provider")["results"] == []
    assert search_directory(license_kind="open", access="commercial-license")["results"] == []


def test_pagination_is_stable_disjoint_and_facets_cover_matches():
    first = search_directory(category="serif", limit=7)
    second = search_directory(category="serif", limit=7, offset=first["pagination"]["next_offset"])
    assert {r["id"] for r in first["results"]}.isdisjoint(r["id"] for r in second["results"])
    assert first["facets"] == second["facets"]
    assert first["facets"]["category"]["serif"] == first["pagination"]["total"]
    assert first == search_directory(category="serif", limit=7)
    beyond = search_directory(category="serif", offset=1000000)
    assert beyond["results"] == [] and beyond["pagination"]["next_offset"] is None
    missing = search_directory("nothingmatchesthisstring")
    assert missing["pagination"]["total"] == 0 and not missing["pagination"]["has_more"]


@pytest.mark.parametrize("kwargs", [
    {"limit": 0}, {"limit": 101}, {"limit": True}, {"limit": 2.0},
    {"offset": -1}, {"offset": 1000001}, {"offset": False}, {"offset": "0"},
    {"query": None}, {"query": "x" * 241}, {"query": "abc\nxyz"}, {"query": "!!!"},
    {"category": "fake"}, {"category": 1}, {"license_kind": "all"}, {"access": "installed"},
    {"variable": "true"}, {"variable": 1}, {"provider": ""}, {"vendor": []},
    {"tags": ["a"] * 17}, {"tags": [None]}, {"tags": {"a": True}}, {"tags": ""},
])
def test_invalid_requests_fail_clearly(kwargs):
    with pytest.raises(ValueError):
        search_directory(**kwargs)


def test_search_detail_and_stats_do_not_mutate_cached_source():
    entry = search_directory("Inter")["results"][0]
    original = deepcopy(directory_detail(entry["id"]))
    entry["family"] = "changed"
    entry["axes"].clear()
    detail = directory_detail(original["id"])
    detail["acquisition"]["available"] = False
    detail["tags"].append("injected")
    stats = directory_stats()
    stats["snapshot"]["sources"].clear()
    assert directory_detail(original["id"]) == original
    assert directory_stats()["snapshot"]["sources"]


@pytest.mark.parametrize("identifier", ["a" * 64 + ":0", "Inter", "directory:no:such-family", None])
def test_detail_never_resolves_names_or_exact_face_ids(identifier):
    with pytest.raises(ValueError):
        directory_detail(identifier)


def test_offline_search_never_needs_network(monkeypatch):
    import socket
    def denied(*args, **kwargs):
        raise AssertionError("directory search must be offline")
    monkeypatch.setattr(socket, "socket", denied)
    assert search_directory("Graphik")["results"][0]["family"] == "Graphik"
    assert directory_detail("directory:google-fonts:inter")["family"] == "Inter"


def test_repository_and_live_catalog_difference_is_preserved():
    data = json.loads(DIRECTORY_PATH.read_text(encoding="utf-8"))
    snapshot = data["snapshot"]
    assert snapshot["google_repository_family_directories"] > snapshot["google_served_families"]
    unmatched = [r for r in data["families"] if r["provider"] == "Google Fonts" and r["source_path"] is None]
    assert [r["family"] for r in unmatched] == sorted(snapshot["google_families_without_repository_match"], key=str.casefold)
    assert all(r["acquisition"]["available"] is False for r in unmatched)
    assert snapshot["google_families_with_pinned_acquisition"] == sum(r["acquisition"]["available"] for r in data["families"])


def test_acquisition_references_match_exact_pinned_manifest():
    manifest = json.loads(DIRECTORY_PATH.with_name("source-packs.json").read_text(encoding="utf-8"))
    by_id = {r["id"]: r for r in manifest["families"]}
    for row in all_rows():
        if row["acquisition"]["available"]:
            source = by_id[row["acquisition"]["source_id"]]
            assert source["path"] == row["source_path"]
            assert row["provenance"]["repository_commit"] == manifest["collection"]["commit"]
    for name in ("Tinos", "Kumar One Outline", "M PLUS Rounded 1c", "Playwrite NZ Basic Guides"):
        row = next(row for row in all_rows() if row["family"] == name)
        assert row["acquisition"]["available"] is False
        assert row["acquisition"]["reason"] == "family-license-file-not-pinned"


def test_offline_builder_is_deterministic_and_rejects_truncation(tmp_path):
    path = Path(__file__).resolve().parents[1] / "scripts" / "build_font_directory.py"
    spec = importlib.util.spec_from_file_location("build_font_directory_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    metadata = tmp_path / "metadata.json"
    metadata.write_text(json.dumps({"familyMetadataList": [{
        "family": "Example Sans", "category": "Sans Serif", "fonts": {"400": {}, "700i": {}},
        "subsets": ["menu", "latin"], "isOpenSource": True,
    }]}))
    tree = tmp_path / "tree.json"
    tree.write_text(json.dumps({"truncated": False, "tree": [
        {"path": "ofl/examplesans/METADATA.pb"}, {"path": "ofl/examplesans/OFL.txt"},
    ]}))
    args = (metadata, tree, "a" * 40, "2026-10-13T00:00:00Z")
    first = module.build(*args)
    assert first == module.build(*args)
    row = next(row for row in first["families"] if row["family"] == "Example Sans")
    assert row["source_path"] == "ofl/examplesans"
    assert row["styles"] == ["400", "700i"] and row["subsets"] == ["latin"]
    assert row["acquisition"]["available"] is False
    tree.write_text(json.dumps({"truncated": True, "tree": []}))
    with pytest.raises(ValueError, match="untruncated"):
        module.build(*args)
