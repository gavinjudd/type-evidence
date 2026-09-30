"""Contextual typography layouts rendered from verified exact font faces.

The compact block format supports reading pages, dense interfaces, and posters.
It deliberately keeps the composition, its fonts, and application settings in
one revisable specification. PNGs are authoritative for this renderer; the CSS
recipe is a starting point to verify in the real application, not a claim of
browser-identical layout.
"""
from __future__ import annotations

import copy
import html
import json
import math
import re
from pathlib import Path
from typing import Any

import freetype
import uharfbuzz as hb
from PIL import Image, ImageDraw

from .render import (AA, RenderError, _check_image, _digest, _features, _load,
                     _raster_glyph, _union, _validate_text, _wrap, _write_png)


_TEMPLATES = {
    "editorial": {"width": 1040, "padding": 72, "gap": 20,
                  "background": "#f6f3ec", "color": "#252a27",
                  "sizes": {"eyebrow": 13, "title": 56, "dek": 25, "body": 21, "caption": 13, "heading": 28}},
    "interface": {"width": 1200, "padding": 40, "gap": 18,
                  "background": "#f7f8fa", "color": "#1d2836",
                  "sizes": {"eyebrow": 12, "title": 34, "dek": 18, "body": 16, "caption": 13, "heading": 21}},
    "poster": {"width": 1000, "padding": 64, "gap": 28,
               "background": "#132e33", "color": "#fff3d5",
               "sizes": {"eyebrow": 17, "title": 96, "dek": 32, "body": 23, "caption": 15, "heading": 42}},
}
_ROLE_NAME = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
_COLOR = re.compile(r"#[0-9a-fA-F]{6}\Z")


def _number(value, label, low, high, *, integer=False):
    types = (int,) if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, types) or not math.isfinite(value) or not low <= value <= high:
        raise RenderError(f"{label} must be {'an integer' if integer else 'a finite number'} between {low} and {high}.")
    return value


def _color(value, label):
    if not isinstance(value, str) or not _COLOR.fullmatch(value):
        raise RenderError(f"{label} must be a six-digit hexadecimal color such as #17232b.")
    return value.lower()


def _fields(value, allowed, label):
    if not isinstance(value, dict):
        raise RenderError(f"{label} must be an object.")
    unknown = set(value) - allowed
    if unknown:
        raise RenderError(f"Unknown {label} fields: {', '.join(sorted(map(str, unknown)))}.")


def _normalize(spec):
    _fields(spec, {"template", "title", "medium", "width", "padding", "gap", "min_height", "background", "roles", "blocks"}, "composition")
    template = spec.get("template", "editorial")
    if not isinstance(template, str) or template not in _TEMPLATES:
        raise RenderError("Template must be editorial, interface, or poster.")
    defaults = _TEMPLATES[template]
    result = {key: spec.get(key, defaults[key]) for key in ("width", "padding", "gap", "background")}
    result.update(template=template, title=spec.get("title", "Typography composition"),
                  medium=spec.get("medium", "screen"), min_height=spec.get("min_height", 0))
    if not isinstance(result["title"], str) or not 1 <= len(result["title"]) <= 200:
        raise RenderError("Composition title must contain 1–200 characters.")
    if result["medium"] not in ("screen", "print-preview"):
        raise RenderError("Medium must be screen or print-preview; dimensions are always pixels.")
    _number(result["width"], "Width", 320, 2400, integer=True)
    _number(result["padding"], "Padding", 8, 200, integer=True)
    _number(result["gap"], "Gap", 0, 160, integer=True)
    _number(result["min_height"], "Minimum height", 0, 12000, integer=True)
    result["background"] = _color(result["background"], "Background")
    if result["padding"] * 2 >= result["width"] - 64:
        raise RenderError("Padding leaves too little room for the composition.")
    roles = spec.get("roles")
    if not isinstance(roles, dict) or not 1 <= len(roles) <= 12:
        raise RenderError("Provide 1–12 typography roles, each with an exact font_id.")
    result["roles"] = {}
    for name, value in roles.items():
        if not isinstance(name, str) or not _ROLE_NAME.fullmatch(name):
            raise RenderError("Role names must use lowercase ASCII letters, digits, underscores, or hyphens.")
        _fields(value, {"font_id", "size", "line_height", "color", "weight", "italic", "axes", "features", "language", "direction", "align"}, f"role {name}")
        font_id = value.get("font_id")
        if not isinstance(font_id, str) or not font_id or len(font_id) > 160:
            raise RenderError(f"Role {name} needs an exact font_id.")
        size = _number(value.get("size", defaults["sizes"].get(name, defaults["sizes"]["body"])), f"Role {name} size", 8, 256, integer=True)
        leading = 1.1 if name in ("title", "heading") else (1.55 if template == "editorial" and name == "body" else 1.4)
        role = {"font_id": font_id, "size": size,
                "line_height": _number(value.get("line_height", leading), f"Role {name} line_height", .85, 3),
                "color": _color(value.get("color", defaults["color"]), f"Role {name} color"),
                "features": _features(value.get("features")), "axes": value.get("axes", {}),
                "language": value.get("language", "und"), "direction": value.get("direction"), "align": value.get("align", "start")}
        if not isinstance(role["axes"], dict) or len(role["axes"]) > 32:
            raise RenderError(f"Role {name} axes must be a mapping with at most 32 tags.")
        for tag, number in role["axes"].items():
            if not isinstance(tag, str) or not re.fullmatch(r"[A-Za-z0-9]{4}", tag):
                raise RenderError(f"Role {name} axis tags must contain four ASCII letters or digits.")
            _number(number, f"Role {name} axis {tag}", -1_000_000, 1_000_000)
        if not isinstance(role["language"], str) or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", role["language"]):
            raise RenderError(f"Role {name} language must be a BCP-47-style language tag.")
        if role["direction"] not in (None, "ltr", "rtl") or role["align"] not in ("start", "end", "left", "right", "center"):
            raise RenderError(f"Role {name} uses an unsupported direction or alignment.")
        if "weight" in value:
            role["weight"] = _number(value["weight"], f"Role {name} weight", 1, 1000, integer=True)
        if "italic" in value:
            if not isinstance(value["italic"], bool):
                raise RenderError(f"Role {name} italic must be a boolean.")
            role["italic"] = value["italic"]
        result["roles"][name] = role
    budget = {"blocks": 0, "characters": 0, "cells": 0}
    texts = {name: [] for name in roles}

    def text(value, role, label):
        if not isinstance(role, str) or role not in result["roles"]:
            raise RenderError(f"{label} refers to an unknown role {role!r}.")
        if not isinstance(value, str) or not value.strip():
            raise RenderError(f"{label} must contain nonempty text.")
        value = value.replace("\r\n", "\n").replace("\r", "\n")
        _validate_text(value, result["roles"][role]["direction"])
        budget["characters"] += len(value)
        if budget["characters"] > 16000:
            raise RenderError("Composition exceeds 16000 characters; use a representative page or screen.")
        texts[role].append(value)
        return value

    def blocks(values, depth=0):
        if depth > 4 or not isinstance(values, list) or not values:
            raise RenderError("Blocks must be a nonempty list, nested at most four levels.")
        out = []
        for value in values:
            budget["blocks"] += 1
            if budget["blocks"] > 100:
                raise RenderError("Composition exceeds 100 blocks.")
            if not isinstance(value, dict):
                raise RenderError("Each block must be an object.")
            kind = value.get("type", "text")
            allowed = {
                "text": {"role", "text"}, "rule": {"color", "thickness"}, "spacer": {"height"},
                "columns": {"columns"}, "panel": {"blocks", "background", "padding"},
                "table": {"role", "header_role", "columns", "rows", "row_padding", "rule_color"},
            }
            if not isinstance(kind, str) or kind not in allowed:
                raise RenderError(f"Unknown block type {kind!r}.")
            _fields(value, allowed[kind] | {"type", "gap"}, f"{kind} block")
            block = {"type": kind, "gap": _number(value.get("gap", result["gap"]), "Block gap", 0, 200, integer=True)}
            if kind == "text":
                block["role"] = value.get("role", "body")
                block["text"] = text(value.get("text"), block["role"], "Text block")
            elif kind == "rule":
                block.update(color=_color(value.get("color", "#bcc3c3"), "Rule color"),
                             thickness=_number(value.get("thickness", 1), "Rule thickness", 1, 16, integer=True))
            elif kind == "spacer":
                block["height"] = _number(value.get("height", 24), "Spacer height", 0, 1000, integer=True)
            elif kind == "panel":
                block.update(blocks=blocks(value.get("blocks"), depth+1),
                             background=_color(value.get("background", "#e9edef"), "Panel background"),
                             padding=_number(value.get("padding", 24), "Panel padding", 0, 100, integer=True))
            elif kind == "columns":
                columns = value.get("columns")
                if not isinstance(columns, list) or not 2 <= len(columns) <= 4:
                    raise RenderError("Use 2–4 columns.")
                block["columns"] = []
                for column in columns:
                    _fields(column, {"width", "blocks"}, "column")
                    block["columns"].append({"width": _number(column.get("width", 1), "Column fraction", .1, 10),
                                              "blocks": blocks(column.get("blocks"), depth+1)})
            elif kind == "table":
                role, header_role = value.get("role", "body"), value.get("header_role", value.get("role", "body"))
                columns, rows = value.get("columns"), value.get("rows")
                if not isinstance(columns, list) or not 1 <= len(columns) <= 8 or not isinstance(rows, list) or not 1 <= len(rows) <= 30:
                    raise RenderError("Tables require 1–8 columns and 1–30 body rows.")
                block.update(role=role, header_role=header_role, columns=[], rows=[],
                             row_padding=_number(value.get("row_padding", 12), "Row padding", 2, 48, integer=True),
                             rule_color=_color(value.get("rule_color", "#d3d9dd"), "Table rule color"))
                for column in columns:
                    _fields(column, {"text", "width", "align"}, "table column")
                    align = column.get("align", "start")
                    if align not in ("start", "end", "left", "right", "center"):
                        raise RenderError("Unsupported table column alignment.")
                    block["columns"].append({"text": text(column.get("text"), header_role, "Table header"),
                                              "width": _number(column.get("width", 1), "Table column fraction", .1, 10), "align": align})
                for row in rows:
                    if not isinstance(row, list) or len(row) != len(columns):
                        raise RenderError("Each table row must match its column count.")
                    block["rows"].append([text(cell, role, "Table cell") for cell in row])
                    budget["cells"] += len(row)
                    if budget["cells"] > 160:
                        raise RenderError("Composition exceeds 160 table cells.")
            out.append(block)
        return out

    result["blocks"] = blocks(spec.get("blocks"))
    unused = [name for name, parts in texts.items() if not parts]
    if unused:
        raise RenderError(f"Unused typography roles: {', '.join(unused)}. Remove them or use them in a block.")
    return result, texts


def _load_role(catalog, role, text):
    record = catalog.get(role["font_id"])
    axes = dict(role["axes"])
    available = {axis["tag"] for axis in record.get("axes", [])}
    if "weight" in role:
        if "wght" in available:
            if "wght" in axes and axes["wght"] != role["weight"]:
                raise RenderError("Role weight conflicts with its explicit wght axis.")
            axes["wght"] = role["weight"]
        elif record.get("weight", 400) != role["weight"]:
            raise RenderError(f"Exact face {role['font_id']} does not have requested weight {role['weight']}; select the correct style. Synthetic weight is disabled.")
    if "italic" in role:
        if "ital" in available:
            if "ital" in axes and axes["ital"] != int(role["italic"]):
                raise RenderError("Role italic conflicts with its explicit ital axis.")
            axes["ital"] = int(role["italic"])
        elif bool(record.get("italic", False)) != role["italic"]:
            raise RenderError("Exact face does not have the requested italic state; select a real italic face. Synthetic italic is disabled.")
    return _load(catalog, role["font_id"], axes, text)


def _text_mask(asset, text, role, width):
    """Shape, wrap, and retain actual ink at explicitly requested line height."""
    size = role["size"]
    if width < 32:
        raise RenderError("A text column is narrower than 32 pixels; increase the canvas or simplify the layout.")
    lines = []
    for paragraph, value in enumerate(text.split("\n")):
        for line in _wrap(asset, value, size, role["features"], role["direction"], role["language"], width-8):
            line["paragraph"] = paragraph
            lines.append(line)
    extents = asset.font.get_font_extents(role["direction"] or "ltr")
    ascender = max(0, extents.ascender * size / asset.upem) if extents else .8*size
    descender = max(0, -extents.descender * size / asset.upem) if extents else .2*size
    leading = role["line_height"] * size
    bounds, placements = None, []
    for index, line in enumerate(lines):
        advance = abs(line["advance_px"][0])
        if advance > width-8 + .001:
            raise RenderError(f"Unbreakable text exceeds its {width}px column: {line['text'][:70]!r}. Reduce size, widen the column, or insert an explicit newline; no text was clipped.")
        align = role["align"]
        if align == "start":
            align = "right" if line["direction"] == "rtl" else "left"
        if align == "end":
            align = "left" if line["direction"] == "rtl" else "right"
        offset = ((width-8-advance)/2 if align == "center" else width-8-advance if align == "right" else 0) + 4
        line["baseline_px"] = ascender + index*leading
        line["offset_x_px"] = offset
        ink = None
        for glyph in line["glyphs"]:
            key = (size, glyph["glyph_id"])
            if key not in asset.cache:
                asset.cache[key] = _raster_glyph(asset.freetype_face, glyph["glyph_id"], size)
            raster = asset.cache[key]
            if raster is None:
                continue
            mask, left, top = raster
            x = round((offset+glyph["x"])*AA)+left
            y = round((line["baseline_px"]+glyph["y"])*AA)+top
            nonempty = mask.getbbox()
            if nonempty:
                ink = _union(ink, (x+nonempty[0], y+nonempty[1], x+nonempty[2], y+nonempty[3]))
            placements.append((mask, x, y))
        bounds = _union(bounds, ink)
        line["ink_bounds_px"] = [round(v/AA, 4) for v in ink] if ink else None
    # A font may have ink that escapes its advances (swashes/negative bearings).
    # Keep it by shifting the origin, but fail if it cannot fit the chosen column.
    logical = (0, 0, width*AA, math.ceil((ascender+descender+(len(lines)-1)*leading)*AA))
    bounds = _union(bounds, logical)
    left, top = math.floor(min(0, bounds[0])), math.floor(min(0, bounds[1]))
    right, bottom = math.ceil(max(width*AA, bounds[2])), math.ceil(bounds[3])
    out_width, out_height = math.ceil((right-left)/AA), math.ceil((bottom-top)/AA)
    if out_width > width:
        raise RenderError(f"Font ink overhang exceeds its {width}px column by {out_width-width}px. Reduce size or choose a wider layout; no ink was clipped.")
    _check_image(out_width, out_height)
    if out_width*out_height*AA*AA > 112_000_000:
        raise RenderError("Text block exceeds the supersampled raster budget; split it into shorter blocks.")
    canvas = Image.new("L", (out_width*AA, out_height*AA), 0)
    for mask, x, y in placements:
        x, y = x-left, y-top
        a, b, c, d = max(0, -x), max(0, -y), min(mask.width, canvas.width-x), min(mask.height, canvas.height-y)
        if c > a and d > b:
            canvas.paste(255, (x+a, y+b, x+c, y+d), mask.crop((a, b, c, d)))
    overlaps = []
    for index in range(1, len(lines)):
        before, after = lines[index-1]["ink_bounds_px"], lines[index]["ink_bounds_px"]
        if before and after and before[3] > after[1]:
            overlaps.append([index-1, index])
    return canvas.resize((out_width, out_height), Image.Resampling.LANCZOS), {
        "text": text, "size_px": size, "line_height_px": leading, "line_count": len(lines),
        "canvas_px": [out_width, out_height], "ink_origin_shift_px": [-left/AA, -top/AA],
        "lines": lines, "ink_vertical_overlap_lines": overlaps, "clipped": False,
    }


class _Layout:
    def __init__(self, spec, assets):
        self.spec, self.assets = spec, assets
        self.draws, self.measurements = [], []

    def sequence(self, blocks, x, y, width, path="blocks"):
        start = y
        for index, block in enumerate(blocks):
            if index:
                y += block["gap"]
            y += self.block(block, x, y, width, f"{path}.{index}")
            if y > 12000:
                raise RenderError("Composition is taller than 12000 pixels; render representative pages separately.")
        return y-start

    def text(self, name, text, x, y, width, path, align=None):
        role = dict(self.spec["roles"][name])
        if align:
            role["align"] = align
        mask, evidence = _text_mask(self.assets[name], text, role, width)
        self.draws.append(("text", (x, y), mask, role["color"]))
        evidence.update(role=name, block_path=path, position_px=[x, y], width_px=width,
                        font_id=role["font_id"], align=role["align"])
        self.measurements.append(evidence)
        return mask.height

    def block(self, block, x, y, width, path):
        kind = block["type"]
        if kind == "text":
            return self.text(block["role"], block["text"], x, y, width, path)
        if kind == "spacer":
            return block["height"]
        if kind == "rule":
            self.draws.append(("rect", (x, y, x+width-1, y+block["thickness"]-1), None, block["color"]))
            return block["thickness"]
        if kind == "panel":
            padding = block["padding"]
            position = len(self.draws)
            height = self.sequence(block["blocks"], x+padding, y+padding, width-2*padding, path+".blocks") + 2*padding
            self.draws.insert(position, ("rect", (x, y, x+width-1, y+height-1), None, block["background"]))
            return height
        if kind == "columns":
            columns, gutter = block["columns"], block["gap"]
            widths = _widths(width-gutter*(len(columns)-1), [c["width"] for c in columns])
            heights = []
            for index, (column, cell_width) in enumerate(zip(columns, widths)):
                heights.append(self.sequence(column["blocks"], x, y, cell_width, f"{path}.columns.{index}.blocks"))
                x += cell_width+gutter
            return max(heights)
        if kind == "table":
            start, padding = y, block["row_padding"]
            widths = _widths(width, [c["width"] for c in block["columns"]])
            rows = [[c["text"] for c in block["columns"]]] + block["rows"]
            for index, row in enumerate(rows):
                cell_x, heights = x, []
                role = block["header_role"] if index == 0 else block["role"]
                for cell, (value, cell_width) in enumerate(zip(row, widths)):
                    heights.append(self.text(role, value, cell_x+padding, y+padding, cell_width-2*padding,
                                             f"{path}.rows.{index}.{cell}", block["columns"][cell]["align"]))
                    cell_x += cell_width
                y += max(heights)+2*padding
                self.draws.append(("rect", (x, y, x+width-1, y), None, block["rule_color"]))
                y += 1
            return y-start
        raise AssertionError(kind)


def _widths(total, ratios):
    result, allocated = [], 0
    denominator = sum(ratios)
    for index, ratio in enumerate(ratios):
        width = total-allocated if index == len(ratios)-1 else math.floor(total*ratio/denominator)
        result.append(width)
        allocated += width
    return result


def _implementation(spec, assets):
    """Generate scoped exact-face declarations; do not copy or expose sources."""
    css = ["/* Stage only authorized exact assets at the URLs below. No fonts are bundled. */",
           "/* Recheck layout/rasterization in your browser; this is an implementation recipe. */",
           ".te-recipe { margin: 0; }",
           ".te-status { font: 16px/1.5 system-ui,sans-serif; padding: 20px; overflow-wrap: anywhere; }",
           ".te-composition, .te-composition * { box-sizing: border-box; }",
           f".te-composition {{ margin: 0 auto; width: {spec['width']}px; max-width: 100%; padding: {spec['padding']}px; background: {spec['background']}; min-height: {spec['min_height']}px; }}",
           ".te-text { margin: 0; white-space: pre-wrap; overflow-wrap: normal; font-synthesis: none; }",
           ".te-columns { display: grid; grid-template-columns: var(--te-column-tracks); }",
           ".te-table-scroll { max-width: 100%; overflow-x: auto; }",
           ".te-scroll-hint { display: none; margin: 0 0 8px; font: 12px/1.4 system-ui,sans-serif; color: inherit; }",
           ".te-table-group[data-overflow] > .te-scroll-hint { display: block; }"]
    recipes, unsupported = {}, []
    for name, role in spec["roles"].items():
        asset = assets[name]
        with Path(asset.resolution["path"]).open("rb") as source:
            signature = source.read(4)
        suffix = {b"wOFF": "woff", b"wOF2": "woff2"}.get(signature)
        if suffix is None:
            suffix = "otf" if "CFF " in asset.outline_tables or "CFF2" in asset.outline_tables else "ttf"
        weight = asset.axes.get("wght", asset.record.get("weight", 400))
        italic = bool(asset.axes.get("ital", asset.record.get("italic", False)))
        slant = asset.axes.get("slnt", 0)
        style = "italic" if italic else (f"oblique {-slant:g}deg" if slant else "normal")
        alias = f"te-{asset.resolution['sha256'][:16]}-{asset.resolution.get('face_index', 0)}-{name}"
        url = f"assets/{asset.resolution['sha256']}.{suffix}"
        application_supported = int(asset.resolution.get("face_index", 0)) == 0 and signature != b"ttcf"
        if not application_supported:
            unsupported.append(name)
        # A TTC face must be deliberately extracted and re-verified. Do not claim
        # src:url(...ttf) would select an indexed collection member.
        if application_supported:
            css.append(f'@font-face {{ font-family: "{alias}"; src: url("{url}"); font-weight: {weight:g}; font-style: {style}; font-display: block; }}')
        else:
            css.append(f"/* Role {name}: collection face {asset.resolution.get('face_index', 0)} requires explicit extraction and a new verified standalone asset before defining @font-face. */")
        features = ", ".join(f'"{tag}" {value}' for tag, value in role["features"].items()) or "normal"
        variations = ", ".join(f'"{tag}" {value:g}' for tag, value in asset.axes.items()) or "normal"
        settings = {"font-family": f'"{alias}"', "font-size": f"{role['size']}px", "line-height": str(role["line_height"]),
                    "font-weight": f"{weight:g}", "font-style": style, "font-synthesis": "none",
                    "font-feature-settings": features, "font-variation-settings": variations,
                    "font-optical-sizing": "none", "color": role["color"], "text-align": role["align"]}
        if role["direction"]:
            settings["direction"] = role["direction"]
        else:
            settings["unicode-bidi"] = "plaintext"
        css.append(f".te-role-{name} {{ " + "; ".join(f"{key}: {value}" for key, value in settings.items()) + "; }")
        recipes[name] = {"exact_id": role["font_id"], "sha256": asset.resolution["sha256"], "face_index": asset.resolution.get("face_index", 0),
                         "asset_url": url if application_supported else None, "css_family_alias": alias, "settings": settings,
                         "language": role["language"], "direct_webfont_recipe_supported": application_supported,
                         "source_asset_not_copied": True}
    mobile_padding = min(spec["padding"], 24)
    css.extend(["@media (max-width: 640px) {",
                f"  .te-composition {{ padding: {mobile_padding}px; min-height: 0; }}",
                "  .te-columns { grid-template-columns: 1fr; }",
                "  .te-text { overflow-wrap: break-word; }"])
    mobile_sizes = {}
    for name, role in spec["roles"].items():
        if role["size"] > 48:
            value = f"clamp(32px, 12vw, {min(role['size'], 64)}px)"
            css.append(f"  .te-role-{name} {{ font-size: {value}; }}")
            mobile_sizes[name] = value
    css.append("}")
    escape = lambda value: html.escape(str(value), quote=True)

    def markup(blocks):
        output = []
        for index, block in enumerate(blocks):
            margin = block["gap"] if index else 0
            style = f"margin-top:{margin}px"
            kind = block["type"]
            if kind == "text":
                role, content = block["role"], escape(block["text"])
                language = escape(spec["roles"][role]["language"])
                direction = spec["roles"][role]["direction"]
                output.append(f'<div class="te-text te-role-{role}" lang="{language}" dir="{direction or "auto"}" style="{style}">{content}</div>')
            elif kind == "rule":
                output.append(f'<div style="{style};height:{block["thickness"]}px;background:{block["color"]}"></div>')
            elif kind == "spacer":
                output.append(f'<div style="{style};height:{block["height"]}px"></div>')
            elif kind == "panel":
                output.append(f'<div style="{style};background:{block["background"]};padding:{block["padding"]}px">{markup(block["blocks"])}</div>')
            elif kind == "columns":
                widths = " ".join(f'{column["width"]}fr' for column in block["columns"])
                columns = "".join(f'<div style="min-width:0">{markup(column["blocks"])}</div>' for column in block["columns"])
                output.append(f'<div class="te-columns" style="{style};--te-column-tracks:{widths};gap:{block["gap"]}px">{columns}</div>')
            elif kind == "table":
                denominator = sum(column["width"] for column in block["columns"])
                cols = "".join(f'<col style="width:{100*column["width"]/denominator:g}%">' for column in block["columns"])
                rows = []
                for row_index, row in enumerate([[column["text"] for column in block["columns"]]]+block["rows"]):
                    role = block["header_role"] if row_index == 0 else block["role"]
                    language = escape(spec["roles"][role]["language"])
                    direction = spec["roles"][role]["direction"] or "auto"
                    tag, scope = ("th", ' scope="col"') if row_index == 0 else ("td", "")
                    cells = "".join(f'<{tag}{scope} class="te-text te-role-{role}" lang="{language}" dir="{direction}" style="padding:{block["row_padding"]}px;text-align:{column["align"]};vertical-align:top;border-bottom:1px solid {block["rule_color"]}">{escape(value)}</{tag}>' for value, column in zip(row, block["columns"]))
                    rows.append(f"<tr>{cells}</tr>")
                minimum = max(480, len(block["columns"])*140)
                output.append(f'<div class="te-table-group" style="{style};color:{spec["roles"][block["role"]]["color"]}"><p class="te-scroll-hint">Scroll horizontally to see every column.</p><div class="te-table-scroll" tabindex="0" role="region" aria-label="Scrollable data table"><table style="width:100%;min-width:{minimum}px;table-layout:fixed;border-collapse:collapse"><colgroup>{cols}</colgroup>{"".join(rows)}</table></div></div>')
        return "\n".join(output)

    warning = "Stage the exact authorized assets at the CSS URLs and serve this directory over localhost HTTP. The composition stays hidden until every font has been hash-verified and loaded."
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; font-src 'self'; base-uri 'none'"><title>{escape(spec['title'])} — application recipe</title><link rel="stylesheet" href="application.css"><script src="application.js" defer></script></head><body class="te-recipe"><p id="te-asset-status" class="te-status" role="status">{warning}</p><main class="te-composition" hidden>{markup(spec['blocks'])}</main></body></html>'''
    javascript = "const typeEvidenceRoles = " + json.dumps(recipes, ensure_ascii=True) + ";\n" + r'''
(async () => {
  const status = document.getElementById("te-asset-status");
  try {
    if (!window.crypto?.subtle) throw new Error("SHA-256 verification requires a secure context such as localhost HTTP.");
    const assets = new Map();
    for (const role of Object.values(typeEvidenceRoles)) {
      if (!role.direct_webfont_recipe_supported) throw new Error("A collection face needs explicit extraction and re-verification before browser use.");
      if (!assets.has(role.asset_url)) assets.set(role.asset_url, (async () => {
        const response = await fetch(role.asset_url, {credentials: "omit"});
        if (!response.ok) throw new Error("Exact font asset is missing: " + role.asset_url);
        const bytes = await response.arrayBuffer();
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
        if (hash !== role.sha256) throw new Error("Font hash mismatch: " + role.asset_url);
        return bytes;
      })());
      const face = new FontFace(role.css_family_alias, await assets.get(role.asset_url), {
        weight: role.settings["font-weight"], style: role.settings["font-style"],
        variationSettings: role.settings["font-variation-settings"],
        featureSettings: role.settings["font-feature-settings"]
      });
      await face.load();
      document.fonts.add(face);
    }
    await document.fonts.ready;
    document.querySelector(".te-composition").hidden = false;
    const updateOverflowHints = () => document.querySelectorAll(".te-table-scroll").forEach(region => {
      region.parentElement.toggleAttribute("data-overflow", region.scrollWidth > region.clientWidth + 1);
    });
    updateOverflowHints();
    window.addEventListener("resize", updateOverflowHints);
    status.textContent = "Exact font assets verified and loaded. Inspect this browser's actual layout and rasterization before release.";
  } catch (error) {
    status.textContent = "Composition hidden to prevent font substitution. " + error.message + " Stage the authorized exact files and serve this folder over localhost HTTP. The verified PNG preview remains available in index.html.";
  }
})();
'''
    return "\n".join(css)+"\n", document, javascript, {"roles": recipes, "collection_roles_requiring_extraction": unsupported,
            "status": "requires assets and target-environment validation", "files": ["application.css", "application.html", "application.js"],
            "browser_asset_gate": "Composition hidden until SHA-256 verification and FontFace loading succeed for every role; no fallback preview on failure.",
            "responsive_layout": {"canvas": "PNG uses the exact requested width; the browser recipe adapts to its viewport.",
                                  "breakpoint_px": 640, "mobile_padding_px": mobile_padding,
                                  "columns": "stack into one column at or below the breakpoint", "tables": "keyboard-focusable horizontal scroll region with a visible hint only when overflowing",
                                  "interface_labels": "Status and scroll hints use a separate system UI font; project content uses verified role faces.",
                                  "mobile_role_font_sizes": mobile_sizes, "font_ids_axes_features": "unchanged"},
            "instructions": ["Resolve each exact_id immediately before staging authorized font assets at its asset_url. Check the expected SHA-256. Fonts are not copied by compose.",
                             "Use the scoped CSS family aliases, explicit axes/features and font-synthesis:none; do not substitute a similarly named family.",
                             "Inspect the implementation at its actual viewport, zoom, content, language, and device. The live layout recomputes line breaks and may differ from this unhinted preview.",
                             "For collection faces, explicitly extract the selected face if permitted, index and verify the standalone derivative, then regenerate the recipe. Do not point a TTF URL at a TTC."]}


def _preview_html(spec, manifest):
    escape = lambda value: html.escape(str(value), quote=True)
    rows = "".join(f'<tr><td>{escape(name)}</td><td>{escape(font["family"])} / {escape(font["style"])}</td><td>{font["size_px"]} px / {font["line_height_px"]:g} px</td><td>{escape(json.dumps(font["axes"]))}</td></tr>' for name, font in manifest["roles"].items())
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; base-uri 'none'"><title>{escape(spec['title'])}</title><style>body{{margin:0;background:#e8e9e7;color:#1a252d;font:15px/1.5 system-ui,sans-serif}}main{{max-width:1280px;margin:auto;padding:32px 24px 64px}}h1{{font-size:24px;font-weight:600;margin:0 0 12px}}nav{{display:flex;gap:24px;flex-wrap:wrap;margin-bottom:24px}}a{{color:inherit}}img{{max-width:100%;height:auto;display:block;box-shadow:0 1px 10px #0002}}table{{border-collapse:collapse;margin:28px 0;width:100%}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #bcc3c3}}p{{max-width:90ch}}code{{overflow-wrap:anywhere}}@media(max-width:600px){{main{{padding:20px 12px}}table{{font-size:12px}}td,th{{padding:5px}}}}</style></head><body><main><h1>{escape(spec['title'])}</h1><nav><a href="composition.png">Inspect PNG at 100%</a><a href="spec.json">Revise composition spec</a><a href="manifest.json">Exact settings and measurements</a><a href="application.css">Implementation CSS</a></nav><img src="composition.png" width="{manifest['canvas_px'][0]}" height="{manifest['canvas_px'][1]}" alt="{escape(spec['title'])}; contextual typography rendered from exact selected fonts"><table><thead><tr><th>Role</th><th>Selected face</th><th>Size / line height</th><th>Axes</th></tr></thead><tbody>{rows}</tbody></table><p>The composition above uses only the selected exact fonts. This page's controls and table use a separate system UI font. The PNG previews unhinted outline rasterization; inspect the final browser, printer, or engine before release.</p><p>Change IDs or role settings in <code>spec.json</code> and compose to a new directory to compare alternatives. One family for every role is supported. Assets are not bundled in the implementation recipe.</p></main></body></html>'''


def compose(catalog, spec: dict, output: Path) -> dict:
    """Render a complete contextual page/screen from a compact revisable spec.

    Supported block types: text, rule, spacer, columns, panel and table. Templates
    editorial/interface/poster provide defaults, not a prescribed aesthetic.
    Role font_id is always an exact catalog ID; weight/italic requests must be
    satisfied by the selected face or its explicit supported variation axes.
    All text is validated and all assets loaded before creating any outputs.
    """
    spec, texts = _normalize(copy.deepcopy(spec))
    assets = {name: _load_role(catalog, role, "\n".join(texts[name])) for name, role in spec["roles"].items()}
    layout = _Layout(spec, assets)
    padding, width = spec["padding"], spec["width"]
    height = max(spec["min_height"], layout.sequence(spec["blocks"], padding, padding, width-2*padding)+2*padding)
    _check_image(width, height)
    image = Image.new("RGB", (width, height), spec["background"])
    draw = ImageDraw.Draw(image)
    for kind, position, mask, color in layout.draws:
        if kind == "text":
            image.paste(color, position, mask)
        else:
            draw.rectangle(position, fill=color)
    css, implementation_html, implementation_js, recipe = _implementation(spec, assets)
    roles = {}
    for name, asset in assets.items():
        role = spec["roles"][name]
        roles[name] = {"id": role["font_id"], "family": asset.record.get("family", "(unnamed)"),
                       "style": asset.record.get("style", ""), "sha256": asset.resolution["sha256"],
                       "face_index": asset.resolution.get("face_index", 0), "size_px": role["size"],
                       "line_height_px": role["size"]*role["line_height"], "color": role["color"],
                       "axes": asset.axes, "axis_value_sources": asset.axis_source, "features": role["features"],
                       "language": role["language"], "direction": role["direction"] or "inferred per line",
                       "coverage": asset.coverage, "glyph_zero_count": 0, "asset_verified": True,
                       "provenance": asset.resolution.get("provenance", asset.record.get("origins", [])),
                       "rights": asset.resolution.get("rights", asset.record.get("rights", {"status": "unknown"}))}
    warnings = [{"block_path": block["block_path"], "kind": "line-ink-overlap", "line_pairs": block["ink_vertical_overlap_lines"],
                 "action": "Inspect the actual line spacing; increase role.line_height if overlap is unintended."}
                for block in layout.measurements if block["ink_vertical_overlap_lines"]]
    manifest = {"schema_version": 1, "kind": "exact-font-composition", "title": spec["title"], "template": spec["template"],
                "medium": spec["medium"], "canvas_px": [width, height], "roles": roles,
                "renderer": {"backend": "HarfBuzz shaping + native FreeType unhinted outline rasterization", "harfbuzz": hb.version_string(),
                             "freetype": ".".join(map(str, freetype.version())), "supersampling": AA, "system_font_lookup": False},
                "no_fallback": {"verified": True, "glyph_zero_count": 0, "font_synthesis": False},
                "measurements": layout.measurements, "warnings": warnings, "implementation": recipe,
                "limitations": ["Contextual PNGs show this unhinted renderer, not browser, OS, printer, or game-engine equivalence.",
                                "Whitespace wrapping preserves text; hyphenation, full Unicode line breaking, bidi paragraphs, color fonts, and vertical writing are unsupported.",
                                "Print-preview describes a pixel layout; no physical dimensions, ICC color profile, or printer calibration is implied.",
                                "CSS/HTML use exact scoped font aliases and settings but require authorized local asset staging and target-environment verification. Collection faces require explicit extraction.",
                                "Geometry is measured; visual suitability and pairing quality require inspecting the composition in the project's context."],
                "outputs": {"composition": "composition.png", "html": "index.html", "manifest": "manifest.json", "spec": "spec.json",
                            "css": "application.css", "application_html": "application.html", "application_js": "application.js"}, "images": []}
    output = Path(output)
    if output.is_symlink() or output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise RenderError("Output directory must be absent or empty and not a symlink; preserve previous composition evidence.")
    output.mkdir(parents=True, exist_ok=True)
    manifest["images"].append(_write_png(image, output/"composition.png"))
    for name, content in (("spec.json", json.dumps(spec, indent=2, ensure_ascii=False)+"\n"),
                          ("application.css", css), ("application.html", implementation_html), ("application.js", implementation_js),
                          ("index.html", _preview_html(spec, manifest))):
        (output/name).write_text(content, encoding="utf-8")
    manifest["file_sha256"] = {name: _digest((output/name).read_bytes()) for name in ("spec.json", "application.css", "application.html", "application.js", "index.html")}
    (output/"manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return manifest
