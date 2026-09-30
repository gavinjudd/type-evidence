# Type Evidence

A local font library that lets an agent discover, inspect, compare and resolve actual typefaces. It combines the two pinned collections without installing fonts system-wide or sending project text to a service.

This repository contains the harness, documentation, tests and rendered review evidence. Font binaries stay in your local library and are not published here. Upstream font rights remain separate from the harness.

**Start with the project, finish with the files.** Search produces a small, diverse shortlist with reasons. A comparison renders the real text from exact verified font bytes. Resolution gives a file path, collection face index and SHA-256. Neither a ranking nor a license notice is approval to ship a font.

## Setup

Python 3.10+ and Git are required. Tested platform/version details and limitations are in [evidence](evidence/). Source downloads need roughly 6 GB plus space for the index and derivatives. No font binaries are included in the review ZIP.

Clone the harness, then follow the commands for your platform:

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

The commands below use `type-evidence`; activate your venv or use its executable path. Fetch pins sources to [sources.lock.json](sources.lock.json). It refuses to reset an existing checkout. Indexing reads actual signatures and font tables, records parse/render failures, groups byte duplicates while preserving all origins, and keeps distinct versions and styles. Re-running index refreshes source membership and reuses content metadata. See [maintenance](docs/maintenance.md).

## Use

```sh
type-evidence project /path/to/project
type-evidence search --brief examples/dashboard.json
type-evidence inspect SHA256:FACE_INDEX
type-evidence family SHA256:FACE_INDEX
type-evidence compare ID1 ID2 ID3 --text-file project-copy.txt --sizes 16 32 64 --out library/review
type-evidence resolve SHA256:FACE_INDEX
```

`compare` writes PNG specimens, an HTML comparison and a machine-readable manifest. Open its `index.html` locally or give PNGs to a visual agent. It embeds no font binaries, uses no remote assets and rejects missing glyphs instead of substituting a fallback. Axis choices, feature settings and renderer limitations are recorded. OpenType input is exact: `--axes '{"wght":600}'`, `--features kern=1 liga=0`, `--language en`. Pass required axes from search into compare and your eventual application.

All successful CLI output is JSON. Errors go to stderr with a nonzero exit status. Put `--catalog /path/catalog.sqlite` **before** the subcommand. `doctor`, `stats` and `issues` explain the local environment and indexed scope.

For an agent, read [AGENTS.md](AGENTS.md) first. For MCP-capable tools, launch `type-evidence --catalog /absolute/path/catalog.sqlite mcp --out /absolute/path/comparisons` using the configuration in [agent integration](docs/agents.md). No API key or model dependency is needed.

## What the evidence means

- **Measured:** byte identity, usable Unicode cmap, sampled outline bounds/advances, actual shaped runs and raster output. An x-height measurement is not a readability score.
- **Declared:** family/style names, PANOSE category, weight, axes, feature tags, vendor/version, embedded legal notices. Fonts can declare these incorrectly.
- **Heuristic:** role fit and search score. No popularity, foundry prestige or automatic novelty bonus. Unknown words are disclosed, not secretly turned into visual understanding.
- **Judgment:** your choice after inspecting text at its actual size and in its intended environment. Preserve the existing font or use one family when that best serves the project.

Both upstream collections have uncertain and mixed rights. Unknown stays unknown. An `embedded-open-license` signal means that the file carries such a notice; it does not authenticate the distributor, check all conditions or grant permission. Nearby license files are hashed and scoped as unverified evidence. No deployment/export command is provided.

The library intentionally keeps supported but unfamiliar fonts discoverable. Archives, encoded files, empty files and unsupported formats are accounted for. See [architecture and limits](docs/architecture.md), [source audit](evidence/source-audit.md) and [evaluation](evidence/evaluation.md) for the exact observed scope.

## Development

```sh
python -m pytest -q
```

Tests create their own tiny font fixtures. The source code does not need the large collections to run its regression suite. Corpus experiments are separate evidence, not a claim of human preference or a controlled design study.
