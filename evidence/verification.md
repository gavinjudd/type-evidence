# Verification record — v0.1.0

Observed on macOS arm64 with Python 3.12.13. This repository's `.venv` has an editable installed package. FontTools 4.60.2, Pillow 11.3.0, uharfbuzz 0.52.0 (HarfBuzz 12.1.0) and freetype-py 2.5.1 (FreeType 2.13.2) were used. `requirements-lock.txt` records the exact validation environment.

## Automated checks

The full regression suite passes. The accompanying `pytest.txt` and `pytest.xml` contain the final count, timing and individual test results. Tests synthesize fonts instead of relying on the large downloaded corpus. They cover collection faces, container equivalence, duplicate provenance, cache refresh/deletion and partial failures, source/ZIP/7z path handling, portable Git materialization, missing/changing files, exact style/coverage constraints, baseline retention, version/width grouping, malformed metrics, missing glyph rejection, ligatures/kerning, variable settings, script runs, output clipping limits, HTML escaping, CLI errors and MCP handshake/tool behavior.

The independent reviewer supplied regression cases for issues fixed before packaging: excluded companions, repeated family versions, NaN/boolean metrics, lost cached TTC failures, oversized-file duplicate counts, incompatible schema rebuilds, verbose stats and original Windows path provenance. The fresh-agent trial supplied additional actual-corpus regressions described in [evaluation.md](evaluation.md).

## Corpus and installation checks

- Both pinned source trees were fully acquired and inspected. 571 supported font derivatives were recovered from Base64 and archives, plus seven sidecars. Preparation completed without reported issues. Original assets remain intact under `library/sources`.
- Final index: **27,454 faces**, 8,012 declared family names, 8,674 conservative family/version/width groups. The catalog records 2,651 redundant file occurrences, 1,816 decoded-table equivalence groups and 144 parse/render failures. A family count is not a quality claim.
- Rights signals: 19,732 unknown, 7,356 embedded-open-license, 366 restricted-notice. These are evidence classifications, not permissions.
- Every indexed face was resolved after the library moved into the delivered repository: **27,454/27,454 verified**, zero failures, representing 27,293 exact source-file hashes. See [all-face-resolution.json](all-face-resolution.json). This checks source identity, not every glyph.
- The installed CLI reused both pinned repositories, prepared the derivative manifest and rebuilt the index. Complete source trees and the local database are intentionally absent from the review ZIP.
- A live subprocess MCP client initialized, listed tools, searched, independently checked a resolved file hash and rendered a specimen. All calls succeeded; see [mcp-e2e.json](mcp-e2e.json). No particular editor integration is claimed.
- The generated dashboard HTML was opened in the Codex browser; its specimen images, metadata, rights signals and evidence links were visible. [dashboard-browser.png](dashboard-browser.png) is the browser screenshot. Exact-size PNGs are in `previews/`; the browser interface uses a separate system font.

## Limits of this verification

Windows path mapping was checked over all actual upstream names and portable Git materialization was tested with a real fixture repository on macOS. A native Windows setup/run remains unverified. The renderer uses unhinted outlines; browser/Word/game-engine equivalence and human reading performance were not tested. Formative aesthetic judgments from one fresh agent are not a controlled study. The archive receipt reports CRC, member hashes, path safety and known secret-signature scans; those scans do not prove the absence of every imaginable secret.

Fresh extraction/setup results are recorded in `clean-install.json`; the final archive verification receipt is delivered beside the ZIP. No fonts were installed system-wide, no archives published and no paid service used.
