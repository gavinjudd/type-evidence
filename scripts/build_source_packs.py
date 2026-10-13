#!/usr/bin/env python3
"""Rebuild the bundled acquisition manifest from saved official inputs, offline.

No network calls, font downloads, or changes to sources.lock.json occur here.
See docs/collection-v3.md for input provenance and a deterministic invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

MAX_FILE = 128 * 1024 * 1024
MAX_FAMILY_BYTES = 512 * 1024 * 1024
MAX_INPUT = 32 * 1024 * 1024
FONT_EXT = {'.ttf', '.otf', '.ttc', '.otc', '.woff', '.woff2'}
LICENSE_NAMES = {'OFL.txt', 'LICENSE.txt', 'LICENCE.txt', 'UFL.txt'}
LICENSE_KINDS = {'ofl': 'OFL-1.1', 'apache': 'Apache-2.0', 'ufl': 'Ubuntu-font-1.0'}


def normalize(value):
    return re.sub('[^a-z0-9]', '', value.lower())


def read_bounded(path, limit):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > limit:
        raise ValueError('Missing or oversized input: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Input exceeded byte bound: ' + str(path))
    return data


def validate_record(record):
    path = record.get('path', '')
    if (not isinstance(path, str) or not path or '\\' in path or '\0' in path
            or PurePosixPath(path).is_absolute()
            or any(p in {'', '.', '..'} for p in path.split('/'))):
        raise ValueError('Unsafe tree file path')
    if (not re.fullmatch('[0-9a-f]{40}', record.get('sha', ''))
            or not isinstance(record.get('size'), int) or isinstance(record['size'], bool)
            or not 0 <= record['size'] <= MAX_FILE):
        raise ValueError('Invalid or oversized tree blob: ' + path)


def unlisted_metadata(path, record, metadata_dir):
    # Accept an ordinary upstream directory layout or the original flat cache.
    nested = Path(metadata_dir) / path / 'METADATA.pb'
    flat = Path(metadata_dir) / (path.replace('/', '__') + '__METADATA.pb')
    data = read_bounded(nested if nested.exists() else flat, 2 * 1024 * 1024)
    digest = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
    if len(data) != record['size'] or digest != record['sha']:
        raise ValueError('Pinned METADATA.pb bytes differ from tree: ' + path)
    text = data.decode('utf-8')
    name = re.search('^name: "(.*)"', text, re.M)
    if name is None:
        raise ValueError('METADATA.pb has no family name: ' + path)
    category = re.search('^category: "(.*)"', text, re.M)
    return (name.group(1), category.group(1).replace('_', ' ').title() if category else 'Unknown',
            re.findall('^subsets: "(.*)"', text, re.M))


def build_families(tree, metadata, metadata_dir):
    """Reconcile live listed names and pinned historical names with licensed blobs."""
    if tree.get('truncated') is not False or not re.fullmatch('[0-9a-f]{40}', tree.get('sha', '')):
        raise ValueError('An untruncated recursive tree with a full tree SHA is required')
    live = {}
    for row in metadata['familyMetadataList']:
        slug = normalize(row['family'])
        if slug in live:
            raise ValueError('Ambiguous normalized family name: ' + slug)
        live[slug] = row
    metadata_records = {}
    for record in tree['tree']:
        path = record['path']
        if re.fullmatch('(ofl|apache|ufl)/[^/]+/METADATA[.]pb', path):
            if record.get('type') != 'blob' or record.get('mode') not in {'100644', '100755'}:
                raise ValueError('Family metadata must be a regular blob')
            validate_record(record)
            parent = path.rsplit('/', 1)[0]
            if parent in metadata_records:
                raise ValueError('Duplicate family metadata path: ' + parent)
            metadata_records[parent] = record
    by_dir = {path: [] for path in sorted(metadata_records)}
    for record in tree['tree']:
        directory = record['path'].rsplit('/', 1)[0]
        if directory in by_dir and record['type'] == 'blob' and record['mode'] in {'100644', '100755'}:
            by_dir[directory].append(record)
    families, excluded = [], []
    for path, records in by_dir.items():
        slug = path.split('/')[1]
        display = live.get(slug)
        if display:
            name, category, subsets = display['family'], display['category'], display['subsets']
        else:
            name, category, subsets = unlisted_metadata(path, metadata_records[path], metadata_dir)
        fonts = [r for r in records if Path(r['path']).suffix.lower() in FONT_EXT]
        licenses = [r for r in records if Path(r['path']).name in LICENSE_NAMES]
        if not fonts or not licenses:
            excluded.append(dict(path=path, family=name,
                                 reason='no-fonts' if not fonts else 'no-family-license'))
            continue
        selected = fonts + licenses + [r for r in records if Path(r['path']).name in
                                       {'METADATA.pb', 'DESCRIPTION.en_us.html'}]
        for record in selected:
            validate_record(record)
        if any(r['size'] == 0 for r in fonts + licenses):
            raise ValueError('Font or license blob is empty: ' + path)
        if len(selected) > 10000 or sum(r['size'] for r in selected) > MAX_FAMILY_BYTES:
            raise ValueError('Family selection exceeds source limits: ' + path)
        paths = [r['path'] for r in selected]
        if len({p.casefold() for p in paths}) != len(paths):
            raise ValueError('Duplicate or case-colliding family paths: ' + path)
        files = [dict(path=r['path'], bytes=r['size'], git_blob=r['sha'])
                 for r in sorted(selected, key=lambda r: r['path'])]
        families.append(dict(id='google-' + slug, family=name, path=path, category=category,
                             subsets=subsets, listed_on_google_fonts=bool(display),
                             license=dict(spdx=LICENSE_KINDS[path.split('/')[0]],
                                          evidence_paths=[r['path'] for r in licenses],
                                          classification_basis='official repository license directory; included exact family license controls use'),
                             files=files))
    if len({f['id'] for f in families}) != len(families):
        raise ValueError('Family source IDs collide across license directories')
    return families, excluded


def build_packs(families):
    by_slug = {f['path'].split('/')[1]: f for f in families}

    def selected_names(text):
        slugs = [normalize(n) for n in text.split('|')]
        missing = [s for s in slugs if s not in by_slug]
        if missing:
            raise ValueError('Curated pack families missing from this snapshot: ' + ', '.join(missing))
        return ['google-' + s for s in slugs]
    packs = []

    def pack(ident, name, description, ids):
        packs.append({'id': ident, 'name': name, 'description': description, 'families': sorted(set(ids))})
    pack('starter', 'Small project starter', '20 families covering interfaces, reading, display, code, Arabic, Devanagari and Thai; inspect real text before choosing.', selected_names('Inter|Manrope|Atkinson Hyperlegible Next|Public Sans|Instrument Sans|Source Serif 4|Newsreader|Literata|Alegreya|Fraunces|Bricolage Grotesque|Space Grotesk|Syne|Unbounded|JetBrains Mono|IBM Plex Mono|Recursive|Noto Sans Arabic|Noto Sans Devanagari|Noto Sans Thai'))
    pack('ui', 'Interfaces and information', 'Sans families with distinct proportions and tone for interfaces, dashboards and product text. Role tags are discovery prompts, not readability certification.', selected_names('Inter|Manrope|Atkinson Hyperlegible|Atkinson Hyperlegible Next|Atkinson Hyperlegible Mono|Public Sans|Instrument Sans|Source Sans 3|IBM Plex Sans|IBM Plex Sans Condensed|Figtree|Geist|Roboto|Roboto Flex|Roboto Condensed|Open Sans|Lato|Nunito Sans|DM Sans|Plus Jakarta Sans|Urbanist|Work Sans|Hanken Grotesk|Onest|Outfit|Epilogue|Sora|Albert Sans|Be Vietnam Pro|Asap|Barlow|Barlow Condensed|Cabin|Cairo|Chivo|Commissioner|Encode Sans|Fira Sans|Golos Text|Karla|Lexend|Libre Franklin|Mulish|Noto Sans|Noto Sans Display|Overpass|Red Hat Text|Signika|Spline Sans|Ubuntu Sans'))
    pack('editorial', 'Reading and editorial', 'Serif and text families spanning contemporary reading, book typography and expressive headings, including every upstream style in each family.', selected_names('Source Serif 4|Newsreader|Literata|Alegreya|Alegreya Sans|Lora|Merriweather|Libre Baskerville|Libre Caslon Text|Libre Caslon Display|Crimson Pro|Crimson Text|EB Garamond|Cormorant|Cormorant Garamond|Bitter|Bodoni Moda|Brygada 1918|Cardo|Castoro|Domine|Eczar|Faustina|Figtree|Frank Ruhl Libre|Fraunces|Gentium Plus|Gelasio|IBM Plex Serif|Instrument Serif|Kreon|Lusitana|Lustria|Noto Serif|Noto Serif Display|Old Standard TT|Petrona|Piazzolla|Playfair Display|PT Serif|Roboto Serif|Rokkitt|Spectral|STIX Two Text|Vollkorn|Yrsa|Zilla Slab'))
    pack('display', 'Display and identity', 'Expressive, condensed, rounded, slab, script and experimental families for headings and identity explorations.', selected_names('Bricolage Grotesque|Space Grotesk|Syne|Unbounded|Anton|Anton SC|Archivo Black|Bebas Neue|Big Shoulders|Big Shoulders Inline|Big Shoulders Stencil|Bungee|Bungee Shade|Bungee Spice|Black Ops One|Bowlby One SC|Bree Serif|Climate Crisis|Dela Gothic One|DM Serif Display|DM Serif Text|Doto|Fascinate|Fugaz One|Gloock|Graduate|Grenze Gotisch|Kanit|Koulen|Lilita One|Limelight|Lobster|Londrina Solid|Monoton|Nabla|Oi|Orbitron|Oswald|Pacifico|Passion One|Permanent Marker|Plaster|Press Start 2P|Racing Sans One|Righteous|Rubik Glitch|Russo One|Silkscreen|Sonsie One|Staatliches|Teko|Tilt Neon|Tilt Prism|Tilt Warp|Titan One|Ultra|Wallpoet|Yeseva One|Young Serif'))
    pack('code', 'Code and tabular exploration', 'All currently listed families categorized as Monospace by Google Fonts. Verify required symbols, figure behavior and language support on the exact face.', [f['id'] for f in families if f['listed_on_google_fonts'] and f['category'] == 'Monospace'])
    pack('global', 'Scripts and multilingual text', 'Families covering Arabic, Hebrew, South and Southeast Asian scripts, Ethiopic, Armenian, Georgian, Japanese, Korean and Chinese. Large CJK families make this pack larger; script coverage remains font-specific.', selected_names('Amiri|Aref Ruqaa|Cairo|Changa|El Messiri|Fustat|IBM Plex Sans Arabic|Noto Kufi Arabic|Noto Naskh Arabic|Noto Nastaliq Urdu|Noto Sans Arabic|Noto Serif Hebrew|Noto Sans Hebrew|Assistant|Heebo|Rubik|Noto Sans Devanagari|Noto Serif Devanagari|Hind|Tiro Devanagari Hindi|Mukta|Noto Sans Bengali|Noto Serif Bengali|Hind Siliguri|Noto Sans Tamil|Noto Serif Tamil|Hind Madurai|Noto Sans Telugu|Noto Sans Kannada|Noto Sans Malayalam|Noto Sans Gujarati|Noto Sans Gurmukhi|Noto Sans Sinhala|Noto Sans Thai|Noto Serif Thai|IBM Plex Sans Thai|Sarabun|Noto Sans Khmer|Noto Serif Khmer|Noto Sans Lao|Noto Sans Myanmar|Noto Serif Myanmar|Padauk|Noto Sans Ethiopic|Noto Serif Ethiopic|Noto Sans Armenian|Noto Serif Armenian|Noto Sans Georgian|Noto Serif Georgian|Noto Sans JP|Noto Serif JP|Noto Sans KR|Noto Serif KR|Noto Sans SC|Noto Serif SC|Noto Sans TC|Noto Serif TC'))
    # Retain the explicit role packs, then sample remaining categories deterministically.
    ids = set((i for p in packs if p['id'] in {'ui', 'editorial', 'display', 'code', 'starter'} for i in p['families']))
    for category in ['Sans Serif', 'Serif', 'Display', 'Handwriting', 'Monospace']:
        candidates = sorted([f for f in families if f['listed_on_google_fonts'] and f['category'] == category and (f['id'] not in ids) and (sum((r['bytes'] for r in f['files'])) < 8 * 1024 * 1024)], key=lambda f: f['family'])
        target = min((300 - len(ids) + 4) // 5 if category != 'Monospace' else 300 - len(ids), len(candidates))
        for n in range(target):
            ids.add(candidates[n * len(candidates) // max(target, 1)]['id'])
    remaining = sorted([f for f in families if f['listed_on_google_fonts'] and f['id'] not in ids and (sum((r['bytes'] for r in f['files'])) < 8 * 1024 * 1024)], key=lambda f: f['family'])
    need = 300 - len(ids)
    ids.update((remaining[i * len(remaining) // max(need, 1)]['id'] for i in range(need)))
    pack('discovery-300', 'Broad discovery: 300 families', 'A bounded cross-category exploration pack: UI, editorial, display and code selections plus deterministic samples from the remaining listed collection. Selection is not a quality ranking.', ids)
    pack('all-open', 'All currently listed open families', 'Every Google Fonts website family matched to a licensed font directory at this pinned commit. Several gigabytes; use a smaller pack or exact family first.', [f['id'] for f in families if f['listed_on_google_fonts']])
    pack('upstream-archive', 'Complete upstream family archive', 'Also includes historical, delisted and experimental family directories present at the pin. This is an archival superset, not a recommendation pack.', [f['id'] for f in families])
    return packs


def build_manifest(tree, metadata_bytes, metadata_dir, *, commit, commit_date, snapshot_date):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('A full lowercase commit SHA is required')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', commit_date):
        raise ValueError('Commit date must be an explicit UTC ISO timestamp')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', snapshot_date):
        raise ValueError('Snapshot date must be explicit YYYY-MM-DD')
    families, excluded = build_families(tree, json.loads(metadata_bytes), metadata_dir)
    packs = build_packs(families)
    return dict(schema=1, collection=dict(
        id='google-fonts-' + snapshot_date, name='Google Fonts official pinned repository',
        url='https://github.com/google/fonts', commit=commit, tree=tree['sha'], commit_date=commit_date,
        family_metadata_url='https://fonts.google.com/metadata/fonts',
        family_metadata_sha256=hashlib.sha256(metadata_bytes).hexdigest(), snapshot_date=snapshot_date,
        available_families=len(families), listed_families=sum(f['listed_on_google_fonts'] for f in families),
        license_note='Per-family license text is fetched with the font. Upstream license classification is not a grant for unrelated proprietary fonts.'),
        packs=packs, families=families, excluded=excluded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True, help='Saved exact recursive Git tree JSON')
    parser.add_argument('--metadata', type=Path, required=True, help='Saved Google Fonts website metadata JSON')
    parser.add_argument('--metadata-dir', type=Path, required=True, help='Pinned METADATA.pb files for unlisted family names')
    parser.add_argument('--commit', required=True, help='Verified full google/fonts commit SHA for the tree')
    parser.add_argument('--commit-date', required=True, help='Commit UTC timestamp, e.g. 2026-10-12T19:38:43Z')
    parser.add_argument('--snapshot-date', required=True, help='Metadata snapshot date, e.g. 2026-10-12')
    parser.add_argument('--out', type=Path, default=Path('type_evidence/source-packs.json'))
    parser.add_argument('--check', action='store_true', help='Require exact existing output bytes; never write')
    args = parser.parse_args(argv)
    try:
        tree = json.loads(read_bounded(args.tree, MAX_INPUT))
        metadata = read_bounded(args.metadata, MAX_INPUT)
        manifest = build_manifest(tree, metadata, args.metadata_dir, commit=args.commit,
                                  commit_date=args.commit_date, snapshot_date=args.snapshot_date)
        data = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        if args.check:
            if not args.out.is_file() or args.out.read_bytes() != data:
                raise ValueError('Generated bytes differ from output: ' + str(args.out))
        else:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_bytes(data)
        print(json.dumps(dict(output=str(args.out), check=args.check, sha256=hashlib.sha256(data).hexdigest(),
                              families=len(manifest['families']), packs=len(manifest['packs']))))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps(dict(error=str(exc))), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
