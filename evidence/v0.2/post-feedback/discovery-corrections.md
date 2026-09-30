# Post-feedback discovery corrections

This is a **non-heldout iteration** informed by the completed first pass. It does not replace the frozen comparison or establish better typography. No new aesthetic assessment, composition, font selection, model build, or corpus change was performed here.

Query and tone now use one interpretation function, with independent negation scopes. A comma preserves a coordinated negative list; a contrast such as “but,” or an explicit comma-led positive clause such as “prefer” or “use,” switches polarity. Sentence, semicolon, and colon boundaries reset it.

| Original observed C search | Objective before/after result |
| --- | --- |
| Case C, initial | Tone words were reported as negative by metadata ranking but positive by visual retrieval. Both now report them positive. The four returned exact IDs are unchanged. |
| Case C, refined | “Ornate” and “delicate” were incorrectly positive. Both are now negative in the ranker and visual prompt. The retained baseline remains Roboto; alternatives change from LatoLatin, Lato, and Amazon Ember to Ubuntu, Noto Sans Display, and IBM Plex Sans Condensed. Their suitability has not been reassessed. |

The original briefs, sanitized original responses, and new actual CLI responses are preserved in `case-c-initial/` and `case-c-refined/`. `manifest.json` records source hashes, timings, commands, response hashes, and the unchanged frozen files. These are the only C searches rerun for this correction.

Hard style/weight requests now reject explicit static name conflicts without rewriting the catalog: Taskforce’s `Outline CondItalic` cannot satisfy upright, and Pangram’s static `Compact Extrabold` cannot satisfy weight 400 despite its numeric declaration. Camel-case words are recognized; exact family prefixes are removed before checking style evidence. Broad discovery and unrequested dimensions remain available. Supported `ital` and `wght` settings take precedence, while out-of-range axes cannot fall back to matching static metadata. Weight-name bands deliberately identify clear conflicts rather than infer an exact weight from names. The two actual observed records and rejection results are in `observed-style-conflicts.json`.

The three Noto regional candidates share an identical indexed Latin mask at default weight 100. That does not establish equivalence for requested weights 400/700, French punctuation, or other scripts. `diversity-investigation.json` records this finding. No diversity ranking change was made; sample duplication remains a limitation.

Validation: 107 focused tests pass across discovery, observed-corpus regressions, and the visual adapter. `git diff --check` is clean for the changed source/test files. All 413 checked frozen evidence, catalog, and index files remain unchanged. The first-pass freeze and results were not overwritten; no font binaries were copied.
