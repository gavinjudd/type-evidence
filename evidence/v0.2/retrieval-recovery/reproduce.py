"""Replay six recorded recovery requests against a caller-supplied local library."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--index', required=True, type=Path)
    parser.add_argument('--checkpoint', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--cases', type=Path, default=Path(__file__).with_name('api-recovery.json'))
    args = parser.parse_args()
    if args.out.exists():
        parser.error('--out must be a new directory; historical evidence is never overwritten')
    for path in (args.catalog, args.index, args.checkpoint, args.cases):
        if not path.is_file():
            parser.error(f'Required local input is missing: {path.name}')

    from type_evidence import __version__
    from type_evidence.catalog import Catalog
    from type_evidence.discovery import search
    from type_evidence.render import compare
    from type_evidence.visual import MODEL_SHA256, _render, scores

    if digest(args.checkpoint) != MODEL_SHA256:
        parser.error('Checkpoint differs from the pinned released FontCLIP model')
    recorded = json.loads(args.cases.read_text(encoding='utf-8'))
    args.out.mkdir(parents=True)
    catalog = Catalog(args.catalog)
    results = []
    try:
        for case in recorded['cases']:
            name = case['case'] + '-' + case['variant']
            brief = case['brief']
            reference = case.get('reference_font')
            reference_path = None
            if reference:
                image, evidence = _render(catalog, catalog.get(reference['id']))
                reference_path = args.out / (name + '-input.png')
                image.save(reference_path)
            mapping, status = scores(catalog, brief, index_path=args.index,
                                     checkpoint=args.checkpoint, reference_image=reference_path)
            response = search(catalog, brief, visual_index=mapping)
            candidates = [{key: item[key] for key in
                           ('id', 'family', 'style', 'category', 'score', 'reasons')}
                          for item in response['candidates']]
            result = {'case': case['case'], 'variant': case['variant'], 'brief': brief,
                      'reference_font': reference, 'top_candidates': candidates,
                      'visual_retrieval': status}
            if reference:
                compare(catalog, [item['id'] for item in candidates], brief['text'],
                        args.out / name, sizes=[24, 48])
                result['comparison'] = name + '/comparison.png'
            results.append(result)
            print(name + ': ' + ', '.join(item['family'] for item in candidates), flush=True)
        report = {
            'scope': 'Current-code replay of historical non-held-out recovery cases. References are explicitly selected direction anchors, not zero-shot semantic recovery.',
            'version': __version__,
            'inputs': {name: {'name': path.name, 'sha256': digest(path)} for name, path in
                       [('catalog', args.catalog), ('index', args.index),
                        ('checkpoint', args.checkpoint), ('cases', args.cases)]},
            'cases': results,
        }
        (args.out / 'replay.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    finally:
        catalog.close()


if __name__ == '__main__':
    main()
