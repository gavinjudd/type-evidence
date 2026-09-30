const typeEvidenceRoles = {"eyebrow": {"exact_id": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de:0", "sha256": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de", "face_index": 0, "asset_url": "assets/287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de.ttf", "css_family_alias": "te-287ce04f595cf0d6-0-eyebrow", "settings": {"font-family": "\"te-287ce04f595cf0d6-0-eyebrow\"", "font-size": "14px", "line-height": "1.4", "font-weight": "700", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#244542", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "tr", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "title": {"exact_id": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de:0", "sha256": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de", "face_index": 0, "asset_url": "assets/287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de.ttf", "css_family_alias": "te-287ce04f595cf0d6-0-title", "settings": {"font-family": "\"te-287ce04f595cf0d6-0-title\"", "font-size": "28px", "line-height": "1.15", "font-weight": "700", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#244542", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "tr", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "body": {"exact_id": "36244e91159a268a8ef2875cb70a957058d7c1c83bc64969b98c8e3574968025:0", "sha256": "36244e91159a268a8ef2875cb70a957058d7c1c83bc64969b98c8e3574968025", "face_index": 0, "asset_url": "assets/36244e91159a268a8ef2875cb70a957058d7c1c83bc64969b98c8e3574968025.woff", "css_family_alias": "te-36244e91159a268a-0-body", "settings": {"font-family": "\"te-36244e91159a268a-0-body\"", "font-size": "18px", "line-height": "1.5", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#244542", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "tr", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "heading": {"exact_id": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de:0", "sha256": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de", "face_index": 0, "asset_url": "assets/287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de.ttf", "css_family_alias": "te-287ce04f595cf0d6-0-heading", "settings": {"font-family": "\"te-287ce04f595cf0d6-0-heading\"", "font-size": "18px", "line-height": "1.4", "font-weight": "700", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#244542", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "tr", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "caption": {"exact_id": "36244e91159a268a8ef2875cb70a957058d7c1c83bc64969b98c8e3574968025:0", "sha256": "36244e91159a268a8ef2875cb70a957058d7c1c83bc64969b98c8e3574968025", "face_index": 0, "asset_url": "assets/36244e91159a268a8ef2875cb70a957058d7c1c83bc64969b98c8e3574968025.woff", "css_family_alias": "te-36244e91159a268a-0-caption", "settings": {"font-family": "\"te-36244e91159a268a-0-caption\"", "font-size": "15px", "line-height": "1.4", "font-weight": "400", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#244542", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "tr", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}, "button": {"exact_id": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de:0", "sha256": "287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de", "face_index": 0, "asset_url": "assets/287ce04f595cf0d64201986970341b95f5a9c14fd6deb9621c20856eb1bfd3de.ttf", "css_family_alias": "te-287ce04f595cf0d6-0-button", "settings": {"font-family": "\"te-287ce04f595cf0d6-0-button\"", "font-size": "18px", "line-height": "1.4", "font-weight": "700", "font-style": "normal", "font-synthesis": "none", "font-feature-settings": "normal", "font-variation-settings": "normal", "font-optical-sizing": "none", "color": "#ffffff", "text-align": "start", "unicode-bidi": "plaintext"}, "language": "tr", "direct_webfont_recipe_supported": true, "source_asset_not_copied": true}};

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
