# Held-out typography evaluation, v0.2

These three authored briefs and their small project fixtures were frozen before the evaluator or implementation coordinator saw their text. The author inspected the existing compositor schema and verified that one ordinary current family had coherent regular/bold faces; the author did not run semantic retrieval, inspect alternatives, or evaluate outcomes on these briefs. This is an internal formative study, not an independent clinical reading study or a statistical proof of better taste.

The coordinator may read this protocol without opening `case-*/brief.json`. The exact briefs remain in those files until a fresh evaluator starts. `sealed-inputs.sha256.json` commits the authored input files. Preserve their initial hashes when copying into review evidence. Record any later input correction as a new revision, with its cause and timing.

## Preparation outside the evaluation budget

1. Freeze the actual catalog and visual index for the whole comparison. Record catalog digest, source commits, face/family counts, visual index coverage and model/checkpoint identity. All three conditions must resolve against that same font collection, including proprietary/unknown-rights material. Do not give the harness a richer corpus than the basic condition.
2. Verify tooling is installed and the renderer operates using a separate smoke sample, never a held-out brief. Warm model loading outside the measured stages and record that choice. Font indexing or dependency installation time is setup time, not a design result.
3. Render each supplied `context/baseline.json` once, save its manifest and exact PNG, and make that same baseline image available in all three conditions. Inspecting the current project is a valid input to unaided work. The baseline's face IDs are part of that existing project, not a recommendation list.
4. Give one fresh agent this protocol, the three briefs, their fixtures and the result template. It must not read harness recommendation examples or the new font-source shortlist before sealing the unaided choices. It may read the minimal exact rendering/resolve documentation needed to execute selections.
5. Run condition A for all three cases before condition B for any case. Run B for all cases before C. Use case order A/B/C in the first condition, B/C/A in the second, C/A/B in the third. This prevents the unaided choices on later briefs being contaminated by earlier catalog browsing. It does not eliminate carryover into later conditions.

## Equal practical budgets

Use the same evaluator model, effort and execution environment. Each case/condition gets at most eight minutes of active investigation and six information operations, each returning at most twelve candidate face/family records. Stop at either budget. The cap is on logical operations and returned records, not shell command count; batching multiple reads into one process does not make them free.

Each case/condition additionally gets four contextual option renders, including the reused baseline, and one final revision render. At most two candidate font families per option, unless the brief explicitly permits and the evaluator justifies a third. Reusing an unchanged baseline does not consume compute time, but it occupies one of the four option slots in every condition. Each option must be inspected at the project size, and the expressive fixture also at its specified reduced size. Saving JSON, extracting already-returned IDs, and writing the event log do not count as information operations.

Record actual wall-clock start/end, active elapsed time, tool calls, failed calls, records seen, candidates rendered and revisions. If latency, a crash or an implementation error exceeds the budget, report it; do not silently grant only one condition extra work. Necessary operational recovery can be run afterward as a separately marked diagnostic. A no-improvement outcome is allowed.

For a shorter exploratory run, the coordinator may reduce all stages to the same lower budget before any case starts, then record that predeclared budget. Never raise one condition's budget after seeing its output.

## Condition A: unaided choice, then exact execution

Before any catalog search, write and timestamp `sealed-plan.json`: the baseline decision, up to three proposed family/style combinations from the agent's existing knowledge, intended role sizes/settings, expected advantages and uncertainties. Include a hash of that file in the stage record. The family names may be familiar; do not encourage novelty or prescribe candidates.

After sealing, exact-name resolution is allowed against the fixed corpus. It returns the requested named family and its actual styles, or an honest not-found result. No alternative recommendations, semantic ranking, family browse, model descriptors, or nearest neighbors are allowed. A name miss is an asset/discovery failure, not a visual-quality failure. The evaluator may fall back to another already-sealed option or retain the existing baseline. It may not change a missing name to a newly discovered near match without logging a protocol violation.

Use the shared exact renderer/compositor to view feasible sealed options and refine their settings. This separates the effect of discovery from the correctness of rendering; it does not measure the compositor as a unique harness advantage.

## Condition B: basic access to the same fonts

Allow a conventional bounded catalog view: family names, declared style/weight/width, Unicode coverage, observed styles and exact IDs. Permit literal family-name matching, non-ranked metadata filters, stable alphabetical or content-hash pagination, and exact rendering. State which ordering is used. Unknown metadata stays visible in an unfiltered browse.

Do not use the new semantic/visual index, its generated descriptions or scores, similarity/refinement tools, role/context heuristic ranking, or outputs saved by condition C. Do not relabel a harness-ranked shortlist as basic access. Record the actual browsing query, response order and families seen, so this condition is auditable.

Before inspecting candidate renders, seal the candidate options and their expected fit. The agent may revise after viewing within the shared budget, preserving the initial sealed plan. The goal is to learn whether the catalog's availability alone changes a decision and whether simple browsing can find useful unfamiliar fonts.

## Condition C: complete harness

Allow CLI or MCP discovery, content-based visual ranking/descriptions, measured context preferences, exact constraints, pagination, exclusions, similar/avoid references, and exact composition rendering, against the same frozen collection.

Before inspecting candidate renders, seal the candidate options, reasons and uncertainties. Record the actual initial query, all results seen, which IDs were rendered, how the search was refined, and why any replacement or retained baseline won. Failed initial results are valuable evidence. A second family is not required; novelty and a higher search score do not establish better design.

Use a representative actual brief text and the intended role size/language. The full project can require separate roles instead of requiring a display font to cover characters it never renders. Exact resolved styles and language settings remain mandatory in all conditions.

## Stage records and final deliverables

Create `results/<condition>/<case>/` containing:

- `sealed-plan.json` written before candidate image inspection, with timestamp/hash and chosen or proposed families/styles.
- `events.jsonl` with timestamp, operation, query/filters, exact candidates returned, image inspections, failures, refinements and budget use.
- `result.json` following `result-template.json`; do not overwrite an earlier choice without retaining its revision.
- Initial option and final composition specifications, manifests, exact PNGs and implementation CSS/recipes. Never copy font binaries into the evidence package.
- A short observation explaining the final choice, any baseline retention and the best plausible counterargument.

For each chosen role, record exact face ID and file hash, actual weight/italic state, axes, features, language/direction, size, line height, and the role's actual text coverage. The fixture HTML/CSS is an implementation surface: bind the exact verified assets before claiming a browser result. The compositor PNG is not proof that a browser produces identical layout. Browser implementation or physical print checks that were not run remain unverified.

## Separate outcome categories

**Asset correctness:** requested family present/absent; real style available/unavailable; Unicode coverage; shaping/render success; exact-byte verification; synthetic style or fallback prohibited. These can be mechanically checked and should be reported as counts and concrete failures.

**Discovery:** unique families actually seen/rendered, previously unfamiliar families considered, query intent and negation respected, recovery from an initial miss, and viable alternatives found within budget. Familiarity is self-report. More unusual names or larger candidate counts are not automatically better.

**Composition/implementation:** clipping, overlap, text/geometry constraints, hierarchy clarity, intended size, visible language-specific glyph distinctions, numerical comparison, exact reproducible settings, and how a pair behaves together. Inspect full compositions, not only specimens. Cmap alone is not a visual or shaping pass.

**Subjective design:** record 1–5 assessments with one concrete observation each for audience/context fit, intended tone, hierarchy, and coherence of roles/pairing. A single family is judged on role coherence, not penalized for lacking a pair. Also record an overall preference, confidence and strongest counterargument. Do not convert subjective scores into an objective quality claim.

Where practical, ask a second fresh judge to inspect anonymized final composition PNGs in randomized order without names, rankings or condition labels, along with the same brief. Save the randomization seed and mapping separately. Report disagreement and ties. If only the selecting agent judges, label the results self-assessment.

## Interpretation and iteration

The same agent sees the conditions sequentially, so later stages benefit from earlier ideas, candidates and familiarity with the layout. The fixed corpus, matched budgets and sealed choices reduce confounding but do not remove it. This design is formative and cannot attribute all C-over-A improvement to the harness. State explicitly whether C reused a candidate first discovered in B or a family proposed in A.

Do not claim improvement from an available file, green test, attractive standalone specimen, extra candidate, or search score. Compare final compositions and report ties, baseline retention, failed aesthetic directions and operational friction. Missing assets and weak design are different failures.

Freeze first-pass results before changing the harness in response. Re-runs on these same briefs become post-feedback diagnostics, not new held-out evidence. For a fresh holdout claim after tuning, commission a new brief from an unexposed author. Any unresolved scope, platform or evaluator limitations belong in the report.
