# Discover fonts before downloading them

The bundled directory contains **2,167 provider listings**: all **1,950 families** in the Google Fonts metadata snapshot and **217 selected commercial listings from seven foundries**. Search works offline, without a local font catalog, credentials, downloaded fonts, or a visual model.

```sh
type-evidence directory --query 'Arabic' --license-kind open --limit 6
type-evidence directory --category sans-serif --variable --limit 6
type-evidence directory --provider 'Klim Type Foundry' --limit 6
type-evidence directory --license-kind commercial --offset 6 --limit 6
type-evidence directory --id directory:google-fonts:inter
type-evidence directory --stats
```

MCP exposes the same search as `font_directory` and one-record inspection as `font_directory_detail`. The [browser explorer](https://gavinjudd.github.io/type-evidence/) uses the same snapshot; its publication state is independent of this checkout.

## From a listing to usable fonts

Directory IDs begin with `directory:`. They describe provider listings and cannot be passed to exact-face rendering or resolution. For an open family with `acquisition.available: true`, inspect the download plan and fetch it explicitly:

```sh
type-evidence fetch --family Inter --plan
type-evidence fetch --family Inter
type-evidence index
type-evidence search --family Inter --text 'Review 24 requests' --limit 4
```

The final search returns the actual local `sha256:face_index` identities. Inspect and render those IDs with the project text before making a design choice.

Commercial entries link to the official foundry specimen and acquisition page. Obtain the appropriate license and files, then register the authorized local folder:

```sh
type-evidence import-local /absolute/path/to/owned-fonts --id owned-fonts --index
```

Registration does not buy a license, copy fonts, or install them into the operating system. A foundry trial is not a production license. The directory includes no proprietary font binaries and does not retrieve commercial fonts or treat browser specimens as local font assets.

## Search behavior

Search matches family names, designer/vendor names, provider names, categories, declared tags, and provider subsets. It is case insensitive and accent insensitive: `sohne` finds `Söhne`. All query words must match; exact family names rank first, followed by family-name prefixes and then other literal metadata matches. Ties are alphabetic with an identifier tie-breaker. There is no popularity ranking or inferred visual similarity in directory search.

| Filter | Behavior |
| --- | --- |
| `category` | `sans-serif`, `serif`, `display`, `handwriting`, `monospace`, or `unknown` |
| `provider` / `vendor` | Exact normalized name; Google vendor strings contain the listed designers |
| `license_kind` | `open`, `commercial`, or `unknown`; classification is source evidence, not a license grant |
| `access` | `open-download`, `commercial-license`, or `unknown`; describes the provider route |
| `tags` | All requested tags must match; CLI repeats `--tag`; at most 16 tags |
| `variable` | `true` or `false`; an unknown value matches neither; CLI uses `--variable` or `--static` |
| `limit` / `offset` | 1–100 results per page; nonnegative integer offset up to 1,000,000 |

Follow `pagination.next_offset` with the same query and filters. Facets count the complete matching set before pagination. Vendor, tag, and subset facets return at most 50 values, with omitted-value counts in `facets.truncated_values`. Overlapping tags/subsets do not add up to a unique-family count.

Unknown commercial categories and styles remain unknown; they are not guessed from a familiar name. A hard category filter therefore excludes commercial listings without a recorded category. Clear that filter or search a foundry/name when exploring more broadly.

## Snapshot and sources

Retrieved **13 October 2026 UTC**. The Google catalog metadata and repository tree are separate sources:

- [Google Fonts served-family metadata](https://fonts.google.com/metadata/fonts): 1,950 family records, with provider-declared categories, designers, style keys, axes, and subsets. Popularity/trending scores are deliberately not imported.
- [Google Fonts repository at `66928797f271fed5ee428544e7229685e2d90127`](https://github.com/google/fonts/tree/66928797f271fed5ee428544e7229685e2d90127): 2,031 family directories. Repository contents include families outside the live served catalog. This is not an additional 2,031 discovered families.
- The directory matches 1,944 live records to pinned repository paths. **1,940** have an eligible source in the acquisition manifest. Four live records lack a family-local license file in that pin: Kumar One Outline, M PLUS Rounded 1c, Playwrite NZ Basic Guides, and Tinos. They retain provider links, but the pinned downloader does not offer them.
- Six live families have no matching directory in that repository pin: Edu NSW ACT Cursive, Edu NSW ACT Hand Pre, Edu QLD Hand, Edu SA Hand, Edu VIC WA NT Hand, and Edu VIC WA NT Hand Pre. Their provider metadata remains discoverable without inventing a repository mapping.

The commercial selection uses official retail listings, not third-party downloads:

| Foundry | Selected listings | Source |
| --- | ---: | --- |
| Commercial Type | 24 | [Catalog](https://commercialtype.com/catalog) |
| Dinamo | 41 | [Retail typefaces](https://abcdinamo.com/catalogue) |
| Displaay | 32 | [Typefaces](https://displaay.net/typefaces/) |
| Grilli Type | 21 | [Library](https://www.grillitype.com/typefaces) |
| Klim Type Foundry | 30 | [Fonts](https://klim.co.nz/fonts/) |
| Pangram Pangram | 50 | [Font collection](https://pangrampangram.com/collections/fonts) |
| Swiss Typefaces | 19 | [Catalog](https://www.swisstypefaces.com/fonts/) |

A foundry listing may represent a family, a subfamily, or a collection. Counts preserve the upstream listing level rather than claiming every row is an independent type design. The commercial selection excludes custom-only work, gated early-access fonts, unrelated merchandise, and font bundles. Family names and links are factual discovery metadata; foundry descriptions and specimens are not republished.

The snapshot records source URLs, retrieval dates, content hashes, the Google repository commit, and per-entry provenance. Some commercial categories, style counts, and variable flags are declared in the catalog; others remain `unknown`, `null`, or empty. Provider subsets are not verified character coverage, axes are not inspected local font tables, and advertised style counts are not evidence of a complete local family.

## Data and Python API

Runtime metadata lives in `type_evidence/font_directory.json`, with `schema_version`, `snapshot`, and `families`. The website copy is `docs/font-directory.json` and must remain byte identical. Each family includes:

- A stable directory ID, provider label, category, source and acquisition URLs.
- License classification and a license URL when known; commercial rights are never inferred from availability.
- Declared styles, axes, subsets, tags, and provenance, retaining missing values.
- An `acquisition` object distinguishing a pinned open source from a provider link.
- `local_availability: "not-checked"`. `indexed: false` and `renderable: false` mean the directory entry is metadata only; they do not assert that the user lacks the font elsewhere on the computer.

```python
from type_evidence.directory import directory_detail, directory_stats, search_directory

page = search_directory("editorial", license_kind="commercial", limit=6)
details = directory_detail(page["results"][0]["id"])
counts = directory_stats()
```

These calls do not read the local font database, make network requests, or check ownership. Search arguments are bounded and validated; invalid enum values, noninteger pagination, and ambiguous variable flags fail with `ValueError`. Results are independent copies, so caller mutation cannot alter the cached snapshot.

## Rebuild and verify

The builder accepts saved official metadata and a verified untruncated tree; it performs no downloads. The curated commercial facts and source hashes are versioned in `scripts/build_font_directory.py`. Review source changes before updating those facts. Supply an acquisition manifest built from the same Google commit and metadata hash:

```sh
python scripts/build_font_directory.py \
  --metadata /absolute/path/to/google-fonts-metadata.json \
  --tree /absolute/path/to/google-fonts-pinned-tree.json \
  --commit 66928797f271fed5ee428544e7229685e2d90127 \
  --retrieved-at 2026-10-13T01:35:55Z \
  --acquisition-manifest type_evidence/source-packs.json
python -m pytest tests/test_directory.py tests/test_directory_integration.py
```

For identical inputs, output bytes are deterministic. After an intentional refresh, update the website copy and the documented counts together. Dates and hashes identify a snapshot; provider offerings and terms can change after it was captured.
