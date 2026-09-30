# Harness license, font rights and upstream attribution

## Original harness

The original Type Evidence code and documentation are licensed under the [MIT License](../LICENSE), copyright © 2026 Gavin Judd. The owner approved this grant on 2026-09-30. Keep the copyright and license notice with copies or substantial portions of the software.

This grant covers the original harness work. **It does not grant rights to third-party fonts, model weights, dependencies or other third-party material.** Font binaries and model weights are not distributed in this repository or its review ZIP. Rendered examples demonstrate the harness and retain links to face/source provenance; they do not license the pictured typefaces.

## Fonts and source metadata

The pinned library deliberately preserves mixed open, proprietary and unknown-rights sources. A public GitHub repository, source pin, file hash, embedded notice or catalog entry is not universal permission to use, embed, modify or redistribute a font. Review the applicable authoritative license for the exact face and intended use. Unknown rights stay unknown.

The selected Google Fonts families and Arrow Type Recursive include upstream OFL files in their pinned selections. The [official SIL Open Font License](https://openfontlicense.org/open-font-license-official-text/) specifies its own redistribution, notice and reserved-name conditions. Those terms should not be inferred for the two broad mixed collections or for every file with a familiar family name. See [sources.lock.json](../sources.lock.json) and [collection scope](collection-v2.md).

When contributing a source, submit provenance, a reviewed pin, selected paths and applicable license metadata. Do not upload font binaries, font archives, model weights or unauthorized assets. See [CONTRIBUTING.md](../CONTRIBUTING.md).

## FontCLIP and model weights

Optional visual retrieval is based on [FontCLIP](https://github.com/yukistavailable/FontCLIP/tree/3d4c6af01f668800d8e4f9f4f753d29c74dad252), through an adapter that uses installed [OpenCLIP](https://github.com/mlfoundations/open_clip). Type Evidence records the upstream commit, checkpoint hash and [adapter parity checks](../evidence/v0.2/fontclip-parity.json). The checkpoint is downloaded only by explicit `visual-setup`.

FontCLIP's pinned [upstream licensing section](https://github.com/yukistavailable/FontCLIP/blob/3d4c6af01f668800d8e4f9f4f753d29c74dad252/README.md#L101-L117) describes mixed component licenses: a main MIT license and separate terms for VPT and vector-optimization components. Type Evidence does not vendor those implementations. Its parity script requires a separately supplied official checkout.

**Checkpoint-specific usage terms were not established by this review.** The upstream [download code](https://github.com/yukistavailable/FontCLIP/blob/3d4c6af01f668800d8e4f9f4f753d29c74dad252/setup_data.py#L146-L149) identifies the model file, but its availability does not assign it the harness's MIT license or establish commercial clearance. Consult upstream terms for the intended use. The core toolkit remains available without downloading or using the model.

## Dependencies and third-party code

Core rendering and inspection use [FontTools](https://github.com/fonttools/fonttools), [Pillow](https://github.com/python-pillow/Pillow), [uharfbuzz](https://github.com/harfbuzz/uharfbuzz) and [freetype-py](https://github.com/rougier/freetype-py). The optional visual path also uses [PyTorch](https://github.com/pytorch/pytorch), [torchvision](https://github.com/pytorch/vision), OpenCLIP, [NumPy](https://github.com/numpy/numpy) and [gdown](https://github.com/wkentaro/gdown). Tests use [pytest](https://github.com/pytest-dev/pytest).

These packages are installed separately and retain their own licenses and component notices. The harness MIT file does not replace them. Consult the exact installed versions and their complete distributions when redistributing dependencies, native libraries or a bundled application. Preserve upstream copyright/license notices if copying third-party code in a future contribution.
