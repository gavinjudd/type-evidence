"""Pinned, non-destructive acquisition and bounded font preparation.

Never executes source scripts, installs fonts, or modifies original source files.
Derived fonts retain byte-level provenance. Archive metadata is untrusted.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import threading
import tarfile
import tempfile
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
import zipfile

MAGIC_EXT = {b'\x00\x01\x00\x00': '.ttf', b'OTTO': '.otf', b'true': '.ttf',
             b'typ1': '.otf', b'wOFF': '.woff', b'wOF2': '.woff2', b'ttcf': '.ttc'}
FONT_EXT = {'.ttf', '.otf', '.woff', '.woff2', '.ttc', '.otc', '.eot'}
LICENSE_NAME = re.compile(r'^(licen[sc]e|ofl|copying|copyright|eula|readme|notice|about)([._ -]|$)', re.I)
MAX_FILE = 128 * 1024 * 1024
MAX_ARCHIVE_TOTAL = 512 * 1024 * 1024
MAX_MEMBERS = 10000
MAX_RATIO = 250


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _git(root, *args):
    env = os.environ.copy()
    env['GIT_TERMINAL_PROMPT'] = '0'
    env['GIT_LFS_SKIP_SMUDGE'] = '1'
    command = ['git', '-c', 'core.hooksPath=/dev/null', '-c', 'filter.lfs.required=false',
               '-c', 'filter.lfs.smudge=', '-c', 'submodule.recurse=false']
    if root is not None:
        command += ['-C', str(root)]
    result = subprocess.run(command + list(args), env=env, check=True, capture_output=True, text=True, timeout=600)
    return result.stdout.strip()


def _safe_directory(path):
    path = Path(path).expanduser().absolute()
    for ancestor in [path, *path.parents]:
        if ancestor.is_symlink():
            raise ValueError('Symlink directory refused: ' + str(ancestor))
    return path.resolve()


def fetch(lock_path, library_root, *, portable=None):
    """Fetch exact commits into library_root/sources; refuse modified/mismatched trees.

    Lock shape: {"sources": [{"id": "name", "url": "https://...git", "commit": "40 hex"}]}.
    A github-subtree entry additionally carries exact path/hash/length records;
    it downloads only that reviewed subset instead of the entire repository.
    Existing trees are reused only at the exact pin, with the expected remote and
    clean status. Failed/partial downloads are left for inspection, never reset.
    """
    if portable is None:
        portable = os.name == 'nt'
    lock = json.loads(Path(lock_path).read_text(encoding='utf-8'))
    entries = lock['sources'] if isinstance(lock, dict) else lock
    destination = _safe_directory(Path(library_root) / 'sources')
    destination.mkdir(parents=True, exist_ok=True)
    result, seen = [], set()
    for entry in entries:
        ident, commit = entry['id'], entry['commit']
        url = entry.get('url', 'https://github.com/' + entry.get('repository', '') + '.git')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', ident) or ident in seen:
            raise ValueError('Source ids must be unique safe directory names')
        if not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
            raise ValueError('Full 40-character commit pin required')
        if not re.fullmatch(r'https://[^\s/@]+/[^\s?#]+', url):
            raise ValueError('Only credential-free HTTPS source URLs are accepted')
        seen.add(ident)
        root = _safe_directory(destination / ident)
        if entry.get('acquisition') == 'github-subtree':
            result.append(_fetch_github_subset(entry, root, url))
            continue
        if entry.get('acquisition') not in {None, 'git'}:
            raise ValueError('Unknown source acquisition mode')
        if portable:
            result.append(_fetch_portable(entry, root, Path(library_root) / 'repositories' / (ident + '.git'), url))
            continue
        if root.exists():
            if not (root / '.git').is_dir() or (root / '.git').is_symlink():
                raise ValueError('Existing destination is not an independent Git checkout: ' + str(root))
            if _git(root, 'status', '--porcelain', '--untracked-files=all'):
                raise ValueError('Existing checkout has changes; preserved: ' + str(root))
            if _git(root, 'rev-parse', 'HEAD') != commit.lower():
                raise ValueError('Existing checkout is at another commit; preserved: ' + str(root))
            if _git(root, 'remote', 'get-url', 'origin').removesuffix('.git') != url.removesuffix('.git'):
                raise ValueError('Existing checkout remote differs; preserved: ' + str(root))
        else:
            root.mkdir()
            _git(root, 'init', '--quiet')
            _git(root, 'remote', 'add', 'origin', url)
            _git(root, 'fetch', '--depth', '1', '--no-tags', '--no-recurse-submodules', 'origin', commit)
            _git(root, 'checkout', '--quiet', '--detach', commit)
            if _git(root, 'rev-parse', 'HEAD') != commit.lower():
                raise ValueError('Fetched commit does not match lock')
        result.append(dict(id=ident, root=str(root), url=url, commit=commit.lower()))
    return result


def _github_repository(value):
    match = re.fullmatch(r'(?:https://github\.com/)?([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', value)
    if not match or any(p in {'.', '..'} for p in match.group(1).split('/')):
        raise ValueError('A public GitHub owner/repository is required')
    return match.group(1)


def _upstream_path(value):
    if not isinstance(value, str) or '\\' in value or '\x00' in value or any(p in {'', '.', '..'} for p in value.split('/')):
        raise ValueError('Unsafe source path')
    portable_path(value)
    return value


def _https_bytes(url, limit):
    """Read bounded public HTTPS data; no credentials or local scripts are used."""
    request = Request(url, headers={'User-Agent': 'type-evidence-source-fetch/0.2', 'Accept': 'application/vnd.github+json'})
    with urlopen(request, timeout=90) as response:
        final = urlparse(response.geturl())
        if final.scheme != 'https' or final.hostname not in {'api.github.com', 'raw.githubusercontent.com'}:
            raise ValueError('Unexpected source download redirect')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Source download exceeded byte limit')
    return data


def pin_github_source(repository, commit, paths, ident):
    """Build a reviewed lock entry from exact files or immediate directory files.

    Directories select their fonts, license files, METADATA.pb and descriptions;
    nested directories are not traversed. Add a nested directory explicitly when
    static styles are required. Returned hashes identify the downloaded bytes,
    while Git blob hashes verify their relationship to the pinned upstream tree.
    This returns metadata only and never installs or saves font binaries.
    """
    repository = _github_repository(repository)
    if not re.fullmatch(r'[0-9a-fA-F]{40}', commit):
        raise ValueError('Full 40-character commit pin required')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', ident):
        raise ValueError('Source id must be a safe directory name')
    if not isinstance(paths, list) or not 1 <= len(paths) <= 100:
        raise ValueError('Select 1–100 exact files or directories')
    selected = {}
    for path in paths:
        path = _upstream_path(path)
        endpoint = 'https://api.github.com/repos/' + repository + '/contents/' + quote(path, safe='/') + '?ref=' + commit.lower()
        listing = json.loads(_https_bytes(endpoint, 4 * 1024 * 1024))
        records = listing if isinstance(listing, list) else [listing]
        # GitHub contents responses cap a directory listing at 1000 entries.
        if len(records) >= 1000:
            raise ValueError('Directory listing may be truncated; select narrower paths')
        for record in records:
            name = _upstream_path(record['path'])
            if record.get('type') != 'file':
                continue
            if isinstance(listing, list) and not (Path(name).suffix.lower() in FONT_EXT or _license(name)
                                                  or Path(name).name in {'METADATA.pb', 'DESCRIPTION.en_us.html'}):
                continue
            size, blob = record.get('size'), record.get('sha')
            if not isinstance(size, int) or not 0 <= size <= MAX_FILE or not re.fullmatch(r'[0-9a-f]{40}', blob or ''):
                raise ValueError('Invalid pinned file metadata')
            selected[name] = dict(path=name, bytes=size, git_blob=blob)
    if not selected or len(selected) > MAX_MEMBERS or sum(r['bytes'] for r in selected.values()) > MAX_ARCHIVE_TOTAL:
        raise ValueError('Source selection is empty or exceeds bounded source limits')
    for record in selected.values():
        data = _https_bytes('https://raw.githubusercontent.com/' + repository + '/' + commit.lower() + '/' + quote(record['path'], safe='/'), record['bytes'])
        _verify_source_bytes(data, record, require_sha=False)
        record['sha256'] = _sha(data)
    return dict(id=ident, url='https://github.com/' + repository, commit=commit.lower(),
                acquisition='github-subtree', selection=paths, files=sorted(selected.values(), key=lambda r: r['path']))


def _verify_source_bytes(data, record, *, require_sha=True):
    if len(data) != record['bytes'] or (require_sha and _sha(data) != record['sha256']):
        raise ValueError('Source byte length or SHA-256 differs from lock')
    blob = hashlib.sha1(b'blob ' + str(len(data)).encode('ascii') + b'\0' + data).hexdigest()
    if blob != record['git_blob']:
        raise ValueError('Source Git blob hash differs from lock')


def _fetch_github_subset(entry, root, url):
    repository = _github_repository(url)
    files = entry.get('files')
    if not isinstance(files, list) or not 1 <= len(files) <= MAX_MEMBERS:
        raise ValueError('A bounded list of locked files is required')
    records, names, components, total = [], set(), {}, 0
    for record in files:
        upstream = _upstream_path(record['path'])
        safe = portable_path(upstream)
        if safe.casefold() in names or safe.casefold() == '.type-evidence-source.json':
            raise ValueError('Portable source path collision')
        names.add(safe.casefold())
        parts = safe.split('/')
        for end in range(1, len(parts) + 1):
            prefix = '/'.join(parts[:end])
            folded = prefix.casefold()
            if folded in components and components[folded] != (prefix, end == len(parts)):
                raise ValueError('Portable source directory or file collision')
            components[folded] = (prefix, end == len(parts))
        if (not re.fullmatch(r'[0-9a-f]{64}', record.get('sha256', ''))
                or not re.fullmatch(r'[0-9a-f]{40}', record.get('git_blob', ''))
                or not isinstance(record.get('bytes'), int) or not 0 <= record['bytes'] <= MAX_FILE):
            raise ValueError('Every selected file needs SHA-256, Git blob hash and bounded byte length')
        total += record['bytes']
        records.append(dict(record, path=safe, upstream_path=upstream))
    if total > MAX_ARCHIVE_TOTAL:
        raise ValueError('Selected source exceeds total byte limit')
    config = dict(id=entry['id'], root=str(root), url=url, commit=entry['commit'].lower(),
                  upstream_paths={r['path']: r['upstream_path'] for r in records if r['path'] != r['upstream_path']},
                  acquisition=dict(mode='pinned-github-subtree', files=len(records), bytes=total,
                                   selection=entry.get('selection', []), path_spelling='portable percent encoding'))
    expected = dict(config, files=records)
    marker = root / '.type-evidence-source.json'
    if root.exists():
        if marker.is_symlink() or not marker.is_file() or json.loads(marker.read_text(encoding='utf-8')) != expected:
            raise ValueError('Existing subset manifest differs from lock; preserved')
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
        if actual != {r['path'] for r in records} | {marker.name}:
            raise ValueError('Existing subset has added/missing files; preserved')
        for record in records:
            path = root / record['path']
            _safe_directory(path.parent)
            if path.is_symlink():
                raise ValueError('Source symlink refused')
            _verify_source_bytes(path.read_bytes(), record)
        return config
    # The final directory appears only once every pinned file verifies. A failed
    # download does not leave a destination that looks like a usable source.
    with tempfile.TemporaryDirectory(prefix='.' + entry['id'] + '-', dir=root.parent) as staging:
        staging = Path(staging)
        for record in records:
            raw_url = 'https://raw.githubusercontent.com/' + repository + '/' + entry['commit'].lower() + '/' + quote(record['upstream_path'], safe='/')
            data = _https_bytes(raw_url, record['bytes'])
            _verify_source_bytes(data, record)
            target = staging / record['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        (staging / marker.name).write_text(json.dumps(expected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        staging.rename(root)
    return config


def portable_path(upstream_path):
    """Injective Windows-safe spelling; original Git paths remain in provenance."""
    parts = []
    for component in PurePosixPath(upstream_path).parts:
        if component in {'', '.', '..'}:
            raise ValueError('Unsafe Git path')
        reserved = bool(re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', component, re.I))
        last_real = len(component.rstrip(' .'))
        encoded = []
        for index, char in enumerate(component):
            if char in '%<>:"\\|?*' or ord(char) < 32 or index >= last_real or (reserved and index == 0):
                encoded.extend('%' + format(byte, '02X') for byte in char.encode('utf-8'))
            else:
                encoded.append(char)
        parts.append(''.join(encoded))
    if not parts or PurePosixPath(upstream_path).is_absolute():
        raise ValueError('Unsafe Git path')
    return '/'.join(parts)


def _fetch_portable(entry, root, repository, url):
    commit = entry['commit'].lower()
    marker = root / '.type-evidence-source.json'
    if root.exists():
        if not marker.is_file() or marker.is_symlink():
            raise ValueError('Existing portable destination has no valid manifest; preserved')
        manifest = json.loads(marker.read_text(encoding='utf-8'))
        if manifest.get('id') != entry['id'] or manifest.get('commit') != commit or manifest.get('url') != url:
            raise ValueError('Existing portable destination differs from lock; preserved')
        known = {'.type-evidence-source.json'}
        for record in manifest['files']:
            path = root / record['path']
            _safe_directory(path.parent)
            if path.is_symlink() or not path.is_file() or _sha(path.read_bytes()) != record['sha256']:
                raise ValueError('Existing portable source has changed/missing bytes; preserved')
            known.add(record['path'])
        actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
        if actual != known:
            raise ValueError('Existing portable source has untracked files; preserved')
        return dict({k: manifest[k] for k in ['id', 'url', 'commit', 'upstream_paths', 'acquisition']}, root=str(root))
    repository = _safe_directory(repository)
    repository.parent.mkdir(parents=True, exist_ok=True)
    if repository.exists():
        if _git(repository, 'rev-parse', '--is-bare-repository') != 'true' or _git(repository, 'rev-parse', 'HEAD') != commit:
            raise ValueError('Existing bare repository differs from pin; preserved')
        if _git(repository, 'remote', 'get-url', 'origin').removesuffix('.git') != url.removesuffix('.git'):
            raise ValueError('Existing bare repository remote differs; preserved')
    else:
        repository.mkdir()
        _git(repository, 'init', '--bare', '--quiet')
        _git(repository, 'remote', 'add', 'origin', url)
        _git(repository, 'fetch', '--depth', '1', '--no-tags', '--no-recurse-submodules', 'origin', commit)
        _git(repository, 'update-ref', 'refs/heads/pinned', commit)
        _git(repository, 'symbolic-ref', 'HEAD', 'refs/heads/pinned')
    return _materialize(repository, root, dict(entry, commit=commit, url=url))


def _materialize(repository, root, entry, tree_records=None):
    """Read pinned blobs from a bare repo, never check out unsafe upstream paths."""
    root = _safe_directory(root)
    if root.exists():
        raise ValueError('Materialization destination already exists; preserved')
    listing = _git(repository, 'ls-tree', '-rzl', entry['commit']) if tree_records is None else tree_records
    records, skipped, names = [], [], set()
    for raw in listing.split('\0'):
        if not raw:
            continue
        metadata, upstream = raw.split('\t', 1)
        mode, kind, oid, size = metadata.split()
        if kind != 'blob' or mode == '120000':
            skipped.append(dict(upstream_path=upstream, kind='gitlink-or-symlink-preserved-in-bare-repository'))
            continue
        safe = portable_path(upstream)
        folded = safe.casefold()
        if folded in names:
            raise ValueError('Portable case-insensitive collision; no materialization written')
        names.add(folded)
        if int(size) > MAX_FILE:
            skipped.append(dict(upstream_path=upstream, kind='oversize-blob-preserved-in-bare-repository'))
            continue
        records.append(dict(path=safe, upstream_path=upstream, git_blob=oid, bytes=int(size)))
    root.mkdir(parents=True)
    process = subprocess.Popen(['git', '-C', str(repository), 'cat-file', '--batch'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        for record in records:
            process.stdin.write((record['git_blob'] + '\n').encode('ascii'))
            process.stdin.flush()
            header = process.stdout.readline().decode('ascii').strip().split()
            if header != [record['git_blob'], 'blob', str(record['bytes'])]:
                raise ValueError('Git blob response did not match pinned tree')
            data = process.stdout.read(record['bytes'])
            if len(data) != record['bytes'] or process.stdout.read(1) != b'\n':
                raise ValueError('Git blob was truncated')
            if hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() != record['git_blob']:
                raise ValueError('Git blob hash verification failed')
            target = root / record['path']
            _safe_directory(target.parent).mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            record['sha256'] = _sha(data)
        process.stdin.close()
        if process.wait(timeout=30) != 0:
            raise ValueError('Git blob reader failed')
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        if not process.stdin.closed:
            process.stdin.close()
        process.stdout.close()
    config = dict(id=entry['id'], root=str(root), url=entry['url'], commit=entry['commit'],
                  upstream_paths={r['path']: r['upstream_path'] for r in records if r['path'] != r['upstream_path']},
                  acquisition=dict(mode='pinned-git-blob-materialization', files=len(records), skipped=skipped,
                                   path_spelling='percent-encoded Windows-invalid components; original Git paths retained'))
    marker = root / '.type-evidence-source.json'
    with marker.open('x', encoding='utf-8') as stream:
        json.dump(dict(config, files=records), stream, ensure_ascii=False, indent=2)
    return config


def _member_name(name):
    # Backslashes, drive prefixes and ADS are rejected on every OS, not normalized.
    if not name or '\x00' in name or '\\' in name or ':' in name or name.startswith('/'):
        raise ValueError('Unsafe archive member path')
    p = PurePosixPath(name)
    if any(part in {'..', '.'} for part in name.rstrip('/').split('/')):
        raise ValueError('Unsafe archive member path')
    return p


def _license(path):
    p = PurePosixPath(path)
    return p.suffix.lower() not in FONT_EXT | {'.glif', '.ttx', '.svg'} and bool(LICENSE_NAME.match(p.name))


def _run_bounded(command, limit, timeout=60):
    """Bound subprocess stdout on Windows and Unix without shell interpretation."""
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    timer = threading.Timer(timeout, process.kill)
    timer.start()
    result = bytearray()
    try:
        while True:
            chunk = process.stdout.read(min(65536, limit + 1 - len(result)))
            if not chunk:
                break
            result.extend(chunk)
            if len(result) > limit:
                raise ValueError('Archive tool exceeded output limit')
        if process.wait() != 0:
            raise ValueError('Archive tool failed or timed out')
        return bytes(result)
    finally:
        timer.cancel()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def _seven_entries(archive, tool):
    listing = _run_bounded([tool, 'l', '-slt', '-ba', '-bd', '--', str(archive)], 8 * 1024 * 1024).decode('utf-8', errors='strict')
    entries = []
    for block in re.split(r'\r?\n\r?\n', listing.strip()):
        fields = dict(line.split(' = ', 1) for line in block.splitlines() if ' = ' in line)
        if 'Path' not in fields:
            continue
        _member_name(fields['Path'])
        if any('link' in key.lower() for key in fields) or 'L' in fields.get('Attributes', ''):
            raise ValueError('Archive links refused')
        if fields.get('Encrypted') == '+':
            raise ValueError('Encrypted archive refused')
        size = int(fields.get('Size', 0))
        if size < 0 or size > MAX_FILE:
            raise ValueError('Archive member exceeds size limit')
        entries.append((fields['Path'], size, fields.get('Folder') == '+' or fields.get('Attributes', '').startswith('D')))
    if len(entries) > MAX_MEMBERS or sum(x[1] for x in entries) > MAX_ARCHIVE_TOTAL:
        raise ValueError('Archive exceeds member/total limit')
    return entries


def prepare(root, output, source_id, commit, url=''):
    """Return a derived source config with per-file provenance and preparation report.

    Base64 font text and ZIP font/license members are prepared separately from
    originals. Optional 7zz/7z or libarchive bsdtar handles .7z. Nested archives are not traversed.
    No archive paths are used as destination names; fonts use SHA256 plus the
    extension detected from actual bytes. Existing derivative bytes must match.
    """
    root, output = _safe_directory(root), _safe_directory(output)
    if not root.is_dir() or output == root or output.is_relative_to(root) or root.is_relative_to(output):
        raise ValueError('Source and derived roots must be existing/separate trees')
    output.mkdir(parents=True, exist_ok=True)
    derivations, issues = {}, []
    counts = {'base64_fonts': 0, 'archive_fonts': 0, 'license_sidecars': 0, 'archives_seen': 0}
    tool = shutil.which('7zz') or shutil.which('7z')
    bsdtar = shutil.which('bsdtar')
    if tool is None and bsdtar is None:
        candidate = shutil.which('tar')
        if candidate:
            try:
                if b'bsdtar' in _run_bounded([candidate, '--version'], 65536).lower():
                    bsdtar = candidate
            except (OSError, ValueError):
                pass

    def save(data, original, original_sha, member, transform, group):
        ext = MAGIC_EXT.get(data[:4])
        is_license = ext is None and _license(member or original)
        if ext is None and not is_license:
            return False
        if len(data) > (2 * 1024 * 1024 if is_license else MAX_FILE):
            raise ValueError('Prepared asset exceeds size limit')
        sha = _sha(data)
        if is_license:
            original_ext = PurePosixPath(member or original).suffix.lower()
            ext = original_ext if original_ext in {'.txt', '.md', '.rtf', '.pdf', '.html', '.htm', '.textile', '.markdown'} else '.txt'
        name = ('LICENSE-' if is_license else '') + sha + ext
        relative = group + '/' + name
        target = output / relative
        _safe_directory(target.parent).mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            raise ValueError('Symlink derivative refused')
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError('Existing derivative content differs; preserved')
        else:
            with target.open('xb') as stream:
                stream.write(data)
        provenance = dict(original_source_id=source_id, source_commit=commit, original_path=original,
                          original_sha256=original_sha, member=member, member_sha256=_sha(data) if member else None,
                          transform=transform, sha256=sha, kind='license-sidecar' if is_license else 'font')
        if relative in derivations:
            existing = derivations[relative]
            if provenance == {k: v for k, v in existing.items() if k != 'additional_origins'} or provenance in existing.get('additional_origins', []):
                return True
            existing.setdefault('additional_origins', []).append(provenance)
        else:
            derivations[relative] = provenance
        counts['license_sidecars' if is_license else ('base64_fonts' if transform == 'base64-decode' else 'archive_fonts')] += 1
        return True

    for folder, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d != '.git' and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                issues.append(dict(path=relative, kind='symlink-skipped'))
                continue
            ext = path.suffix.lower()
            if ext not in FONT_EXT | {'.zip', '.7z'}:
                continue
            try:
                size = path.stat().st_size
                if size > MAX_FILE:
                    raise ValueError('Source file exceeds size limit')
                data = path.read_bytes()
                original_sha = _sha(data)
                if ext in FONT_EXT:
                    if data[:4] in MAGIC_EXT or not data:
                        continue
                    try:
                        decoded = base64.b64decode(re.sub(rb'\s', b'', data), validate=True)
                    except (ValueError, base64.binascii.Error):
                        continue
                    if decoded[:4] in MAGIC_EXT:
                        group = 'base64/' + _sha(str(path.parent.relative_to(root)).encode())[:24]
                        save(decoded, relative, original_sha, None, 'base64-decode', group)
                        # Preserve adjacent license/readme evidence; scope remains unverified.
                        for sidecar in sorted(path.parent.iterdir()):
                            if sidecar.is_file() and not sidecar.is_symlink() and _license(sidecar.name) and sidecar.stat().st_size <= 2 * 1024 * 1024:
                                raw = sidecar.read_bytes()
                                save(raw, sidecar.relative_to(root).as_posix(), _sha(raw), None, 'copy-sidecar', group)
                    continue
                counts['archives_seen'] += 1
                group = 'archive/' + _sha(relative.encode())[:24]
                if ext == '.zip':
                    with zipfile.ZipFile(path) as archive:
                        entries = archive.infolist()
                        if len(entries) > MAX_MEMBERS or sum(e.file_size for e in entries) > MAX_ARCHIVE_TOTAL:
                            raise ValueError('Archive exceeds member/total limit')
                        for entry in entries:
                            _member_name(entry.filename)
                            mode = entry.external_attr >> 16
                            if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode))):
                                raise ValueError('Archive links/special files refused')
                            if entry.flag_bits & 1 or entry.file_size > MAX_FILE or entry.file_size > max(entry.compress_size, 1) * MAX_RATIO:
                                raise ValueError('Encrypted/oversized/high-ratio archive refused')
                        for entry in entries:
                            if entry.is_dir():
                                continue
                            if PurePosixPath(entry.filename).suffix.lower() in FONT_EXT or _license(entry.filename):
                                with archive.open(entry) as stream:
                                    raw = stream.read(MAX_FILE + 1)
                                if len(raw) > MAX_FILE or len(raw) != entry.file_size:
                                    raise ValueError('Archive member length mismatch')
                                save(raw, relative, original_sha, entry.filename, 'zip-extract', group)
                elif tool is None and bsdtar is None:
                    issues.append(dict(path=relative, kind='7z-tool-unavailable', message='Install 7zz/7z or libarchive bsdtar optionally, then prepare again; original retained'))
                elif tool is None:
                    # Transcode archive entries to a bounded tar stream; never extract paths to disk.
                    tar_data = _run_bounded([bsdtar, '-cf', '-', '@' + str(path)], MAX_ARCHIVE_TOTAL + MAX_MEMBERS * 2048)
                    with tarfile.open(fileobj=io.BytesIO(tar_data), mode='r:') as archive:
                        entries = archive.getmembers()
                        if len(entries) > MAX_MEMBERS or sum(e.size for e in entries) > min(MAX_ARCHIVE_TOTAL, max(size, 1) * MAX_RATIO):
                            raise ValueError('Archive exceeds member/total/ratio limit')
                        for entry in entries:
                            _member_name(entry.name)
                            if not (entry.isfile() or entry.isdir()):
                                raise ValueError('Archive links/special files refused')
                            if entry.size < 0 or entry.size > MAX_FILE:
                                raise ValueError('Archive member exceeds size limit')
                        for entry in entries:
                            if entry.isfile() and (PurePosixPath(entry.name).suffix.lower() in FONT_EXT or _license(entry.name)):
                                with archive.extractfile(entry) as stream:
                                    raw = stream.read(MAX_FILE + 1)
                                if len(raw) != entry.size or len(raw) > MAX_FILE:
                                    raise ValueError('Archive member length mismatch')
                                save(raw, relative, original_sha, entry.name, '7z-via-libarchive', group)
                else:
                    entries = _seven_entries(path, tool)
                    if sum(e[1] for e in entries) > max(size, 1) * MAX_RATIO:
                        raise ValueError('High-ratio archive refused')
                    for member, member_size, directory in entries:
                        if not directory and (PurePosixPath(member).suffix.lower() in FONT_EXT or _license(member)):
                            raw = _run_bounded([tool, 'x', '-so', '-spd', '-bd', '-y', '--', str(path), member], min(member_size, MAX_FILE))
                            if len(raw) != member_size:
                                raise ValueError('Archive member length mismatch')
                            save(raw, relative, original_sha, member, '7z-extract', group)
            except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError, RuntimeError, EOFError) as exc:
                issues.append(dict(path=relative, kind='preparation-refused', error=str(exc)[:400]))
    report = dict(**counts, derived_files=len(derivations), issues=issues,
                  limitations=['No nested archive traversal', 'Original sidecar scope and rights remain unverified',
                               'EOT, source UFO/TTX and legacy formats are preserved in originals; no conversion'])
    config = dict(id=source_id + '-derived', root=str(output), url=url, commit=commit,
                  derivations=derivations, report=report)
    manifest = output / 'provenance.json'
    if manifest.is_symlink():
        raise ValueError('Symlink provenance file refused')
    temporary = output / 'provenance.json.tmp'
    if temporary.exists() or temporary.is_symlink():
        raise ValueError('Existing provenance temporary file preserved')
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(config, stream, indent=2, ensure_ascii=False)
    temporary.replace(manifest)
    return config
