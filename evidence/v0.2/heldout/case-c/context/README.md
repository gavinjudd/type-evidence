# Project fixture

This is a faithful authored typography context, not a deployed customer product. The brief, copy, colors and layout are frozen before retrieval evaluation.

`baseline.json` is executable by the exact-font composition renderer and contains the current styles. `candidate-template.json` is the editable composition with unresolved candidate IDs. Replace every `CHOOSE_EXACT_..._ID` with a verified face ID, and change corresponding weight/axes only when the exact face supports them. Do not treat unresolved templates as runnable output.

The baseline uses the same coherent Roboto Version 2.137 regular/bold group from the pre-existing collection: it was selected as an ordinary operational current system, without testing alternatives or semantic retrieval on this brief. It is a control condition, not a font recommendation.

`layout.css` and `index.html` provide the small project implementation surface. They intentionally contain no font files or remote font services. The initial CSS refers to the locally provisioned Current Project Sans alias; use the exact implementation recipe generated for each evaluated choice to bind font sources. Opening that HTML before binding files can use a system fallback and is not an exact-font screenshot. The compositor PNG is the exact rendered comparison until browser implementation has been verified separately.

All copy is fictional. Preserve it across comparison conditions. Do not infer a real service, event, claim, or publication from the fixture.
