"""Content-addressed font inventory. Source bytes, declarations and observations stay distinct."""
from __future__ import annotations

import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
from concurrent.futures import ProcessPoolExecutor
from collections import Counter, defaultdict

from fontTools.ttLib import TTFont, TTCollection
from fontTools.pens.boundsPen import BoundsPen
from PIL import ImageFont

SCHEMA = 1
EXTENSIONS = {'.ttf', '.otf', '.woff', '.woff2', '.ttc', '.otc'}
MAGICS = {b'\x00\x01\x00\x00', b'OTTO', b'true', b'typ1', b'wOFF', b'wOF2', b'ttcf'}
MAX_BYTES = 128 * 1024 * 1024
LICENSE_NAMES = re.compile(r'^(ofl|licen[sc]e|copying|copyright|eula)([._ -]|$)', re.I)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ranges(points):
    result = []
    for point in sorted(set(points)):
        if result and point == result[-1][1] + 1:
            result[-1][1] = point
        else:
            result.append([point, point])
    return result


def covers(font, text):
    return all(any(a <= ord(c) <= b for a, b in font['coverage'])
               for c in set(text) if c not in '\n\r\t')


def _name(font, *ids):
    if 'name' not in font:
        return ''
    for ident in ids:
        value = font['name'].getDebugName(ident)
        if value:
            return value.replace('\x00', '').strip()
    return ''


def _canonical(font):
    """Same decoded tables with container, signatures and head timestamps ignored.

    Evidence of equivalent table content, not license identity or visual identity.
    Never used to delete a different source binary.
    """
    h = hashlib.sha256()
    for tag in sorted(font.reader.keys()):
        if tag == 'DSIG':
            continue
        data = font.reader[tag]
        if tag == 'head' and len(data) >= 36:
            data = data[:8] + b'\0' * 4 + data[12:20] + b'\0' * 16 + data[36:]
        h.update(str(tag).encode('ascii') + len(data).to_bytes(8, 'big') + data)
    return h.hexdigest()


def _metrics(font, cmap, upm):
    glyphs = font.getGlyphSet()
    result = {}
    for char, label in [('x', 'x_height_em'), ('H', 'cap_height_em')]:
        if ord(char) in cmap:
            pen = BoundsPen(glyphs)
            glyphs[cmap[ord(char)]].draw(pen)
            result[label] = round(pen.bounds[3] / upm, 4) if pen.bounds else None
        else:
            result[label] = None
    widths = [font['hmtx'].metrics[cmap[ord(c)]][0] for c in 'Hamburgefontsiv0123456789' if ord(c) in cmap]
    letters = [font['hmtx'].metrics[cmap[ord(c)]][0] for c in 'ilMW0123456789' if ord(c) in cmap]
    digits = [font['hmtx'].metrics[cmap[ord(c)]][0] for c in '0123456789' if ord(c) in cmap]
    result.update(average_advance_em=round(sum(widths) / len(widths) / upm, 4) if widths else None,
                  mono_measured=len(letters) == 14 and len(set(letters)) == 1,
                  digit_tabular_default=len(digits) == 10 and len(set(digits)) == 1,
                  measurement_sample='Hamburgefontsiv0123456789; default unshaped hmtx advances')
    return result


def _inspect_face(font, sha, index):
    for required in ['head', 'hmtx', 'maxp']:
        if required not in font:
            raise ValueError('missing required table ' + required)
    upm = font['head'].unitsPerEm
    if not 16 <= upm <= 16384:
        raise ValueError('invalid unitsPerEm')
    cmap = {c: g for c, g in (font.getBestCmap() or {}).items() if g != '.notdef' and font.getGlyphID(g) != 0}
    warnings = []
    if not cmap:
        warnings.append('No usable Unicode cmap; excluded from ordinary text discovery')
    family = _name(font, 16, 1) or '(unnamed)'
    if family == '(unnamed)':
        warnings.append('Missing embedded family identity; excluded from default discovery')
    style = _name(font, 17, 2) or '(unnamed)'
    os2 = font.get('OS/2')
    weight = int(getattr(os2, 'usWeightClass', 400))
    width = int(getattr(os2, 'usWidthClass', 5))
    italic = bool(getattr(os2, 'fsSelection', 0) & 1 or font['head'].macStyle & 2)
    vendor = str(getattr(os2, 'achVendID', '')).strip()
    version = _name(font, 5)
    metrics = _metrics(font, cmap, upm)
    panose = getattr(os2, 'panose', None)
    category = 'unknown'
    if metrics['mono_measured']:
        category = 'mono'
    elif panose:
        if panose.bFamilyType == 2:
            category = 'sans' if 11 <= panose.bSerifStyle <= 15 else ('serif' if 2 <= panose.bSerifStyle <= 10 else 'unknown')
        elif panose.bFamilyType == 3:
            category = 'script'
        elif panose.bFamilyType in (4, 5):
            category = 'display'
    license_text = _name(font, 13)
    license_url = _name(font, 14)
    evidence = [{'kind': 'embedded-name-' + str(i), 'text': _name(font, i)} for i in [0, 7, 8, 9, 11, 13, 14] if _name(font, i)]
    combined = (license_text + ' ' + license_url).lower()
    status = 'unknown'
    if 'sil open font license' in combined or 'openfontlicense.org' in combined or 'scripts.sil.org/ofl' in combined or 'apache.org/licenses/license-2.0' in combined:
        status = 'embedded-open-license'
    if re.search(r'personal use only|not for commercial|evaluation only|trial use|demo use|non.commercial', combined):
        status = 'restricted-notice'
    if re.search(r'\b(trial|demo|test)\b', family + ' ' + style, re.I):
        warnings.append('Name contains trial/demo/test; inspect rights and glyph coverage')
    if getattr(os2, 'fsType', 0):
        warnings.append('OS/2 embedding flags set: ' + str(os2.fsType) + '; technical flags are not a license')
    axes = []
    if 'fvar' in font:
        axes = [{'tag': a.axisTag, 'min': a.minValue, 'default': a.defaultValue, 'max': a.maxValue} for a in font['fvar'].axes]
    features = sorted({r.FeatureTag for table in ['GSUB', 'GPOS'] if table in font and font[table].table.FeatureList for r in font[table].table.FeatureList.FeatureRecord})
    canonical = _canonical(font)
    # Validate FreeType can load a decoded face; never a system font lookup.
    sfnt = io.BytesIO()
    font.flavor = None
    font.save(sfnt)
    probe = ImageFont.truetype(io.BytesIO(sfnt.getvalue()), 20)
    sample = ''.join(chr(cp) for cp in sorted(cmap) if 33 <= cp <= 126)[:60]
    if sample:
        probe.getmask(sample)
    family_key = digest(json.dumps([family.casefold(), vendor, version], ensure_ascii=False).encode())[:24]
    return dict(id=f'{sha}:{index}', sha256=sha, face_index=index, family=family, style=style,
                full_name=_name(font, 4), postscript_name=_name(font, 6), vendor=vendor,
                version=version, weight=weight, width_class=width, italic=italic,
                units_per_em=upm, axes=axes, features=features, coverage=ranges(cmap),
                glyph_count=font['maxp'].numGlyphs, unicode_count=len(cmap),
                metrics=metrics, category=category, category_basis='measured sample widths then declared PANOSE',
                family_key=family_key, canonical_hash=canonical,
                rights=dict(status=status, evidence=evidence, review_required=True),
                warnings=warnings, render_probe=True, origins=[])


def inspect_file(job):
    path, sha = job
    logging.getLogger('fontTools').setLevel(logging.ERROR)
    records, errors = [], []
    try:
        with open(path, 'rb') as stream:
            magic = stream.read(4)
        if magic == b'ttcf':
            collection = TTCollection(path, lazy=True)
            fonts = collection.fonts
        else:
            fonts = [TTFont(path, lazy=True, recalcTimestamp=False)]
        try:
            for index, font in enumerate(fonts):
                try:
                    records.append(_inspect_face(font, sha, index))
                except Exception as exc:
                    errors.append(dict(face_index=index, error=type(exc).__name__ + ': ' + str(exc)[:400]))
        finally:
            for font in fonts:
                font.close()
    except Exception as exc:
        errors.append(dict(error=type(exc).__name__ + ': ' + str(exc)[:400]))
    return sha, records, errors


def _safe_path(root, relative):
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts:
        raise ValueError('Source path escapes root')
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Symlink assets are not resolved')
    path = current.resolve()
    if not path.is_relative_to(root):
        raise ValueError('Source path escapes root')
    return path


class Catalog:
    def __init__(self, path):
        self.path = Path(path).resolve()
        if not self.path.is_file():
            raise ValueError(f'Catalog not found: {self.path}. Run index first.')
        self.db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)
        try:
            row = self.db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if row is None:
                raise ValueError('Catalog schema is missing; rebuild with index')
            schema = json.loads(row[0])
            if schema != SCHEMA:
                raise ValueError('Unsupported catalog schema; rebuild with index')
        except BaseException:
            # A failed constructor has no caller-owned Catalog to close. Keep
            # invalid/old catalogs replaceable, including on Windows.
            self.db.close()
            raise

    def close(self):
        self.db.close()

    def all(self):
        return [json.loads(row[0]) for row in self.db.execute('SELECT data FROM fonts ORDER BY id')]

    def get(self, ident):
        row = self.db.execute('SELECT data FROM fonts WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise ValueError('Unknown exact font id: ' + ident)
        return json.loads(row[0])

    def stats(self):
        return json.loads(self.db.execute("SELECT value FROM meta WHERE key='report'").fetchone()[0])

    def issues(self, limit=50):
        return [json.loads(row[0]) for row in self.db.execute('SELECT data FROM issues LIMIT ?', (max(1, min(limit, 1000)),))]

    def resolve(self, ident):
        font = self.get(ident)
        failures = []
        for origin in font['origins']:
            source = json.loads(self.db.execute('SELECT data FROM sources WHERE id=?', (origin['source_id'],)).fetchone()[0])
            try:
                path = _safe_path(Path(source['root']), origin['path'])
                if not path.is_file() or file_hash(path) != font['sha256']:
                    raise ValueError('Asset missing or hash changed; rebuild index')
                return dict(path=str(path), face_index=font['face_index'], sha256=font['sha256'],
                            id=ident, provenance=origin, rights=font['rights'])
            except (OSError, ValueError) as exc:
                failures.append(str(exc))
        raise ValueError('No verified copy of asset: ' + '; '.join(failures))


def index_sources(sources, target, workers=4):
    """Rebuild atomically; exact byte duplicates share faces but retain every origin.

    Reuses immutable content metadata from the previous same-schema catalog.
    Source metadata and license sidecar hashes are always refreshed.
    """
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    seen_sources = set()
    normalized = []
    for source in sources:
        source = dict(source)
        if not source.get('id') or source['id'] in seen_sources:
            raise ValueError('Every source needs a unique id')
        rawroot = Path(source['root']).expanduser()
        if rawroot.is_symlink() or not rawroot.is_dir():
            raise ValueError('Source root must be an existing non-symlink directory')
        source['root'] = str(rawroot.resolve())
        source.setdefault('url', '')
        source.setdefault('commit', '')
        normalized.append(source)
        seen_sources.add(source['id'])
    origins, paths, sidecars = defaultdict(list), {}, {}
    issues, counts = [], Counter()
    for source in normalized:
        root = Path(source['root'])
        for folder, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d != '.git' and not (Path(folder) / d).is_symlink())
            for name in sorted(files):
                path = Path(folder) / name
                relative = path.relative_to(root).as_posix()
                if 'derivations' in source and relative not in source['derivations']:
                    # Preparation preserves old files; only its current manifest is active.
                    # License sidecars can still provide nearby evidence.
                    if not LICENSE_NAMES.match(name):
                        continue
                counts['files_seen'] += 1
                if path.is_symlink():
                    issues.append(dict(source_id=source['id'], path=relative, kind='symlink-skipped'))
                    continue
                try:
                    size = path.stat().st_size
                    with open(path, 'rb') as stream:
                        magic = stream.read(4)
                    if LICENSE_NAMES.match(name) and magic not in MAGICS and path.suffix.lower() not in EXTENSIONS and size <= 1024 * 1024:
                        sidecars[(source['id'], relative)] = dict(path=relative, sha256=file_hash(path), scope='nearby-file; applicability unverified')
                    if magic not in MAGICS:
                        if path.suffix.lower() in EXTENSIONS:
                            issues.append(dict(source_id=source['id'], path=relative, kind='invalid-signature', bytes=size))
                        elif path.suffix.lower() in {'.zip', '.rar', '.7z', '.gz', '.tar', '.pfb', '.pfm', '.dfont', '.suit', '.eot', '.fon'}:
                            issues.append(dict(source_id=source['id'], path=relative, kind='unsupported-or-archive-not-indexed', bytes=size))
                        continue
                    counts['font_files'] += 1
                    if size > MAX_BYTES:
                        issues.append(dict(source_id=source['id'], path=relative, kind='oversize-not-indexed', bytes=size))
                        continue
                    sha = file_hash(path)
                    origin = dict(source_id=source['id'], path=relative, url=source['url'], commit=source['commit'])
                    origin['upstream_path'] = source.get('upstream_paths', {}).get(relative, relative)
                    if relative in source.get('derivations', {}):
                        origin['derivation'] = source['derivations'][relative]
                    container = {b'OTTO':'otf', b'wOFF':'woff', b'wOF2':'woff2', b'ttcf':'collection'}.get(magic, 'ttf')
                    origin['container'] = container
                    if path.suffix.lower() in {'.woff', '.woff2'} and path.suffix.lower()[1:] != container:
                        origin['warning'] = 'Extension disagrees with actual font container: ' + container
                    if path.suffix.lower() not in EXTENSIONS:
                        origin['warning'] = 'Font signature found with unexpected extension'
                    origins[sha].append(origin)
                    paths.setdefault(sha, str(path))
                except OSError as exc:
                    issues.append(dict(source_id=source['id'], path=relative, kind='read-failed', error=str(exc)))
    cached = defaultdict(list)
    cached_failures = []
    if target.is_file():
        try:
            old = Catalog(target)
        except (ValueError, sqlite3.DatabaseError):
            old = None  # Incompatible cache is a miss; old bytes survive until atomic success.
        try:
            for font in old.all() if old else []:
                if font['sha256'] in paths:
                    cached[font['sha256']].append(font)
            for row in old.db.execute('SELECT data FROM issues') if old else []:
                issue = json.loads(row[0])
                if issue.get('kind') == 'font-parse-or-render-failed' and issue.get('sha256') in cached:
                    issue['origins'] = origins[issue['sha256']]
                    cached_failures.append(issue)
        finally:
            if old:
                old.close()
    issues.extend(cached_failures)
    jobs = [(path, sha) for sha, path in sorted(paths.items()) if sha not in cached]
    font_records = [f for group in cached.values() for f in group]
    counts['metadata_cache_hits'] = len(cached)
    if workers == 1:
        results = map(inspect_file, jobs)
        pool = None
    else:
        pool = ProcessPoolExecutor(max_workers=max(1, min(workers, 8)))
        results = pool.map(inspect_file, jobs, chunksize=8)
    try:
        for sha, records, errors in results:
            font_records.extend(records)
            for error in errors:
                issues.append(dict(sha256=sha, origins=origins[sha], kind='font-parse-or-render-failed', **error))
    finally:
        if pool:
            pool.shutdown()
    canonical_groups = defaultdict(list)
    families = defaultdict(list)
    for font in font_records:
        # Keep width subfamilies coherent while preserving version boundaries.
        font['family_key'] = digest(json.dumps([font['family'].casefold(), font['vendor'], font['version'], font['width_class']], ensure_ascii=False).encode())[:24]
        font['origins'] = origins[font['sha256']]
        font['rights']['nearby_files'] = []
        for origin in font['origins']:
            ancestors = [Path(origin['path']).parent, *Path(origin['path']).parent.parents]
            matches = [dict(source_id=origin['source_id'], **sidecar) for (sid, rel), sidecar in sidecars.items()
                       if sid == origin['source_id'] and Path(rel).parent in ancestors]
            font['rights']['nearby_files'].extend(matches)
        canonical_groups[font['canonical_hash']].append(font['id'])
        families[font['family_key']].append(font)
    for font in font_records:
        font['equivalent_table_variants'] = canonical_groups[font['canonical_hash']]
        group = families[font['family_key']]
        font['family_available_styles'] = sorted({(f['weight'], f['italic'], f['style']) for f in group})
        font['family_limits'] = []
        if not any(f['weight'] == 400 and not f['italic'] for f in group):
            font['family_limits'].append('No static regular upright 400 face in this metadata/version group; inspect variable axes')
        if not any(f['italic'] for f in group):
            font['family_limits'].append('No declared italic in this metadata/version group')
        if len(group) == 1:
            font['family_limits'].append('Only one indexed face in this metadata/version group')
    report = dict(schema=SCHEMA, **counts, source_count=len(normalized), unique_files=len(paths),
                  exact_duplicate_files=sum(max(0,len(items)-1) for items in origins.values()), faces=len(font_records),
                  family_groups=len(families), family_names=len({f['family'] for f in font_records}),
                  equivalent_table_groups=sum(len(v) > 1 for v in canonical_groups.values()),
                  rights_counts=dict(Counter(f['rights']['status'] for f in font_records)),
                  category_counts=dict(Counter(f['category'] for f in font_records)),
                  variable_faces=sum(bool(f['axes']) for f in font_records),
                  issue_counts=dict(Counter(i['kind'] for i in issues)),
                  scope='Unicode OpenType/TrueType faces with successful metadata, outline sample and FreeType load probes. No claim all glyphs are correct or families are complete.',
                  sources=[dict(id=s['id'], url=s['url'], commit=s['commit'],
                                acquisition=s.get('acquisition', 'local-directory'),
                                derivative_files=len(s.get('derivations', {})),
                                mapped_upstream_paths=len(s.get('upstream_paths', {}))) for s in normalized])
    staging = target.with_name(target.name + '.building')
    if staging.exists():
        raise ValueError('An index build already exists at ' + str(staging))
    db = sqlite3.connect(staging)
    try:
        db.executescript('CREATE TABLE fonts(id TEXT PRIMARY KEY, data TEXT); CREATE TABLE sources(id TEXT PRIMARY KEY, data TEXT); CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT); CREATE TABLE issues(data TEXT);')
        db.executemany('INSERT INTO fonts VALUES (?,?)', [(f['id'], json.dumps(f, ensure_ascii=False)) for f in font_records])
        db.executemany('INSERT INTO sources VALUES (?,?)', [(s['id'], json.dumps(s)) for s in normalized])
        db.executemany('INSERT INTO meta VALUES (?,?)', [('schema', json.dumps(SCHEMA)), ('report', json.dumps(report))])
        db.executemany('INSERT INTO issues VALUES (?)', [(json.dumps(i, ensure_ascii=False),) for i in issues])
        db.commit()
    except BaseException:
        db.close()
        staging.unlink(missing_ok=True)
        raise
    db.close()
    staging.replace(target)
    return report
