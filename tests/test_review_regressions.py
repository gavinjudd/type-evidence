"""Independent regression cases found during review of exact resolution/discovery."""
import io
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from fontTools.ttLib import TTCollection, TTFont

from test_catalog import make_font
from test_discovery import face
from type_evidence.catalog import Catalog, index_sources
from type_evidence.discovery import search


def test_required_styles_honor_excluded_companion_ids():
    fonts = [face('regular'), face('bold', style='Bold', weight=700)]
    result = search(fonts, {'text': 'ABC', 'weight': 400, 'exclude': ['bold'],
                            'required_styles': [{'weight': 700, 'italic': False}]})
    assert result['status'] == 'no_matches'


def test_family_versions_do_not_fill_a_diverse_shortlist():
    fonts = [face(f'a{i}', family='Same Family', family_key=f'version{i}') for i in range(8)]
    fonts += [face('z', family='Different Family')]
    result = search(fonts, {'limit': 4})
    names = [font['family'] for font in result['candidates']]
    assert names.count('Same Family') == 1
    assert 'Different Family' in names


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), float('-inf'), True, False])
def test_nonfinite_or_boolean_metrics_are_not_measured_evidence(bad):
    result = search([face('a', metrics={'x_height_em': bad, 'average_advance_em': bad})],
                    {'query': 'high x-height compact'})
    candidate = result['candidates'][0]
    assert candidate['metrics']['x_height_em'] is None
    assert candidate['metrics']['average_advance_em'] is None
    assert not any(r['basis'].startswith('measured') for r in candidate['reasons'])


def test_partial_collection_parse_issues_survive_cache_rebuild(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    valid = tmp_path / 'valid.ttf'; invalid = tmp_path / 'invalid.ttf'
    make_font(valid); make_font(invalid, family='Broken')
    collection = TTCollection()
    collection.fonts = [TTFont(valid), TTFont(invalid)]
    del collection.fonts[1]['hmtx']
    collection.save(source / 'mixed.ttc')
    for font in collection.fonts: font.close()
    target = tmp_path / 'catalog.sqlite'
    spec = [{'id': 'fixture', 'root': str(source)}]
    initial = index_sources(spec, target, workers=1)
    assert initial['faces'] == 1
    assert initial['issue_counts']['font-parse-or-render-failed'] == 1
    rebuilt = index_sources(spec, target, workers=1)
    assert rebuilt['issue_counts'].get('font-parse-or-render-failed') == 1
    cat = Catalog(target)
    try:
        assert cat.issues()[0]['face_index'] == 1
    finally:
        cat.close()


def test_stats_summarizes_derivations_instead_of_dumping_source_manifest(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    make_font(source / 'face.ttf')
    derivations = {f'path-{i}.ttf': {'original_path': 'X' * 1000} for i in range(1000)}
    derivations['face.ttf'] = {'original_path': 'upstream-face.ttf'}
    target = tmp_path / 'catalog.sqlite'
    report = index_sources([{'id': 'derived', 'root': str(source), 'derivations': derivations}], target, workers=1)
    assert 'derivations' not in report['sources'][0]
    assert len(json.dumps(report)) < 20000


def test_upstream_path_survives_portable_source_materialization(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    make_font(source / 'percent%3F.ttf')
    target = tmp_path / 'catalog.sqlite'
    index_sources([{'id': 'portable', 'root': str(source),
                    'upstream_paths': {'percent%3F.ttf': 'percent?.ttf'}}], target, workers=1)
    cat = Catalog(target)
    try:
        resolved = cat.resolve(cat.all()[0]['id'])
        assert resolved['provenance']['upstream_path'] == 'percent?.ttf'
    finally:
        cat.close()


def test_rebuild_can_replace_an_old_schema_without_discarding_sources(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    make_font(source / 'face.ttf')
    target = tmp_path / 'catalog.sqlite'
    spec = [{'id': 'fixture', 'root': str(source)}]
    index_sources(spec, target, workers=1)
    # SQLite's transaction context manager commits but does not close a handle.
    # The fixture itself must release it before testing atomic replacement.
    with closing(sqlite3.connect(target)) as db:
        with db:
            db.execute("UPDATE meta SET value='0' WHERE key='schema'")
    report = index_sources(spec, target, workers=1)
    assert report['faces'] == 1


@pytest.mark.parametrize('schema_state', ['old', 'invalid-json', 'missing-row', 'missing-table'])
def test_failed_catalog_initialization_closes_connection_before_rebuild(tmp_path, monkeypatch, schema_state):
    source = tmp_path / 'source'; source.mkdir()
    make_font(source / 'face.ttf')
    target = tmp_path / 'catalog.sqlite'
    with closing(sqlite3.connect(target)) as db:
        if schema_state != 'missing-table':
            db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT)')
            if schema_state != 'missing-row':
                db.execute('INSERT INTO meta VALUES (?, ?)',
                           ('schema', '0' if schema_state == 'old' else 'not JSON'))
        db.commit()
    connect = sqlite3.connect
    connections = []

    def tracked_connect(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)  # Retain it so GC cannot hide a leak.
        return connection

    monkeypatch.setattr(sqlite3, 'connect', tracked_connect)
    try:
        with pytest.raises((ValueError, sqlite3.DatabaseError)):
            Catalog(target)
        with pytest.raises(sqlite3.ProgrammingError, match='closed'):
            connections[0].execute('SELECT 1')
        report = index_sources([{'id': 'fixture', 'root': str(source)}], target, workers=1)
        assert report['faces'] == 1
        for connection in connections:
            with pytest.raises(sqlite3.ProgrammingError, match='closed'):
                connection.execute('SELECT 1')
        with closing(Catalog(target)) as catalog:
            assert catalog.stats()['sources'][0]['id'] == 'fixture'
            assert catalog.get(catalog.all()[0]['id'])['family'] == 'Fixture'
    finally:
        for connection in connections:
            connection.close()


def test_pin_source_preserves_utf8_lock_under_a_legacy_locale(tmp_path, monkeypatch):
    from type_evidence import cli, sources
    lock = tmp_path / 'sources.lock.json'
    original = {'id': 'existing', 'note': 'Café İplik 日本語'}
    lock.write_text(json.dumps({'schema': 2, 'sources': [original]}, ensure_ascii=False), encoding='utf-8')
    read_text = Path.read_text

    def legacy_read_text(path, encoding=None, errors=None):
        return read_text(path, encoding=encoding or 'cp1252', errors=errors)

    monkeypatch.setattr(Path, 'read_text', legacy_read_text)
    monkeypatch.setattr(sources, 'pin_github_source', lambda *args: {'id': 'new'})
    args = cli.parser().parse_args(['pin-source', '--repository', 'example/fonts', '--commit', 'a' * 40,
                                    '--paths', 'fonts/example', '--id', 'new', '--lock', str(lock)])
    assert cli.run(args)['added_source'] == 'new'
    result = json.loads(lock.read_text(encoding='utf-8'))
    assert result['sources'] == [original, {'id': 'new'}]


def test_oversize_assets_are_not_counted_as_duplicate_files(tmp_path, monkeypatch):
    import type_evidence.catalog as catalog_module
    source = tmp_path / 'source'; source.mkdir()
    make_font(source / 'face.ttf')
    monkeypatch.setattr(catalog_module, 'MAX_BYTES', 64)
    report = index_sources([{'id': 'fixture', 'root': str(source)}], tmp_path / 'catalog.sqlite', workers=1)
    assert report['issue_counts']['oversize-not-indexed'] == 1
    assert report['exact_duplicate_files'] == 0
