"""Adversarial optional-index integration checks; no downloaded model required."""
import json
import sqlite3

import pytest

from test_catalog import make_font
from type_evidence.catalog import Catalog, index_sources
from type_evidence.operations import discover, visual_status
from type_evidence import visual


def catalog_fixture(tmp_path):
    source = tmp_path / 'fonts'
    source.mkdir()
    for family in ['Futura', 'Alternative', 'Unindexed']:
        make_font(source / (family + '.ttf'), family=family)
    path = tmp_path / 'catalog.sqlite'
    index_sources([{'id': 'fixture', 'root': str(source)}], path, workers=1)
    cat = Catalog(path)
    return cat, {f['family']: f['id'] for f in cat.all()}


def write_index(tmp_path, rows):
    np = pytest.importorskip('numpy')
    db = visual._open_index(tmp_path / 'visual.sqlite')
    evidence = json.dumps({'script': 'Fixture', 'axes': {}, 'model_associations': []})
    for ident, vector in rows:
        db.execute('INSERT INTO vectors VALUES (?,?,?,?)', (ident, ident, np.asarray(vector, dtype='<f4').tobytes(), evidence))
    db.commit()
    db.close()


@pytest.mark.parametrize('damage', ['not_sqlite', 'missing_tables', 'missing_config'])
def test_damaged_optional_index_keeps_auto_search_usable(tmp_path, damage):
    cat, _ = catalog_fixture(tmp_path)
    path = tmp_path / 'visual.sqlite'
    if damage == 'not_sqlite':
        path.write_bytes(b'incomplete or damaged database')
    elif damage == 'missing_tables':
        sqlite3.connect(path).close()
    else:
        db = visual._open_index(path)
        db.execute('DELETE FROM meta')
        db.commit()
        db.close()
    try:
        result = discover(cat, {'query': 'friendly', 'text': 'abc'}, visual='auto')
        assert result['candidates']
        assert result['visual_retrieval']['status'] == 'unavailable'
        assert result['visual_retrieval']['error']
    finally:
        cat.close()


def test_name_lookup_cannot_be_overridden_by_auto_semantic_scoring(tmp_path, monkeypatch):
    cat, ids = catalog_fixture(tmp_path)
    visual._open_index(tmp_path / 'visual.sqlite').close()
    monkeypatch.setattr(visual, 'scores', lambda *args, **kwargs: (
        {ids['Futura']: {'score': -20, 'basis': 'learned-visual'},
         ids['Alternative']: {'score': 20, 'basis': 'learned-visual'}},
        {'status': 'used'}))
    try:
        result = discover(cat, {'query': 'Futura', 'text': 'abc'}, visual='auto')
        assert result['candidates'][0]['id'] == ids['Futura']
        assert result['query_interpretation']['exact_name_match_count'] > 0
    finally:
        cat.close()


def test_partial_index_excludes_stale_rows_and_uses_reference_without_model(tmp_path, monkeypatch):
    np = pytest.importorskip('numpy')
    torch = pytest.importorskip('torch')
    cat, ids = catalog_fixture(tmp_path)
    reference = np.zeros(512); reference[0] = 1
    other = np.zeros(512); other[:2] = [.8, .6]
    write_index(tmp_path, [(ids['Futura'], reference), (ids['Alternative'], other), ('removed-source-id', reference)])
    monkeypatch.setattr(visual, '_dependencies', lambda: (np, torch, None))
    monkeypatch.setattr(visual, 'load_model', lambda *args, **kwargs: pytest.fail('Neighbor query must not load a checkpoint'))
    try:
        scores, status = visual.scores(cat, {'similar_to': ids['Futura']})
        assert set(scores) == {ids['Futura'], ids['Alternative']}
        assert status['indexed_faces'] == 2 and status['catalog_faces'] == 3 and status['unindexed_faces'] == 1
        assert scores[ids['Futura']]['raw_similarity'] == pytest.approx(1)
        assert scores[ids['Alternative']]['raw_similarity'] == pytest.approx(.8)
        result = discover(cat, {'similar_to': ids['Futura'], 'text': 'abc', 'limit': 20}, visual='on')
        assert ids['Unindexed'] in {f['id'] for f in result['candidates']}
    finally:
        cat.close()


def test_status_counts_only_active_catalog_vectors_as_coverage(tmp_path):
    np = pytest.importorskip('numpy')
    cat, ids = catalog_fixture(tmp_path)
    vector = np.zeros(512); vector[0] = 1
    write_index(tmp_path, [(ids['Futura'], vector), ('removed-source-id', vector)])
    try:
        status = visual_status(cat)
        assert status['indexed_current_faces'] == 1
        assert status['catalog_faces'] == 3
        assert status['stale_vectors'] == 1
    finally:
        cat.close()


@pytest.mark.parametrize('damage', ['zero', 'nonunit', 'nan', 'wrong_dimension'])
def test_malformed_vectors_never_produce_fake_cosine_evidence(tmp_path, monkeypatch, damage):
    np = pytest.importorskip('numpy')
    torch = pytest.importorskip('torch')
    cat, ids = catalog_fixture(tmp_path)
    vector = np.zeros(512)
    if damage == 'nonunit': vector[0] = 100
    elif damage == 'nan': vector[0] = float('nan')
    elif damage == 'wrong_dimension': vector = np.ones(2)
    write_index(tmp_path, [(ids['Futura'], vector)])
    monkeypatch.setattr(visual, '_dependencies', lambda: (np, torch, None))
    try:
        with pytest.raises(ValueError, match='[Vv]ector|[Nn]orm|[Mm]alformed'):
            visual.scores(cat, {'similar_to': ids['Futura']})
    finally:
        cat.close()


def test_explicit_visual_failure_stays_visible_instead_of_silent_fallback(tmp_path, monkeypatch):
    cat, _ = catalog_fixture(tmp_path)
    monkeypatch.setattr(visual, 'scores', lambda *args, **kwargs: (_ for _ in ()).throw(ValueError('Model incompatible')))
    try:
        with pytest.raises(ValueError, match='Model incompatible'):
            discover(cat, {'query': 'friendly'}, visual='on')
    finally:
        cat.close()


def test_saved_json_brief_and_mcp_keep_visual_controls_in_parity(tmp_path, monkeypatch):
    from type_evidence import operations
    from type_evidence.cli import parser, run
    from type_evidence.mcp import call
    cat, _ = catalog_fixture(tmp_path)
    brief = {'query': 'friendly', 'text': 'abc', 'visual': 'on', 'reference_image': 'reference.png'}
    path = tmp_path / 'brief.json'
    path.write_text(json.dumps(brief))
    monkeypatch.setattr(operations, 'discover', lambda catalog, brief, **kwargs: {'brief': brief, **kwargs})
    try:
        cli = run(parser().parse_args(['--catalog', str(cat.path), 'search', '--brief', str(path)]))
        mcp = call(cat, tmp_path / 'preview', 'font_search', brief)
        assert cli == mcp
        assert cli['visual'] == 'on' and cli['reference_image'] == 'reference.png'
        explicit = run(parser().parse_args(['--catalog', str(cat.path), 'search', '--brief', str(path),
                                           '--visual', 'off', '--reference-image', 'changed.png']))
        assert explicit['visual'] == 'off' and explicit['reference_image'] == 'changed.png'
    finally:
        cat.close()


@pytest.mark.parametrize('bad_evidence', ['{}', '[]', '{"script":"Latin","axes":{},"model_associations":[null]}'])
def test_malformed_render_evidence_falls_back_in_auto_mode(tmp_path, monkeypatch, bad_evidence):
    np = pytest.importorskip('numpy')
    torch = pytest.importorskip('torch')
    cat, ids = catalog_fixture(tmp_path)
    vector = np.zeros(512); vector[0] = 1
    write_index(tmp_path, [(ids['Futura'], vector)])
    db = sqlite3.connect(tmp_path / 'visual.sqlite')
    db.execute('UPDATE vectors SET evidence=?', (bad_evidence,))
    db.commit(); db.close()
    monkeypatch.setattr(visual, '_dependencies', lambda: (np, torch, None))
    try:
        result = discover(cat, {'similar_to': ids['Futura'], 'text': 'abc'}, visual='auto')
        assert result['candidates'] and result['visual_retrieval']['status'] == 'unavailable'
        with pytest.raises(ValueError):
            discover(cat, {'similar_to': ids['Futura']}, visual='on')
    finally:
        cat.close()


@pytest.mark.parametrize('brief, expected', [
    ({'text': 'English text 123'}, None),
    ({'text': 'English Αθήνα'}, 'Greek'),
    ({'text': 'English مرحبا'}, 'Arabic'),
    ({'text': 'नमस्ते दुनिया'}, 'Devanagari'),
    ({'text': '東京へようこそ'}, 'Japanese'),
    ({'text': 'カタカナ'}, 'Japanese'),
    ({'text': '東京', 'language': 'ja-JP'}, 'Japanese'),
    ({'text': '漢字', 'language': 'zh-Hant'}, 'ChineseTraditional'),
    ({'text': '漢字', 'language': 'ko-KR'}, 'Korean'),
    ({'text': '서울'}, 'Korean'),
    ({'text': 'Добро пожаловать'}, 'Cyrillic'),
    ({'text': 'שלום'}, 'Hebrew'),
    ({'text': 'እንኳን ደህና መጡ'}, 'Ethiopic'),
    ({'text': 'ยินดีต้อนรับ'}, 'Thai'),
])
def test_script_selection_uses_requested_text_and_han_language(brief, expected):
    assert visual.requested_script(brief) == expected


def test_script_specific_sample_never_silently_substitutes_latin():
    from type_evidence.catalog import ranges
    latin = visual.SAMPLES['Latin']
    arabic = visual.SAMPLES['Arabic']
    multilingual = {'coverage': ranges(ord(c) for c in latin + arabic)}
    assert visual._sample(multilingual)[0] == 'Latin'
    assert visual._sample(multilingual, 'Arabic') == ('Arabic', arabic)
    latin_only = {'coverage': ranges(ord(c) for c in latin)}
    assert visual._sample(latin_only, 'Arabic') == (None, None)


def test_missing_script_index_does_not_use_available_latin_index(tmp_path, monkeypatch):
    cat, _ = catalog_fixture(tmp_path)
    visual._open_index(tmp_path / 'visual.sqlite').close()
    monkeypatch.setattr(visual, 'scores', lambda *args, **kwargs: pytest.fail('Latin vectors cannot stand in for Arabic'))
    try:
        result = discover(cat, {'query': 'warm', 'text': 'مرحبا'}, visual='auto')
        assert result['visual_retrieval']['status'] == 'not_configured'
        assert result['visual_retrieval']['requested_sample_script'] == 'Arabic'
        assert '--script Arabic' in result['visual_retrieval']['next']
    finally:
        cat.close()


def test_unsupported_script_never_suggests_an_invalid_indexing_command(tmp_path):
    cat, _ = catalog_fixture(tmp_path)
    try:
        result = discover(cat, {'query': 'warm', 'text': 'Բարի գալուստ'}, visual='auto')
        status = result['visual_retrieval']
        assert status['status'] in {'not_configured', 'unavailable'}
        assert '--script Armn' not in status.get('next', '')
    finally:
        cat.close()


def test_reference_image_cannot_be_silently_ignored_with_visual_off(tmp_path):
    cat, _ = catalog_fixture(tmp_path)
    try:
        with pytest.raises(ValueError, match='reference image requires visual'):
            discover(cat, {'query': 'friendly'}, visual='off', reference_image='reference.png')
    finally:
        cat.close()


def test_mcp_size_budget_rejects_oversized_request_before_render(tmp_path):
    from type_evidence.mcp import call
    cat, ids = catalog_fixture(tmp_path)
    output = tmp_path / 'preview'
    try:
        with pytest.raises(ValueError):
            call(cat, output, 'font_compare', {'ids': [ids['Futura']], 'text': 'abc',
                                              'sizes': [10, 12, 14, 16, 18, 20]})
        assert not output.exists()
    finally:
        cat.close()


def parity_script():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('verify_fontclip_parity',
        Path(__file__).resolve().parents[1] / 'scripts' / 'verify_fontclip_parity.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parity_checkpoint_gate_precedes_torch_load(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    module = parity_script()
    checkpoint = tmp_path / 'wrong.pt'
    checkpoint.write_bytes(b'not the released model')
    monkeypatch.setattr(module, 'verify_official', lambda *args: {})
    monkeypatch.setitem(sys.modules, 'torch', SimpleNamespace(load=lambda *args, **kwargs: pytest.fail('Unverified checkpoint was loaded')))
    args = SimpleNamespace(official=str(tmp_path), checkpoint=str(checkpoint), out=str(tmp_path / 'report.json'),
                           images=None, canonical_pairs=0, verify_git=False)
    with pytest.raises(ValueError, match='Checkpoint checksum'):
        module.verify(args)
    assert not (tmp_path / 'report.json').exists()


def test_parity_reproduction_preserves_existing_report(tmp_path):
    from types import SimpleNamespace
    module = parity_script()
    report = tmp_path / 'report.json'
    report.write_text('{"keep":"existing canonical audit"}')
    before = report.read_bytes()
    args = SimpleNamespace(official=str(tmp_path), checkpoint=str(tmp_path / 'missing.pt'),
                           out=str(report), images=None)
    with pytest.raises(ValueError, match='already exists'):
        module.verify(args)
    assert report.read_bytes() == before


def test_parity_source_gate_accepts_windows_line_endings_and_rejects_changes(tmp_path, monkeypatch):
    import hashlib
    module = parity_script()
    root = tmp_path / 'official'
    (root / 'models').mkdir(parents=True)
    source = root / 'models' / 'lora.py'
    source.write_bytes(b'first\r\nsecond\r\n')
    expected = hashlib.sha256(b'first\nsecond\n').hexdigest()
    monkeypatch.setattr(module, 'SOURCE_HASHES', {'models/lora.py': expected})
    checked = module.verify_official(root)
    assert checked['normalized_lf_sha256'] == {'models/lora.py': expected}
    source.write_bytes(b'first\r\nmodified\r\n')
    with pytest.raises(ValueError, match='differs from pinned commit'):
        module.verify_official(root)
