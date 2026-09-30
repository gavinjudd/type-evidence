# Get started with Type Evidence

Type Evidence is an AI font discovery and typography toolkit for real local fonts. Start with a small directory you are authorized to use, then add sources or optional visual retrieval as needed. Nothing installs fonts into the operating system.

[Overview and examples](../README.md) · [MCP setup](agents.md#local-setup-and-mcp) · [Contributor setup](../CONTRIBUTING.md) · [Licensing](licensing.md)

## Install the core toolkit

Python 3.10+ and Git are needed for these steps. Python 3.12 is the version used in the recorded native CI checks. These commands install source and core dependencies, not a font collection or model.

```sh
git clone https://github.com/gavinjudd/type-evidence.git
cd type-evidence
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/type-evidence doctor
```

Windows PowerShell:

```powershell
git clone https://github.com/gavinjudd/type-evidence.git
cd type-evidence
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\type-evidence.exe doctor
```

For the remaining commands, activate the environment (`source .venv/bin/activate` on macOS/Linux, or `.\.venv\Scripts\Activate.ps1` in PowerShell), or continue using the full executable paths above. If PowerShell activation is restricted, use those executable paths; changing system policy is unnecessary. Install from this GitHub source; no PyPI publication is assumed.

## Use fonts you already have

Create a local file `local-sources.json`. Replace `root` with the absolute path to an existing directory containing font files you are authorized to use. JSON uses forward slashes on Windows too, for example `C:/Projects/MyProject/fonts`.

```json
[
  {
    "id": "my-project-fonts",
    "root": "/absolute/path/to/my-project/fonts",
    "url": "",
    "commit": ""
  }
]
```

Keep unknown provenance blank; do not invent an upstream URL or commit. Then run:

```sh
type-evidence index --sources local-sources.json
type-evidence stats
type-evidence search --role ui --text 'Review 24 requests' --weight 400 --upright --visual off --limit 4
```

This builds the default `library/catalog.sqlite` from the fonts you supplied. It does not fetch the full collection or a model. Indexing replaces the catalog's source set with the configuration you provide; include every desired source when rebuilding. If you already have a catalog, preserve it by choosing a new path:

```sh
type-evidence --catalog library-my-project/catalog.sqlite index --sources local-sources.json
type-evidence --catalog library-my-project/catalog.sqlite stats
```

If you choose a custom catalog, include `--catalog` with that same path before every later subcommand, and use that path in the MCP configuration.

A small collection may have no face matching the requested text and styles. Relax a preference or provide another authorized face; do not assume a substitute was used. Read `issues` and result evidence gaps.

## Use the pinned collection

Review [the source selections](collection-v2.md) and [font rights](licensing.md) first. The broad collection mixes open and proprietary/unknown-rights material. Public availability is not a universal use or redistribution license.

```sh
type-evidence fetch
type-evidence index
type-evidence stats
```

Allow roughly **6 GB for the source collections**, plus catalogs, derived assets and optional visual caches. Fetch uses the pinned commits and selected-file hashes in [sources.lock.json](../sources.lock.json), preserves modified checkouts and reports preparation failures. It downloads sources; it does not install system fonts. Windows acquisition maps incompatible upstream names to safe local paths with provenance retained.

Use a short Windows checkout path. Some source archives need a compatible `7z`, `7zz` or libarchive `tar`; absent support is reported, not silently counted as success. See [maintenance](maintenance.md) for adding selected families, refreshing pins, or keeping libraries separate.

## Add optional visual discovery

The core path uses metadata and measured properties. Rendered-content retrieval additionally needs PyTorch/OpenCLIP dependencies, the approximately **653 MB** pinned FontCLIP checkpoint, and a local index for your fonts. Dependency downloads and rendered caches require additional disk space; setup and indexing time depend on hardware and the selected corpus.

```sh
python -m pip install -e '.[visual]'
type-evidence visual-setup
type-evidence visual-index --limit 500
type-evidence visual-status
```

`visual-setup` explicitly downloads and verifies the checkpoint. Its [terms are separate from the MIT harness](licensing.md#fontclip-and-model-weights). Search never downloads weights. The first index can be partial; `--limit 500` bounds new work. Rerun `visual-index` to resume and extend it. CPU is the default; MPS received a bounded local probe, while CUDA and Windows model execution remain unverified.

```sh
type-evidence search --query 'angular technical' --role display --text 'NIGHT SHIFT' --visual on --limit 4
```

- `--visual on` requires a usable visual index for the actual text.
- `--visual auto` uses one when available and otherwise reports metadata/measurement discovery.
- `--visual off` gives the non-model path. Unindexed fonts remain eligible there.

For non-Latin text, build the relevant recorded sample index, for example `type-evidence visual-index --script Arabic`. Read [script and language selection](agents.md#search-the-writing-system-you-will-use). A configured sample does not establish full language coverage; the index represents default axes, not every possible variable-font instance.

## Inspect a choice and use it

Copy exact IDs from search results. Replace the placeholders below with those IDs:

```sh
type-evidence inspect EXACT_ID
type-evidence family EXACT_ID
type-evidence compare BASELINE_ID CANDIDATE_ID --text 'Review 24 requests' --sizes 15 24 48 --out library/first-comparison
type-evidence resolve EXACT_ID
```

Open the returned PNG or `index.html`. For roles and pairing in context, start from a [composition example](../examples/), replace role IDs with your finalists, and run:

```sh
type-evidence compose --spec examples/composition-interface.json --out library/interface-study
```

The unedited examples require their exact pinned-collection faces. A catalog containing only your own fonts will not resolve those IDs until you replace them. Carry required axes and features into rendering and implementation. The generated `application.html` is a separate recipe: stage authorized exact font assets and serve it over localhost HTTP, then verify the target browser. Its hash/loading gate hides missing or substituted assets.

## Connect an AI agent

[Configure the local MCP server](agents.md#local-setup-and-mcp) with absolute executable, catalog and output paths, or let your agent use the JSON CLI directly. Read [AGENTS.md](../AGENTS.md) for a bounded discover → compare → revise → apply loop. A client must support local stdio MCP and filesystem access; a remote-only client cannot directly open your local font library.

## Troubleshooting

| Symptom | Next check |
| --- | --- |
| No catalog or no results | Run `doctor`, then `stats`; confirm the global `--catalog` path comes before the subcommand and the source directory contains fonts. |
| Visual retrieval unavailable | Run `visual-status`; complete explicit model/index setup for the actual writing system, or choose `--visual off`. |
| A poor visual direction | Inspect actual results, then follow [reference-led refinement](agents.md#recover-from-a-weak-first-result). More negative words are not a reliable fix. |
| Missing glyph/style | Inspect exact coverage and `required_axes`; select a compatible face instead of relying on fallback. |
| A recipe stays hidden | Stage the exact assets, serve over HTTP and inspect browser errors. The preview PNG needs no staged fonts. |
| Platform or setup failure | File a [bug/platform report](https://github.com/gavinjudd/type-evidence/issues/new?template=bug-platform.yml) with the command, OS, Python version and redacted error. Do not attach fonts, weights or private project data. |
