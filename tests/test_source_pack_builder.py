import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    'build_source_packs', Path(__file__).resolve().parents[1] / 'scripts/build_source_packs.py')
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def record(path, data):
    return dict(path=path, type='blob', mode='100644', size=len(data),
                sha=hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest())


@pytest.fixture
def inputs(tmp_path):
    metadata = {'familyMetadataList': [dict(family='Alpha', category='Sans Serif', subsets=['latin'])]}
    beta_metadata = b'name: "Beta"\ncategory: "SERIF"\nsubsets: "latin"\n'
    records = [record('ofl/alpha/METADATA.pb', b'name: "Alpha"\n'),
               record('ofl/alpha/Alpha.ttf', b'font-alpha'), record('ofl/alpha/OFL.txt', b'license'),
               record('ofl/alpha/DESCRIPTION.en_us.html', b''),
               record('ofl/beta/METADATA.pb', beta_metadata),
               record('ofl/beta/Beta.ttf', b'font-beta'), record('ofl/beta/OFL.txt', b'license')]
    tree = dict(sha='b' * 40, truncated=False, tree=records)
    (tmp_path / 'ofl/beta').mkdir(parents=True)
    (tmp_path / 'ofl/beta/METADATA.pb').write_bytes(beta_metadata)
    return tree, metadata, tmp_path


def test_builder_reconciles_listed_names_and_verified_historical_metadata(inputs):
    tree, metadata, directory = inputs
    first = builder.build_families(tree, metadata, directory)
    assert builder.build_families(tree, metadata, directory) == first
    families, excluded = first
    assert not excluded
    assert [(f['family'], f['listed_on_google_fonts']) for f in families] == [('Alpha', True), ('Beta', False)]
    assert families[1]['category'] == 'Serif'
    assert families[0]['license']['evidence_paths'] == ['ofl/alpha/OFL.txt']
    assert all('sha256' not in r for f in families for r in f['files'])


def test_builder_refuses_unverified_historical_name(inputs):
    tree, metadata, directory = inputs
    (directory / 'ofl/beta/METADATA.pb').write_bytes(b'name: "Different"\n')
    with pytest.raises(ValueError, match='differ from tree'):
        builder.build_families(tree, metadata, directory)


@pytest.mark.parametrize('problem', ['file-size', 'negative-size', 'hash', 'collision', 'family-size', 'empty-license', 'truncated'])
def test_builder_refuses_unusable_or_unbounded_source_records(inputs, problem):
    tree, metadata, directory = inputs
    font = tree['tree'][1]
    if problem == 'file-size':
        font['size'] = builder.MAX_FILE + 1
    elif problem == 'negative-size':
        font['size'] = -1
    elif problem == 'hash':
        font['sha'] = 'not-a-pin'
    elif problem == 'collision':
        tree['tree'].append(dict(font, path='ofl/alpha/alpha.ttf'))
    elif problem == 'family-size':
        tree['tree'].extend(dict(font, path=f'ofl/alpha/Additional{n}.ttf', size=builder.MAX_FILE) for n in range(5))
    elif problem == 'empty-license':
        tree['tree'][2]['size'] = 0
    else:
        tree['truncated'] = True
    with pytest.raises(ValueError):
        builder.build_families(tree, metadata, directory)


def test_missing_license_is_excluded_instead_of_inferred(inputs):
    tree, metadata, directory = inputs
    tree['tree'] = [r for r in tree['tree'] if r['path'] != 'ofl/alpha/OFL.txt']
    families, excluded = builder.build_families(tree, metadata, directory)
    assert [f['family'] for f in families] == ['Beta']
    assert excluded == [dict(path='ofl/alpha', family='Alpha', reason='no-family-license')]


def test_cli_rebuild_and_check_are_deterministic_and_check_never_writes(inputs, monkeypatch, capsys):
    tree, metadata, directory = inputs
    # The fixture isolates serialization/check behavior from the fixed real
    # pack roster, whose exact snapshot rebuild is documented and verified.
    monkeypatch.setattr(builder, 'build_packs', lambda families: [dict(id='fixture', families=[f['id'] for f in families])])
    tree_path = directory / 'tree.json'; tree_path.write_text(json.dumps(tree))
    metadata_path = directory / 'metadata.json'; metadata_path.write_text(json.dumps(metadata))
    output = directory / 'output.json'
    args = ['--tree', str(tree_path), '--metadata', str(metadata_path), '--metadata-dir', str(directory),
            '--commit', 'a' * 40, '--commit-date', '2026-10-12T19:38:43Z', '--snapshot-date', '2026-10-12',
            '--out', str(output)]
    assert builder.main(args) == 0
    first = output.read_bytes()
    assert builder.main(args + ['--check']) == 0
    assert output.read_bytes() == first
    output.write_bytes(b'user changes')
    assert builder.main(args + ['--check']) == 1
    assert output.read_bytes() == b'user changes'
