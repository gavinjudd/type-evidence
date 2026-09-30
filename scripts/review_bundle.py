"""Build/verify a compact review archive from an explicit source/evidence allowlist."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile

ROOT_FILES = {'README.md','AGENTS.md','pyproject.toml','sources.lock.json','.gitignore','requirements-lock.txt'}
ROOT_DIRS = {'type_evidence','tests','docs','examples','evidence','scripts'}
SUFFIXES = {'.py','.md','.json','.toml','.txt','.xml','.png','.html'}
FONT_MAGIC = {b'\0\1\0\0',b'OTTO',b'ttcf',b'wOFF',b'wOF2',b'true',b'typ1'}
SECRET = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|sk-[A-Za-z0-9_-]{35,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def verify(path):
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate ZIP members')
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failed')
        manifest=json.loads(archive.read('type-evidence/REVIEW-MANIFEST.json'))
        expected={'type-evidence/'+item['path']:item for item in manifest['files']}
        if set(names)!=set(expected)|{'type-evidence/REVIEW-MANIFEST.json'}:
            raise ValueError('ZIP contents differ from manifest')
        for name in names:
            entry=archive.getinfo(name)
            relative=PurePosixPath(name)
            if relative.is_absolute() or '..' in relative.parts or '\\' in name or stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError('Unsafe ZIP member')
            data=archive.read(name)
            if data[:4] in FONT_MAGIC or SECRET.search(data):
                raise ValueError('Font bytes or secret signature in review archive: '+name)
            if name in expected and (sha(data)!=expected[name]['sha256'] or len(data)!=expected[name]['bytes']):
                raise ValueError('Manifest digest mismatch: '+name)
    return {'archive':Path(path).name,'sha256':sha(Path(path).read_bytes()),'bytes':Path(path).stat().st_size,
            'members':len(names),'manifest_files_verified':len(expected),'crc':'passed','path_safety':'passed',
            'font_magic_scan':'passed','known_secret_signature_scan':'passed',
            'scope':'Explicit source/evidence allowlist. Signature scan is not a proof against every possible secret.'}


def build(root, destination):
    root=Path(root).resolve(); destination=Path(destination).resolve()
    files=[]
    paths = [root/name for name in ROOT_FILES if (root/name).exists()]
    paths += [path for directory in ROOT_DIRS if (root/directory).is_dir() for path in (root/directory).rglob('*')]
    for path in sorted(paths):
        rel=path.relative_to(root)
        if rel.parts[0] not in ROOT_DIRS and str(rel) not in ROOT_FILES:
            continue
        if any(p in {'__pycache__','.pytest_cache','.venv','.git'} for p in rel.parts):
            continue
        if path.is_symlink():
            raise ValueError('Symlink refused: '+str(rel))
        if not path.is_file() or (path.name not in ROOT_FILES and path.suffix not in SUFFIXES):
            continue
        data=path.read_bytes()
        if data[:4] in FONT_MAGIC or SECRET.search(data):
            raise ValueError('Font or secret signature: '+str(rel))
        files.append((rel.as_posix(),data))
    manifest={'version':'0.1.0','kind':'source-and-evidence-review','font_binaries_included':False,
              'files':[{'path':name,'bytes':len(data),'sha256':sha(data)} for name,data in files]}
    files.append(('REVIEW-MANIFEST.json',(json.dumps(manifest,indent=2)+'\n').encode()))
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name,data in files:
            item=zipfile.ZipInfo('type-evidence/'+name,date_time=(2026,9,30,0,0,0))
            item.compress_type=zipfile.ZIP_DEFLATED
            item.external_attr=0o100644 << 16
            archive.writestr(item,data)
    result=verify(destination)
    destination.with_suffix(destination.suffix+'.sha256').write_text(result['sha256']+'  '+destination.name+'\n')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--out')
    parser.add_argument('--verify')
    args=parser.parse_args()
    if bool(args.out)==bool(args.verify): parser.error('Use either --out or --verify')
    print(json.dumps(verify(args.verify) if args.verify else build(args.root,args.out),indent=2))
