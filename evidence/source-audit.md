# Source audit and acquisition evidence

Observed 2026-09-30. Originals preserved; no source scripts run and no fonts installed.

| Source | Exact commit | Tracked files | Source bytes (without Git storage) | Font extension files |
|---|---|---:|---:|---:|
| bekahmcdonald/fonts | `7841ca896a9a770d5ea18fd5faef0eb91ad90ef3` | 28,098 | 3,450,846,297 | 19,845 |
| extsalt/10000-font-collection | `71fa21742b9f51afb2b0d83a5d0de6e1dedd269c` | 10,492 | 805,838,996 | 10,492 |

Both original clones matched their fetched pins and were clean after acquisition. No Git submodule entries or LFS pointers were found. Bekah's `.gitmodules` names a helper but the tree has no gitlinks. No symlinks or case/Unicode filename collisions were found. GitHub reports no repository license for either source; that is not a classification of individual font rights. Bekah's README explicitly requests font-by-font rights verification and records a historical DMCA notice. Extsalt has no license/readme sidecars.

## Actual formats and anomalies

Bekah contains 4,075 CFF SFNTs, 7,597 TrueType SFNTs, 4,208 WOFF2s, 3,142 WOFFs, and 3 collections by byte signature (19,025 recognized font containers). There are 3,098 extension/signature disagreements; these are evidence of unreliable filenames, not automatically broken fonts. Four true SFNTs have `.txt` filenames. Of 495 `.eot` files, 40 actually carry supported SFNT/WOFF signatures and 455 carry EOT signatures.

The 369 ordinary font-extension files without recognized raw signatures resolve to 204 Base64-encoded fonts and 165 empty files. Seven further empty files are nonfont placeholders. Source UFO/GLIF (6,879 `.glif` files), 266 TTX files, legacy formats, EOTs, and design assets remain preserved. Font validity beyond magic bytes is the catalog parser/renderer's separate responsibility.

Extsalt is a flat collection of 10,492 true SFNT `.ttf` assets. Neither advertised repository name nor file count means 10,492 distinct families or useful designs.

Original font-extension-or-signature inventory totals 30,341 occurrences and 27,651 original byte hashes. There are no exact byte duplicates across the two repositories. Byte-level identity does not establish visual or semantic identity. All original duplicates remain on disk; the catalog coalesces identities without deleting provenance.

## Archive and encoded-font preparation

Fourteen archives were inspected: nine ZIPs and five 7z files. All nine ZIP CRC tests passed. No unsafe archive member paths were observed. Four 7z archives contain visual assets; `Foundries/Pangram Pangram/Old.7z` contains 259 OTF members. Meslo's outer ZIP repeats nested ZIPs that also exist separately in the source, so nested recursion is unnecessary for this snapshot.

The bounded preparation pass produced 204 Base64 fonts, 259 fonts from Old.7z, 108 recognized ZIP font members, and seven license/document sidecars: **571 font derivatives, 578 derived files, zero preparation issues**. Eight EOT ZIP members were preserved in originals but not converted. Every derived file carries original source id, commit, original path and SHA256, archive member when applicable, member/derived hash, and transformation. Git/source originals are untouched. Libarchive was used only to transcode archives to a bounded tar byte stream; no archive-supplied paths were extracted to disk.

## Portability

The upstream bekah tree has **777 Windows-invalid paths**, mostly forbidden characters and trailing dots. Extsalt has zero. Normal Git checkout is therefore unsuitable on Windows. `fetch` defaults to a bare Git fetch and safe blob materialization on Windows, percent-encoding invalid path components while retaining directory structure and original Git paths in `upstream_paths`. Blob SHA1 and materialized SHA256 are verified. Existing changed files are refused, never reset. All 38,590 upstream paths were checked against this mapper: zero remaining invalid names or casefold collisions; maximum relative path length is 136 characters. Use a short Windows library root because total legacy Windows path limits still depend on the root. Windows runtime execution has not been observed.

## Verification

29 focused source tests passed on macOS, including actual Git blob materialization, Base64 provenance, exact repeat preparation, ZIP traversal and link rejection, size/ratio limits, libarchive links and exact extraction, duplicate origins, symlink outputs, changed derivatives, dirty checkout preservation, and bounded subprocess output. The source scan and archive preparation ran against the full downloaded collections. These checks do not constitute a security audit of font parsers or proof of every glyph's correctness.

Machine-readable review evidence: `remote-metadata.json`, the two source audit JSON files, `combined-byte-audit.json`, `license-indicators.json`, `windows-path-audit.json`, `portable-path-verification.json`, `preparation-summary.json` and `catalog-summary.json`. Full preparation provenance remains in the local library's derived manifests and source configuration. Per-font raw inventories and original duplicate groups remain local intermediate evidence; they are not needed in the compact review ZIP. See `research-leads.md` for primary-source reuse research.
