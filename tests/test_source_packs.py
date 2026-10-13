import hashlib
import json
from pathlib import Path

import pytest

from type_evidence import sources


def blob(path, data):
    return dict(path=path, bytes=len(data), git_blob=hashlib.sha1(
        b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest())


@pytest.fixture
def collection(tmp_path, monkeypatch):
    files = {'ofl/alpha/Alpha.ttf': b'alpha-font', 'ofl/alpha/OFL.txt': b'license',
             'ofl/beta/Beta.ttf': b'beta-font', 'ofl/beta/OFL.txt': b'license'}
    families = [dict(id='google-' + slug, family=slug.title(), path='ofl/' + slug,
                     license={'spdx': 'OFL-1.1'}, files=[blob(p, d) for p, d in files.items()
                                                      if p.startswith('ofl/' + slug + '/')])
                for slug in ['alpha', 'beta']]
    manifest = dict(collection={'url': 'https://github.com/example/fonts', 'commit': 'a' * 40}, families=families,
                    packs=[dict(id='starter', name='Starter', description='Small pack', families=['google-alpha']),
                           dict(id='all-open', name='All', description='All files', families=['google-alpha', 'google-beta'])])
    monkeypatch.setattr(sources, '_pack_manifest', lambda: manifest)
    return files, manifest


def test_pack_listing_and_plan_are_offline_and_deduplicate(collection, monkeypatch):
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('Network used for a plan'))
    listing = sources.source_packs()
    assert listing['packs'][0]['families'] == 1
    assert listing['packs'][0]['font_files'] == 1
    plan = sources.plan_fetch(packs=['starter', 'all-open'], families=['Alpha', 'ofl/alpha', 'google-beta'])
    assert plan['source_count'] == 2
    assert plan['family_count'] == 2
    assert plan['font_files'] == 2
    assert plan['known_download_bytes'] == sum(len(data) for data in collection[0].values())
    assert plan['unbounded_git_sources'] == 0


def test_pack_selectors_do_not_require_a_legacy_lock(collection, tmp_path):
    assert sources.plan_fetch(tmp_path / 'not-there.json', packs=['starter'])['source_count'] == 1


def test_unknown_selection_fails_before_any_network_or_writes(collection, tmp_path, monkeypatch):
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('Network used'))
    for kwargs in [{'packs': ['missing']}, {'families': ['missing']}, {'families': ['']}]:
        with pytest.raises(ValueError):
            sources.fetch(None, tmp_path / 'library', **kwargs)
    assert not (tmp_path / 'library').exists()


def test_source_id_selection_keeps_legacy_entries_opt_in(collection, tmp_path):
    path = tmp_path / 'sources.lock.json'
    path.write_text(json.dumps({'sources': [dict(id='original', commit='b' * 40, url='https://github.com/example/original')]}))
    assert sources.plan_fetch(path)['unbounded_git_sources'] == 1
    plan = sources.plan_fetch(path, packs=['starter'])
    assert plan['unbounded_git_sources'] == 0
    assert plan['sources'][0]['id'] == 'google-alpha'
    plan = sources.plan_fetch(path, source_ids=['original'], families=['beta'])
    assert plan['source_count'] == 2
    assert plan['unbounded_git_sources'] == 1
    with pytest.raises(ValueError, match='Unknown source IDs'):
        sources.plan_fetch(path, source_ids=['absent'])


def test_tree_pins_record_sha256_and_repeat_offline(collection, tmp_path, monkeypatch):
    files, _ = collection
    calls = []

    def download(url, limit):
        calls.append(url)
        return next(data for path, data in files.items() if url.endswith(path))

    monkeypatch.setattr(sources, '_https_bytes', download)
    first = sources.fetch(None, tmp_path, packs=['starter'], workers=1)
    assert first[0]['acquisition']['mode'] == 'pinned-github-tree'
    receipt = json.loads(Path(first[0]['root'], '.type-evidence-source.json').read_text())
    assert all(r['sha256'] == hashlib.sha256(files[r['path']]).hexdigest() for r in receipt['files'])
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('Network used for verified source'))
    assert sources.fetch(None, tmp_path, families=['ALPHA']) == first
    assert len(calls) == 2


def test_optional_sha256_in_tree_pin_is_also_enforced(collection, tmp_path, monkeypatch):
    files, manifest = collection
    record = manifest['families'][0]['files'][0]
    record['sha256'] = 'f' * 64
    monkeypatch.setattr(sources, '_https_bytes', lambda url, _: next(d for p, d in files.items() if url.endswith(p)))
    with pytest.raises(ValueError, match='SHA-256'):
        sources.fetch(None, tmp_path, packs=['starter'], workers=1)
    record['sha256'] = hashlib.sha256(files[record['path']]).hexdigest()
    result = sources.fetch(None, tmp_path, packs=['starter'], workers=1)
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('Network used'))
    assert sources.fetch(None, tmp_path, packs=['starter'], workers=1) == result


def test_overlapping_packs_expand_without_refetching_or_duplicate_origins(collection, tmp_path, monkeypatch):
    files, _ = collection
    calls = []

    def download(url, limit):
        calls.append(url)
        return next(data for path, data in files.items() if url.endswith(path))

    monkeypatch.setattr(sources, '_https_bytes', download)
    first = sources.fetch(None, tmp_path, packs=['starter'], workers=1)
    expanded = sources.fetch(None, tmp_path, packs=['starter', 'all-open'], workers=1)
    assert expanded[0] == first[0]
    assert len(expanded) == 2
    assert len(calls) == 3  # Shared license blob is reused across family roots.


def test_cli_pack_expansion_preserves_imported_sources_and_existing_provenance(collection, tmp_path, monkeypatch):
    from type_evidence.cli import parser, run
    from type_evidence.library import import_local

    files, _ = collection
    owned = tmp_path / 'owned'
    owned.mkdir()
    (owned / 'font.ttf').write_bytes(b'owned original bytes')
    library = tmp_path / 'library'
    registered = import_local(owned, 'owned', library)
    monkeypatch.setattr(sources, '_https_bytes', lambda url, _: next(d for p, d in files.items() if url.endswith(p)))
    command = ['fetch', '--library', str(library), '--workers', '1']
    first = run(parser().parse_args(command + ['--pack', 'starter']))
    assert first['sources'] == 1
    before = json.loads(Path(first['sources_file']).read_text())
    expanded = run(parser().parse_args(command + ['--pack', 'starter', '--pack', 'all-open']))
    rows = json.loads(Path(expanded['sources_file']).read_text())
    assert len({r['id'] for r in rows}) == len(rows) == 5
    assert rows[0] == registered['source']
    assert rows[:3] == before
    assert (owned / 'font.ttf').read_bytes() == b'owned original bytes'


def test_interrupted_family_download_resumes_from_verified_blobs(collection, tmp_path, monkeypatch):
    files, _ = collection
    calls = []

    def download(url, limit):
        calls.append(url)
        if url.endswith('OFL.txt'):
            raise OSError('connection interrupted')
        return files['ofl/alpha/Alpha.ttf']

    monkeypatch.setattr(sources, '_https_bytes', download)
    with pytest.raises(OSError, match='interrupted'):
        sources.fetch(None, tmp_path, packs=['starter'], workers=1)
    assert not (tmp_path / 'sources/google-alpha').exists()
    assert len(list((tmp_path / '.source-cache/git-blobs').iterdir())) == 1
    resumed = []

    def resume(url, limit):
        resumed.append(url)
        return files['ofl/alpha/OFL.txt']

    monkeypatch.setattr(sources, '_https_bytes', resume)
    sources.fetch(None, tmp_path, packs=['starter'], workers=1)
    assert len(resumed) == 1 and resumed[0].endswith('OFL.txt')


def test_modified_cached_blob_is_preserved_and_refused(collection, tmp_path, monkeypatch):
    files, manifest = collection
    record = manifest['families'][0]['files'][0]
    cache = tmp_path / '.source-cache/git-blobs'
    cache.mkdir(parents=True)
    target = cache / record['git_blob']
    target.write_bytes(b'user-edited')
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('Network used'))
    with pytest.raises(ValueError):
        sources.fetch(None, tmp_path, packs=['starter'])
    assert target.read_bytes() == b'user-edited'


def test_modified_tree_manifest_or_source_is_not_overwritten(collection, tmp_path, monkeypatch):
    files, _ = collection
    monkeypatch.setattr(sources, '_https_bytes', lambda url, _: next(d for p, d in files.items() if url.endswith(p)))
    selected = sources.fetch(None, tmp_path, packs=['starter'])
    path = Path(selected[0]['root'], 'ofl/alpha/Alpha.ttf')
    path.write_bytes(b'user font')
    with pytest.raises(ValueError):
        sources.fetch(None, tmp_path, packs=['starter'])
    assert path.read_bytes() == b'user font'


@pytest.mark.parametrize('workers', [0, 17, True, '4'])
def test_download_concurrency_is_bounded(collection, tmp_path, workers):
    with pytest.raises(ValueError, match='workers'):
        sources.fetch(None, tmp_path, packs=['starter'], workers=workers)


def test_bundled_manifest_has_large_reproducible_licensed_corpus():
    manifest = sources._pack_manifest()
    assert len(manifest['families']) >= 1900
    assert len(manifest['collection']['commit']) == 40
    families = {f['id']: f for f in manifest['families']}
    assert len(families) == len(manifest['families'])
    for family in families.values():
        files = {r['path']: r for r in family['files']}
        assert all(p.startswith(family['path'] + '/') for p in files)
        assert set(family['license']['evidence_paths']) <= files.keys()
        assert any(Path(p).suffix in sources.FONT_EXT for p in files)
        assert all(len(r['git_blob']) == 40 and 0 <= r['bytes'] <= sources.MAX_FILE for r in files.values())
        assert all(files[p]['bytes'] > 0 for p in family['license']['evidence_paths'])
    for pack in manifest['packs']:
        assert len(set(pack['families'])) == len(pack['families'])
        assert set(pack['families']) <= families.keys()
    starter = next(p for p in sources.source_packs()['packs'] if p['id'] == 'starter')
    assert starter['families'] >= 15
    assert starter['download_bytes'] < 25 * 1024 * 1024
