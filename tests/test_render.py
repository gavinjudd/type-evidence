"""Independent synthetic fonts exercise shaping and integrity, not filenames."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from PIL import Image

from type_evidence.render import RenderError, compare, _load, _raster_glyph


class ExactCatalog:
    def __init__(self, paths, family="Synthetic Evidence"):
        self.entries = {}
        self.resolve_calls = []
        for path in paths:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            font_id = digest+":0"
            self.entries[font_id] = {"id": font_id, "path": path, "sha256": digest,
                                     "face_index": 0, "family": family, "style": "Regular",
                                     "rights": {"status": "unknown", "review_required": True},
                                     "origins": [{"source_id": "test", "path": path.name}]}

    def get(self, font_id):
        return dict(self.entries[font_id])

    def resolve(self, font_id):
        self.resolve_calls.append(font_id)
        entry = self.entries[font_id]
        if hashlib.sha256(entry["path"].read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("changed source")
        return {key: entry[key] for key in ("id", "path", "sha256", "face_index", "rights")}


def build_font(path, *, width=600, overlap=False, variable=False, bad_substitution=False):
    builder = FontBuilder(1000, isTTF=True)
    glyph_names = [".notdef", "space", "A", "V", "O", "f", "i", "fi", "acutecomb", "a", "beharabic", "behinit", "behmedi", "behfina"]
    builder.setupGlyphOrder(glyph_names)
    builder.setupCharacterMap({32: "space", 65: "A", 86: "V", 79: "O", 102: "f", 105: "i", 97: "a", 0x301: "acutecomb", 0x628: "beharabic"})
    glyphs = {}
    for name in glyph_names:
        pen = TTGlyphPen(None)
        if name != "space":
            # Curves, counters, and negative bearings exercise native outlines.
            if name == "O":
                pen.moveTo((-40, 0)); pen.lineTo((500, 0)); pen.qCurveTo((660, 350), (500, 700)); pen.lineTo((-40, 700)); pen.closePath()
                if overlap:
                    # Same-direction contours overlap and must remain filled.
                    pen.moveTo((160, 0)); pen.lineTo((700, 0)); pen.lineTo((700, 700)); pen.lineTo((160, 700)); pen.closePath()
                else:
                    # Opposite orientation creates a visible counter.
                    pen.moveTo((100, 140)); pen.lineTo((100, 560)); pen.lineTo((400, 560)); pen.lineTo((400, 140)); pen.closePath()
            elif name == "acutecomb":
                pen.moveTo((-100, 700));pen.lineTo((80, 920));pen.lineTo((180, 920));pen.lineTo((0, 700));pen.closePath()
            else:
                ink_width = width*1.3 if name == "fi" else width*.7
                pen.moveTo((40, 0));pen.lineTo((ink_width, 0));pen.lineTo((ink_width, 700));pen.lineTo((40, 700));pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    metrics = {name: (0 if name == "acutecomb" else width*2 if name == "fi" else width, -40 if name == "O" else 40) for name in glyph_names}
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=800, descent=-220)
    builder.setupNameTable({"familyName": "Synthetic Evidence", "styleName": "Regular", "uniqueFontIdentifier": "Synthetic Evidence " + str(width), "fullName": "Synthetic Evidence Regular", "psName": "SyntheticEvidence-Regular"})
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-220, usWinAscent=1000, usWinDescent=250)
    builder.setupPost()
    if variable:
        builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    builder.setupMaxp()
    addOpenTypeFeaturesFromString(builder.font, '''
        languagesystem DFLT dflt;
        languagesystem latn dflt;
        languagesystem arab dflt;
        feature liga { sub f i by fi; } liga;
        feature kern { pos A V -120; } kern;
        feature init { sub beharabic by behinit; } init;
        feature medi { sub beharabic by behmedi; } medi;
        feature fina { sub beharabic by behfina; } fina;
    ''' + ("feature ss01 { sub A by .notdef; } ss01;" if bad_substitution else ""))
    builder.save(path)
    return path


@pytest.fixture
def catalog(tmp_path):
    path = build_font(tmp_path/"evidence.ttf")
    return ExactCatalog([path])


def test_exact_asset_outputs_have_real_geometry_and_digests(catalog, tmp_path):
    ids = list(catalog.entries)
    manifest = compare(catalog, ids, "AV Office\nO a\u0301".replace("c", "f").replace("e", "i"), tmp_path/"out", sizes=[16, 64])
    assert catalog.resolve_calls == ids
    assert manifest["no_fallback"]["verified"]
    assert manifest["renderer"]["backend"].startswith("HarfBuzz")
    assert manifest["renderer"]["freetype"]
    assert manifest["fonts"][0]["glyph_zero_count"] == 0
    assert manifest["fonts"][0]["measurements"][0]["size_px"] == 16
    assert manifest["fonts"][0]["measurements"][1]["ink_bounds_px"][0] < 0
    for image in manifest["images"]:
        path = tmp_path/"out"/image["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == image["sha256"]
        with Image.open(path) as png:
            assert png.size == (image["width"], image["height"])
            assert png.getextrema()[0][0] < 80
    disk = json.loads((tmp_path/"out"/"manifest.json").read_text())
    assert disk == manifest


def test_native_raster_preserves_counter_and_overlapping_contours(tmp_path):
    normal = ExactCatalog([build_font(tmp_path/"normal.ttf")])
    overlap = ExactCatalog([build_font(tmp_path/"overlap.ttf", overlap=True)])
    a = _load(normal, next(iter(normal.entries)), {}, "O")
    b = _load(overlap, next(iter(overlap.entries)), {}, "O")
    gid = a.font.get_nominal_glyph(ord("O"))
    hole_mask, hole_left, hole_top = _raster_glyph(a.freetype_face, gid, 100)
    filled_mask, fill_left, fill_top = _raster_glyph(b.freetype_face, gid, 100)
    # Font point (250,350), scaled by 100px/em * fourfold supersampling.
    hole_xy = (100-hole_left, -140-hole_top)
    fill_xy = (100-fill_left, -140-fill_top)
    assert hole_mask.getpixel(hole_xy) == 0
    assert filled_mask.getpixel(fill_xy) == 255


def test_missing_character_rejected_before_output(catalog, tmp_path):
    with pytest.raises(RenderError, match="U\\+2603"):
        compare(catalog, list(catalog.entries), "A\u2603", tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_changed_file_rejected_by_resolution(catalog, tmp_path):
    entry = next(iter(catalog.entries.values()))
    entry["path"].write_bytes(entry["path"].read_bytes()+b"changed")
    with pytest.raises(ValueError, match="changed source"):
        compare(catalog, list(catalog.entries), "A", tmp_path/"out")


def test_hash_recheck_closes_resolve_read_race(catalog, tmp_path):
    original = catalog.resolve
    def changed_after_resolve(font_id):
        resolved = original(font_id)
        resolved["path"].write_bytes(resolved["path"].read_bytes()+b"changed")
        return resolved
    catalog.resolve = changed_after_resolve
    with pytest.raises(RenderError, match="changed after resolution"):
        compare(catalog, list(catalog.entries), "A", tmp_path/"out")


def test_ligatures_and_kerning_apply_to_actual_glyph_stream(catalog, tmp_path):
    enabled = compare(catalog, list(catalog.entries), "fi AV", tmp_path/"on", sizes=[64])
    disabled = compare(catalog, list(catalog.entries), "fi AV", tmp_path/"off", sizes=[64], features=["-liga", "-kern"])
    on = enabled["fonts"][0]["measurements"][0]["lines"][0]
    off = disabled["fonts"][0]["measurements"][0]["lines"][0]
    assert len(on["glyphs"]) == len(off["glyphs"])-1
    assert on["advance_px"][0] == pytest.approx(off["advance_px"][0]-7.68)
    assert enabled["fonts"][0]["measurements"][0]["mask_sha256"] != disabled["fonts"][0]["measurements"][0]["mask_sha256"]


def test_post_shaping_notdef_rejected(tmp_path):
    cat = ExactCatalog([build_font(tmp_path/"notdef.ttf", bad_substitution=True)])
    with pytest.raises(RenderError, match="glyph 0"):
        compare(cat, list(cat.entries), "A", tmp_path/"out", features={"ss01": 1})
    assert not (tmp_path/"out").exists()


def test_woff_decompression_preserves_visual_glyphs_and_source_digest(tmp_path):
    ttf = build_font(tmp_path/"source.ttf")
    woff = tmp_path/"source.woff"
    with TTFont(ttf) as font:
        font.flavor = "woff"
        font.save(woff)
    cat = ExactCatalog([ttf, woff])
    manifest = compare(cat, list(cat.entries), "AV O fi", tmp_path/"out", sizes=[48])
    a, b = manifest["fonts"]
    assert not a["decompressed_in_memory"]
    assert b["decompressed_in_memory"]
    assert a["sha256"] != b["sha256"]
    assert a["measurements"][0]["mask_sha256"] == b["measurements"][0]["mask_sha256"]


def test_single_script_arabic_shapes_with_native_context(catalog, tmp_path):
    manifest = compare(catalog, list(catalog.entries), "\u0628\u0628\u0628", tmp_path/"out", sizes=[64], language="ar")
    line = manifest["fonts"][0]["measurements"][0]["lines"][0]
    assert line["direction"] == "rtl"
    assert line["script"] == "Arab"
    assert len(set(g["glyph_id"] for g in line["glyphs"])) == 3
    assert [g["cluster"] for g in line["glyphs"]] == [2, 1, 0]


@pytest.mark.parametrize("text,error", [("A\u0628", "Mixed-direction"), ("\u062812", "Mixed-direction"), ("A\tV", "control"), ("A\ufe0f", "variation-selector"), ("A\u202eV", "control")])
def test_unsupported_layout_is_explicit_not_silent(catalog, tmp_path, text, error):
    with pytest.raises(RenderError, match=error):
        compare(catalog, list(catalog.entries), text, tmp_path/"out")


def test_variation_axes_record_defaults_and_explicit_coords(tmp_path):
    cat = ExactCatalog([build_font(tmp_path/"variable.ttf", variable=True)])
    ids = list(cat.entries)
    default = compare(cat, ids, "A", tmp_path/"default", sizes=[16])
    assert default["fonts"][0]["axes"] == {"wght": 400.0}
    assert default["fonts"][0]["axis_value_sources"] == {"wght": "font-default"}
    explicit = compare(cat, ids, "A", tmp_path/"explicit", sizes=[16], axes={ids[0]: {"wght": 700}})
    assert explicit["fonts"][0]["axes"] == {"wght": 700.0}
    with pytest.raises(RenderError, match="outside"):
        compare(cat, ids, "A", tmp_path/"bad", axes={"wght": 999})
    with pytest.raises(RenderError, match="Unknown variation axes"):
        compare(cat, ids, "A", tmp_path/"bad", axes={"wdth": 75})


def test_html_escapes_metadata_and_text(tmp_path):
    cat = ExactCatalog([build_font(tmp_path/"safe.ttf")], family='<img src=x onerror="alert(1)">')
    # Keep project text covered by the synthetic face while checking the exact
    # untrusted name that would otherwise create an HTML element.
    result = compare(cat, list(cat.entries), "AV", tmp_path/"out", sizes=[16])
    source = (tmp_path/"out"/"index.html").read_text()
    assert '<img src=x' not in source
    assert '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;' in source
    assert "default-src 'none'" in source
    assert 'https://' not in source
    assert result["fonts"][0]["family"].startswith("<img")


def test_wrapping_preserves_spaces_and_reports_no_clipping(catalog, tmp_path):
    text = "AV  "*25
    manifest = compare(catalog, list(catalog.entries), text, tmp_path/"out", sizes=[64], width=600)
    specimen = manifest["fonts"][0]["measurements"][0]
    assert specimen["line_count"] > 1
    assert "".join(line["text"] for line in specimen["lines"]) == text
    assert specimen["clipped"] is False


def test_different_face_widths_produce_distinct_geometry(tmp_path):
    cat = ExactCatalog([build_font(tmp_path/"narrow.ttf", width=400), build_font(tmp_path/"wide.ttf", width=900)])
    result = compare(cat, list(cat.entries), "AV fi", tmp_path/"out", sizes=[32])
    a, b = result["fonts"]
    assert a["measurements"][0]["lines"][0]["advance_px"][0] < b["measurements"][0]["lines"][0]["advance_px"][0]
    assert a["measurements"][0]["mask_sha256"] != b["measurements"][0]["mask_sha256"]


def test_prior_outputs_preserved(catalog, tmp_path):
    out = tmp_path/"out";out.mkdir();(out/"keep.txt").write_text("keep")
    with pytest.raises(RenderError, match="absent or empty"):
        compare(catalog, list(catalog.entries), "A", out, sizes=[16])
    assert (out/"keep.txt").read_text() == "keep"


def test_ltr_scripts_are_itemized_with_global_clusters(tmp_path):
    path = build_font(tmp_path/"multilingual.ttf")
    with TTFont(path) as font:
        for table in font["cmap"].tables:
            if table.isUnicode():
                table.cmap[0x391] = "A"
                table.cmap[0x3BF] = "O"
        font.save(path)
    cat = ExactCatalog([path])
    result = compare(cat, list(cat.entries), "AV Αο", tmp_path/"out", sizes=[32])
    line = result["fonts"][0]["measurements"][0]["lines"][0]
    assert line["script"] == "mixed-LTR-itemized"
    assert [run["script"] for run in line["script_runs"]] == ["Latn", "Grek"]
    assert [g["cluster"] for g in line["glyphs"]] == [0, 1, 2, 3, 4]
    assert line["script_runs"][1]["start"] == 3


def test_cli_unspecified_language_is_deterministic_und(catalog, tmp_path):
    result = compare(catalog, list(catalog.entries), "A", tmp_path/"out", sizes=[16], language=None)
    assert result["settings"]["language"] == "und"
