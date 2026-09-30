# API contract

CLI success responses are JSON. Errors go to stderr and return nonzero. Global `--catalog` precedes the subcommand. MCP uses the same operations, with compact render responses and optional inline image content. Current serialized catalog/search/composition schema versions are recorded in their respective outputs; package version and schema version are distinct.

## Catalog and exact identities

`Catalog(path)` exposes `all()`, `get(id)`, `resolve(id)`, `stats()`, `issues(limit)` and `close()`. Exact IDs are the full source `sha256:face_index`. `resolve` returns `{path, face_index, sha256, id, provenance, rights}` after checking source containment, symlinks and bytes. It can use another verified duplicate origin when one is unavailable. No operation resolves a font by taking the first family-name match.

Font records include identity, family/style/full/PostScript names, vendor/version, weight, width class, italic state, units per em, variation axes (`tag,min,default,max`), feature tags, inclusive cmap ranges, sampled metrics, metadata category, family key, canonical table hash, origins, rights evidence, warnings and render-probe status. Metadata is untrusted font content. Origin paths are relative to their source roots. Category is declared/derived metadata, never a visual-certainty label.

## Discovery

`operations.discover(catalog, brief, visual="auto", reference_image=None) -> dict` is the CLI/MCP entrypoint. `discovery.search(catalog, brief, visual_index=None)` is the lower-level deterministic ranker; it also accepts a list of font records. The optional visual mapping is keyed by exact ID and contains labeled score/description/sample evidence.

| Brief field | Meaning / bound |
| --- | --- |
| `role` | `ui`, `body`, `display`, `code`, `brand`, `game`, `document`; default `ui`. |
| `text` | Actual required characters; at most 20,000 characters. Coverage excludes newline/CR/tab layout controls. |
| `query`, `tone` | Appearance/name preferences, up to 300 characters each; explicit negation polarity is reported. |
| `family`, `style` | Hard exact embedded family/style name; query is not a hard lookup. |
| `weight`, `italic` | Required real weight (1–1000) and boolean slant state; supported variable axes can satisfy them. |
| `required_styles` | Up to 8 `{weight: integer, italic: boolean}` companions in the same family/vendor/version/width group, covering the same text. |
| `min_styles` | Minimum observed distinct face-style count; does not prove the required weights exist. |
| `category` | Hard declared category: `sans`, `serif`, `mono`, `script`, `display`, `unknown`. Leave unset for broad visual exploration. |
| `require_open_evidence` | Optional embedded-notice filter, not legal clearance or an aesthetic score. |
| `limit`, `offset` | 1–20 returned faces (default 6); 0–5000 distinct-alternative offset. |
| `exclude`, `exclude_families` | Up to 1000 exact IDs / 100 literal family names. |
| `existing_id` | Reserve an eligible baseline slot; otherwise return rejection reasons. |
| `similar_to`, `avoid_like` | Exact catalog IDs. Use learned resemblance where available, otherwise proximity across at least two measured proportions. |
| `size`, `density` | Size 6–300 CSS pixels; `comfortable`, `balanced`, or `dense`; modest labeled context preferences. |
| `audience`, `medium`, `hierarchy` | Bounded context strings used by documented small preference rules. |
| `language` | Language tag for script-locale selection and composition handoff; Han-only text distinguishes `ja`, `ko` and Traditional Chinese locales. |
| `surroundings` | Bounded handoff context; does not imply automatic surrounding-design analysis. |

In CLI, `--visual` and `--reference-image` are options separate from the JSON brief. MCP `font_search` accepts `visual` and `reference_image` alongside brief fields and separates them before discovery. `auto` uses applicable configured local visual retrieval, `on` requires it, and `off` disables it. A supplied reference image requires visual retrieval; combining it with `off` is an error. Image files are bounded to 20 MB / 20 million pixels. An otherwise unqualified exact embedded-name query in auto mode uses `name_lookup` rather than semantic scoring.

Responses include candidates, evidence-labeled reasons, required axes, concrete companion resolutions, baseline status, rejection counts, query/context interpretation, refinement method, evidence gaps and `visual_retrieval`. Scores are preference values, never probabilities or a quality/readability measurement. Unknown brief fields are reported as having no effect by the ranker; MCP rejects unsupported top-level arguments.

`pagination.next_offset` counts distinct alternatives excluding the reserved baseline. Preserve the brief and catalog between pages. Changing constraints starts a new exploration at offset 0. At most one normalized family and canonical-content variant appears per page, with equal-score diversity based on available measurements/metadata. Fonts lacking visual embeddings remain eligible without a learned score.

## Visual setup and indexing

`visual.setup_model(directory)` explicitly downloads/checks the pinned FontCLIP checkpoint. `visual.build_index(catalog, output=None, checkpoint=None, limit=None, device="cpu", batch_size=16, progress=None, script=None)` incrementally adds vectors to catalog-adjacent `visual.sqlite` by default, or `visual-SCRIPT.sqlite` for a supplied script. Batch size is 1–64. Devices are `cpu`, `mps`, `cuda`; unavailable acceleration is an error. `limit` bounds newly processed successful/reused faces for a pass. Re-running resumes existing work.

The index configuration fixes the model SHA-256, render version and 512-dimensional shape; script indexes also fix the sample script, text digest and shaping language. Configuration mismatch fails rather than mixing indexes. Each vector records its actual sample script/text/language, axes, source and mask digests, and learned attribute associations. Failures stay explicit. Search uses the catalog-adjacent index selected from actual non-Latin text plus the Han locale language tag, and `models/fontclip-original.pt`. Custom build paths are intended for explicit Python use or deliberate placement before CLI search.

A missing script index yields the supported `visual-index --script SCRIPT` command, never Latin similarity as a replacement. In `on` mode it fails; auto mode retains metadata discovery with status. Scripts without a configured sample produce an unsupported-script explanation. [Configured script names](agents.md#search-the-writing-system-you-will-use) do not imply that the current corpus contains an eligible face for every sample.

`operations.visual_status(catalog)` reports the default index's availability, stored/current/stale vectors and last completed build report. During a running build, a stored count can advance beyond that report; it is not a completion claim. Script-specific coverage appears in that script's build and search reports. `visual.scores` excludes IDs absent from the current catalog and reports indexed/unindexed eligible current faces. Search never downloads a model.

## Exact specimens

`render.compare(catalog, ids, text, output, sizes=None, **options) -> manifest` accepts 1–12 distinct IDs and 1–6 distinct integer sizes 8–256 px. Default sizes are 16/32/64. Options are `axes`, `features`, `direction`, `language`, `width`; default width is 1440, allowed 600–4096.

Axes can be one tag/value mapping or a mapping from exact IDs to axis mappings. Tags must exist and values must be within the selected face's ranges. Features are global four-character tags, such as `liga`, `-kern`, `ss01=1`, or a tag/integer mapping. Direction is `ltr`/`rtl` or inferred per line; language is a BCP-47-style tag, default `und`.

Rendering re-verifies source bytes, decodes WOFF in memory when needed, and uses HarfBuzz/FreeType on that exact face. It rejects missing characters, glyph zero and unsupported layout rather than falling back. Text is bounded to 4,000 characters; CRLF/CR normalization is recorded. Outputs are PNGs, escaped local HTML and a manifest containing settings, source/image digests, coverage, glyph positions and renderer versions. Output directories must be absent or empty and cannot be symlinks.

## Contextual compositions

`composition.compose(catalog, spec: dict, output: Path) -> manifest` renders actual roles together. A minimal spec is:

```json
{
  "template": "interface",
  "title": "Queue typography study",
  "width": 1000,
  "roles": {
    "heading": {"font_id": "EXACT_HEADING_ID", "size": 32, "line_height": 1.15},
    "body": {"font_id": "EXACT_BODY_ID", "size": 16, "line_height": 1.5}
  },
  "blocks": [
    {"role": "heading", "text": "Review the queue"},
    {"role": "body", "text": "24 requests need a decision."}
  ]
}
```

Root fields: `template` (`editorial`, `interface`, `poster`), `title`, `medium` (`screen`, `print-preview`), integer `width` (320–2400), `padding` (8–200), `gap` (0–160), `min_height` (0–12000), six-digit hex `background`, `roles` and `blocks`. Templates supply defaults; they do not lock the layout or choice of fonts. Dimensions are pixels, including print-preview.

Provide 1–12 named roles. Each requires an exact `font_id` and may set:

- Integer `size` (8–256), unitless `line_height` (0.85–3), hex `color`.
- Real `weight` (integer 1–1000) / boolean `italic`, validated against the face or supported variable axes; conflicting axis/style requests fail.
- `axes`, global `features`, `language`, `direction`.
- `align`: `start`, `end`, `left`, `right`, `center`.

Role names use lowercase ASCII letters, digits, underscores or hyphens, beginning with a letter. Every declared role must be used. Unknown fields fail with an actionable error.

Blocks are a nonempty sequence. Each may set integer `gap` (0–200), applied before the block except the first in its sequence. For columns, that value is also the column gutter.

| Block | Fields |
| --- | --- |
| `text` (default) | `role` (default `body`), nonempty `text`. |
| `rule` | Optional hex `color`, integer `thickness` 1–16. |
| `spacer` | Integer `height` 0–1000. |
| `columns` | 2–4 `columns`, each with positive relative `width` (0.1–10, default 1) and nested `blocks`. |
| `panel` | Nested `blocks`, hex `background`, integer `padding` 0–100. |
| `table` | `role`, optional `header_role`, 1–8 `columns` with `text`, relative `width`, optional `align`; 1–30 `rows` of matching nonempty string cells; optional `row_padding` 2–48 and hex `rule_color`. |

Bounds are 100 blocks, four nesting levels, 16,000 total characters and 160 body-table cells; individual text values use the specimen text checks. No text column may be narrower than 32 px. Wrapping preserves whitespace and uses actual shaped advances. Unbreakable overflow or ink outside the available column fails without clipping. Tight line height is retained and potential vertical ink overlap appears in warnings.

Outputs:

- `composition.png` and `index.html`: immediate verified raster preview, without embedded fonts.
- `manifest.json`: exact role identities/settings, source and image hashes, glyph/line geometry, warnings and application recipe.
- `spec.json`: normalized, editable layout for the next revision.
- `application.css`, `application.html`, `application.js`: scoped exact-face recipe with local asset URLs; no font copies.

The application loader verifies SHA-256 and successfully loads all requested browser faces before showing the composition. Missing/mismatched assets leave it hidden with an explanation. Serve over localhost HTTP after staging authorized exact files. Collection faces are renderable but need explicit extraction, indexing and regeneration before a standalone webfont recipe is supplied. The browser still recomputes its own layout/rasterization and must be inspected.

The browser recipe adapts its container to the viewport. At 640 px and below it stacks columns, reduces padding to at most 24 px and applies reported fluid sizes to roles larger than 48 px. Dense tables keep readable columns inside a focusable horizontal scroll region, with a hint when more columns are offscreen. `implementation.responsive_layout` records these rules; exact IDs, axes and features stay unchanged. Status/scroll helper labels use a separate system UI face. The PNG always retains the requested fixed canvas and role sizes.

## MCP transport bounds

MCP validates input types and advertised bounds. `font_compare` accepts at most 8 IDs and 4 sizes; `font_compose` accepts one spec. Both return a compact summary and one image by default (`include_image:false` disables it). Full manifests remain on disk. Preview transport fits the original within 1440 × 1800; generated PNG reads are capped at 20 MB and 28 million pixels. `font_image` accepts a contained relative `.png` path, never an arbitrary absolute image path.

MCP messages are bounded to 100,000 characters. Rendering creates unique output directories; read operations do not fetch sources, download weights or install fonts. Source acquisition and model setup remain explicit CLI operations.
