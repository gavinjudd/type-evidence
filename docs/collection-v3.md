# Open font packs and incremental acquisition

The v0.3 acquisition manifest makes **1,940 currently listed Google Fonts families** downloadable independently. A separate archive selection exposes **81 additional historical or experimental families**. These are available source families, not a claim that every family has already been downloaded, indexed or visually evaluated on your machine.

The original four sources remain intact in `sources.lock.json`. Selecting a pack or family does not fetch those mixed collections. Font binaries are fetched into your local library; no font binaries are distributed with the harness.

## Choose a useful download

```sh
type-evidence packs
type-evidence fetch --pack starter --plan
type-evidence fetch --pack starter --library library
type-evidence index --sources library/sources.local.json
```

| Pack | Families | Canonical font files | Source bytes |
| --- | ---: | ---: | ---: |
| `starter` | 20 | 43 | 17.35 MB |
| `ui` | 50 | 182 | 59.06 MB |
| `editorial` | 47 | 142 | 67.37 MB |
| `display` | 59 | 84 | 23.70 MB |
| `code` | 51 | 133 | 87.80 MB |
| `global` | 57 | 118 | 164.23 MB |
| `discovery-300` | 300 | 747 | 288.83 MB |
| `all-open` | 1,940 | 3,592 | 2,238.10 MB |
| `upstream-archive` | 2,021 | 3,741 | 2,379.85 MB |

Sizes use decimal MB and include the selected fonts, family license, `METADATA.pb` and available description. Files at the family-directory root are canonical; duplicate nested static instances and upstream build assets are omitted. Variable files can contain many weights or styles; file counts are not style counts. Download sizes are upper bounds before verified-cache reuse. The resumable blob cache can consume approximately one additional copy of downloaded bytes, in addition to the catalog and optional visual index.

The small packs cover different design directions without downloading the full collection. Their role labels are starting points for inspection. They do not certify readability, language coverage, accessibility or quality. `discovery-300` combines the UI, editorial, display and code selections with deterministic samples across other categories; selection is not a ranking. `upstream-archive` deliberately includes delisted, historical and experimental directories, so use it only when that scope is useful.

Packs may overlap. Stable family source IDs deduplicate a combined selection, and later fetches reuse the same verified source roots. To add one family, use its name, directory slug, upstream path or source ID:

```sh
type-evidence fetch --family 'Instrument Serif' --plan
type-evidence fetch --family 'Instrument Serif' --library library
type-evidence fetch --pack ui --pack editorial --library library
type-evidence index --sources library/sources.local.json
```

The CLI merges fetched sources into the existing `sources.local.json`. Index after acquisition to make the new files searchable. Directory listings can include fonts that are not locally available; only an indexed and resolved face can be rendered or supplied as an exact implementation asset.

To fetch an original mixed source explicitly, use its locked ID, for example `--source google-curated-2026`. An unqualified legacy `fetch` still follows the original lock for compatibility; the documented starting path is `--pack starter`.

## Pins, licenses and safe resume

The official [`google/fonts` repository](https://github.com/google/fonts) is pinned to commit [`66928797f271fed5ee428544e7229685e2d90127`](https://github.com/google/fonts/tree/66928797f271fed5ee428544e7229685e2d90127), committed October 12, 2026. Its complete, untruncated recursive tree was checked against tree `857dc09256d277cddb793db158257ba417b964bf`. Every selected path has an exact Git blob hash and byte length in the bundled `type_evidence/source-packs.json` manifest. Each download verifies that blob and length, then records a local SHA-256 receipt in `.type-evidence-source.json`.

Every downloadable family includes its family-local license text. License classifications reflect the upstream `ofl`, `apache` or `ufl` directory and identify OFL 1.1, Apache 2.0 or Ubuntu Font License 1.0. Read the included license for the intended use and distribution. Metadata and repository availability do not grant rights to unrelated commercial fonts.

Four currently listed families have a matching pinned directory but no family-local license file: Kumar One Outline, M PLUS Rounded 1c, Playwrite NZ Basic Guides and Tinos. They are excluded from automatic acquisition. Six live educational families have no matching directory at this pin. The manifest also excludes six historical jsMath directories without a family-local license. These gaps remain explicit rather than substituting another font or a guessed license.

Acquisition uses bounded HTTPS requests, portable paths and one stable destination per family. It neither executes upstream scripts nor installs fonts into the operating system. A family appears in `sources/` only after all its locked files verify. Completed blobs survive an interrupted download in `.source-cache/git-blobs`, so retrying the same command resumes at verified file boundaries. Existing source or cache bytes that differ from their pin are refused and preserved. Up to 16 source workers are allowed; the default is four.

## Recorded acquisition check

A fresh `discovery-300` plus `global` acquisition downloaded **349 distinct family sources, 849 canonical font files and 1,863 total files**, totaling **446,782,963 verified source bytes**. Every selected file passed pinned Git-blob and length verification. A subsequent offline run reverified all 349 source roots and their recorded SHA-256 receipts with network access disabled. This checks acquisition; local indexing, rendering and visual-search coverage are separate evidence. The automated source tests additionally exercise overlapping packs, offline plans, exact family selectors, interrupted-download resume, byte tampering, unknown selections and preservation of existing source data.

## Python API

`sources.source_packs()` lists family/file counts and source sizes without network access. `sources.plan_fetch(lock_path=None, source_ids=None, packs=None, families=None)` describes a selection without touching the library. Large plans show the first 50 source records and an explicit truncation flag. `sources.fetch(lock_path, library_root, portable=None, source_ids=None, packs=None, families=None, workers=4)` returns normal source configurations suitable for catalog indexing. Explicit pack/family selections work without a legacy lock file; `source_ids` select entries from the supplied lock. Pack and family selectors combine as a deduplicated union. A conflicting legacy source ID is refused.

## Rebuild the acquisition manifest offline

[`scripts/build_source_packs.py`](../scripts/build_source_packs.py) reproduces the manifest from explicit saved inputs. It makes no network requests and does not edit the legacy source lock. Retain the original input bytes: the Google Fonts website metadata endpoint changes over time, and its SHA-256 is recorded in the manifest.

Prepare these official inputs in a directory of your choice:

- The complete, untruncated recursive Git tree response for tree `857dc09256d277cddb793db158257ba417b964bf`. Independently verify the associated commit and timestamp from the official `google/fonts` commit response before passing them to the script. A commit argument alone does not establish its relationship to a supplied tree.
- The saved `https://fonts.google.com/metadata/fonts` JSON snapshot whose SHA-256 is `cfd553b7a9a3f777866bc92c093b5f951daf4f346bc4377fb4d7ef530c2277d8`.
- The pinned `METADATA.pb` files for names missing from the website snapshot, including historical and subsequently excluded directories. Store them under their ordinary upstream paths inside `pinned-metadata/`, or use the original flat spelling such as `ofl__adobeblank__METADATA.pb`. The script verifies each of these files against its exact tree blob and byte length.

For this snapshot, using `work/font-snapshot/` as the input directory:

```sh
python3 scripts/build_source_packs.py \
  --tree work/font-snapshot/google-fonts-pinned-tree.json \
  --metadata work/font-snapshot/google-fonts-metadata.json \
  --metadata-dir work/font-snapshot/pinned-metadata \
  --commit 66928797f271fed5ee428544e7229685e2d90127 \
  --commit-date 2026-10-12T19:38:43Z \
  --snapshot-date 2026-10-12 \
  --out type_evidence/source-packs.json \
  --check
```

`--check` compares exact serialized bytes and never writes. Omit it to generate a reviewed replacement. The current snapshot rebuilt byte for byte with SHA-256 `197be5434e53c52bbb8875716b19641917c67c133b3e2efdf6b28a0c9ed04eed`. The generator retains the explicit pack roster and deterministic breadth-selection algorithm, refuses missing curated families, and validates file lengths, hashes, source-size bounds, empty licenses and path collisions. Updating an upstream pin still requires reviewing changed metadata, pack membership, licenses and the corresponding `sources.lock.json` collection pointer.
