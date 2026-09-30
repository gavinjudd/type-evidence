# Fresh adoption review

**Result: core flow and local stdio MCP passed without font-collection or model downloads.**

`$REPO` in JSON/text receipts denotes the checkout root. Only synthetic boxed glyphs and public sample text were used. The existing core environment was reused; source installation was not repeated.

## Persona review

| Persona | Can start without collection/model? | Evidence |
| --- | --- | --- |
| New user | Yes | README → getting started → own-font source JSON → exact search/compare/resolve. |
| Local AI agent | Yes | AGENTS workflow and absolute MCP config; initialize, 11 tools, and search exercised via actual stdio process. |
| Contributor | Yes | Core/test-only setup and synthetic fixture pointers; documented focused selection passed 41 tests. |

## Findings

No blocking setup, CLI/MCP mismatch, hidden model requirement, or rights misstatement was found in the reviewed docs. Rights descriptions distinguish the harness MIT license from fonts, dependencies, and unestablished checkpoint terms. Own-font records retained `rights.status=unknown` and `review_required=true`.

One low-priority clarity improvement: after the alternate-catalog example at `docs/getting-started.md:54–59`, say to carry that same global `--catalog` flag into every later subcommand and the MCP configuration. The subsequent inspect/compare/resolve examples omit it and otherwise use the default catalog. README/troubleshooting already explain flag placement.

## Executed checks

- Python 3.12.13, with no Torch, OpenCLIP or NumPy in the reused clean environment.
- Two synthetic faces generated using `tests/test_catalog.py:make_font`, with printable ASCII coverage and distinct advances.
- 13 CLI/MCP subprocess invocations; successful own-font index/stats/search/inspect/family/compare/resolve/visual-status.
- Comparison manifest: no fallback, no system font lookup, zero glyph-zero occurrences. Resolved file bytes matched their SHA-256.
- Auto visual retrieval reported `not_configured`; required visual retrieval failed with an explicit optional-dependency instruction.
- Missing-glyph comparison failed with `U+6F22` and “No fallback was used.”
- MCP negotiated `2025-06-18`, returned 11 tools, and returned search JSON exactly equal to CLI.
- Contributor command: `work/clean-v02/bin/python -m pytest -q tests/test_discovery_v2.py tests/test_mcp_v2.py` → **41 passed in 0.27s**.

Exact normalized commands, exit codes, per-command output references, and limitations are in [receipt.json](receipt.json). [mcp-requests.json](mcp-requests.json) contains the transmitted requests, converted from JSONL to an array for this archive. The original local smoke script and synthetic font files are not part of this publication.

## Limits

This verifies synthetic core behavior and the local transport, not aesthetic quality or a configured editor integration. It does not verify fresh dependency installation, full corpus/model execution, Windows behavior, font/model commercial clearance, or browser production rendering. Published source/docs and existing library/catalog/model data were not edited.

## Correction after review

The setup guide now explicitly tells readers to carry the custom catalog path through every later command and MCP configuration. The original finding above is retained.
