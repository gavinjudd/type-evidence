import hashlib
import json
from pathlib import Path

import pytest

from type_evidence import sources


def record(path, data):
    return dict(path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                git_blob=hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest())


def entry(files):
    return dict(id='curated', url='https://github.com/example/fonts', commit='a' * 40,
                acquisition='github-subtree', selection=['ofl/example'], files=files)


def fetch(tmp_path, value):
    path = tmp_path / 'lock.json'
    path.write_text(json.dumps({'sources': [value]}))
    return sources.fetch(path, tmp_path / 'library')[0]


def test_subset_fetch_is_pinned_portable_and_reusable(tmp_path, monkeypatch):
    data = b'font bytes'
    value = entry([record('ofl/Example/CON.ttf', data), record('ofl/Example/OFL.txt', b'license')])
    calls = []

    def download(url, limit):
        calls.append(url)
        return b'license' if url.endswith('OFL.txt') else data

    monkeypatch.setattr(sources, '_https_bytes', download)
    result = fetch(tmp_path, value)
    assert result['acquisition']['mode'] == 'pinned-github-subtree'
    assert result['upstream_paths'] == {'ofl/Example/%43ON.ttf': 'ofl/Example/CON.ttf'}
    assert (Path(result['root']) / 'ofl/Example/%43ON.ttf').read_bytes() == data
    assert all('/' + 'a' * 40 + '/' in url for url in calls)
    assert fetch(tmp_path, value) == result
    assert len(calls) == 2  # Existing verified files work fully offline.


@pytest.mark.parametrize('change', ['bytes', 'extra', 'manifest', 'symlink'])
def test_subset_preserves_and_refuses_changed_existing_destination(tmp_path, monkeypatch, change):
    data = b'font bytes'
    value = entry([record('Regular.ttf', data)])
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: data)
    result = fetch(tmp_path, value)
    root = Path(result['root'])
    if change == 'bytes':
        (root / 'Regular.ttf').write_bytes(b'user edit')
    elif change == 'extra':
        (root / 'user-note.txt').write_text('keep')
    elif change == 'manifest':
        value['files'] = [record('Regular.ttf', b'different')]
    else:
        (root / 'Regular.ttf').unlink()
        (root / 'Regular.ttf').symlink_to(tmp_path / 'outside.ttf')
    with pytest.raises(ValueError):
        fetch(tmp_path, value)
    assert root.exists()
    if change == 'bytes':
        assert (root / 'Regular.ttf').read_bytes() == b'user edit'
    if change == 'extra':
        assert (root / 'user-note.txt').read_text() == 'keep'


@pytest.mark.parametrize('bad', ['../escape.ttf', '/absolute.ttf', 'a/./font.ttf', 'a//font.ttf', 'a\\font.ttf'])
def test_subset_rejects_unsafe_paths_before_network(tmp_path, monkeypatch, bad):
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('network called'))
    with pytest.raises(ValueError):
        fetch(tmp_path, entry([record(bad, b'font')]))
    assert not (tmp_path / 'library/sources/curated').exists()


@pytest.mark.parametrize('problem', ['sha', 'blob', 'length', 'collision', 'oversize'])
def test_subset_bounds_and_verifies_download_before_publication(tmp_path, monkeypatch, problem):
    data = b'font bytes'
    value = entry([record('Regular.ttf', data)])
    if problem == 'sha':
        value['files'][0]['sha256'] = 'f' * 64
    elif problem == 'blob':
        value['files'][0]['git_blob'] = 'f' * 40
    elif problem == 'length':
        value['files'][0]['bytes'] += 1
    elif problem == 'collision':
        value['files'].append(record('regular.ttf', data))
    else:
        value['files'][0]['bytes'] = sources.MAX_FILE + 1
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: data)
    with pytest.raises(ValueError):
        fetch(tmp_path, value)
    assert not (tmp_path / 'library/sources/curated').exists()


def test_pin_exact_files_and_immediate_font_family_directory(monkeypatch):
    files = {'ofl/example/Example.ttf': b'font', 'ofl/example/OFL.txt': b'license',
             'ofl/example/METADATA.pb': b'metadata', 'custom/readme.md': b'exact file'}

    def api_record(path, kind='file'):
        r = record(path, files.get(path, b''))
        return dict(path=path, type=kind, size=r['bytes'], sha=r['git_blob'])

    def download(url, limit):
        if 'api.github.com' in url:
            if '/contents/ofl/example?' in url:
                return json.dumps([api_record(p) for p in files if p.startswith('ofl/')]
                                  + [api_record('ofl/example/build.py'), api_record('ofl/example/static', 'dir')]).encode()
            return json.dumps(api_record('custom/readme.md')).encode()
        return next(data for path, data in files.items() if url.endswith(path))

    monkeypatch.setattr(sources, '_https_bytes', download)
    lock = sources.pin_github_source('example/fonts', 'a' * 40, ['ofl/example', 'custom/readme.md'], 'curated')
    assert {r['path'] for r in lock['files']} == set(files)
    assert all(r['sha256'] == hashlib.sha256(files[r['path']]).hexdigest() for r in lock['files'])


def test_pin_rejects_truncated_directory(monkeypatch):
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: json.dumps([{}] * 1000).encode())
    with pytest.raises(ValueError, match='truncated'):
        sources.pin_github_source('example/fonts', 'a' * 40, ['ofl/example'], 'curated')


def test_pin_checks_blob_relationship_to_commit(monkeypatch):
    calls = 0

    def download(*_):
        nonlocal calls
        calls += 1
        return json.dumps(dict(path='Regular.ttf', type='file', size=4, sha='0' * 40)).encode() if calls == 1 else b'font'

    monkeypatch.setattr(sources, '_https_bytes', download)
    with pytest.raises(ValueError, match='Git blob'):
        sources.pin_github_source('example/fonts', 'a' * 40, ['Regular.ttf'], 'curated')


@pytest.mark.parametrize('paths', [('Family/a.ttf', 'family/b.ttf'), ('Family', 'Family/a.ttf')])
def test_subset_rejects_cross_platform_directory_collisions(tmp_path, monkeypatch, paths):
    monkeypatch.setattr(sources, '_https_bytes', lambda *_: pytest.fail('network called'))
    with pytest.raises(ValueError, match='collision'):
        fetch(tmp_path, entry([record(p, b'font') for p in paths]))


def test_pin_cli_preserves_existing_lock_and_refuses_duplicate_id(tmp_path, monkeypatch):
    from type_evidence.cli import parser, run
    old = dict(id='original', url='https://github.com/example/original', commit='b' * 40)
    path = tmp_path / 'sources.lock.json'
    path.write_text(json.dumps({'schema': 1, 'sources': [old]}))
    addition = entry([record('Regular.ttf', b'font')])
    monkeypatch.setattr(sources, 'pin_github_source', lambda *_: addition)
    args = parser().parse_args(['pin-source', '--repository', 'example/fonts', '--commit', 'a' * 40,
                                '--paths', 'Regular.ttf', '--id', 'curated', '--lock', str(path)])
    result = run(args)
    assert result['added_source'] == 'curated'
    assert json.loads(path.read_text()) == {'schema': 2, 'sources': [old, addition]}
    before = path.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        run(args)
    assert path.read_bytes() == before
