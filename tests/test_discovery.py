import copy
import json
from pathlib import Path

import pytest

from type_evidence.discovery import project_context, search


def face(identifier, family="Family", style="Regular", weight=400, **overrides):
    result = {
        "id": identifier, "family": family, "family_key": family.lower(),
        "style": style, "full_name": f"{family} {style}", "weight": weight,
        "italic": False, "width_class": 5, "category": "sans", "axes": [],
        "coverage": [[32, 126]], "metrics": {"x_height_em": 0.5},
        "canonical_hash": identifier, "rights": {"status": "unknown"},
        "render_probe": True, "warnings": [],
    }
    result.update(overrides)
    return result


def test_exact_text_weight_italic_and_style_are_hard_constraints():
    fonts = [
        face("a"), face("b", style="Bold", weight=700),
        face("c", style="Bold Italic", weight=700, italic=True),
        face("d", family="Extended", style="Bold Italic", weight=700, italic=True,
             coverage=[[32, 126], [233, 233]]),
    ]
    result = search(fonts, {"text": "café", "weight": 700, "italic": True, "style": "Bold Italic"})
    assert [f["id"] for f in result["candidates"]] == ["d"]
    assert result["constraint_rejections"]["missing_requested_characters"] == 3
    assert result["constraint_rejections"]["requested_weight_unavailable"] == 1
    assert result["constraint_rejections"]["requested_italic_state_unavailable"] == 2


def test_layout_controls_are_not_required_glyphs_but_unicode_is():
    assert search([face("a")], {"text": "A\nB\tC\r"})["status"] == "candidates"
    assert search([face("a")], {"text": "AΩ"})["status"] == "no_matches"
    assert search([face("a")], {"text": "A\u00a0B"})["status"] == "no_matches"


def test_variable_axes_resolve_exact_weight_and_italic_without_inventing_faces():
    variable = face("v", axes=[
        {"tag": "wght", "min": 300, "default": 400, "max": 800},
        {"tag": "ital", "min": 0, "default": 0, "max": 1},
    ])
    found = search([variable], {"weight": 650, "italic": True})["candidates"][0]
    assert found["required_axes"] == {"wght": 650, "ital": 1}
    assert found["family_available_styles"]["count"] == 1
    assert search([variable], {"min_styles": 2})["status"] == "no_matches"
    assert search([variable], {"weight": 900})["status"] == "no_matches"


def test_slant_axis_does_not_implicitly_claim_italic():
    slanted = face("s", axes=[{"tag": "slnt", "min": -15, "default": 0, "max": 0}])
    assert search([slanted], {"italic": True})["status"] == "no_matches"


def test_diversity_and_duplicate_content_prevent_variant_domination():
    fonts = [face(f"a{i}", weight=400 + i, style=f"Style {i}") for i in range(30)]
    fonts += [face("b", "Second"), face("c", "Third"), face("d", "Alias", canonical_hash="b")]
    result = search(fonts, {"limit": 20})
    assert len(result["candidates"]) == 3
    assert len({f["family"] for f in result["candidates"]}) == 3


def test_observed_styles_are_grouped_and_counted_without_duplicate_files():
    fonts = [face("a"), face("duplicate"), face("b", style="Bold", weight=700)]
    result = search(fonts, {"min_styles": 2})
    candidate = result["candidates"][0]
    assert candidate["family_available_styles"]["count"] == 2
    assert len(candidate["family_available_styles"]["styles"]) == 2
    assert search(fonts, {"min_styles": 3})["status"] == "no_matches"


def test_broken_faces_do_not_count_toward_available_styles():
    fonts = [face("a"), face("bad", style="Bold", weight=700, render_probe=False)]
    assert search(fonts, {"min_styles": 2})["status"] == "no_matches"


def test_equal_score_choices_prefer_measured_and_metadata_diversity():
    fonts = [face("a", "First"), face("b", "Second"),
             face("c", "Third", category="serif"),
             face("d", "Narrow", width_class=3)]
    result = search(fonts, {"limit": 3})
    assert [f["id"] for f in result["candidates"]] == ["a", "c", "d"]


def test_existing_baseline_has_reserved_slot_even_when_outscored():
    fonts = [face("existing", "Current", category="unknown"), face("better", "Alternative")]
    result = search(fonts, {"existing_id": "existing", "limit": 1})
    assert result["baseline"]["status"] == "retained"
    assert result["candidates"][0]["id"] == "existing"
    assert result["candidates"][0]["existing_baseline"] is True
    assert {x["option"] for x in result["alternatives"]} == {"single_family", "keep_existing"}


@pytest.mark.parametrize("brief, reason", [
    ({"existing_id": "missing"}, "id_not_in_catalog"),
    ({"existing_id": "existing", "exclude": ["existing"]}, "explicitly_excluded"),
    ({"existing_id": "existing", "text": "Ω"}, "missing_requested_characters"),
    ({"existing_id": "existing", "weight": 700}, "requested_weight_unavailable"),
])
def test_baseline_is_explicitly_rejected_instead_of_disappearing(brief, reason):
    result = search([face("existing")], brief)
    assert result["baseline"]["status"] == "rejected"
    assert reason in result["baseline"]["reasons"]


def test_open_evidence_filter_preserves_unknown_and_does_not_claim_permission():
    fonts = [face("unknown"), face("open", "Open", rights={"status": "embedded-open-license"})]
    result = search(fonts, {"require_open_evidence": True})
    assert [f["id"] for f in result["candidates"]] == ["open"]
    assert result["candidates"][0]["rights"]["review_required"] is True
    unknown = search([fonts[0]], {})["candidates"][0]
    assert unknown["rights"]["status"] == "unknown"


def test_code_query_uses_measurement_without_prestige_or_name_ranking():
    fonts = [face("1", "Well Known", category="mono", vendor="Prestigious"),
             face("2", "Obscure", metrics={"mono_measured": True, "digit_tabular_default": True})]
    result = search(fonts, {"role": "code", "query": "tabular monospace"})
    assert result["candidates"][0]["id"] == "2"
    assert result["query_interpretation"]["aliases"] == {"monospace": "measured:mono", "tabular": "measured:tabular"}
    assert search(fonts, {"query": "Well Known"})["candidates"][0]["id"] == "1"


def test_equal_scores_are_stable_under_input_order_and_family_rename():
    fonts = [face("z", "A"), face("a", "Z")]
    before = [f["id"] for f in search(fonts, {})["candidates"]]
    renamed = copy.deepcopy(fonts[::-1])
    renamed[0]["family"] = "Prestigious"
    assert [f["id"] for f in search(renamed, {})["candidates"]] == before


def test_unsupported_semantics_and_unknown_brief_fields_are_visible():
    result = search([face("a")], {"query": "friendly futuristic", "audience": "children"})
    interpretation = result["query_interpretation"]
    assert interpretation["unmodeled_terms"] == ["friendly", "futuristic"]
    assert interpretation["unrecognized_brief_fields"] == ["audience"]
    assert "unrecognized brief fields have no effect" in interpretation["method"]


def test_failed_render_probe_excluded():
    result = search([face("bad", render_probe=False)], {"existing_id": "bad"})
    assert result["status"] == "no_matches"
    assert "render_probe_failed" in result["baseline"]["reasons"]


@pytest.mark.parametrize("brief", [
    {"limit": 0}, {"limit": 21}, {"limit": True}, {"weight": "bold"},
    {"italic": "false"}, {"role": "anything"}, {"min_styles": 0},
    {"require_open_evidence": "true"}, {"exclude": "abc"}, {"text": "x" * 20001},
])
def test_invalid_briefs_fail_clearly(brief):
    with pytest.raises(ValueError):
        search([], brief)


def test_output_is_bounded_and_does_not_dump_project_text_or_rights():
    fonts = [face(str(i), f"Family {i}" + "X" * 1000,
                  warnings=["danger\n" * 1000] * 50,
                  rights={"status": "unknown", "evidence": ["private" * 10000]}) for i in range(100)]
    result = search(fonts, {"limit": 20, "text": "sensitive project text"})
    encoded = json.dumps(result)
    assert "sensitive project text" not in encoded
    assert "private" not in encoded
    assert len(encoded) < 70000
    assert all(len(c["family"]) <= 100 for c in result["candidates"])


def test_project_context_reports_stacks_without_source_text_or_execution(tmp_path):
    (tmp_path / "app.css").write_text('''
      /* font-family: Commented; */
      :root { --font-body: "Atlas Serif", serif; --font-size: 16px; }
      body { font-family: "Atlas Serif", serif; }
      code { font-family: var(--font-code), monospace; }
      .secret { content: "DO NOT COPY THIS PROSE"; }
    ''')
    (tmp_path / "ui.tsx").write_text('const style = {fontFamily: "Display Face"};')
    (tmp_path / "theme.json").write_text('{"fontFamily": ["Document Face", "serif"]}')
    (tmp_path / "tailwind.config.js").write_text('throw new Error("must never execute");')
    result = project_context(tmp_path)
    names = {f["name"] for f in result["font_families"]}
    assert {"Atlas Serif", "serif", "Display Face", "Document Face", "var(--font-code)", "monospace"} <= names
    assert "Commented" not in names
    assert "16px" not in names
    assert "DO NOT COPY THIS PROSE" not in json.dumps(result)
    assert result["scan"]["files_read"] == 4


def test_project_context_reads_literal_theme_maps_and_css_shorthand(tmp_path):
    (tmp_path / "tailwind.config.ts").write_text('''
    export default {theme: {fontFamily: {
      sans: ['Interface Face', 'sans-serif'],
      display: ['Brand Face', 'serif'],
    }}};
    ''')
    (tmp_path / "app.vue").write_text('<style>body {font: bold 16px/1.4 "Body Face", serif;}</style>')
    result = project_context(tmp_path)
    names = {f["name"] for f in result["font_families"]}
    assert {"Interface Face", "Brand Face", "Body Face", "serif", "sans-serif"} <= names


def test_project_context_skips_symlinks_dependency_hidden_and_large_files(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    target = external / "target.css"
    target.write_text("body { font-family: LinkedFont; }")
    project = tmp_path / "project"
    project.mkdir()
    (project / "link.css").symlink_to(target)
    (project / "linked-dir").symlink_to(external, target_is_directory=True)
    for folder in ("node_modules", ".git", ".private"):
        directory = project / folder
        directory.mkdir()
        (directory / "ignored.css").write_text("body { font-family: IgnoredFont; }")
    (project / ".secret.json").write_text('{"fontFamily": "HiddenFont"}')
    (project / "huge.css").write_text("body { font-family: HugeFont; }" + " " * 70000)
    result = project_context(project)
    assert result["font_families"] == []
    assert result["scan"]["symlinks_skipped"] == 2
    assert result["scan"]["oversized_files_skipped"] == 1
    linked_root = tmp_path / "link-root"
    linked_root.symlink_to(project, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        project_context(linked_root)


def test_project_context_scan_limits_are_reported(tmp_path):
    for i in range(310):
        (tmp_path / f"{i:03}.css").write_text("body { font-family: Common; }")
    result = project_context(tmp_path)
    assert result["scan"]["files_read"] == 300
    assert result["scan"]["truncated"] is True


def test_project_context_invalid_root(tmp_path):
    with pytest.raises(ValueError, match="existing directory"):
        project_context(tmp_path / "missing")
