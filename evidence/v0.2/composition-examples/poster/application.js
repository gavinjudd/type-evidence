const typeEvidenceRoles = {"eyebrow": {"exact_id": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425:0", "sha256": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425", "face_index": 0, "asset_url": "assets/6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425.ttf", "css_family_alias": "te-6ed23dfdede6b4a9-0-eyebrow", "settings": {"font-family": "\"te-6ed23dfdede6b4a9-0-eyebrow\"", "font-size": "17px", "line-height": "1.4", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#d8e4d1", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "und", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "title": {"exact_id": "5d4ba5e8d894601672d04f1663c66c306e581b12eb60163314d764a2306d1110:0", "sha256": "5d4ba5e8d894601672d04f1663c66c306e581b12eb60163314d764a2306d1110", "face_index": 0, "asset_url": "assets/5d4ba5e8d894601672d04f1663c66c306e581b12eb60163314d764a2306d1110.ttf", "css_family_alias": "te-5d4ba5e8d8946016-0-title", "settings": {"font-family": "\"te-5d4ba5e8d8946016-0-title\"", "font-size": "108px", "line-height": "1.08", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#e8ef7b", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "und", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "dek": {"exact_id": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425:0", "sha256": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425", "face_index": 0, "asset_url": "assets/6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425.ttf", "css_family_alias": "te-6ed23dfdede6b4a9-0-dek", "settings": {"font-family": "\"te-6ed23dfdede6b4a9-0-dek\"", "font-size": "31px", "line-height": "1.3", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#f2f3de", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "und", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "body": {"exact_id": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425:0", "sha256": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425", "face_index": 0, "asset_url": "assets/6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425.ttf", "css_family_alias": "te-6ed23dfdede6b4a9-0-body", "settings": {"font-family": "\"te-6ed23dfdede6b4a9-0-body\"", "font-size": "22px", "line-height": "1.4", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#f2f3de", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "und", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "caption": {"exact_id": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425:0", "sha256": "6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425", "face_index": 0, "asset_url": "assets/6ed23dfdede6b4a9e7e62dcc03ffb3348681b04428ed474f3d68ddf5b46ee425.ttf", "css_family_alias": "te-6ed23dfdede6b4a9-0-caption", "settings": {"font-family": "\"te-6ed23dfdede6b4a9-0-caption\"", "font-size": "15px", "line-height": "1.45", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#c4d1d0", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "und", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}};

(async () => {
  const status = document.getElementById("te-asset-status");
  try {
    if (!window.crypto?.subtle) throw new Error("SHA-256 verification requires a secure context such as localhost HTTP.");
    const assets = new Map();
    for (const role of Object.values(typeEvidenceRoles)) {
      if (!role.direct_webfont_recipe_supported) throw new Error("A collection face needs explicit extraction and re-verification before browser use.");
      if (!assets.has(role.asset_url)) assets.set(role.asset_url, (async () => {
        const response = await fetch(role.asset_url, {credentials: "omit"});
        if (!response.ok) throw new Error("Exact font asset is missing: " + role.asset_url);
        const bytes = await response.arrayBuffer();
        const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
        if (hash !== role.sha256) throw new Error("Font hash mismatch: " + role.asset_url);
        return bytes;
      })());
      const face = new FontFace(role.css_family_alias, await assets.get(role.asset_url), {
        weight: role.settings["font-weight"], style: role.settings["font-style"],
        variationSettings: role.settings["font-variation-settings"],
        featureSettings: role.settings["font-feature-settings"]
      });
      await face.load();
      document.fonts.add(face);
    }
    await document.fonts.ready;
    document.querySelector(".te-composition").hidden = false;
    const updateOverflowHints = () => document.querySelectorAll(".te-table-scroll").forEach(region => {
      region.parentElement.toggleAttribute("data-overflow", region.scrollWidth > region.clientWidth + 1);
    });
    updateOverflowHints();
    window.addEventListener("resize", updateOverflowHints);
    status.textContent = "Exact font assets verified and loaded. Inspect this browser's actual layout and rasterization before release.";
  } catch (error) {
    status.textContent = "Composition hidden to prevent font substitution. " + error.message + " Stage the authorized exact files and serve this folder over localhost HTTP. The verified PNG preview remains available in index.html.";
  }
})();
