import base64
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import zipfile

import pytest

from type_evidence import sources


FONT = b'\x00\x01\x00\x00' + b'synthetic test font bytes; parser is tested separately'
COMMIT = 'a' * 40


def prepare(tmp_path, files):
    root = tmp_path / 'original'
    root.mkdir()
    for relative, data in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    result = sources.prepare(root, tmp_path / 'derived', 'test', COMMIT)
    return root, result


def make_zip(path, entries):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries:
            archive.writestr(name, data)


def test_base64_decoding_keeps_original_and_exact_provenance(tmp_path):
    encoded = base64.encodebytes(FONT)
    root, result = prepare(tmp_path, {'Font.otf': encoded, 'LICENSE.txt': b'Unknown rights for testing'})
    assert root.joinpath('Font.otf').read_bytes() == encoded
    fonts = [(path, provenance) for path, provenance in result['derivations'].items() if provenance['kind'] == 'font']
    assert len(fonts) == 1
    path, provenance = fonts[0]
    assert path.endswith(hashlib.sha256(FONT).hexdigest() + '.ttf')
    assert Path(result['root'], path).read_bytes() == FONT
    assert provenance['original_sha256'] == hashlib.sha256(encoded).hexdigest()
    assert provenance['source_commit'] == COMMIT
    assert provenance['transform'] == 'base64-decode'
    assert result['report']['license_sidecars'] == 1
    repeat = sources.prepare(root, Path(result['root']), 'test', COMMIT)
    assert repeat['derivations'] == result['derivations']


def test_zip_extracts_only_fonts_and_license_without_upstream_code(tmp_path):
    root = tmp_path / 'original'
    root.mkdir()
    make_zip(root / 'fonts.zip', [('font.woff2', FONT), ('LICENSE.txt', b'Test license'), ('run.py', b'raise Exception()'), ('inner.zip', b'ignored')])
    result = sources.prepare(root, tmp_path / 'derived', 'test', COMMIT)
    assert result['report']['archive_fonts'] == 1
    assert result['report']['license_sidecars'] == 1
    assert not result['report']['issues']
    assert {d['member'] for d in result['derivations'].values()} == {'font.woff2', 'LICENSE.txt'}
    assert all(d['original_path'] == 'fonts.zip' for d in result['derivations'].values())
    assert (root / 'fonts.zip').exists()


@pytest.mark.parametrize('unsafe', ['../escape.ttf', '/escape.ttf', 'C:/escape.ttf', 'a\\escape.ttf', 'a/../escape.ttf'])
def test_zip_traversal_refuses_entire_archive(tmp_path, unsafe):
    root = tmp_path / 'original'
    root.mkdir()
    make_zip(root / 'fonts.zip', [('safe.ttf', FONT), (unsafe, FONT)])
    result = sources.prepare(root, tmp_path / 'derived', 'test', COMMIT)
    assert not result['derivations']
    assert result['report']['issues'][0]['kind'] == 'preparation-refused'


def test_zip_symlink_refused(tmp_path):
    root = tmp_path / 'original'
    root.mkdir()
    with zipfile.ZipFile(root / 'links.zip', 'w') as archive:
        info = zipfile.ZipInfo('font.ttf')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b'/some/file')
    result = sources.prepare(root, tmp_path / 'derived', 'test', COMMIT)
    assert not result['derivations']
    assert 'links/special' in result['report']['issues'][0]['error']


def test_zip_bomb_ratio_and_total_limits(tmp_path, monkeypatch):
    root = tmp_path / 'original'
    root.mkdir()
    make_zip(root / 'bomb.zip', [('font.ttf', b'0' * 100000)])
    result = sources.prepare(root, tmp_path / 'derived', 'test', COMMIT)
    assert not result['derivations']
    assert 'high-ratio' in result['report']['issues'][0]['error']
    monkeypatch.setattr(sources, 'MAX_ARCHIVE_TOTAL', 5)
    result = sources.prepare(root, tmp_path / 'derived', 'test', COMMIT)
    assert 'total limit' in result['report']['issues'][0]['error']


def test_missing_7z_tool_is_explicit(tmp_path, monkeypatch):
    monkeypatch.setattr(sources.shutil, 'which', lambda _: None)
    _, result = prepare(tmp_path, {'old.7z': b'7z placeholder'})
    assert result['report']['issues'][0]['kind'] == '7z-tool-unavailable'


def test_same_decoded_bytes_keep_multiple_origins(tmp_path):
    _, result = prepare(tmp_path, {'first.ttf': base64.b64encode(FONT), 'second.otf': base64.b64encode(FONT)})
    values = list(result['derivations'].values())
    assert len(values) == 1
    assert values[0]['original_path'] == 'first.ttf'
    assert values[0]['additional_origins'][0]['original_path'] == 'second.otf'


def test_symlink_output_refused(tmp_path):
    root = tmp_path / 'original'
    root.mkdir()
    actual = tmp_path / 'actual'
    actual.mkdir()
    try:
        (tmp_path / 'link').symlink_to(actual, target_is_directory=True)
    except OSError:
        pytest.skip('Symlink creation unavailable')
    with pytest.raises(ValueError, match='Symlink'):
        sources.prepare(root, tmp_path / 'link', 'test', COMMIT)


def test_modified_derivative_is_not_overwritten(tmp_path):
    root, result = prepare(tmp_path, {'font.ttf': base64.b64encode(FONT)})
    path = Path(result['root'], next(iter(result['derivations'])))
    path.write_bytes(b'user work')
    retry = sources.prepare(root, Path(result['root']), 'test', COMMIT)
    assert path.read_bytes() == b'user work'
    assert 'Existing derivative' in retry['report']['issues'][0]['error']


def lock(tmp_path, commit=COMMIT):
    path = tmp_path / 'sources.lock.json'
    path.write_text(json.dumps({'sources': [{'id': 'one', 'url': 'https://github.com/example/fonts.git', 'commit': commit}]}))
    return path


def test_fetch_reuses_exact_clean_checkout_without_mutation(tmp_path, monkeypatch):
    root = tmp_path / 'library' / 'sources' / 'one'
    (root / '.git').mkdir(parents=True)
    commands = []
    def fake_git(path, *args):
        commands.append(args)
        return {'status': '', 'rev-parse': COMMIT, 'remote': 'https://github.com/example/fonts.git'}[args[0]]
    monkeypatch.setattr(sources, '_git', fake_git)
    result = sources.fetch(lock(tmp_path), tmp_path / 'library')
    assert result[0]['commit'] == COMMIT
    assert all(args[0] in {'status', 'rev-parse', 'remote'} for args in commands)


def test_fetch_refuses_dirty_checkout_without_reset(tmp_path, monkeypatch):
    root = tmp_path / 'library' / 'sources' / 'one'
    (root / '.git').mkdir(parents=True)
    (root / 'user.txt').write_text('preserve me')
    commands = []
    def fake_git(path, *args):
        commands.append(args)
        return '?? user.txt'
    monkeypatch.setattr(sources, '_git', fake_git)
    with pytest.raises(ValueError, match='has changes'):
        sources.fetch(lock(tmp_path), tmp_path / 'library')
    assert (root / 'user.txt').read_text() == 'preserve me'
    assert len(commands) == 1


def test_fetch_requires_immutable_pin(tmp_path):
    with pytest.raises(ValueError, match='40-character'):
        sources.fetch(lock(tmp_path, commit='main'), tmp_path / 'library')


def test_7z_listing_refuses_links_and_total(tmp_path, monkeypatch):
    monkeypatch.setattr(sources, '_run_bounded', lambda *args: b'Path = safe.ttf\nSize = 10\nSymbolic Link = /escape\n')
    with pytest.raises(ValueError, match='links'):
        sources._seven_entries(tmp_path / 'x.7z', '7z')


def test_bounded_process_output():
    import sys
    with pytest.raises(ValueError, match='output limit'):
        sources._run_bounded([sys.executable, '-c', 'print("x" * 10000)'], 10)


def test_font_named_copyright_is_not_license_or_copied(tmp_path):
    _, result = prepare(tmp_path, {'font.ttf': base64.b64encode(FONT), 'Copyright Example.otf': FONT})
    assert result['report']['base64_fonts'] == 1
    assert result['report']['archive_fonts'] == 0
    assert result['report']['license_sidecars'] == 0


def test_libarchive_stream_refuses_links_without_disk_extraction(tmp_path, monkeypatch):
    import io
    import tarfile
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        member = tarfile.TarInfo('font.ttf')
        member.type = tarfile.SYMTYPE
        member.linkname = '/escape'
        archive.addfile(member)
    monkeypatch.setattr(sources.shutil, 'which', lambda name: '/fake/bsdtar' if name == 'bsdtar' else None)
    monkeypatch.setattr(sources, '_run_bounded', lambda *args: data.getvalue())
    _, result = prepare(tmp_path, {'old.7z': b'archive placeholder'})
    assert not result['derivations']
    assert 'links/special' in result['report']['issues'][0]['error']


def test_libarchive_stream_extracts_exact_member(tmp_path, monkeypatch):
    import io
    import tarfile
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        member = tarfile.TarInfo('folder/font.ttf')
        member.size = len(FONT)
        archive.addfile(member, io.BytesIO(FONT))
    monkeypatch.setattr(sources.shutil, 'which', lambda name: '/fake/bsdtar' if name == 'bsdtar' else None)
    monkeypatch.setattr(sources, '_run_bounded', lambda *args: data.getvalue())
    _, result = prepare(tmp_path, {'old.7z': b'archive placeholder'})
    assert result['report']['archive_fonts'] == 1
    value = next(iter(result['derivations'].values()))
    assert value['member'] == 'folder/font.ttf'
    assert value['transform'] == '7z-via-libarchive'


@pytest.mark.parametrize('original,encoded', [
    ('Foundries/Indestructible Type*/Jost*/font.ttf', 'Foundries/Indestructible Type%2A/Jost%2A/font.ttf'),
    ('Connary Fagen, Inc./a.ttf', 'Connary Fagen, Inc%2E/a.ttf'),
    ('CON.txt', '%43ON.txt'),
    ('aux.ttf', '%61ux.ttf'),
    ('100%/font?.ttf', '100%25/font%3F.ttf'),
    ('a. /font.ttf', 'a%2E%20/font.ttf'),
])
def test_portable_path_preserves_structure_and_encodes_invalid(original, encoded):
    assert sources.portable_path(original) == encoded


def test_portable_materialization_reads_real_git_blobs_without_checkout(tmp_path):
    if not sources.shutil.which('git'):
        pytest.skip('Git unavailable')
    repository = tmp_path / 'bare.git'
    repository.mkdir()
    def git(*args, data=None):
        return subprocess.run(['git', '-c', 'core.hooksPath=/dev/null', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', '-C', str(repository), *args], input=data, capture_output=True, check=True).stdout.decode().strip()
    git('init', '--bare', '--quiet')
    blob = git('hash-object', '-w', '--stdin', data=FONT)
    license_blob = git('hash-object', '-w', '--stdin', data=b'Test license text')
    tree = git('mktree', data=(f'100644 blob {blob}\tCON.ttf\n100644 blob {blob}\tfont*.ttf\n100644 blob {license_blob}\tLICENSE%.txt\n').encode())
    commit = git('commit-tree', tree, '-m', 'Portable fixture')
    config = sources._materialize(repository, tmp_path / 'materialized', {'id': 'fixture', 'commit': commit, 'url': 'https://example.invalid/fonts.git'})
    assert Path(config['root'], '%43ON.ttf').read_bytes() == FONT
    assert Path(config['root'], 'font%2A.ttf').read_bytes() == FONT
    assert config['upstream_paths']['font%2A.ttf'] == 'font*.ttf'
    assert config['acquisition']['files'] == 3
    assert not config['acquisition']['skipped']
    manifest = json.loads(Path(config['root'], '.type-evidence-source.json').read_text())
    assert all(len(record['sha256']) == 64 for record in manifest['files'])
    reused = sources._fetch_portable({'id': 'fixture', 'commit': commit}, Path(config['root']), repository, config['url'])
    assert reused == config
    Path(config['root'], 'font%2A.ttf').write_bytes(b'user work')
    with pytest.raises(ValueError, match='changed/missing'):
        sources._fetch_portable({'id': 'fixture', 'commit': commit}, Path(config['root']), repository, config['url'])


def test_portable_case_collision_refused_before_writing(tmp_path):
    listing = '100644 blob ' + 'a' * 40 + ' 4\tFont.ttf\0' + '100644 blob ' + 'b' * 40 + ' 4\tfont.ttf\0'
    with pytest.raises(ValueError, match='collision'):
        sources._materialize(tmp_path / 'unused', tmp_path / 'new', {'commit': COMMIT}, listing)
    assert not (tmp_path / 'new').exists()
