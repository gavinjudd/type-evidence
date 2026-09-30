# Maintaining the local library

## Reuse and refresh

`fetch` uses full commit pins. It never resets a checkout with modifications, switches a mismatched existing source or installs a font. Normal macOS/Linux checkouts can be inspected with Git. Windows materialization retains a manifest of original Git names and content hashes; changed or extra files are refused on reuse.

Re-running `index` hashes current files, refreshes origins and removes absent faces from the new catalog. Unchanged font bytes reuse parsed metadata. Partial collection failures remain in the issue ledger. The replacement catalog is built alongside the current file and swapped after success; interrupted parsing does not overwrite the current catalog. A leftover `.building` file is an explicit stop for inspection, not automatically deleted.

For a source update, make a **new library directory**, update a copy of `sources.lock.json` to full reviewed commit IDs, then fetch and index there. Compare `stats`, `issues`, exact IDs and project specimens before pointing an agent to the new catalog. Keep the old library until its saved decisions are no longer needed. Changing upstream HEAD never silently rewrites a pin.

```sh
type-evidence fetch --lock sources-next.lock.json --library library-next
type-evidence --catalog library-next/catalog.sqlite index --sources library-next/sources.local.json
```

Use a short Windows path such as `C:\\TypeEvidence` to avoid legacy total path limits. The repository includes source paths that cannot be checked out verbatim there; the Windows fetch mode maps them safely. Install 7-Zip and make `7z` available if neither `7zz` nor compatible libarchive `tar` is present; otherwise the preparation report explicitly lists unhandled `.7z` archives. No install is attempted automatically.

## Add another source or a project's current font

Add an entry to your local source configuration with a unique `id`, an absolute `root`, and provenance fields if known. The directory must already exist and cannot be a symlink. Do not invent a commit for an arbitrary directory.

```json
[
  {"id":"project-baseline","root":"/absolute/project/assets/fonts","url":"","commit":""}
]
```

Include the existing source entries as well when rebuilding the combined library. The configuration is the complete desired source set. For an archive/encoded source, call `prepare` from Python first and include its returned derived-source manifest; current derived membership is explicitly allowlisted. Old derivative files are preserved but not silently re-admitted.

```python
from type_evidence.sources import prepare
derived = prepare("/source", "/library/derived/new", "new", "", "")
```

For selected directories from a public GitHub repository, copy the lock file and add a pinned selection:

```sh
type-evidence pin-source --repository OWNER/REPOSITORY --commit FULL_COMMIT_SHA --paths path/to/family path/to/license --id source-next --lock sources-next.lock.json
type-evidence fetch --lock sources-next.lock.json --library library-next
type-evidence --catalog library-next/catalog.sqlite index --sources library-next/sources.local.json
```

`pin-source` records each selected file's SHA-256, Git blob hash and size. It preserves existing entries and refuses a duplicate source ID. Include the applicable upstream license files alongside the fonts. Review the selection before fetching; this route avoids cloning an entire repository just to add a few families.

## Refresh visual retrieval

Visual indexes are derived local data. After catalog changes, rerun `visual-index` and any script-specific builds you use. Current faces are matched by exact ID, so search excludes stale vectors; `visual-status` reports current default-index coverage separately from stored rows. Interrupted builds resume, and failed faces are retried on the next build.

```sh
type-evidence --catalog library-next/catalog.sqlite visual-setup
type-evidence --catalog library-next/catalog.sqlite visual-index
type-evidence --catalog library-next/catalog.sqlite visual-index --script Arabic
```

Keep each script build's JSON report with the maintenance record. `visual-status` summarizes the default index only. A model/render configuration mismatch is refused; build a new index at a new output path rather than mixing embeddings. The checkpoint, all SQLite indexes and visual caches stay out of Git and review archives.

## Inspect gaps

`stats` is compact. `issues --limit 100` returns bounded details; complete issue rows remain in SQLite. Unknown rights are deliberately common. `inspect ID` exposes embedded notices and nearby-file hashes, which can then be verified against an authoritative license source. Embedded-open-license is a signal, never an automatic distribution permission.

`search --family 'Exact Family Name'` performs a hard lookup; `--query` is a preference search and may return alternatives even if a particular name is absent. `required_styles` in a JSON brief is stronger than `min_styles`: it verifies exact requested weights/slants and text in the same family/version/width group.

## What is safe to share

The versioned review ZIP contains source, docs, small public-metadata summaries, test results and rendered specimens. It excludes the font library, SQLite catalog, virtualenv, source Git objects and raw font archives. `scripts/review_bundle.py` uses an explicit file allowlist, rejects symlinks and font magic bytes, verifies member hashes and ZIP CRC, and emits a SHA-256 checksum. It is a review artifact, not a font distribution.
