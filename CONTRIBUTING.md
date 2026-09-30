# Contributing to Type Evidence

Help agents find useful fonts, inspect them in real content, and apply the selected settings faithfully. Improvements can be code, source metadata, a reproducible poor recommendation, a platform check, or a careful design comparison. Keep changes focused and preserve evidence of what did and did not work.

The original harness code and documentation use the [MIT license](LICENSE), copyright © 2026 Gavin Judd. Contributions to that code and documentation should be compatible with MIT; identify any third-party material and preserve its notices. Fonts, model weights, and dependencies keep their own terms. See the [licensing boundaries](docs/licensing.md); the harness license does not grant rights to those assets.

## Develop without downloading fonts or a model

From a checkout, use Python 3.10+ and Git. CI currently exercises Python 3.12 on Linux, macOS, and Windows. The tests construct small synthetic fonts and catalogs in temporary directories; you do not need `fetch`, `index`, `visual-setup`, or a personal font collection.

macOS / Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

Optional tensor/vector tests skip when their dependencies are absent. To work on those tests, install `.[test,visual]` in the same environment; the regression suite still does not download checkpoint weights. Actual model/corpus experiments require separate explicit setup from the [README](README.md). Keep their data in ignored `library/` or `work/` directories.

For a focused change, run its nearby tests first, for example:

```sh
.venv/bin/python -m pytest -q tests/test_discovery_v2.py tests/test_mcp_v2.py
```

Use the Windows interpreter path above on Windows. See the [core CI workflow](.github/workflows/core-tests.yml) and [recorded platform scope](evidence/v0.2/portability.json). Passing synthetic core tests does not verify a full collection, model, or browser workflow on every platform.

## Find the extension point

| Work | Start here | Nearby tests |
| --- | --- | --- |
| Query interpretation, constraints, ranking, diversity | [discovery.py](type_evidence/discovery.py); shared CLI/MCP orchestration in [operations.py](type_evidence/operations.py) | [Discovery](tests/test_discovery_v2.py), [observed regressions](tests/test_observed_corpus_regressions.py), [family requirements](tests/test_family_requirements.py) |
| Visual samples, script routing, embeddings, index compatibility | [visual.py](type_evidence/visual.py) | [Visual unit tests](tests/test_visual.py), [integration fixtures](tests/test_visual_integration_review.py) |
| Source pins, selected directories, safe acquisition and preparation | [sources.py](type_evidence/sources.py), [sources.lock.json](sources.lock.json) | [Sources](tests/test_sources.py), [source expansion](tests/test_source_expansion.py) |
| Face metadata, provenance, coverage, catalog replacement | [catalog.py](type_evidence/catalog.py) | [Catalog](tests/test_catalog.py), [review regressions](tests/test_review_regressions.py) |
| Exact shaping/rasterization and contextual layout | [render.py](type_evidence/render.py), [composition.py](type_evidence/composition.py) | [Render](tests/test_render.py), [composition](tests/test_composition.py) |
| Command options, bounded responses, MCP schemas | [cli.py](type_evidence/cli.py), [mcp.py](type_evidence/mcp.py) | [CLI/MCP](tests/test_cli_mcp.py), [MCP validation](tests/test_mcp_v2.py) |
| Shareable review packages | [review_bundle.py](scripts/review_bundle.py) | [Bundle checks](tests/test_review_bundle.py) |

Read the [agent workflow](AGENTS.md), [API and composition contract](docs/contract.md), and [architecture](docs/architecture.md) before changing shared behavior. `operations.discover` is the common search entrypoint: keep CLI and MCP behavior aligned. Tests in [test_catalog.py](tests/test_catalog.py) and [test_render.py](tests/test_render.py) show how to build synthetic assets instead of committing binary fixtures.

## Bounded starting points

These are unassigned task ideas, not claims of active issues or reserved work. Open an issue to describe the scope if you want to coordinate.

- **Check one additional Python version.** Run the clean core setup on Python 3.10 or 3.13, record the exact runtime and results, and reduce any failure to a small fixture. The current CI matrix covers 3.12.
- **Reproduce shortlist crowding.** Make a small fake catalog with regional families whose Latin shapes are similar. Compare one bounded diversity change against the unchanged ranker while retaining an eligible baseline. Report tradeoffs rather than assuming more family names mean more visual variety.
- **Propose one source selection.** Identify one useful family/style or script gap, a public upstream URL and full commit, selected paths, and the associated license/notice paths. Submit metadata and rationale, not font files.
- **Add one language sample proposal.** For a currently unconfigured script, propose a short sample and language tag with a knowledgeable reader's rationale. Cover routing, sample eligibility, and index-configuration invalidation in synthetic tests before any large rebuild.
- **Contribute one contextual comparison.** Use public or invented text for a specific reading page, interface, or poster. Preserve the baseline and original outcome, then record an independently judged comparison or a clearly labeled self-assessment.

## Report poor recommendations and platform failures

Use the issue form closest to the problem. A useful recommendation report includes the actual text and language tag, brief/query, expected appearance or use, returned exact IDs, and what looks wrong at the intended size. Include `visual_retrieval` and `query_interpretation` from the response so missing-model behavior and semantic misses can be distinguished. A familiar baseline or reference is useful, but a reference chosen after a failed query is a supervised recovery, not evidence that the query succeeded.

Keep reports small: one brief, at most six candidate records, one or two authorized screenshots, and the relevant error excerpt. Redact private project copy, usernames, absolute machine paths, credentials, and unrelated logs. Exact font IDs and source commits usually provide better reproduction clues than attaching assets.

For platform reports, include the project commit/version, OS and architecture, Python version, `python -m type_evidence doctor` output, the exact command or MCP request, and expected versus actual behavior. State whether the failure occurred in core tests, acquisition, rendering, the optional model, or a browser. A passing synthetic test and a successful real collection run are different evidence.

## Source metadata and shared artifacts

Never upload font binaries or archives, model weights, SQLite catalogs/indexes, virtual environments, or secrets in commits, PRs, or issue attachments. This also applies to proprietary fonts used locally. `.gitignore` is a convenience, not proof that an attachment or staged file is safe.

Source proposals should preserve upstream identity: repository URL, full commit, selected file paths, notice paths, and, for a lock change, byte sizes, Git blob hashes, and SHA-256 values generated by the pinning workflow. See [adding a source](docs/maintenance.md#add-another-source-or-a-projects-current-font) and [collection scope](docs/collection-v2.md). Preserve existing pins and provenance; do not relabel unknown rights as open because a font was publicly downloadable. A source-metadata proposal does not authorize redistribution of its font bytes.

Small JSON records and rendered PNGs can support review when you have permission to share their content. Keep binaries local and refer to exact hashes. Put exploratory output in a new directory; do not overwrite historical evaluation records.

## Evidence and pull requests

Explain the concrete problem, resulting behavior, and validation in the PR. For a behavior change, add a regression that fails before the fix and checks the meaningful outcome. Run focused tests, then the core suite. Keep UTF-8 explicit at text I/O boundaries and close files/databases before replacement so fixtures work across platforms. Do not weaken assertions or skip a failing platform to obtain a pass.

For docs-only changes, check links and commands; code tests are unnecessary unless behavior changed. For visual retrieval changes, distinguish unit tests, model-loader parity, corpus coverage, and judged design outcomes. Record model/index configuration, source pins, text, axes, sizes, and comparison conditions for actual experiments. If a relevant check could not run, state that limit.

Design evaluations should hold the brief, collection, renderer, and effort caps consistent where possible, preserve the original baseline, identify the judge and whether labels were blinded, and retain failures and ties. Label post-feedback changes separately. The [v0.2 held-out report](evidence/v0.2/heldout/README.md) found no final harness improvement over basic collection access; new contributions should test improvements rather than erase that result.

Before submitting, inspect your diff and staged files, verify that no local assets or private data are included, and keep the PR limited to its stated purpose. Larger model, index-format, source-policy, or API changes benefit from a short proposal before implementation; small fixes can arrive directly as a PR.
