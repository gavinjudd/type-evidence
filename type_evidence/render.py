"""Exact-file specimens: HarfBuzz shaping and unhinted outline rasterization.

No platform font lookup occurs. HarfBuzz supplies positioned glyph IDs and
FreeType rasterizes the same verified in-memory face. Native nonzero winding
outline rasterization preserves counters and overlapping contours. It is intentionally not a browser
screenshot: screen hinting, color fonts, bidi paragraphs, and vertical layout are
outside this renderer's contract and are disclosed or rejected.
"""
from __future__ import annotations

import hashlib
import html
import io
import json
import math
import platform
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fontTools
import freetype
from importlib.metadata import version as package_version
from fontTools.ttLib import TTFont
from fontTools.unicodedata import script as unicode_script
from PIL import Image, ImageDraw, ImageFont, __version__ as pillow_version
import uharfbuzz as hb

AA = 4
PAPER = "#f4f1eb"
INK = "#17232b"
MUTED = "#5b6467"
RULE = "#c7c9c4"
MAX_PIXELS = 28_000_000
MAX_DIMENSION = 12_000
MAX_TEXT = 4_000
MAX_GLYPHS = 24_000


class RenderError(ValueError):
    """Requested evidence cannot be rendered faithfully within the contract."""


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _features(value: Any) -> dict[str, int]:
    """Accept global OpenType feature tags, deliberately excluding ranges."""
    if value is None:
        return {}
    if isinstance(value, dict):
        pairs = list(value.items())
    elif isinstance(value, (list, tuple)):
        pairs = []
        for item in value:
            if not isinstance(item, str):
                raise RenderError("Features must be tags such as 'liga', '-kern', or 'ss01=1'.")
            match = re.fullmatch(r"([+-]?)([A-Za-z0-9]{4})(?:=(\d+))?", item)
            if not match:
                raise RenderError(f"Unsupported feature specification: {item!r}; use global four-character tags.")
            sign, tag, number = match.groups()
            if sign and number is not None:
                raise RenderError("Use either a feature sign or '=value', not both.")
            pairs.append((tag, int(number) if number is not None else (0 if sign == "-" else 1)))
    else:
        raise RenderError("Features must be a mapping or a list of global OpenType feature tags.")
    result = {}
    for tag, setting in pairs:
        if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9]{4}", tag):
            raise RenderError("OpenType feature tags must contain four ASCII letters or digits.")
        if not isinstance(setting, (int, bool)) or not 0 <= int(setting) <= 65535:
            raise RenderError(f"Feature {tag} must have an integer value between 0 and 65535.")
        if tag in result:
            raise RenderError(f"Duplicate OpenType feature: {tag}.")
        result[tag] = int(setting)
    return dict(sorted(result.items()))


def _validate_text(text: str, direction: str | None) -> list[dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        raise RenderError("Provide nonempty project text.")
    if len(text) > MAX_TEXT:
        raise RenderError(f"Text exceeds the {MAX_TEXT}-character specimen limit; compare a representative excerpt.")
    if direction not in (None, "ltr", "rtl"):
        raise RenderError("Direction must be 'ltr' or 'rtl'; vertical layout is not supported.")
    for character in text:
        point = ord(character)
        category = unicodedata.category(character)
        if character != "\n" and (category in {"Cc", "Cs"} or (category == "Cf" and character not in "\u200c\u200d")):
            raise RenderError(f"Unsupported control U+{point:04X}; use explicit newlines and spaces, without bidi controls.")
        if 0xFE00 <= point <= 0xFE0F or 0xE0100 <= point <= 0xE01EF:
            raise RenderError("Unicode variation-selector sequences are not supported by this specimen renderer.")
    runs = []
    for line in text.split("\n"):
        scripts = sorted({unicode_script(c) for c in line} - {"Zyyy", "Zinh", "Zzzz"})
        bidi = {unicodedata.bidirectional(c) for c in line}
        rtl = bool(bidi & {"R", "AL"})
        if rtl and bidi & {"L", "EN", "AN"}:
            raise RenderError("Mixed-direction text requires a Unicode bidi paragraph engine; separate directional runs.")
        if rtl and len(scripts) > 1:
            raise RenderError("Mixed-script RTL text requires a Unicode bidi paragraph engine; compare separate lines.")
        if direction == "ltr" and rtl:
            raise RenderError("An RTL script cannot be forced to LTR in this renderer.")
        if direction == "rtl" and "L" in bidi:
            raise RenderError("An LTR script cannot be forced to RTL in this renderer.")
        runs.append({"scripts": scripts or ["Zyyy"], "direction": direction or ("rtl" if rtl else "ltr")})
    return runs


def _raster_glyph(face, glyph: int, size: int):
    """Rasterize the selected glyph ID, never remap a character through a font."""
    face.set_pixel_sizes(0, size * AA)
    try:
        face.load_glyph(glyph, freetype.FT_LOAD_NO_HINTING | freetype.FT_LOAD_NO_BITMAP)
        # Inspect outline metrics before FreeType allocates a potentially large
        # raster for an unusual/malformed font.
        metrics = face.glyph.metrics
        estimate_width = math.ceil(abs(metrics.width)/64)+4
        estimate_height = math.ceil(abs(metrics.height)/64)+4
        if estimate_width*estimate_height > 6_000_000 or max(estimate_width, estimate_height) > MAX_DIMENSION:
            raise RenderError("Glyph bounds exceed the safe raster limit.")
        face.glyph.render(freetype.FT_RENDER_MODE_NORMAL)
    except freetype.FT_Exception as exc:
        raise RenderError(f"FreeType could not rasterize glyph {glyph}: {exc}") from exc
    bitmap = face.glyph.bitmap
    if not bitmap.width or not bitmap.rows:
        return None
    if bitmap.pixel_mode != freetype.FT_PIXEL_MODE_GRAY or bitmap.num_grays != 256:
        raise RenderError("FreeType returned a bitmap format other than 8-bit grayscale.")
    if bitmap.width*bitmap.rows > 6_000_000 or max(bitmap.width, bitmap.rows) > MAX_DIMENSION:
        raise RenderError("Glyph bounds exceed the safe raster limit.")
    # Native gray bitmaps can have row padding (pitch); do not interpret it as ink.
    raw = bytes(bitmap.buffer)
    pitch = abs(bitmap.pitch)
    rows = [raw[y*pitch:y*pitch+bitmap.width] for y in range(bitmap.rows)]
    if bitmap.pitch < 0:
        rows.reverse()
    mask = Image.frombytes("L", (bitmap.width, bitmap.rows), b"".join(rows))
    return mask, face.glyph.bitmap_left, -face.glyph.bitmap_top


@dataclass
class _Asset:
    record: dict[str, Any]
    resolution: dict[str, Any]
    font: hb.Font
    freetype_face: Any
    upem: int
    axes: dict[str, float]
    axis_source: dict[str, str]
    coverage: dict[str, Any]
    decompressed: bool
    outline_tables: list[str]
    source_bytes: int
    cache: dict[tuple[int, int], Any]


def _load(catalog, font_id, axes, text):
    record = catalog.get(font_id)
    resolution = catalog.resolve(font_id)  # Mandatory catalog integrity/containment checks.
    path = Path(resolution["path"])
    source = path.read_bytes()
    # Verify the actual bytes we are about to use, closing the resolve/read race.
    if _digest(source) != resolution["sha256"]:
        raise RenderError(f"Font changed after resolution: {font_id}.")
    face_index = int(resolution.get("face_index", 0))
    with TTFont(io.BytesIO(source), fontNumber=face_index, lazy=False) as tt:
        if any(tag in tt for tag in ("COLR", "SVG ", "sbix", "CBDT", "EBDT")):
            raise RenderError(f"Color/bitmap font rendering is unsupported: {font_id}.")
        outline_tables = [tag for tag in ("glyf", "CFF ", "CFF2") if tag in tt]
        if not outline_tables:
            raise RenderError(f"No supported outline table: {font_id}.")
        upem = tt["head"].unitsPerEm
        if not 16 <= upem <= 16384:
            raise RenderError(f"Unsupported units per em: {upem}.")
        available = {axis.axisTag: axis for axis in tt["fvar"].axes} if "fvar" in tt else {}
        if not isinstance(axes, dict):
            raise RenderError("Axes must be a mapping of tags to numeric design-space coordinates.")
        unknown = set(axes) - set(available)
        if unknown:
            raise RenderError(f"Unknown variation axes for {font_id}: {', '.join(sorted(unknown))}.")
        applied, axis_source = {}, {}
        for tag, axis in available.items():
            value = axes.get(tag, axis.defaultValue)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise RenderError(f"Axis {tag} must be a finite number.")
            if not axis.minValue <= value <= axis.maxValue:
                raise RenderError(f"Axis {tag}={value} lies outside [{axis.minValue}, {axis.maxValue}].")
            applied[tag] = float(value)
            axis_source[tag] = "explicit" if tag in axes else "font-default"
        cmap = tt.getBestCmap() or {}
        required = sorted({ord(c) for c in text if c not in "\n\u200c\u200d"})
        missing = [point for point in required if point not in cmap or tt.getGlyphID(cmap[point]) == 0]
        if missing:
            pretty = ", ".join(f"U+{point:04X}" for point in missing[:20])
            raise RenderError(f"Font {font_id} lacks required characters: {pretty}. No fallback was used.")
        decompressed = tt.flavor is not None
        if decompressed:
            tt.flavor = None
            buffer = io.BytesIO()
            tt.save(buffer, reorderTables=False)
            shape_bytes, hb_index = buffer.getvalue(), 0
        else:
            shape_bytes, hb_index = source, face_index
    font = hb.Font(hb.Face(shape_bytes, hb_index))
    font.scale = (upem, upem)
    font.set_variations(applied)
    face = freetype.Face(io.BytesIO(shape_bytes), index=hb_index)
    if face.num_glyphs != font.face.glyph_count:
        raise RenderError("HarfBuzz and FreeType disagree about the exact face glyph count.")
    if applied:
        face.set_var_design_coords(tuple(applied.values()))
    return _Asset(record, resolution, font, face, upem, applied, axis_source,
                  {"required_codepoints": required, "missing_codepoints": [],
                   "join_controls": sorted({ord(c) for c in text if c in "\u200c\u200d"}),
                   "checked_against": "exact-face Unicode cmap and post-shaping glyph IDs"},
                  decompressed, outline_tables, len(source), {})


def _script_runs(text):
    """Itemize LTR text; Common/Inherited characters follow their neighbor."""
    strong = [unicode_script(c) for c in text if unicode_script(c) not in {"Zyyy", "Zinh", "Zzzz"}]
    current = strong[0] if strong else "Zyyy"
    start, result = 0, []
    for index, character in enumerate(text):
        script = unicode_script(character)
        if script not in {"Zyyy", "Zinh", "Zzzz", current}:
            result.append((text[start:index], current, start))
            start, current = index, script
    result.append((text[start:], current, start))
    return result


def _shape(asset, text, size, features, direction, language):
    # HarfBuzz operates on a script run. It is not a paragraph bidi engine.
    # Same-direction LTR scripts can be placed in source order; mixed-direction
    # and mixed-script RTL paragraphs have already been explicitly rejected.
    resolved_direction = direction or ("rtl" if any(unicodedata.bidirectional(c) in {"R", "AL"} for c in text) else "ltr")
    glyphs, x, y, run_evidence = [], 0, 0, []
    factor = size/asset.upem
    runs = _script_runs(text)
    for run_text, script, start in runs:
        buffer = hb.Buffer()
        buffer.add_str(run_text)
        buffer.language = language
        buffer.direction = resolved_direction
        buffer.script = script
        buffer.guess_segment_properties()
        hb.shape(asset.font, buffer, features)
        positions = buffer.glyph_positions or []
        if len(positions)+len(glyphs) > MAX_GLYPHS:
            raise RenderError("Shaped glyph count exceeds the specimen limit.")
        for info, position in zip(buffer.glyph_infos, positions):
            if info.codepoint == 0:
                raise RenderError(f"Shaping produced glyph 0 for {asset.record['id']} at cluster {start+info.cluster}; no fallback was used.")
            glyphs.append({"glyph_id": info.codepoint, "cluster": start+info.cluster,
                           "x": (x+position.x_offset)*factor, "y": -(y+position.y_offset)*factor,
                           "x_advance": position.x_advance*factor, "y_advance": -position.y_advance*factor})
            x += position.x_advance
            y += position.y_advance
        run_evidence.append({"start": start, "end": start+len(run_text), "script": str(buffer.script),
                             "direction": str(buffer.direction), "glyph_count": len(positions)})
    return {"text": text, "direction": resolved_direction,
            "script": runs[0][1] if len(runs) == 1 else "mixed-LTR-itemized",
            "language": language, "script_runs": run_evidence,
            "glyphs": glyphs, "advance_px": [x*factor, -y*factor]}


def _wrap(asset, paragraph, size, features, direction, language, width):
    full = _shape(asset, paragraph, size, features, direction, language)
    if abs(full["advance_px"][0]) <= width or not paragraph:
        return [full]
    # Preserve every character, including whitespace. A wrap boundary follows a
    # whitespace run; words/joined sequences are never cut to force a fit.
    tokens = re.findall(r"\S+\s*|\s+", paragraph)
    lines, current = [], ""
    for token in tokens:
        candidate = current + token
        shaped = _shape(asset, candidate, size, features, direction, language)
        if current and abs(shaped["advance_px"][0]) > width:
            lines.append(_shape(asset, current, size, features, direction, language))
            current = token
        else:
            current = candidate
    if current:
        lines.append(_shape(asset, current, size, features, direction, language))
    return lines or [full]


def _specimen(asset, text, size, features, direction, language, width):
    shaped_lines = []
    for index, paragraph in enumerate(text.split("\n")):
        for line in _wrap(asset, paragraph, size, features, direction, language, width):
            line["paragraph"] = index
            shaped_lines.append(line)
    extents = asset.font.get_font_extents(direction or "ltr")
    ascender = max(0, extents.ascender*size/asset.upem) if extents else .8*size
    descender = max(0, -extents.descender*size/asset.upem) if extents else .2*size
    gap = max(0, extents.line_gap*size/asset.upem) if extents else 0
    leading = max(size*1.35, ascender+descender+gap)
    ink_bounds = None
    placements = []
    for line_number, line in enumerate(shaped_lines):
        baseline = ascender + line_number*leading
        line["baseline_px"] = baseline
        line_ink = None
        for glyph in line["glyphs"]:
            key = (size, glyph["glyph_id"])
            if key not in asset.cache:
                asset.cache[key] = _raster_glyph(asset.freetype_face, glyph["glyph_id"], size)
            raster = asset.cache[key]
            if raster is None:
                continue
            mask, left, top = raster
            x = round(glyph["x"]*AA)+left
            y = round((baseline+glyph["y"])*AA)+top
            bounds = mask.getbbox()
            if bounds:
                placed = (x+bounds[0], y+bounds[1], x+bounds[2], y+bounds[3])
                line_ink = _union(line_ink, placed)
                ink_bounds = _union(ink_bounds, placed)
            placements.append((mask, x, y))
        line["ink_bounds_px"] = [round(v/AA, 4) for v in line_ink] if line_ink else None
    logical_width = max((abs(line["advance_px"][0]) for line in shaped_lines), default=0)
    logical_height = ascender+descender+(len(shaped_lines)-1)*leading
    logical = (0, 0, math.ceil(logical_width*AA), math.ceil(logical_height*AA))
    bounds = _union(ink_bounds, logical)
    pad = AA*4
    left, top = math.floor(bounds[0])-pad, math.floor(bounds[1])-pad
    right, bottom = math.ceil(bounds[2])+pad, math.ceil(bounds[3])+pad
    out_width, out_height = math.ceil((right-left)/AA), math.ceil((bottom-top)/AA)
    _check_image(out_width, out_height)
    if out_width > 4096:
        raise RenderError("An unbreakable line exceeds 4096 px; insert a newline or use a smaller size. No text was clipped.")
    if out_width*out_height*AA*AA > MAX_PIXELS*4:
        raise RenderError("Supersampled specimen exceeds the raster budget; shorten the text or reduce sizes.")
    canvas = Image.new("L", (out_width*AA, out_height*AA), 0)
    # Union opaque glyph coverage rather than XORing or knocking out overlaps.
    for mask, x, y in placements:
        x, y = x-left, y-top
        # Crop only the guaranteed blank raster padding outside the canvas.
        a, b = max(0, -x), max(0, -y)
        c, d = min(mask.width, canvas.width-x), min(mask.height, canvas.height-y)
        if c <= a or d <= b:
            continue
        glyph_mask = mask.crop((a, b, c, d))
        canvas.paste(255, (x+a, y+b, x+c, y+d), glyph_mask)
    result = canvas.resize((out_width, out_height), Image.Resampling.LANCZOS)
    evidence = {"size_px": size, "line_count": len(shaped_lines), "line_height_px": round(leading, 4),
                "ascender_px": round(ascender, 4), "descender_px": round(descender, 4),
                "ink_bounds_px": [round(v/AA, 4) for v in ink_bounds] if ink_bounds else None,
                "canvas_px": [out_width, out_height], "ink_offset_px": [round(-left/AA, 4), round(-top/AA, 4)],
                "clipped": False, "overflow_handling": "canvas expands to include all ink; whitespace wrapping; 4096px unbreakable-line limit",
                "mask_sha256": _digest(result.tobytes()), "lines": shaped_lines}
    return result, evidence


def _union(a, b):
    if a is None:
        return b
    if b is None:
        return a
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def _check_image(width, height):
    if width <= 0 or height <= 0 or max(width, height) > MAX_DIMENSION or width*height > MAX_PIXELS:
        raise RenderError(f"Image {width}×{height} exceeds the safe canvas limit; shorten text or compare fewer faces/sizes.")


def _label(value):
    # Bitmap metadata uses Pillow's bundled label face, never the specimen face.
    return str(value).encode("ascii", "backslashreplace").decode("ascii")


def _label_lines(value, width, font):
    value = _label(value)
    lines, current = [], ""
    for character in value:
        if current and font.getlength(current+character) > width:
            lines.append(current)
            current = character
        else:
            current += character
    return lines+[current]


def _sheet(rows, title, subtitle, min_width=1440):
    margin, label_h = 52, 18
    ui = ImageFont.load_default(size=14)
    small = ImageFont.load_default(size=12)
    heading = ImageFont.load_default(size=29)
    width = max(min_width, max((mask.width+margin*2 for _, _, mask, _ in rows), default=min_width))
    subtitle_lines = _label_lines(subtitle, width-2*margin, small)
    height = 113 + len(subtitle_lines)*16
    prepared = []
    for label, detail, mask, evidence in rows:
        labels = _label_lines(label, width-2*margin, ui)
        details = _label_lines(detail, width-2*margin, small)
        row_height = 30 + label_h*len(labels) + 16*len(details) + mask.height + 28
        prepared.append((labels, details, mask, evidence, row_height))
        height += row_height
    height += 50
    _check_image(width, height)
    canvas = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(canvas)
    draw.text((margin, 30), title, font=heading, fill=INK)
    y = 75
    for line in subtitle_lines:
        draw.text((margin, y), line, font=small, fill=MUTED)
        y += 16
    y += 26
    for labels, details, mask, evidence, row_height in prepared:
        draw.line((margin, y, width-margin, y), fill=RULE, width=1)
        y += 17
        for line in labels:
            draw.text((margin, y), line, font=ui, fill=INK)
            y += label_h
        for line in details:
            draw.text((margin, y), line, font=small, fill=MUTED)
            y += 16
        y += 12
        canvas.paste(INK, (margin, y), mask)
        y += mask.height+29
    draw.text((margin, height-30), "Exact assets / HarfBuzz shaping / unhinted outlines / no font fallback", font=small, fill=MUTED)
    return canvas


def _write_png(image, path):
    image.save(path, format="PNG", optimize=True)
    return {"file": path.name, "sha256": _digest(path.read_bytes()), "width": image.width, "height": image.height}


def _html(manifest):
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for index, font in enumerate(manifest["fonts"], 1):
        sizes = ", ".join(str(row["size_px"]) for row in font["measurements"])
        rows.append(f'''<section id="font-{index}"><div class="section-head"><span class="number">{index:02d}</span><div><h2>{esc(font['family'])} <span>{esc(font['style'])}</span></h2><p>{esc(font['id'])}</p></div></div>
<dl><dt>Source SHA-256</dt><dd>{esc(font['sha256'])}</dd><dt>Face / sizes</dt><dd>{font['face_index']} / {sizes} px</dd><dt>Variation axes</dt><dd>{esc(json.dumps(font['axes'], sort_keys=True))}</dd><dt>Rights evidence</dt><dd>{esc(font['rights'].get('status', 'unknown'))}; review required</dd><dt>Source provenance</dt><dd>{esc(json.dumps(font['provenance'], ensure_ascii=False, sort_keys=True))}</dd></dl>
<img loading="lazy" src="{esc(font['image']['file'])}" width="{font['image']['width']}" height="{font['image']['height']}" alt="Verified font specimen {index}: {esc(font['family'])} {esc(font['style'])}, at {sizes} pixels. Use the adjacent metadata and manifest for nonvisual evidence.">
</section>''')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Type Evidence — exact-file comparison</title><style>
:root{{color-scheme:light;--paper:#f4f1eb;--ink:#17232b;--muted:#5b6467;--rule:#c7c9c4}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 system-ui,sans-serif}}main{{max-width:1480px;margin:auto;padding:48px 32px 80px}}.eyebrow{{font-size:12px;font-weight:650;letter-spacing:.16em;text-transform:uppercase;color:var(--muted)}}h1{{font-size:clamp(32px,5vw,62px);letter-spacing:-.045em;line-height:1.08;font-weight:600;margin:18px 0}}.intro{{max-width:78ch;color:var(--muted)}}a{{color:inherit;text-underline-offset:3px}}nav{{display:flex;gap:24px;flex-wrap:wrap;padding:20px 0;border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);margin:30px 0}}section{{margin-top:48px}}.section-head{{display:flex;gap:20px;align-items:baseline}}.number{{font-size:13px;color:var(--muted);font-variant-numeric:tabular-nums}}h2{{font-size:25px;line-height:1.2;margin:0}}h2 span{{font-weight:400}}.section-head p{{font-size:12px;overflow-wrap:anywhere;color:var(--muted)}}img{{display:block;max-width:100%;height:auto;margin:20px 0;border:1px solid var(--rule)}}dl{{display:grid;grid-template-columns:170px 1fr;font-size:13px;gap:8px 20px;max-width:1100px}}dt{{color:var(--muted)}}dd{{margin:0;overflow-wrap:anywhere}}pre{{font:15px/1.55 ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere;border-left:2px solid var(--ink);padding:4px 0 4px 22px}}.note{{font-size:13px;color:var(--muted);max-width:100ch}}@media(max-width:600px){{main{{padding:28px 16px}}dl{{grid-template-columns:1fr;gap:2px}}dd{{margin-bottom:10px}}}}
</style></head><body><main><div class="eyebrow">Local typography / evidence edition</div><h1>Choose with the actual type.</h1>
<p class="intro">{len(manifest['fonts'])} exact font faces. Your text, shared sizes, explicit settings. The specimens below are PNGs rendered from verified source bytes. The page interface uses your system font; it is separate from the specimens.</p>
<nav><a href="comparison.png">Open full comparison PNG at actual resolution</a><a href="manifest.json">Read machine evidence (JSON)</a><a href="#project-text">Read project text</a></nav>
<p class="note">{esc(manifest['limitations'][0])} Browser scaling can soften previews: open the PNG at 100% to inspect small text. Measurements describe this renderer; they are not subjective design judgments. Source rights remain subject to review.</p>
<img src="comparison.png" width="{manifest['images'][0]['width']}" height="{manifest['images'][0]['height']}" alt="Exact-file comparison of {len(manifest['fonts'])} font faces. Each row uses identical project text and the labeled pixel size. Detailed glyph and measurement evidence is in manifest.json.">
<section id="project-text"><div class="eyebrow">The brief, verbatim</div><pre>{esc(manifest['text'])}</pre><p class="note">SHA-256: {esc(manifest['text_sha256'])}</p></section>
{''.join(rows)}
<section><h2>How to read this evidence</h2><p class="note">{esc(' '.join(manifest['limitations']))}</p><p class="note">{esc(manifest['no_fallback']['statement'])}</p><p class="note">Renderer: HarfBuzz {esc(manifest['renderer']['harfbuzz'])}; uharfbuzz {esc(manifest['renderer']['uharfbuzz'])}; Pillow {esc(manifest['renderer']['pillow'])}. OpenType overrides: {esc(json.dumps(manifest['settings']['features']))}; language: {esc(manifest['settings']['language'])}.</p></section>
</main></body></html>'''


def compare(catalog, ids: list[str], text: str, output: Path, sizes: list[int] | None = None, **options) -> dict:
    """Write comparison PNG, per-face PNGs, safe local HTML and machine evidence.

    Options: axes={tag:value} or {exact_id:{tag:value}}, features=["liga",
    "-kern"] or {tag:int}, direction="ltr"/"rtl", language="en", width=1440.
    Sizes are pixels/em. Defaults are [16, 32, 64]. Unsupported capabilities fail
    before creating output. No matching by family names or fallback is allowed.
    """
    supported = {"axes", "features", "direction", "language", "width"}
    unknown = set(options) - supported
    if unknown:
        raise RenderError(f"Unknown rendering options: {', '.join(sorted(unknown))}.")
    if not ids or len(ids) > 12 or len(set(ids)) != len(ids) or not all(isinstance(i, str) for i in ids):
        raise RenderError("Compare between 1 and 12 distinct exact font IDs.")
    sizes = [16, 32, 64] if sizes is None else list(sizes)
    if not sizes or len(sizes) > 6 or any(isinstance(n, bool) or not isinstance(n, int) or not 8 <= n <= 256 for n in sizes):
        raise RenderError("Use 1–6 integer pixel sizes between 8 and 256.")
    if len(set(sizes)) != len(sizes):
        raise RenderError("Comparison sizes must be distinct.")
    width = options.get("width", 1440)
    if isinstance(width, bool) or not isinstance(width, int) or not 600 <= width <= 4096:
        raise RenderError("Canvas width must be an integer between 600 and 4096 pixels.")
    direction = options.get("direction")
    # Newline normalization is explicit in the manifest; no other text changes.
    if not isinstance(text, str):
        raise RenderError("Project text must be a string.")
    original_text = text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    runs = _validate_text(text, direction)
    features = _features(options.get("features"))
    language = options.get("language") or "und"
    if not isinstance(language, str) or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language):
        raise RenderError("Language must be a BCP-47-style tag, for example 'en', 'ar', or 'und'.")
    axes = options.get("axes", {})
    if not isinstance(axes, dict):
        raise RenderError("Axes must be a mapping.")
    per_font = bool(axes) and all(isinstance(value, dict) for value in axes.values())
    if per_font and set(axes)-set(ids):
        raise RenderError("Per-font axes reference IDs outside this comparison.")
    if not per_font and any(isinstance(value, dict) for value in axes.values()):
        raise RenderError("Do not mix global axis values and per-font axis mappings.")
    assets = [_load(catalog, font_id, axes.get(font_id, {}) if per_font else axes, text) for font_id in ids]
    all_rows, font_entries, per_face_rows = [], [], []
    for index, asset in enumerate(assets, 1):
        rows, measurements = [], []
        for size in sizes:
            mask, evidence = _specimen(asset, text, size, features, direction, language, width-104)
            measurements.append(evidence)
            label = f"{index:02d}  {asset.record.get('family', '(unnamed)')} / {asset.record.get('style', '')}    {size} px"
            detail = f"{asset.record['id']}  |  {evidence['line_count']} line(s)  |  " + (", ".join(f"{k}={v:g}" for k,v in asset.axes.items()) or "static face")
            rows.append((label, detail, mask, evidence))
        per_face_rows.append(rows)
        font_entries.append({"id": asset.record["id"], "family": asset.record.get("family", "(unnamed)"),
                             "style": asset.record.get("style", ""), "sha256": asset.resolution["sha256"],
                             "face_index": int(asset.resolution.get("face_index", 0)), "source_bytes": asset.source_bytes,
                             "provenance": asset.resolution.get("provenance", asset.record.get("origins", [])),
                             "rights": asset.resolution.get("rights", asset.record.get("rights", {"status": "unknown"})),
                             "axes": asset.axes, "axis_value_sources": asset.axis_source,
                             "coverage": asset.coverage, "decompressed_in_memory": asset.decompressed,
                             "outline_tables": asset.outline_tables, "measurements": measurements,
                             "glyph_zero_count": 0, "asset_verified": True})
    # Group equal-size rows together so a comparison does not become a sequence
    # of unrelated specimen posters.
    for size_index in range(len(sizes)):
        all_rows.extend(rows[size_index] for rows in per_face_rows)
    subtitle = f"{len(ids)} exact faces | {', '.join(map(str, sizes))} px | language {language} | shared text { _digest(text.encode('utf-8'))[:16]}"
    comparison_image = _sheet(all_rows, "TYPE / EVIDENCE", subtitle, width)
    face_images = [_sheet(rows, f"TYPE / {index:02d}", subtitle, width) for index, rows in enumerate(per_face_rows, 1)]
    manifest = {
        "schema_version": 1, "kind": "exact-font-comparison", "text": text,
        "text_sha256": _digest(text.encode("utf-8")), "original_text_sha256": _digest(original_text.encode("utf-8")),
        "text_transformations": ["CRLF/CR normalized to LF"] if text != original_text else [],
        "settings": {"sizes_px": sizes, "requested_width_px": width, "axes": axes, "features": features,
                     "feature_defaults": "HarfBuzz/OpenType defaults remain enabled unless explicitly overridden",
                     "direction": direction or "inferred per line; same-direction LTR scripts itemized", "language": language,
                     "input_runs": runs, "wrap": "whitespace boundaries only; text preserved"},
        "renderer": {"backend": "HarfBuzz shaping + native FreeType grayscale outline rasterization", "harfbuzz": hb.version_string(),
                     "freetype": ".".join(map(str, freetype.version())), "freetype_py": package_version("freetype-py"),
                     "uharfbuzz": hb.__version__, "fonttools": fontTools.__version__, "pillow": pillow_version,
                     "python": platform.python_version(), "supersampling": AA, "downsampling": "Lanczos",
                     "hinting": "none", "position_quantization_px": 1/AA,
                     "labels": "Pillow bundled default font; labels are separate from candidate specimens"},
        "no_fallback": {"verified": True, "system_font_lookup": False, "glyph_zero_count": 0,
                        "statement": "Every specimen glyph is shaped by HarfBuzz and drawn by FreeType from its exact verified source face. No system lookup, substitute font, or fallback font is used. Labels and page UI are separate."},
        "limitations": ["Specimens use unhinted monochrome outlines; they do not predict browser, game engine, printer, or OS text rasterization.",
                        "LTR scripts are itemized in source order; Common/Inherited characters follow neighboring script runs. Bidirectional paragraphs, mixed-script RTL lines, vertical writing, Unicode variation selectors, and color/bitmap fonts are rejected.",
                        "Line wrapping preserves whitespace and does not implement language-specific hyphenation. All ink bounds receive padding; oversized output is rejected instead of clipped.",
                        "Nonvisual evidence describes measured geometry, coverage, shaping, and settings. It does not claim aesthetic quality, accessibility, or licensing clearance."],
        "fonts": font_entries, "images": [],
        "outputs": {"html": "index.html", "comparison": "comparison.png", "manifest": "manifest.json", "specimens": []},
    }
    output = Path(output)
    # Do not overwrite an earlier review package, and reject symlink destinations.
    if output.is_symlink():
        raise RenderError("Output directory must not be a symlink.")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RenderError("Output directory must be absent or empty; preserve previous comparison evidence.")
    output.mkdir(parents=True, exist_ok=True)
    manifest["images"].append(_write_png(comparison_image, output / "comparison.png"))
    for index, (font, sheet) in enumerate(zip(font_entries, face_images), 1):
        name = f"specimen-{index:02d}-{font['sha256'][:12]}.png"
        font["image"] = _write_png(sheet, output/name)
        manifest["images"].append(font["image"])
        manifest["outputs"]["specimens"].append(name)
    (output/"index.html").write_text(_html(manifest), encoding="utf-8")
    manifest["html_sha256"] = _digest((output/"index.html").read_bytes())
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return manifest
