# Held-out comparison: first-pass results

**The harness did not improve the final composition over basic access to the same font collection in these three cases.** The final C images are byte-identical to B. This is a useful negative result: capable selection and plain catalog browsing already produced good candidates, and keeping them was valid.

| Authored context | Unaided A | Basic collection B | Harness C | Evidence |
| --- | --- | --- | --- | --- |
| English/French ferry notice | Source Sans Pro | Same final image | Same final image | [Brief](case-a/brief.json), [C final](results/C-harness/case-a/source-sans/composition.png) |
| Polish community print poster | Enlarged Roboto fallback after two exact-name misses | Cooper-Black-Stencil title + Roboto support | Same final image as B | [Brief](case-b/brief.json), [A final](results/A-unaided/case-b/baseline-large/composition.png), [B/C final](results/C-harness/case-b/cooper-stencil/composition.png) |
| Turkish mobile sewing lesson | Source Sans Pro | Same final image | Same final image | [Brief](case-c/brief.json), [C final](results/C-harness/case-c/final/composition.png) |

The selecting agent preferred B/C's poster to A; the notice and mobile lesson were ties across all conditions. A [fresh anonymized AI judge](blinded-review/judge.md) independently preferred B=C over A for the poster, and tied A=B=C with the original baseline for the notice and mobile lesson. The [mapping](blinded-review/mapping-revealed-after-judgment.json) was withheld until the judgment was saved. This is one AI judgment, not human user testing. Its critique led to [separately labeled design follow-up](../post-feedback/design-followup.json) and [supplemental visual review](../post-feedback/design-visual-review.json), preserving every first-pass image.

## What was controlled and measured

One fresh agent completed all A stages before any B, then all B before C. Each case/condition had the same caps: eight active minutes, six information operations with at most twelve records each, four options including the baseline, and one final revision. The same exact renderer was available in all conditions, so this comparison isolates discovery more than rendering availability. Catalog and source pins were identical. Visual indexing finished during A/B under a predeclared staging amendment; those stages could not use it. Completed index hashes were frozen before C.

All nine final compositions passed exact-byte/no-fallback checks and measured no-clipping/no-line-overlap checks. Budgets were respected. Active time was A 43–121 seconds, B 77–85 seconds, and C 99–165 seconds; equal caps are not equal time consumed. The full [comparison record](firstpass-comparison.json) preserves counts, times, selected families and image hashes. Each stage retains its decisions, candidate outputs, inputs, recipes, images and manifests under `results/`.

## Failures worth acting on

- Comma-coordinated negatives and query/tone interpretation diverged. Repeating explicit negation recovered interpretation during the trial.
- Regional Noto variants crowded a first page with nearly identical Latin appearance. Family-name diversity did not ensure shape diversity.
- A Noto Sans SC candidate covered French text but produced visibly excessive spacing around curly apostrophes. Cmap presence did not establish suitability.
- Expressive semantic searches led first toward pixel-game faces, then formal serifs. Neither displaced the stronger candidate already found through basic browsing.
- Unaided exact names Cooper Black and Archivo Black were absent. Atkinson Hyperlegible bold did not cover Turkish dotted capital İ in the proposed role. These are asset/coverage findings, separate from taste.

Post-feedback fixes and re-runs are recorded separately in the parent evidence directory. They are not new held-out results and do not rewrite this first pass.

## Limits and provenance

These are three faithful authored fixtures, not live client projects. One agent's sequential access gives later conditions carryover from earlier choices. There was no human reading study, production browser validation of these nine finals, or physical print test. The [protocol](PROTOCOL.md) records the design and limits; the [sealed inputs](sealed-inputs.sha256.json), [catalog freeze](coordinator-freeze.json), [visual freeze](visual-firstpass-freeze.json), [A/B freeze](ab-firstpass-freeze.json) and [full first-pass freeze](firstpass-full-freeze.json) preserve the chronology.

This public copy excludes fonts and local helpers. Machine roots were normalized and event JSONL files became JSON arrays. The [publication manifest](PUBLICATION-MANIFEST.json) maps original hashes to published hashes. Original freeze records refer to the original local pack; PNGs are byte-identical copies. No user-authored private conversations are included.
