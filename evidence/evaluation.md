# Fresh-agent evaluation

The harness completed all four local evidence workflows and made the recommendations more concrete. It found usable alternatives the unaided baseline did not name, rejected missing Greek and missing companion styles, and resolved exact files. It did **not** establish that its rankings improve aesthetic quality or reading performance.

This is a formative evaluation by one fresh agent, with subjective visual inspection. It is not a controlled study. The same evaluator first sealed the [unaided baseline](fresh-baseline.json), then read the onboarding material and exercised the harness. No font catalog, web search, or specimen was used before that baseline was sealed. Its SHA-256 is `0e5dae3a8967a48f709b16c87a99dde2b30de4a95ce23181a78ccb97288e8397`.

## What was actually completed

- Four supplied example briefs searched, with the top three alternatives compared and an eligible baseline retained where available.
- Seven final comparisons: primary candidates for all four briefs, plus real bold/italic companions for the three briefs that require them.
- 22 unique exact faces; 25 face entries rendered at three sizes, producing 75 specimen rows.
- 66 successful `inspect`, `family`, and `resolve` calls. All final assets passed the renderer's byte verification; all final manifests report zero missing glyph IDs and no fallback.
- All seven final comparison PNGs opened and inspected, plus mission-text, paragraph, Greek-accent, and contradictory-italic fixtures.

The existing catalog contained 27,454 faces and 8,012 declared family names. Five of the eight baseline families were absent under their exact names: Atkinson Hyperlegible, Literata, Source Serif 4, Orbitron, and Rajdhani. Noto Sans existed by name but had no indexed 400-weight upright face. IBM Plex Sans and Noto Serif were retained as actual baselines. Source Serif Pro was identified as a different, older family; it was not silently substituted for Source Serif 4.

Final sequential searches took 1.54–1.81 seconds each; the seven comparisons took 0.57–0.76 seconds each. Their process wall times totaled 11.571 seconds, including CLI startup. Inspection and deliberation are additional. These are single observations on macOS arm64 with Python 3.12.13, not a performance benchmark. Setup, fetch, and index time were outside this evaluation.

## Decisions after looking at the PNGs

All observations in this table are subjective. Exact IDs, style resolutions, SHA-256 values, source commits, rights states, and timings are in [evaluation.json](evaluation.json).

| Brief | Unaided baseline | Harness candidates inspected | Judgment |
|---|---|---|---|
| Dense operations dashboard | IBM Plex Sans; Atkinson Hyperlegible | Noto Sans Display SemiCondensed; Source Sans Pro; IBM Plex Sans Condensed; IBM Plex Sans baseline | Keep IBM Plex Sans provisionally. Its roomier texture and I/1/l forms are useful. The narrower options save width, but none earns an unconditional pass for strict O/0 discrimination at 14 px. |
| Literary reading | Literata; Source Serif 4 | Noto Serif SemiCondensed; Untitled Serif; Noto Serif Display Condensed | Prototype one family: Noto Serif SemiCondensed with its matching italic. Untitled Serif is a warmer, relaxed alternative. Reject Noto Serif Display Condensed for small body text despite its equal search score. |
| Sci-fi title and mission text | Orbitron; Rajdhani | Election Day Expanded; Martian Mono; ETC Trispace; Inter UI as a mission-text comparator | Election Day's double-line forms make an expressive 32–64 px title but become busy at 14 px. Explore it with Inter UI for mission copy. Martian Mono is the stronger single-family direction. |
| English/Greek museum document | Noto Serif; Noto Sans | Noto Sans Display; Finder; Noto Serif Display; Noto Serif baseline | Keep Noto Serif Regular/Bold. Latin and Greek form a coherent editorial texture. Finder offers a neutral alternative, but this sample supplies no compelling reason to change the baseline. |

The title/text pairing is only an aesthetic hypothesis. It was compared using separate specimens, not verified together in a game interface. Election Day Expanded, ETC Trispace, Untitled Serif, and Finder carry **unknown** rights status in this catalog; their presence is not clearance to use or redistribute them.

The reading paragraph and mission sentence are evaluator-authored fixtures. They test more than a headline, but they are not real product copy or a reading-endurance study.

## Inspect the evidence

- Dashboard: [regular candidates](previews/dashboard-comparison/comparison.png), [bold companions](previews/dashboard-companions/comparison.png).
- Reading: [upright candidates](previews/reading-comparison/comparison.png), [matching italics](previews/reading-companions/comparison.png), [paragraph fixture](previews/reading-paragraph/comparison.png).
- Game: [title candidates](previews/game-comparison/comparison.png), [small mission text](previews/mission-small/comparison.png).
- Museum: [regular candidates](previews/museum-comparison/comparison.png), [bold companions](previews/museum-companions/comparison.png), [accent fixture](previews/greek-decomposed/comparison.png).

The unfamiliar discoveries were useful because their actual behavior differed: Election Day has outlined squared letters, ETC Trispace has unusually wide thin forms, Untitled Serif offers a quieter paragraph texture, and Finder supplies a neutral bilingual alternative. Novelty itself was not treated as a reason to select them.

## Failures and corrections observed during the run

The evaluator reported issues while the implementer was still refining the harness. The final results above were recaptured after the implementer declared the code and catalog stable.

1. **Companion widths initially changed.** Noto Serif Regular was matched to ExtraCondensed Bold; condensed reading faces received normal-width italics. The PNGs made the error visible. Final matching preserves the width: Regular/Bold, SemiCondensed/SemiCondensed Italic, and Condensed/Condensed Italic.
2. **The selected regular face initially changed IDs.** IBM Plex Sans Condensed used a WOFF candidate but a WOFF2 regular companion with a different canonical hash. Both declared the same version/width and had identical sampled metrics. Final matching preserves the selected face for its own style.
3. **Metadata could contradict appearance.** PP Agrandir Grand Italic declared `italic:false` and passed the initial upright search. Its [direct-ID specimen](previews/ambiguous-metadata-italic/comparison.png) is visibly slanted. Final constrained search excludes this contradictory metadata.
4. **Exact family lookup was unclear.** Initially, a missing name such as Literata returned generic alternatives through preference search. Final `search --family Literata` returns `no_matches`; ordinary query output explains that it can return alternatives.
5. **An unnamed candidate appeared in discovery.** It was removed from final recommendations.

The final supplementary checks also confirmed useful refusals: Election Day could not render the museum sample and exited with five missing Greek code points and an explicit no-fallback message. Source Serif Pro could not serve as the reading baseline because its indexed family lacked the required italic. Noto Serif rendered both precomposed and decomposed acute-accent forms in the Greek fixture.

## Limits that remain meaningful

The dashboard example asks for compact/tabular sans metadata; it does not express or measure O/0 confusion. The visual agent must make that judgment and continue searching when it matters. “Warm,” “restrained,” and “literary” were explicitly disclosed as unmodeled; adding them to the game query left its shortlist unchanged. The tool does not secretly understand those aesthetic adjectives.

Equal search scores are not equal design suitability. The fine-stroked condensed display serif remained a poor body-text choice to this evaluator. The tool helped expose that difference through a specimen; its ranking did not decide it.

The renderer validates exact bytes, cmap coverage, shaping, and its own raster output. It does not establish browser, Word, printer, or game-engine equivalence, full Greek coverage, license clearance, or final product acceptance. Only two briefs had eligible rendered baseline families, so this run cannot support a general before/after quality claim.
