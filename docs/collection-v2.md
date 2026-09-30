# Collection expansion in 0.2

The original mixed collection remains intact. The expansion repairs useful gaps
and adds current, coherent options where they improve real projects: reading,
interfaces, code, expressive headings, and several poorly served scripts.

## What changed

| Need observed in the original collection | Addition and practical value |
|---|---|
| Atkinson Hyperlegible, Literata and Source Serif 4 absent | Atkinson's regular/bold/italic quartet; Atkinson Hyperlegible Next variable upright/italic; Literata and Source Serif 4 upright/italic with weight and optical-size axes |
| Noto Sans lacked an upright regular face | A matched Version 2.015 upright/italic variable pair; weight 100–900 and width 62.5–100 |
| Narrow expressive and distinct reading choices missing | Rajdhani's five weights; Orbitron; matching Newsreader, Fraunces and Alegreya upright/italic pairs |
| Expressive choices should not require a large or fabricated family | Instrument Serif and DM Serif Display regular/italic; Bricolage Grotesque, Gabarito, Spline Sans and Kalam with their actual supplied styles |
| Sparse non-Latin coverage | Noto Arabic and Naskh Arabic; Devanagari sans/serif; Japanese, Simplified Chinese, Korean, Thai, Bengali, Hebrew, Armenian, Georgian and Ethiopic |
| Complete code styles, with useful variation in character | ArrowType's Recursive five-axis variable font plus four Rec Mono families, each with regular, bold, italic and bold italic |

These are additions, not preferred search results. An embedded open notice does
not increase a font's aesthetic rank. The original 19,732 unknown-rights faces
and 366 restricted-notice faces remain available with their original evidence.

The four upstream sources are pinned in `sources.lock.json`:

- [Original Bekah collection](https://github.com/bekahmcdonald/fonts/tree/7841ca896a9a770d5ea18fd5faef0eb91ad90ef3)
- [Original Extsalt collection](https://github.com/extsalt/10000-font-collection/tree/71fa21742b9f51afb2b0d83a5d0de6e1dedd269c)
- [Google Fonts selected families](https://github.com/google/fonts/tree/9710da1eacb3be272583c3224dcb70f9da6eadbb)
- [ArrowType Recursive 1.085](https://github.com/arrowtype/recursive/tree/6d491202cea5cf6a493ef710cbef2527b9b08939/fonts/ArrowType-Recursive-1.085)

The two new sources download 156 files, totaling 73,113,935 bytes, including 66
font files plus licenses and metadata. They represent 35 embedded family names;
29 were absent before. The full catalog changes from 27,454 to 27,520 faces and
8,674 to 8,710 family/version/width groups. Every original face remains present.
No font binaries are included in the public repository or review package.

## Useful coverage, rather than file counts

The checks in [`evidence/v0.2/collection.json`](../evidence/v0.2/collection.json)
use real short phrases. The count below is the number of family/version/width
groups with complete cmap coverage of that phrase, not an assertion that every
language character, shaping rule or reading use is supported.

| Sample | Before | After |
|---|---:|---:|
| Ethiopic: እንኳን ደህና መጡ | 0 | 1 |
| Devanagari: नमस्ते दुनिया | 2 | 7 |
| Arabic: مرحبا بالعالم | 16 | 18 |
| Japanese: ようこそ東京 | 8 | 11 |
| Simplified Chinese: 欢迎来到上海 | 1 | 2 |
| Korean: 서울에 오신 것을 환영합니다 | 1 | 2 |
| Thai: ยินดีต้อนรับ | 2 | 3 |
| Bengali: স্বাগতম | 1 | 2 |

Fourteen representative text probes, including those above plus Latin,
Greek, Cyrillic, Hebrew, Armenian and Georgian, shape through HarfBuzz with zero
missing glyphs in exact newly acquired faces. This establishes available glyphs
and a successful shaping call. Inspect the actual composition before making a
design judgment.

There are intentional limits. Google's current Noto Serif upright is Version
2.015 while its italic is 2.013. They stay in separate family groups; the harness
does not pretend they are a matched pair. Some variable defaults are very light
or black: request weight explicitly and apply the returned axes. Thirty-seven
new faces still have an unknown category in their embedded metadata, so names
and metadata alone remain an inadequate discovery strategy.

## Add another source without cloning its entire repository

`pin-source` creates a `github-subtree` lock entry from a full commit and selected
paths. It preserves existing entries and requires a new source ID. Pinning
downloads bytes to compute SHA-256 and verify upstream Git blob hashes, but
saves only the metadata lock. `fetch` subsequently materializes that selection
inside the local library.

```sh
type-evidence pin-source --repository google/fonts --commit FULL_40_HEX_COMMIT \
  --paths ofl/yourfamily --id yourfamily-verified-version --lock sources.lock.json
type-evidence fetch --lock sources.lock.json --library library
type-evidence index --sources library/sources.local.json
```

Directory selection includes immediate font files, license/readme notices,
`METADATA.pb`, and `DESCRIPTION.en_us.html`. It does not recurse into `static/`
or build directories: add an exact nested path if it contains necessary styles.
Prefer a variable upright/italic pair to redundant exports when it supplies the
required range. Add exact files for an upstream layout that does not follow a
family-directory convention. The Python API is
`pin_github_source(repository, commit, paths, ident)` and returns one entry;
it does not mutate an existing lock.

Fetch validates each file's exact SHA-256, Git blob hash and byte length, then
makes the complete source visible atomically. Existing modified sources are
preserved and refused. File counts, total bytes and individual sizes are
bounded. It uses portable percent-encoded paths, rejects traversal, symlinks,
case collisions and file/directory collisions, and never executes upstream
scripts or installs fonts into the operating system.

Tests exercise successful acquisition/reuse, mutated bytes, changed manifests,
untracked files, symlinks, unsafe paths, cross-platform collisions, wrong hashes,
truncated listings and size limits. The 52 acquisition/preparation tests are
part of the passing synthetic core suite on native Linux, macOS and Windows
([CI run](https://github.com/gavinjudd/type-evidence/actions/runs/36749819569),
[portability receipt](../evidence/v0.2/portability.json)). Full collection
acquisition and visual-model/browser workflows remain unverified on Windows;
CUDA is also unverified.
