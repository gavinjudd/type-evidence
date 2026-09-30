# Type Evidence

Discover fonts by their actual letterforms, explore alternatives, and try them together in the work. Type Evidence gives AI agents a broad local font catalog, optional FontCLIP visual retrieval, exact-font specimens, and contextual compositions with implementation recipes.

The collection preserves the original mixed open/proprietary sources and adds pinned selections from Google Fonts and Arrow Type. Fonts, model weights and large indexes stay local. Project text and reference images are not sent to a service.

## Get started

Python 3.10+ and Git are required. Allow roughly 6 GB for the source collections, plus space for indexes and optional visual dependencies. The core workflow has been exercised on macOS; native Windows verification remains outstanding.

```sh
git clone https://github.com/gavinjudd/type-evidence.git
cd type-evidence
```

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/type-evidence fetch
.venv/bin/type-evidence index
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\type-evidence.exe fetch
.\.venv\Scripts\type-evidence.exe index
```

Activate the venv or use its executable path for the commands below. Fetch uses the full commits and selected-file hashes in [sources.lock.json](sources.lock.json); it preserves existing modified checkouts. Windows acquisition maps incompatible upstream filenames to safe local paths while retaining their original names in provenance.

### Enable visual discovery

Visual retrieval searches rendered font content, including faces with unknown category metadata. Install it once, explicitly download the approximately 653 MB pinned checkpoint, then build the local index:

```sh
python -m pip install -e '.[visual]'
type-evidence visual-setup
type-evidence visual-index
type-evidence visual-status
```

`visual-index` starts with family representatives, commits progress incrementally, and resumes when rerun. CPU is the default; `--device mps` or `--device cuda` can use an available accelerator. `--limit 500` is a bounded first pass. The status report separates stored vectors, current catalog coverage and failures; a partial index is usable, and unindexed fonts remain eligible for ordinary discovery.

Search never downloads a model. `--visual auto` uses the local index for aesthetic queries, tone or references when available and reports its actual retrieval mode. `--visual on` requires working visual retrieval; `--visual off` gives a reproducible metadata/measurement baseline. A supplied reference image requires visual retrieval.

For another writing system, build its sample index, for example `type-evidence visual-index --script Arabic`. Search chooses from the actual project text, with the language tag resolving Han-script locales. A missing script index produces an explicit setup suggestion or metadata fallback; Latin letterforms are not used as a substitute. See the [Arabic example and script options](docs/agents.md#search-the-writing-system-you-will-use).

## Find, inspect, revise, apply

```sh
type-evidence project /path/to/project
type-evidence search --query 'warm humanist, not playful or handwritten' --role ui --text 'Review 24 requests' --weight 400 --upright --size 15 --density dense --limit 6
type-evidence search --query 'warm humanist, not playful or handwritten' --role ui --text 'Review 24 requests' --weight 400 --upright --size 15 --density dense --limit 6 --offset 6
type-evidence search --similar-to EXACT_ID --avoid-like OTHER_ID --text 'Review 24 requests' --limit 6
type-evidence family EXACT_ID
type-evidence compare ID1 ID2 --text-file project-copy.txt --sizes 15 24 48 --out library/first-comparison
```

Use the returned `pagination.next_offset` to explore further with the same brief. Use `--exclude-families 'Family A' 'Family B'` to leave a direction behind. `--reference-image /path/type-crop.png` explores visual resemblance to a typography crop. `--family 'Exact Family Name'` is a hard lookup; `--query` may return alternatives when a name is missing. Auto mode keeps an exact embedded-name query on the name-lookup path. JSON briefs also capture audience, medium, tone, language, hierarchy and surroundings. [Agent integration](docs/agents.md) explains which fields affect ranking and which guide the final composition.

Inspect the actual images. Search returns a starting set with labeled reasons, interpreted negation, required variation axes and evidence gaps. A familiar baseline can be retained with `existing_id`; using one family is a valid result.

### Try the typography in context

```sh
type-evidence compose --spec examples/composition-editorial.json --out library/editorial-study
type-evidence compose --spec examples/composition-interface.json --out library/interface-study
type-evidence compose --spec examples/composition-poster.json --out library/poster-study
```

Open each output's `index.html` or `composition.png`. These examples are editable starting layouts, not recommended fonts for every brief. Replace exact IDs and role settings in `spec.json`, revise the copy or layout, and compose into a new directory. Columns, tables, panels and explicit hierarchy let pairs be judged together at intended sizes.

Each composition also produces `application.css`, `application.html` and `application.js`. The recipe names exact assets and applies their real styles, axes, features and line heights. Fonts are not copied. Stage authorized files at the listed asset URLs, serve the folder over localhost HTTP, and inspect it in the target browser. The page stays hidden until every asset passes SHA-256 verification and font loading; missing files cannot silently become a fallback preview. Collection faces require an explicit standalone derivative before browser use.

Immediately before integrating a selection:

```sh
type-evidence resolve EXACT_ID
```

Resolution returns a verified file path, face index, SHA-256 and provenance. Both specimens and compositions reject missing glyphs rather than substitute another face. Their PNGs are unhinted rendering evidence; the final application still needs its own visual check.

## Use from an agent

Read [AGENTS.md](AGENTS.md) for the bounded decision loop. The JSON CLI and stdio MCP share discovery, family inspection, project context, exact rendering and composition. MCP returns an inline preview image by default, a compact summary, and a path to the full manifest. It also supports paging, refinement and reopening generated images. [Configure an MCP client](docs/agents.md).

All successful CLI output is JSON; errors use stderr and a nonzero exit status. Place `--catalog /absolute/path/catalog.sqlite` **before** the subcommand. `doctor`, `stats`, `issues` and `visual-status` describe the local environment and scope.

## Read the evidence correctly

| Evidence | What it supports |
| --- | --- |
| Measured | Exact bytes, cmap coverage, sampled proportions, glyph positions, line breaks and rendered output. |
| Declared | Family/style names, weight, axes, feature tags, version and embedded notices; metadata can be wrong. |
| Learned | FontCLIP resemblance between rendered samples, text descriptions or a reference crop; not a quality or readability score. |
| Heuristic | Explicit preferences for role, size, density, hierarchy and known attributes. |
| Judgment | The decision after inspecting the real content and surrounding design. |

Font rights remain separate from aesthetic fit. Unknown rights stay unknown; an embedded open-license notice is evidence to review, not distribution permission. No font binaries or model weights are published in this repository or its review ZIP.

See [architecture](docs/architecture.md), [collection additions](docs/collection-v2.md), [maintenance](docs/maintenance.md) and [versioned evidence](evidence/v0.2/). The FontCLIP adapter has CPU float32 parity evidence against the pinned upstream implementation. This checks the model adapter, not whether its recommendations improve design outcomes. The earlier [v0.1 evaluation](evidence/evaluation.md) is historical and does not evaluate the new visual/composition workflow.

## Development

```sh
python -m pytest -q
```

Regression tests use small synthetic fonts; most need neither the large collections nor the optional model. Corpus experiments and design evaluations are separate from the test suite.
