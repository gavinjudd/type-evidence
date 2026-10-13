"""Catalog admission follows exact rendering, and cached rights stay current."""
import re

import pytest
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables.ttProgram import Program
from PIL import ImageFont

from test_catalog import make_font
from type_evidence import catalog as catalog_module
from type_evidence.catalog import Catalog, file_hash, index_sources
from type_evidence.render import compare


def test_bad_hinting_does_not_exclude_renderable_exact_outlines(tmp_path):
    source = tmp_path / 'fonts'
    source.mkdir()
    path = source / 'bad-hints.ttf'
    make_font(path)
    with TTFont(path) as font:
        # A bounded interpreter error like the observed Kumar One failure.
        # The synthetic outline remains valid; no third-party font is needed.
        table = newTable('prep')
        table.program = Program()
        table.program.fromAssembly(['PUSHW[ ]', '-3', 'JMPR[ ]'])
        font['prep'] = table
        font['maxp'].maxStackElements = 256
        font.save(path)
    original_sha = file_hash(path)
    with pytest.raises(OSError, match='execution context too long'):
        ImageFont.truetype(str(path), 20).getmask('H')

    target = tmp_path / 'catalog.sqlite'
    report = index_sources([{'id': 'fixture', 'root': str(source)}], target, workers=1)
    assert report['faces'] == 1
    assert not report['issue_counts']
    cat = Catalog(target)
    try:
        face = cat.all()[0]
        assert face['id'] == original_sha + ':0'
        assert face['render_probe'] is True
        result = compare(cat, [face['id']], 'H', tmp_path / 'comparison', sizes=[20])
        assert result['no_fallback']['verified'] is True
        assert result['fonts'][0]['glyph_zero_count'] == 0
    finally:
        cat.close()
    assert file_hash(path) == original_sha


def test_ufl_evidence_refreshes_even_when_font_metadata_is_cached(tmp_path, monkeypatch):
    source = tmp_path / 'fonts'
    source.mkdir()
    make_font(source / 'fixture.ttf')
    (source / 'LICENCE.txt').write_text('See the accompanying UFL.txt.', encoding='utf-8')
    license_path = source / 'UFL.txt'
    license_path.write_text('Fixture Ubuntu Font Licence evidence.', encoding='utf-8')
    target = tmp_path / 'catalog.sqlite'
    spec = [{'id': 'fixture', 'root': str(source)}]
    # Model an existing catalog produced before UFL.txt was recognized.
    with monkeypatch.context() as old:
        old.setattr(catalog_module, 'LICENSE_NAMES', re.compile(r'^(licen[sc]e)([._ -]|$)', re.I))
        index_sources(spec, target, workers=1)
    monkeypatch.setattr(catalog_module, 'inspect_file', lambda job: pytest.fail('Cached font was reinspected'))
    rebuilt = index_sources(spec, target, workers=1)
    assert rebuilt['metadata_cache_hits'] == 1
    cat = Catalog(target)
    try:
        evidence = {row['path']: row for row in cat.all()[0]['rights']['nearby_files']}
        assert set(evidence) == {'LICENCE.txt', 'UFL.txt'}
        assert evidence['UFL.txt']['sha256'] == file_hash(license_path)
        assert evidence['UFL.txt']['source_id'] == 'fixture'
        assert evidence['UFL.txt']['scope'] == 'nearby-file; applicability unverified'
        assert cat.all()[0]['rights']['status'] == 'unknown'
    finally:
        cat.close()
