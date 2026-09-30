# Composition browser verification

The three generated application recipes were opened in Chrome on macOS through CUA using exact font assets staged on localhost. Each recipe passed its SHA-256 font gate before becoming visible. All 34 role checks across six views matched the expected scoped font aliases. The complete observations, hashes, and staging receipt are in [browser-verification.json](browser-verification.json).

The initial editorial recipe retained its fixed canvas width on a 390px viewport, producing a 1088px document and clipping the right side ([before](editorial-mobile-before.png)). The generated CSS now constrains the composition to the viewport, stacks columns below 640px, reduces outer padding, and scales headings larger than 48px according to the documented recipe. Dense tables retain their column widths inside a focusable horizontal scroll region with an overflow hint. A real keyboard Right input moved the interface table from 0px to 40px scroll offset.

| Example | Desktop, 1280 × 900 | Mobile viewport, 390 × 844 |
| --- | --- | --- |
| Editorial | [Screenshot](editorial-desktop.png) | [Screenshot](editorial-mobile.png) |
| Dense interface | [Screenshot](interface-desktop.png) | [Screenshot](interface-mobile.png) |
| Poster | [Screenshot](poster-desktop.png) | [Screenshot](poster-mobile.png) |

All final views had document width equal to viewport width. Exact face identities, axes, and features were preserved; responsive browser size adjustments are recorded separately from the fixed-canvas PNG settings. The application recipes and deterministic previews are in [composition-examples](../composition-examples/).

These are actual Chrome screenshots, distinct from the unhinted HarfBuzz/FreeType preview PNGs. The mobile views use viewport emulation, not a physical device. Native Windows and browser raster equivalence were not verified. IAB was unavailable for this run. Font files remain in ignored local staging and are absent from this evidence directory. The temporary browser tab was closed, viewport settings reset, and localhost server stopped after verification.
