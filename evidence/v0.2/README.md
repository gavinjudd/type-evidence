# Type Evidence v0.2 review

Start with the [visual review](index.html), [setup instructions](../../README.md), or [agent workflow](../../AGENTS.md).

This version adds rendered-content retrieval, visual/reference refinement, explicit negation, exploration past the first shortlist, and compositions that produce exact-font implementation recipes. The original mixed sources remain intact; curated additions improve usable style and script coverage.

## Measured implementation evidence

| Check | Observed result | Record |
| --- | --- | --- |
| Current assets | 27,520 faces resolve to a hash-verified source copy; all 27,454 original faces retained | [Asset resolution](library-validation.json), [collection](collection.json) |
| Visual coverage | 26,313 faces indexed (95.61%); 19,989 have unknown category metadata | [Visual index coverage and failures](visual-coverage.json) |
| FontCLIP adapter | 12 text and 3 image probes match the pinned official implementation to float32 tolerance; 12 canonical cross-container pairs render identically | [Parity record](fontclip-parity.json), [reproduction script](../../scripts/verify_fontclip_parity.py) |
| Discovery regressions | Four saved deterministic before/after queries document corrected negation and exposed exploration | [Before/after responses](discovery-regressions.json) |
| Exact implementation | Three recipes, six Chrome desktop/mobile views, 34 role-font checks; mobile overflow corrected and keyboard table scroll exercised | [Browser evidence](composition-browser/README.md) |
| Regression suite | 270 passed with visual dependencies; 260 passed and 10 optional tests skipped in a separate core-only environment | [Scope](tests-scope.json), [test output](tests-output.txt), [JUnit](tests-junit.xml), [core-only output](core-only-tests.txt) |

The [three query specimens and reference self-match](query-smoke.json) demonstrate behavior on the frozen complete build. They are development examples, separate from the held-out comparison. Query scores and model associations are interpretations rather than suitability measurements.

## Inspect actual compositions

- [Editorial](composition-examples/editorial/index.html): long-form hierarchy with a supporting information panel.
- [Interface](composition-examples/interface/index.html): dense numeric content, hierarchy and table alignment.
- [Poster](composition-examples/poster/index.html): large display lettering with quieter supporting information.

Each example includes its exact spec, full rendering manifest, PNG and HTML/CSS/JavaScript recipe. Preview pages use saved raster evidence; application recipes require locally staged, authorized exact assets and intentionally remain hidden until hashes and font loading pass. No font files are bundled.

## Held-out outcome and iteration

The [three-case first pass](heldout/README.md) found **no final harness improvement over basic access to the same fonts**: C and B were byte-identical in all cases. One fresh [blinded judge](heldout/blinded-review/judge.md) preferred the B/C poster to A, but tied all notice and mobile variants, including their original baselines. This is bounded formative evidence, not human user testing.

The first pass exposed polarity defects, weak semantic directions and regional-font crowding. [Post-feedback fixes](post-feedback/README.md) unify query/tone interpretation and comma negation, reject explicit static style/weight conflicts, and preserve the original results. [Reference recovery](retrieval-recovery/README.md) found more useful shapes with supplied direction anchors; prompt variations and eight-view augmentation did not solve the failed zero-shot queries.

The blind critique also produced a [bilingual assistance correction and Turkish glyph audit](post-feedback/design-followup.json), separately [visually reviewed](post-feedback/design-visual-review.json). English/French assistance emphasis now matches. The Turkish l/I distinction remains subtle at the depicted size; device reading performance remains unverified.

## Remaining boundaries

- Visual coverage is for recorded sample text at default variation axes. Final choices still require the actual content and settings. 1,207 faces have no stored embedding: 1,121 lack a complete configured sample, 76 use unsupported color/bitmap rendering, and 10 hit explicit renderer limits or face inconsistencies.
- Script indexes include Arabic, Bengali, Chinese (simplified/traditional), Cyrillic, Devanagari, Ethiopic, Greek, Hebrew, Japanese, Korean and Thai. The configured Tamil sample has no eligible face in this corpus. A sample passing does not establish complete language coverage.
- Acquisition and portable-path tests support Windows workflows, but native Windows, CUDA and a physical mobile device were not verified. Full CPU indexing and browser work ran on macOS; MPS received a bounded 64-face probe.
- The source additions are selective repairs, not an exhaustive current-font collection. Noto Serif upright and italic currently have different upstream versions and remain separate groups.
- Font rights remain a separate use/distribution decision. Font binaries, model weights, source caches and SQLite indexes stay local.

The [v0.1 evaluation](../evaluation.md) is preserved as historical evidence. It does not assess this version's visual retrieval or composition workflow.
