# Agent integration

Start with [AGENTS.md](../AGENTS.md). Keep the catalog outside the agent's context: request a few candidates, inspect exact finalists, render real copy and revise the composition. The CLI and MCP adapter call the same operations; neither requires a particular agent model or editor.

## Local setup and MCP

[README setup](../README.md#get-started) creates the catalog. For rendered-content discovery, install `.[visual]`, run `visual-setup`, then `visual-index`. These are explicit local setup operations. The MCP server does not download sources or model weights.

Use absolute paths because clients may start processes in a different directory:

```json
{
  "mcpServers": {
    "type-evidence": {
      "command": "/absolute/path/type-evidence/.venv/bin/type-evidence",
      "args": ["--catalog", "/absolute/path/type-evidence/library/catalog.sqlite", "mcp", "--out", "/absolute/path/type-evidence/library/comparisons"]
    }
  }
}
```

On Windows, use `C:\\path\\type-evidence\\.venv\\Scripts\\type-evidence.exe` as `command`. Native Windows end-to-end verification remains outstanding; path materialization and protocol behavior have tests, and macOS runtime evidence is recorded separately.

| Task | CLI | MCP |
| --- | --- | --- |
| Search, page, refine, reference image | `search` | `font_search` |
| Exact metadata / verified asset | `inspect`, `resolve` | `font_inspect`, `font_resolve` |
| Observed sibling styles and versions | `family` | `font_family` |
| Exact specimen / contextual layout | `compare`, `compose` | `font_compare`, `font_compose` |
| Existing project typography hints | `project` | `font_project` |
| Catalog / bounded issues / visual coverage | `stats`, `issues`, `visual-status` | `font_stats`, `font_issues`, `font_visual_status` |
| Reopen generated PNG | Open returned local PNG | `font_image` |
| Fetch, index, add source, model setup | Explicit CLI commands | Intentionally outside MCP |

The adapter uses newline-delimited stdio JSON-RPC and supports protocol versions 2024-11-05, 2025-03-26 and 2025-06-18. Initialize, send `notifications/initialized`, then call tools. It opens no network port. Rendering writes unique directories under `--out`; project inspection reads only the explicitly supplied root. Client process/filesystem permissions remain the client's responsibility.

## A brief that can be acted on

This is a complete `font_search` input. For CLI use, save it as JSON and pass `--brief`. Saved `visual` and `reference_image` settings are supported; explicit CLI flags override them.

```json
{
  "role": "ui",
  "query": "warm humanist, not playful or handwritten",
  "text": "Review 24 requests · 1,024 records",
  "weight": 400,
  "italic": false,
  "required_styles": [
    {"weight": 400, "italic": false},
    {"weight": 600, "italic": false}
  ],
  "size": 15,
  "density": "dense",
  "audience": "staff reviewing a busy service queue",
  "medium": "desktop dashboard with numeric tables",
  "tone": "calm, capable and approachable",
  "hierarchy": "table labels, body text and section headings",
  "language": "en",
  "surroundings": "quiet neutral colors, compact rows, restrained icons",
  "limit": 6,
  "visual": "auto"
}
```

`text`, weight, italic state, exact family/style and required companions are hard constraints. Size, density, some audience wording, numeric content/medium and hierarchy apply small labeled measurement/metadata preferences. `query` and `tone` also feed learned appearance retrieval when active. Actual text selects the visual sample script, and `language` helps resolve Han-script locales. Language and surroundings also guide the composition; they do not certify complete language support or design fit. Use a language tag such as `en`, `ar` or `zh-Hant` and carry it into rendering.

Read `query_interpretation` to see positive/negative aliases, unmodeled terms and negation scope. Read `visual_retrieval` to learn whether FontCLIP was actually used, which model and sample coverage apply, and whether auto mode fell back. Learned scores are relative resemblance values, not probabilities or design grades. A hard `category` filter matches declared metadata; leave it unset when exploring fonts whose categories may be unknown.

## Search the writing system you will use

Build a separate script index when the project needs it:

```sh
type-evidence visual-index --script Arabic
type-evidence search --query 'calm restrained' --role body --language ar --text 'رحلة عبر المدينة' --visual on --limit 4
```

Other script options are `Greek`, `Cyrillic`, `Devanagari`, `Japanese`, `Chinese`, `ChineseTraditional`, `Hebrew`, `Ethiopic`, `Bengali`, `Tamil`, `Korean` and `Thai`. A configured sample may have no eligible fonts; read the build report rather than assuming coverage. Each index pins the sample text and shaping language as well as the model.

Search detects the non-Latin writing system from the actual text. For Han-only copy, use `ja` for Japanese, `ko` for Korean, or `zh-Hant`/`zh-TW`/`zh-HK` for Traditional Chinese; otherwise the Chinese sample applies. A missing supported index yields its exact build command: `visual:on` fails explicitly, while auto mode retains metadata/measurement discovery. A script without a configured sample is identified as unsupported instead of recommending an invalid command. Latin glyph similarity is not substituted for these requests.

Inspect the requested script at the actual size and settings. The embedding represents its recorded sample at default axes, not every glyph, all orthographies or a readability evaluation.

## Recover from a weak first result

Inspect the initial options in a shared-text comparison. If the direction is useful, keep the brief fixed and use `pagination.next_offset` for distinct family alternatives. If the actual letterforms miss the intent, select an existing font or a typography crop that expresses the desired direction, then make a reference-led pass. Clear the failed `query` and `tone` for this first pass, retain the real text and required styles, and keep the eligible current font as `existing_id`. Reset `offset` to 0 whenever the brief changes.

For example, find and inspect a narrow technical anchor, then use either its exact ID or a crop dominated by the intended typography. Replace `ANCHOR_ID` and `BASELINE_ID` with verified IDs:

```sh
type-evidence search --family 'Rajdhani' --text 'Review 24 requests' --weight 400 --upright --visual off --limit 4
type-evidence inspect ANCHOR_ID
type-evidence search --similar-to ANCHOR_ID --existing-id BASELINE_ID --role ui --text 'Review 24 requests' --weight 400 --upright --visual on --limit 4
type-evidence search --reference-image /absolute/path/type-crop.png --existing-id BASELINE_ID --role ui --text 'Review 24 requests' --weight 400 --upright --visual on --limit 4
type-evidence compare BASELINE_ID CANDIDATE_ID_1 CANDIDATE_ID_2 --text 'Review 24 requests' --sizes 15 24 48 --out library/reference-study
```

Use one reference route per first pass, inspect its results, and refine the selected direction. A reference supplies an explicit visual preference; it is not evidence that the original semantic query succeeded. In the [recorded recovery study](../evidence/v0.2/retrieval-recovery/README.md), references produced more relevant letterforms while extra negations and `avoid_like` sometimes returned unrelated faces or pictograms. Do not keep adding negatives blindly. These controls remain useful when a rendered comparison confirms the change:

- `similar_to: "EXACT_ID"` for neighbors, or `avoid_like: "EXACT_ID"` to move away from a reference.
- `exclude_families: ["Family A", "Family B"]` to leave entire families out; `exclude` operates on exact IDs.
- `reference_image: "/absolute/path/type-crop.png"` for learned visual resemblance. Prefer a crop dominated by the typography, since the image model also sees composition and decoration.
- `existing_id: "EXACT_ID"` to retain the current font, with explicit reasons if constraints reject it.

With learned retrieval disabled or absent, neighbor refinement uses at least two measured proportions and says so. It does not pretend to recognize the reference's personality. With a partial visual index, faces lacking embeddings remain eligible and show that evidence gap.

A text description cannot settle pairing. Compare 2–4 finalists with shared text/settings, then use `font_compose` with a small role/block spec from [the examples](../examples/). Copy `required_axes` to the appropriate comparison ID or composition role. Inspect the image, change a role's face, size, leading or copy, then render again. A retained baseline or one family with real companion styles can win.

## Images and bounded context

`font_compare` and `font_compose` return a compact JSON summary plus one inline PNG by default. Set `include_image:false` for text-only responses. Images are resized to fit 1440 × 1800 for transport; inspect the saved original at 100% when judging small text. Full glyph geometry, hashes, provenance and implementation details remain in `manifest_path` rather than filling the tool response.

Call `font_image` with the returned relative `preview_image`, such as `OUTPUT_ID/composition.png`, to reopen it. The tool accepts only PNGs contained in the configured output directory. CLI users open the generated local PNG or `index.html` directly.

The composition's `application.html` is a separate live implementation recipe. It stays hidden until each staged asset passes its SHA-256 check and loads through the browser FontFace API. `index.html` is the immediate, font-free preview. The live recipe still needs inspection in the actual product viewport and rendering environment.

## Python use

Use the shared operation for CLI/MCP-equivalent retrieval:

```python
from pathlib import Path
from type_evidence.catalog import Catalog
from type_evidence.operations import discover
from type_evidence.composition import compose

catalog = Catalog("library/catalog.sqlite")
try:
    result = discover(catalog, {
        "query": "restrained humanist, not decorative",
        "role": "ui", "text": "Review 24 requests",
        "weight": 400, "italic": False, "size": 15, "limit": 4,
    }, visual="auto")
    choice = result["candidates"][0]  # A candidate to inspect, not an automatic winner.
    compose(catalog, {
        "template": "interface",
        "roles": {"body": {"font_id": choice["id"], "axes": choice["required_axes"], "size": 15}},
        "blocks": [{"role": "body", "text": "Review 24 requests"}],
    }, Path("library/first-context"))
finally:
    catalog.close()
```

`discovery.search` is the lower-level deterministic ranker and accepts optional precomputed visual evidence. `operations.discover` selects and reports the retrieval mode. See [the API contract](contract.md) for bounds and composition fields.

Protocol tests cover the [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports), tools, images and CLI/MCP operations. They do not establish compatibility with every hosted agent or editor.
