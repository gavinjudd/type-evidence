import json

import pytest

from type_evidence.library import import_local, merge_sources
from type_evidence.cli import parser, run
from type_evidence.catalog import Catalog
from test_catalog import make_font


def test_import_owned_fonts_preserves_other_sources_and_bytes(tmp_path):
    first = tmp_path / 'first'; first.mkdir()
    second = tmp_path / 'second'; second.mkdir()
    make_font(first / 'font.ttf', family='First')
    make_font(second / 'font.ttf', family='Second')
    before = (second / 'font.ttf').read_bytes()
    library = tmp_path / 'library'
    import_local(first, 'first', library)
    result = import_local(second, 'second', library, 'https://example.com/foundry')
    assert result['sources'] == 2 and not result['files_copied']
    assert (second / 'font.ttf').read_bytes() == before
    assert import_local(second, 'second', library, 'https://example.com/foundry')['sources'] == 2
    source_rows = json.loads((library / 'sources.local.json').read_text())
    assert [row['id'] for row in source_rows] == ['first', 'second']


def test_conflicting_id_and_malformed_config_preserve_existing_bytes(tmp_path):
    first = tmp_path / 'first'; first.mkdir()
    second = tmp_path / 'second'; second.mkdir()
    library = tmp_path / 'library'
    import_local(first, 'owned', library)
    config = library / 'sources.local.json'
    before = config.read_bytes()
    with pytest.raises(ValueError, match='another root'):
        import_local(second, 'owned', library)
    assert config.read_bytes() == before
    with pytest.raises(ValueError, match='root'):
        merge_sources(config, [{'id':'bad'}])
    assert config.read_bytes() == before
    config.write_text('{}')
    with pytest.raises(ValueError, match='list'):
        import_local(first, 'owned', library)
    assert config.read_text() == '{}'


@pytest.mark.parametrize('ident,url', [('../bad',''), ('bad name',''), ('a','http://example.com'),
    ('a','https://user:secret@example.com'), ('a','https://example.com?token=private')])
def test_invalid_registration_is_rejected_without_writes(tmp_path, ident, url):
    with pytest.raises(ValueError):
        import_local(tmp_path, ident, tmp_path / 'library', url)
    assert not (tmp_path / 'library').exists()


def test_cli_import_and_index_makes_exact_owned_faces_available(tmp_path):
    fonts = tmp_path / 'owned'; fonts.mkdir()
    make_font(fonts / 'paid.ttf', family='Owned Commercial Fixture')
    db = tmp_path / 'catalog.sqlite'
    result = run(parser().parse_args(['--catalog',str(db),'import-local',str(fonts),
        '--id','owned','--library',str(tmp_path / 'library'),'--index','--workers','1']))
    assert result['index']['faces'] == 1
    cat = Catalog(db)
    try:
        face = cat.all()[0]
        assert face['family'] == 'Owned Commercial Fixture'
        assert cat.resolve(face['id'])['path'] == str(fonts / 'paid.ttf')
        assert face['rights']['status'] == 'unknown'
    finally:
        cat.close()


def test_large_fetch_keeps_complete_reports_on_disk_and_bounds_cli_output(tmp_path, monkeypatch):
    from type_evidence import sources
    rows = [{'id':f'source-{i}', 'root':str(tmp_path / str(i)), 'commit':'a'*40, 'url':'https://example.com/fonts'} for i in range(40)]
    monkeypatch.setattr(sources, 'fetch', lambda *args, **kwargs: rows)
    def prepared(root, destination, ident, commit, url):
        return {'id':ident+'-derived','root':str(destination),'commit':commit,'url':url,
                'report':{'derived_files':1,'issues':['reported issue']}}
    monkeypatch.setattr(sources, 'prepare', prepared)
    result = run(parser().parse_args(['--catalog',str(tmp_path / 'custom.sqlite'),'fetch','--pack','all-open','--library',str(tmp_path / 'library')]))
    assert len(result['preparation']) == 30
    assert result['preparation_total'] == 40 and result['preparation_truncated']
    assert result['preparation_summary']['derived_files'] == 40
    assert result['preparation_summary']['issues'] == 40
    saved = json.loads((tmp_path / 'library/sources.local.json').read_text())
    assert sum('report' in row for row in saved) == 40
    assert result['next_argv'][1:3] == ['--catalog',str(tmp_path / 'custom.sqlite')]
