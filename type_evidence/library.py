"""Non-destructive local source registration for owned and downloaded fonts."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit


def merge_sources(config, additions):
    """Keep existing sources; refresh an entry only at the same root and pin.

    A failed validation leaves the previous config intact. This does not index,
    copy, install or grant rights to any asset.
    """
    config = Path(config).expanduser().absolute()
    if config.is_symlink():
        raise ValueError('Source configuration must not be a symlink')
    existing = json.loads(config.read_text(encoding='utf-8')) if config.exists() else []
    if not isinstance(existing, list) or not isinstance(additions, list):
        raise ValueError('Source configuration must be a list')
    merged = {}
    for position, source in enumerate(existing + additions):
        if not isinstance(source, dict) or not isinstance(source.get('id'), str) or not source['id']:
            raise ValueError('Every source needs an id')
        if not isinstance(source.get('root'), str) or not source['root']:
            raise ValueError('Every source needs a root')
        ident = source['id']
        if ident in merged:
            previous = merged[ident]
            if position < len(existing):
                raise ValueError('Existing configuration has duplicate source ids')
            if (Path(previous['root']).expanduser().resolve() != Path(source['root']).expanduser().resolve()
                    or previous.get('commit', '') != source.get('commit', '')
                    or previous.get('url', '') != source.get('url', '')):
                raise ValueError('Source id already refers to another root or provenance; use a new id: ' + ident)
            merged[ident] = {**previous, **source}
        else:
            merged[ident] = source
    config.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=config.parent,
                                         prefix='.sources-', suffix='.json', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(list(merged.values()), stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, config)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return list(merged.values())


def import_local(root, ident, library='library', url=''):
    """Register an explicit user-owned font directory without copying its files."""
    if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', ident):
        raise ValueError('Source id must be a safe name of 1–80 characters')
    path = Path(root).expanduser().absolute()
    if path.is_symlink() or not path.is_dir():
        raise ValueError('Font root must be an existing non-symlink directory')
    if url:
        parsed = urlsplit(url)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError('Use a public HTTPS provenance URL without credentials, query or fragment')
    source = {'id': ident, 'root': str(path.resolve()), 'url': url, 'commit': ''}
    config = Path(library).expanduser().resolve() / 'sources.local.json'
    sources = merge_sources(config, [source])
    return {'sources_file': str(config), 'source': source, 'sources': len(sources),
            'files_copied': False, 'fonts_installed': False,
            'rights_policy': 'Local access is not a license grant. Embedded and nearby rights evidence is inspected during indexing.',
            'next': 'Index this source configuration to obtain exact, hash-verified face IDs.'}
