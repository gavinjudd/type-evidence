"""Contextual layout tests verify exact glyphs, content, hierarchy, and recipes."""
import copy
import hashlib
import json

import pytest
from fontTools.ttLib import TTCollection, TTFont
from PIL import Image

from type_evidence.composition import compose
from type_evidence.render import RenderError
from test_render import ExactCatalog, build_font


@pytest.fixture
def context(tmp_path):
    cat = ExactCatalog([build_font(tmp_path/"regular.ttf"), build_font(tmp_path/"narrow.ttf", width=450)])
    regular, narrow = cat.entries
    spec = {
        "template": "editorial", "title": "Reading in context", "width": 700, "padding": 40,
        "roles": {"title": {"font_id": narrow, "size": 48, "line_height": 1.1},
                  "body": {"font_id": regular, "size": 20, "line_height": 1.6}},
        "blocks": [{"role": "title", "text": "AV O fi"},
                   {"role": "body", "text": "AV  O fi a\u0301 "*20}],
    }
    return cat, spec


def test_contextual_pair_preserves_exact_text_and_settings(context, tmp_path):
    cat, spec = context
    result = compose(cat, spec, tmp_path/"out")
    assert result["kind"] == "exact-font-composition"
    assert result["no_fallback"] == {"verified": True, "glyph_zero_count": 0, "font_synthesis": False}
    assert set(cat.resolve_calls) == {r["font_id"] for r in spec["roles"].values()}
    title, body = result["measurements"]
    assert title["size_px"] == 48 and body["size_px"] == 20
    assert body["line_count"] > 1
    assert body["line_height_px"] == 32
    assert "".join(line["text"] for line in body["lines"]) == spec["blocks"][1]["text"]
    assert body["position_px"][1] >= title["position_px"][1]+title["canvas_px"][1]+20
    assert all(not row["clipped"] for row in result["measurements"])
    with Image.open(tmp_path/"out"/"composition.png") as image:
        assert list(image.size) == result["canvas_px"]
        assert image.getextrema()[0][0] < 80
    assert json.loads((tmp_path/"out"/"manifest.json").read_text(encoding="utf-8")) == result
    assert hashlib.sha256((tmp_path/"out"/"composition.png").read_bytes()).hexdigest() == result["images"][0]["sha256"]


def test_column_panel_and_table_layout_do_not_overlap(context, tmp_path):
    cat, spec = context
    spec["template"] = "interface"
    spec["blocks"] = [
        {"role": "title", "text": "AV O"},
        {"type": "columns", "gap": 24, "columns": [
            {"width": 2, "blocks": [{"type": "panel", "padding": 12, "blocks": [{"role": "body", "text": "AV O "*12}]}]},
            {"blocks": [{"role": "body", "text": "fi a\u0301 "*5}]},
        ]},
        {"type": "table", "role": "body", "columns": [{"text": "A", "width": 2}, {"text": "V", "align": "right"}],
         "rows": [["AV O", "fi"], ["a\u0301", "O"]]},
    ]
    result = compose(cat, spec, tmp_path/"out")
    rows = result["measurements"]
    panel, sidebar = rows[1:3]
    assert panel["position_px"][0]+panel["width_px"] < sidebar["position_px"][0]
    table_start = rows[3]["position_px"][1]
    assert table_start >= max(row["position_px"][1]+row["canvas_px"][1] for row in [panel, sidebar])
    assert rows[4]["align"] == "right"
    for row in rows:
        x, y = row["position_px"]
        w, h = row["canvas_px"]
        assert 0 <= x <= result["canvas_px"][0]-w and 0 <= y <= result["canvas_px"][1]-h


def test_one_family_role_reuse_and_revised_size(context, tmp_path):
    cat, spec = context
    spec["roles"]["title"]["font_id"] = spec["roles"]["body"]["font_id"]
    first = compose(cat, spec, tmp_path/"first")
    spec["roles"]["body"]["size"] = 24
    spec["roles"]["body"]["line_height"] = 1.8
    second = compose(cat, spec, tmp_path/"second")
    assert first["roles"]["title"]["id"] == first["roles"]["body"]["id"]
    assert first["images"][0]["sha256"] != second["images"][0]["sha256"]
    assert first["canvas_px"][1] < second["canvas_px"][1]
    assert second["measurements"][1]["line_height_px"] == pytest.approx(43.2)


def test_css_exact_aliases_features_and_no_font_copy(context, tmp_path):
    cat, spec = context
    spec["roles"]["body"]["features"] = ["-liga", "tnum"]
    result = compose(cat, spec, tmp_path/"out")
    css = (tmp_path/"out"/"application.css").read_text(encoding="utf-8")
    assert "font-synthesis: none" in css and '"liga" 0, "tnum" 1' in css
    assert "font-optical-sizing: none" in css
    assert "local(" not in css and str(tmp_path) not in css
    assert len(list((tmp_path/"out").iterdir())) == 7
    for name, role in result["roles"].items():
        recipe = result["implementation"]["roles"][name]
        assert recipe["exact_id"] == role["id"]
        assert role["sha256"] in recipe["asset_url"]
        assert recipe["source_asset_not_copied"]


def test_application_gate_hides_missing_or_changed_assets(context, tmp_path):
    cat, spec = context
    result = compose(cat, spec, tmp_path/"out")
    html = (tmp_path/"out"/"application.html").read_text(encoding="utf-8")
    javascript = (tmp_path/"out"/"application.js").read_text(encoding="utf-8")
    assert '<main class="te-composition" hidden>' in html
    assert 'crypto.subtle.digest("SHA-256", bytes)' in javascript
    assert 'hash !== role.sha256' in javascript
    assert 'await face.load()' in javascript
    assert javascript.index('await face.load()') < javascript.index('.hidden = false')
    assert 'Composition hidden to prevent font substitution' in javascript
    assert 'no fallback preview' in result["implementation"]["browser_asset_gate"]


def test_application_recipe_adapts_layout_without_substituting_faces(context, tmp_path):
    cat, spec = context
    spec["roles"]["title"]["size"] = 64
    spec["blocks"].append({"type": "columns", "columns": [
        {"blocks": [{"role": "body", "text": "AV O"}]},
        {"blocks": [{"type": "table", "role": "body", "columns": [{"text": "A"}, {"text": "V"}], "rows": [["AV", "fi"]]}]},
    ]})
    result = compose(cat, spec, tmp_path/"out")
    css = (tmp_path/"out"/"application.css").read_text(encoding="utf-8")
    html = (tmp_path/"out"/"application.html").read_text(encoding="utf-8")
    rules = result["implementation"]["responsive_layout"]
    assert 'max-width: 100%' in css and '@media (max-width: 640px)' in css
    assert '.te-columns { grid-template-columns: 1fr; }' in css
    assert 'class="te-columns"' in html and '--te-column-tracks:' in html
    assert 'class="te-table-scroll" tabindex="0" role="region"' in html
    assert '<th scope="col" class="te-text' in html
    assert 'Scroll horizontally to see every column.' in html
    assert '.te-table-group[data-overflow] > .te-scroll-hint' in css
    assert rules["mobile_role_font_sizes"] == {"title": "clamp(32px, 12vw, 64px)"}
    assert rules["font_ids_axes_features"] == "unchanged"
    assert result["canvas_px"][0] == 700  # The evidence PNG keeps its requested layout.
    assert result["roles"]["title"]["size_px"] == 64


def test_static_weight_cannot_be_synthesized(context, tmp_path):
    cat, spec = context
    spec["roles"]["body"]["weight"] = 700
    with pytest.raises(RenderError, match="Synthetic weight"):
        compose(cat, spec, tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_variable_weight_is_applied_to_exact_instance(tmp_path):
    cat = ExactCatalog([build_font(tmp_path/"variable.ttf", variable=True)])
    ident = next(iter(cat.entries))
    cat.entries[ident]["axes"] = [{"tag": "wght", "min": 100, "default": 400, "max": 900}]
    spec = {"roles": {"body": {"font_id": ident, "weight": 650}}, "blocks": [{"text": "AV fi"}]}
    result = compose(cat, spec, tmp_path/"out")
    assert result["roles"]["body"]["axes"] == {"wght": 650}
    assert result["implementation"]["roles"]["body"]["settings"]["font-weight"] == "650"
    spec["roles"]["body"]["axes"] = {"wght": 300}
    with pytest.raises(RenderError, match="conflicts"):
        compose(cat, spec, tmp_path/"bad")


def test_missing_glyph_and_post_shape_notdef_rejected(context, tmp_path):
    cat, spec = context
    spec["blocks"][1]["text"] = "AV ☃"
    with pytest.raises(RenderError, match="No fallback"):
        compose(cat, spec, tmp_path/"missing")
    cat = ExactCatalog([build_font(tmp_path/"bad.ttf", bad_substitution=True)])
    ident = next(iter(cat.entries))
    bad = {"roles": {"body": {"font_id": ident, "features": ["ss01"]}}, "blocks": [{"text": "A"}]}
    with pytest.raises(RenderError, match="glyph 0"):
        compose(cat, bad, tmp_path/"notdef")
    assert not (tmp_path/"missing").exists() and not (tmp_path/"notdef").exists()


def test_long_unbreakable_text_rejected_without_clipping(context, tmp_path):
    cat, spec = context
    spec["blocks"][1]["text"] = "AV"*80
    with pytest.raises(RenderError, match="Unbreakable text"):
        compose(cat, spec, tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_tight_leading_reports_ink_overlap(context, tmp_path):
    cat, spec = context
    spec["roles"]["body"]["line_height"] = .85
    spec["blocks"][1]["text"] = "a\u0301\na\u0301"
    result = compose(cat, spec, tmp_path/"out")
    assert result["warnings"][0]["kind"] == "line-ink-overlap"
    assert result["warnings"][0]["line_pairs"] == [[0, 1]]


def test_collection_is_rendered_but_not_misrepresented_as_ttf(tmp_path):
    first, second = build_font(tmp_path/"one.ttf"), build_font(tmp_path/"two.ttf", width=450)
    fonts = TTCollection(); fonts.fonts = [TTFont(first), TTFont(second)]; fonts.save(tmp_path/"faces.ttc")
    for font in fonts.fonts:
        font.close()
    cat = ExactCatalog([tmp_path/"faces.ttc"])
    ident = next(iter(cat.entries))
    result = compose(cat, {"roles": {"body": {"font_id": ident}}, "blocks": [{"text": "AV O"}]}, tmp_path/"out")
    assert result["roles"]["body"]["asset_verified"]
    assert result["implementation"]["collection_roles_requiring_extraction"] == ["body"]
    assert result["implementation"]["roles"]["body"]["asset_url"] is None
    assert "@font-face {" not in (tmp_path/"out"/"application.css").read_text(encoding="utf-8")


@pytest.mark.parametrize("mutation,error", [
    (lambda s: s.update(width=True), "Width"),
    (lambda s: s.update(template=[]), "Template"),
    (lambda s: s.update(padding=350), "Padding"),
    (lambda s: s["roles"]["body"].update(line_height=float("nan")), "line_height"),
    (lambda s: s["roles"]["body"].update(color="red"), "color"),
    (lambda s: s["roles"]["body"].update(features=["script" ]), "feature"),
    (lambda s: s["blocks"][0].update(role=[]), "unknown role"),
    (lambda s: s["blocks"][0].update(other=1), "Unknown text"),
    (lambda s: s.update(blocks=[]), "nonempty list"),
])
def test_invalid_spec_is_bounded_and_typed(context, tmp_path, mutation, error):
    cat, spec = context
    mutation(spec)
    with pytest.raises(RenderError, match=error):
        compose(cat, spec, tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_prior_outputs_and_input_spec_preserved(context, tmp_path):
    cat, spec = context
    original = copy.deepcopy(spec)
    out = tmp_path/"out"; out.mkdir(); (out/"keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(RenderError, match="absent or empty"):
        compose(cat, spec, out)
    assert (out/"keep.txt").read_text(encoding="utf-8") == "keep" and spec == original


def test_html_text_and_metadata_are_escaped(context, tmp_path):
    cat, spec = context
    spec["title"] = '<script>alert("unsafe")</script>'
    compose(cat, spec, tmp_path/"out")
    html = (tmp_path/"out"/"index.html").read_text(encoding="utf-8")
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert "default-src 'none'" in html
