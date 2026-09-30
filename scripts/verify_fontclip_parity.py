"""Reproduce CPU FontCLIP parity against a separately supplied official checkout.

Install the visual extra first. This script never downloads assets or imports
the upstream init_model module. Example (use new output paths):

python scripts/verify_fontclip_parity.py --official /path/to/FontCLIP \
  --catalog library/catalog.sqlite --checkpoint library/models/fontclip-original.pt \
  --out /path/to/parity.json --images /path/to/parity-images --verify-git

The official checkout must be at the pinned commit. Required upstream source
files are hash-checked even without --verify-git, allowing a source archive to
be used. --verify-git additionally checks HEAD and tracked source modifications.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import socket
import subprocess
import sys

OFFICIAL_COMMIT = '3d4c6af01f668800d8e4f9f4f753d29c74dad252'
SOURCE_HASHES = {
    'models/__init__.py': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'models/ex_clip.py': '04a736d7e1fad2c0afa38d1ee20dbfda02e5609acfe68bff663bb25e16df0d40',
    'models/ex_clip_multiheadattention.py': 'f1685a4ee0ab06983d197beaf7d6689cb8c2b5a5b20c11c2304b7d84d0d5ed5a',
    'models/lora.py': '6c468621792543191af470e4337911ae6898ca91f3a6a7319807a7d01ce939d1',
    'models/oft.py': '479692bc6bac94bfaee6efb08501a9ee184f16ada6fd36d1b89367467b1c1cf3',
}
PROMPTS = ['serif font', 'sans serif font', 'warm humanist font',
           'restrained editorial serif font', 'geometric futuristic font',
           'playful rounded font', 'high contrast elegant font',
           'monospaced technical font', 'rough handwritten font',
           'not playful font', 'Γραμματοσειρά font', '東京 font']


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify_official(root, verify_git=False):
    checked = {}
    for relative, expected in SOURCE_HASHES.items():
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise ValueError('Missing or symlinked official source: ' + relative)
        # Git on Windows may check text out with CRLF. Normalize only line
        # endings; the rest of every imported upstream file must match exactly.
        digest = hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if digest != expected:
            raise ValueError('Official source differs from pinned commit: ' + relative)
        checked[relative] = digest
    if verify_git:
        def git(*args):
            return subprocess.run(['git', '-C', str(root), *args], check=True,
                                  capture_output=True, text=True, timeout=30).stdout.strip()
        if git('rev-parse', 'HEAD') != OFFICIAL_COMMIT:
            raise ValueError('Official Git HEAD differs from pinned commit ' + OFFICIAL_COMMIT)
        if git('status', '--porcelain', '--untracked-files=no', '--', *SOURCE_HASHES):
            raise ValueError('Official imported source files have tracked modifications')
    return {'expected_commit': OFFICIAL_COMMIT, 'git_verified': verify_git,
            'normalized_lf_sha256': checked}


def verify(args):
    from type_evidence.catalog import Catalog
    from type_evidence.visual import MODEL_SHA256, fold_lora, load_model, _render

    official_root = Path(args.official).expanduser().resolve()
    checkpoint = Path(args.checkpoint).expanduser().resolve()
    output = Path(args.out).expanduser().absolute()
    images = Path(args.images).expanduser().absolute() if args.images else None
    if output.exists() or output.is_symlink():
        raise ValueError('Output already exists; use a new path to preserve earlier evidence')
    if images and (images.exists() or images.is_symlink()):
        raise ValueError('Image directory already exists; use a new path')
    if not 0 <= args.canonical_pairs <= 100:
        raise ValueError('--canonical-pairs must be between 0 and 100')
    source_evidence = verify_official(official_root, args.verify_git)
    checkpoint_hash = sha256(checkpoint)
    if checkpoint_hash != MODEL_SHA256:
        raise ValueError('Checkpoint checksum differs from the pinned released model')

    # Do not permit an upstream import or dependency to fetch another model.
    def blocked_network(*unused_args, **unused_kwargs):
        raise RuntimeError('Network is disabled during parity verification')
    socket.create_connection = blocked_network
    socket.socket.connect = blocked_network
    import torch
    import torch.nn.functional as functional
    from torchvision.transforms import Compose, Resize, CenterCrop, ToTensor, Normalize, InterpolationMode
    sys.path.insert(0, str(official_root))
    from models.ex_clip import ExCLIP
    from models.lora import LoRAConfig

    torch.set_num_threads(2)
    # The checksum gate above runs before any torch.load call.
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)['model_state_dict']
    with contextlib.redirect_stdout(io.StringIO()):
        official = ExCLIP(512, 224, 12, 768, 32, 77, 49408, 512, 8, 12,
                          use_lora_text=True,
                          lora_config_text=LoRAConfig(r=256, alpha=1024, apply_q=True,
                                                      apply_k=True, apply_v=True, apply_out=True))
        strict = official.load_state_dict(state, strict=True)
    official.float().eval()
    ours, preprocess, tokenizer = load_model(str(checkpoint), 'cpu')
    torch.set_num_threads(2)

    def metrics(left, right):
        return {'max_absolute_error': float((left - right).abs().max()),
                'mean_absolute_error': float((left - right).abs().mean()),
                'cosine_similarity': float(functional.cosine_similarity(
                    left.reshape(1, -1), right.reshape(1, -1)).item())}

    tokens = tokenizer(PROMPTS)
    with torch.inference_mode():
        official_text, harness_text = official.encode_text(tokens), ours.encode_text(tokens)
    text_results = [dict(prompt=prompt, **metrics(left, right))
                    for prompt, left, right in zip(PROMPTS, official_text, harness_text)]
    # Same evaluation transform as official init_model, without importing it.
    official_preprocess = Compose([
        Resize(224, interpolation=InterpolationMode.BICUBIC), CenterCrop(224),
        lambda image: image.convert('RGB'), ToTensor(),
        Normalize((.48145466, .4578275, .40821073), (.26862954, .26130258, .27577711)),
    ])
    catalog = Catalog(args.catalog)
    try:
        fonts = catalog.all()
        selected = []
        if args.font_id:
            selected = [catalog.get(ident) for ident in args.font_id]
        else:
            for family in ['Noto Sans', 'Fraunces', 'Recursive']:
                candidates = [font for font in fonts if font['family'] == family and not font['italic']]
                if not candidates:
                    raise ValueError(f'{family} is absent; fetch the expanded sources or pass --font-id')
                candidates.sort(key=lambda font: (not any(origin['source_id'] in
                    {'google-curated-2026', 'arrowtype-recursive-1.085'} for origin in font['origins']), font['id']))
                selected.append(candidates[0])
        if images:
            images.mkdir(parents=True)
        image_results = []
        for number, font in enumerate(selected, 1):
            image, render_evidence = _render(catalog, font)
            filename = f'{number:02d}-{font["id"].split(":")[0][:16]}.png'
            if images:
                image.save(images / filename)
            left = official_preprocess(image).unsqueeze(0)
            right = preprocess(image).unsqueeze(0)
            with torch.inference_mode():
                official_image, harness_image = official.encode_image(left), ours.encode_image(right)
            image_results.append(dict(font_id=font['id'], family=font['family'],
                render_evidence=render_evidence, image_file=filename if images else None,
                preprocess_max_error=float((left - right).abs().max()),
                **metrics(official_image, harness_image)))
        canonical = canonical_checks(catalog, fonts, args.canonical_pairs, _render)
    finally:
        catalog.close()

    # Independent published q/k/v and post-output adapter equations, all layers.
    folded = fold_lora(state)
    x = torch.randn(7, 512, generator=torch.Generator().manual_seed(12345))
    algebra = []
    for layer in range(12):
        prefix = f'transformer.resblocks.{layer}.attn.'
        row = {'layer': layer}
        for index, name in enumerate('qkv'):
            a = state[prefix + name + '_lora_proj_weight_a'].float()
            b = state[prefix + name + '_lora_proj_weight_b'].float()
            extent = slice(index * 512, (index + 1) * 512)
            weight = state[prefix + 'in_proj_weight'].float()[extent]
            bias = state[prefix + 'in_proj_bias'].float()[extent]
            reference = functional.linear(x, weight, bias) + 4 * (x @ a @ b)
            row[name] = metrics(reference, functional.linear(x, folded[prefix + 'in_proj_weight'][extent], bias))
        y = functional.linear(x, state[prefix + 'out_proj.weight'].float(), state[prefix + 'out_proj.bias'].float())
        a = state[prefix + 'out_lora_proj_weight_a'].float()
        b = state[prefix + 'out_lora_proj_weight_b'].float()
        row['out'] = metrics(y + 4 * (y @ a @ b), functional.linear(
            x, folded[prefix + 'out_proj.weight'], folded[prefix + 'out_proj.bias']))
        algebra.append(row)

    report = dict(schema=1, device='cpu', dtype='float32', checkpoint_sha256=checkpoint_hash,
        official_repository='https://github.com/yukistavailable/FontCLIP',
        official_commit=OFFICIAL_COMMIT, official_source_verification=source_evidence,
        torch_version=torch.__version__, official_state_strict_load=str(strict), network_disabled=True,
        official_init_model_imported='models.init_model' in sys.modules,
        architecture='ExCLIP(512,224,12,768,32,77,49408,512,8,12), text LoRA r256 alpha1024 q/k/v/out',
        text=text_results, images=image_results, per_layer_algebra=algebra,
        canonical_render_reuse=canonical,
        scope='CPU float32 embedding and projection parity against official ExCLIP; prompts share tokenizer tensors. This does not validate design judgments or other hardware.')
    checks = text_results + image_results + [row[name] for row in algebra for name in ['q', 'k', 'v', 'out']]
    report['passed'] = (all(row['cosine_similarity'] > .99999 and row['max_absolute_error'] < .001 for row in checks)
                        and all(row['preprocess_max_error'] == 0 for row in image_results)
                        and not report['official_init_model_imported']
                        and canonical['all_masks_equal'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return report


def canonical_checks(catalog, fonts, limit, render):
    from collections import defaultdict
    groups = defaultdict(list)
    for font in fonts:
        if font.get('canonical_hash'):
            groups[font['canonical_hash']].append(font)
    choices = [(len({origin['container'] for font in group for origin in font['origins']}), key, group)
               for key, group in groups.items() if len(group) > 1]
    checks = []
    for _, key, group in sorted(choices, key=lambda item: (-item[0], item[1])):
        if len(checks) >= limit:
            break
        rows, seen = [], set()
        for font in sorted(group, key=lambda font: font['id']):
            container = font['origins'][0]['container']
            if container in seen:
                continue
            seen.add(container)
            try:
                _, evidence = render(catalog, font)
            except (ValueError, OSError, RuntimeError):
                continue
            rows.append(dict(id=font['id'], format=container, font_sha256=font['sha256'],
                             mask_sha256=evidence['mask_sha256'], sample_script=evidence['script'], axes=evidence['axes']))
            if len(rows) == 2:
                break
        if len(rows) == 2:
            checks.append(dict(canonical=key, faces=rows, equal_mask=rows[0]['mask_sha256'] == rows[1]['mask_sha256']))
    return dict(requested_groups=limit, groups_checked=len(checks),
                cross_container_checks=len(checks), all_masks_equal=all(row['equal_mask'] for row in checks),
                groups=checks, scope='Independent exact-byte re-rendering of sampled cross-container canonical pairs; not an exhaustive equivalence proof.')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name in ['official', 'catalog', 'checkpoint', 'out']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--images', help='Optional new directory for the exact rendered sample PNGs')
    parser.add_argument('--verify-git', action='store_true', help='Also require pinned Git HEAD and unchanged imported tracked source')
    parser.add_argument('--font-id', action='append', help='Use an exact catalog face instead of the three standard family probes; repeat as needed')
    parser.add_argument('--canonical-pairs', type=int, default=12, help='Cross-container pairs to re-render; 0 disables, maximum 100')
    args = parser.parse_args()
    try:
        report = verify(args)
    except (ValueError, OSError, ImportError, RuntimeError, subprocess.SubprocessError) as exc:
        print(json.dumps({'error': str(exc), 'type': type(exc).__name__}), file=sys.stderr)
        return 2
    print(json.dumps({'passed': report['passed'], 'report': str(Path(args.out).resolve()),
                      'text_probes': len(report['text']), 'image_probes': len(report['images']),
                      'canonical_pairs': report['canonical_render_reuse']['groups_checked']}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
