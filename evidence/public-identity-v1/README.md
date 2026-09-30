# Public identity and adoption review — revision 1

Reviewed 2026-09-30, following the v0.2.0 implementation and evaluation. This revision improves public identity, documentation and contribution paths. It keeps the repository, Python distribution, import path, CLI, MCP names and runtime version stable. It is not a new recommendation-quality result.

## Identity decision

Retain **Type Evidence** and use **Font Discovery & Typography for AI Agents** as the subtitle. The original name is compact but ambiguous by itself; the subtitle states the intended user and outcome. The sampled collision checks did not establish a competing font toolkit serious enough to justify moving the repository and breaking familiarity. No rename or redirect migration was performed.

Observed on 2026-09-30:

| Check | Result and limit |
| --- | --- |
| GitHub `type-evidence in:name` | 19 token matches; the only exact repository-name match returned was this project. This is a bounded query, not exhaustive clearance. |
| PyPI `type-evidence` and normalized `type_evidence` JSON endpoints | HTTP 404; no package returned. This does not reserve or guarantee a package name. |
| npm `type-evidence` endpoint | HTTP 404. An unrelated scoped `@aurelienbbn/oxlint-plugin-type-evidence` exists for TypeScript lint rules. |
| Web phrase | “Type evidence” also appears in [RBMS typography catalog vocabulary](https://rbms.info/vocabularies/type/tr152.htm). Sampled results did not reveal a clear competing font toolkit. |
| An obvious alternative | “FontScout” is already used by a [Chrome font identifier](https://chromewebstore.google.com/detail/fontscout/jjbdoldmdagddkdhikbnhdfaacdflcfn); a generic new name would not eliminate collision concerns. |

Endpoints: [PyPI](https://pypi.org/pypi/type-evidence/json), [normalized PyPI](https://pypi.org/pypi/type_evidence/json), [npm](https://registry.npmjs.org/type-evidence). These checks are not trademark clearance, search-volume measurements or ranking evidence.

## Search language and comparable projects

Primary project descriptions show that **font discovery**, **visual similarity**, **typography**, **CLI** and **MCP** describe real capabilities in this space:

- [Monotype Fonts MCP](https://github.com/Monotype/fonts-mcp): natural-language discovery through font recommendation tools.
- [FontMap](https://github.com/tfrere/fontmap): FontCLIP visual similarity over Google Fonts.
- [fontfyi](https://github.com/fyipedia/fontfyi): Google Fonts metadata, CSS generation, CLI and MCP.

Type Evidence's useful emphasis is local mixed-source collections, visual refinement, comparisons with actual project text and exact assets that can be applied. It makes no claim to generate fonts, select the universally best design or supersede font licenses. Comparable-project descriptions were inspected for language and positioning; this review did not benchmark their performance.

## Separate discovery mechanisms

| Surface | Implemented approach | What it does not establish |
| --- | --- | --- |
| GitHub discovery | Descriptive About text, implemented-scope topics, README opening, images and useful entry links. | Search position, traffic or community adoption. |
| Web search | A lightweight static documentation page with meaningful HTML text, headings, canonical URL, description and preview metadata. | Index inclusion or rankings. |
| AI-assisted search | The same readable public content, explicit scope, useful examples and stable source links. No invented AI-SEO files. | AI citations or selection by any assistant. |
| Agent integration | Actual CLI/MCP configuration, existing machine-readable tool schemas and bounded AGENTS.md instructions. | Discovery before the agent has reached the repository or a registry listing. |

Current primary guidance: [GitHub topics](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/classifying-your-repository-with-topics), [README guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes), [GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages), [Google AI features](https://developers.google.com/search/docs/appearance/ai-features), [Google AI optimization guidance](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide), [OpenAI crawler roles](https://developers.openai.com/api/docs/bots), [MCP tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools), [MCP registry](https://modelcontextprotocol.io/registry/about).

Google's current guidance does not require a special AI file or schema. OpenAI's search crawler is distinct from its training crawler. This is a project subpath on GitHub Pages; the repository does not control a domain-wide root robots policy. No crawler allowlisting or search-console submission is claimed. No `llms.txt` or speculative registry manifest was added. The toolkit has no published package in the checked registries; package publication was outside this request.

Open Graph metadata serves link-preview consumers. Python package metadata serves build/install tools. Existing MCP schemas serve MCP clients. No extra machine-readable documentation format was invented without a consumer.

## Adoption and contribution changes

- The README leads with discovery and appropriate use, with three actual composition examples and separate visitor/agent/contributor links.
- [Getting started](../../docs/getting-started.md) supports an existing authorized font directory before offering the large pinned collection or optional visual model.
- [CONTRIBUTING.md](../../CONTRIBUTING.md) maps extension points, synthetic-core tests and unassigned starter tasks. Four issue forms and a PR template ask for concrete evidence without font/model uploads or fake community activity.
- The owner explicitly approved MIT for original harness code/documentation. [Licensing](../../docs/licensing.md) separates dependencies, mixed font sources and unestablished checkpoint-specific terms. MIT metadata and its full text are included in local builds and review archives.
- The static page reuses byte-identical rendered examples. It has no JavaScript application, tracking code, external font load or paid hosting dependency.

## Verification scope

Local browser checks cover 1280 × 720 and an emulated 390 × 844 viewport, loaded images, page overflow, navigation and keyboard access. Screenshots are in this directory. The fresh-agent exercise uses synthetic fonts in a separate temporary catalog, not the user's corpus. Package validation builds locally and inspects metadata/license contents without publishing a package.

Live publication receipts, link checks, persona smoke results and CI status are recorded alongside this report. Earlier evaluation artifacts under `evidence/v0.2` remain historical and unchanged. Search indexing, rankings, AI citations, organic adoption and real contributor outcomes remain unmeasured.

## Verified result

| Requirement | Current evidence |
| --- | --- |
| Naming decision and compatibility | Research above; repository, package, CLI, import, MCP and runtime version preserved. |
| Live About, topics, homepage and MIT recognition | [GitHub metadata after](github-after.json); 12 relevant topics. |
| Public documentation | [Live verification](live-verification.json): HTTPS enabled, HTML/CSS/three PNGs byte-equal to source; [published screenshot](published-page.jpg). |
| Visitor and agent setup | [Fresh review](fresh-review/README.md): 13 actual CLI/MCP calls on two synthetic own-font faces, no model dependencies; one catalog-path clarification fixed. |
| Contributor workflow | [Issue-form structure checks](issue-forms.json), live contributing/PR-template detection, 41 focused contributor tests passed. |
| Package metadata and approved license | [Local wheel inspection](package-metadata.json): MIT expression, full license text, README and project URLs; no registry publication. |
| Links and responsive layout | [132 link/anchor checks](link-check.json), [browser receipt](browser-local.json), [desktop](desktop.jpg) and [mobile](mobile.jpg) screenshots. |
| Working behavior and packaging | [CI](ci.json): 268 passed and 10 optional skips on each native platform; runtime source unchanged. First Windows fixture failure and correction retained. |
| Provenance and historical evidence | [Prepublication scan](prepublication-check.json); three byte-identical example images and unchanged historical v0.2 evidence. Fonts/weights remain excluded. |

The anonymous issue entrypoint requires GitHub sign-in, so signed-in rendering of the four YAML forms was not observed. Files are committed and their structure is checked; no issue was submitted and no credentials were entered. No requested change was permission-blocked. Search visibility and community adoption remain unmeasured; deployment and metadata verification are not evidence of ranking or AI citations.
