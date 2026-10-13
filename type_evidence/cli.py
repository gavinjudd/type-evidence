"""Model-neutral JSON CLI. All normal output is machine-readable JSON."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .catalog import Catalog, index_sources


def parser():
    p = argparse.ArgumentParser(prog='type-evidence', description=__doc__)
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--catalog', default='library/catalog.sqlite', help='SQLite catalog path')
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('fetch', help='Fetch pinned sources and prepare local derivatives')
    s.add_argument('--lock', default='sources.lock.json')
    s.add_argument('--library', default='library')
    s.add_argument('--pack', action='append', dest='packs', help='Open-font pack; repeat to combine')
    s.add_argument('--family', action='append', dest='families', help='Open family name or slug; repeat to combine')
    s.add_argument('--source', action='append', dest='source_ids', help='Legacy lock source id; repeat to combine')
    s.add_argument('--workers', type=int, default=4)
    s.add_argument('--plan', action='store_true', help='Show sizes and sources without downloading')
    sub.add_parser('packs', help='List downloadable open-font packs and their sizes')
    s = sub.add_parser('directory', help='Search the bundled open/commercial family directory; no local catalog needed')
    s.add_argument('--query', default='')
    for name in ['category', 'provider', 'vendor', 'license-kind', 'access']:
        s.add_argument('--' + name)
    s.add_argument('--tag', action='append', dest='tags')
    variable = s.add_mutually_exclusive_group()
    variable.add_argument('--variable', action='store_true', default=None)
    variable.add_argument('--static', dest='variable', action='store_false', default=None)
    s.add_argument('--limit', type=int, default=20)
    s.add_argument('--offset', type=int, default=0)
    s.add_argument('--id', help='Inspect a directory family identifier')
    s.add_argument('--stats', action='store_true')
    s = sub.add_parser('import-local', help='Register fonts you own without copying or installing them')
    s.add_argument('root')
    s.add_argument('--id', required=True)
    s.add_argument('--library', default='library')
    s.add_argument('--url', default='', help='Optional public provenance URL')
    s.add_argument('--index', action='store_true', help='Also index all registered sources into --catalog')
    s.add_argument('--workers', type=int, default=4)
    s = sub.add_parser('index', help='Inspect source bytes and atomically build/rebuild catalog')
    s.add_argument('--sources', default='library/sources.local.json')
    s.add_argument('--workers', type=int, default=4)
    sub.add_parser('stats')
    s = sub.add_parser('issues')
    s.add_argument('--limit', type=int, default=30)
    s = sub.add_parser('search')
    s.add_argument('--brief', help='JSON brief path; see examples/')
    s.add_argument('--query')
    s.add_argument('--family', help='Hard exact embedded family-name filter')
    s.add_argument('--role', choices=['ui','body','display','code','brand','game','document'])
    s.add_argument('--text')
    s.add_argument('--text-file')
    s.add_argument('--limit', type=int)
    s.add_argument('--weight', type=int)
    s.add_argument('--italic', action='store_true', default=None)
    s.add_argument('--min-styles', type=int)
    s.add_argument('--category')
    s.add_argument('--require-open-evidence', action='store_true', default=None)
    s.add_argument('--existing-id')
    s.add_argument('--offset', type=int)
    s.add_argument('--exclude', nargs='+')
    s.add_argument('--exclude-families', nargs='+')
    s.add_argument('--style')
    s.add_argument('--required-styles', help='JSON list of weight/italic objects')
    s.add_argument('--similar-to')
    s.add_argument('--avoid-like')
    s.add_argument('--audience')
    s.add_argument('--medium')
    s.add_argument('--tone')
    s.add_argument('--language')
    s.add_argument('--hierarchy')
    s.add_argument('--surroundings')
    s.add_argument('--density', choices=['comfortable','balanced','dense'])
    s.add_argument('--size', type=float)
    s.add_argument('--visual', choices=['auto','on','off'], default=None)
    s.add_argument('--reference-image', help='Local cropped typography image for learned resemblance retrieval')
    s.add_argument('--upright', dest='italic', action='store_false', default=None)
    for name in ['inspect', 'resolve', 'family']:
        s = sub.add_parser(name)
        s.add_argument('id', help='Full sha256:face_index returned by search')
    s = sub.add_parser('compare')
    s.add_argument('ids', nargs='+')
    s.add_argument('--text')
    s.add_argument('--text-file')
    s.add_argument('--out', required=True)
    s.add_argument('--sizes', nargs='+', type=int, default=[16,32,64])
    s.add_argument('--axes', default='{}', help='JSON axis tag:value or font-id:{tag:value}')
    s.add_argument('--features', nargs='*', default=[])
    s.add_argument('--direction', default=None)
    s.add_argument('--language', default=None)
    s = sub.add_parser('compose', help='Render a contextual layout and exact application recipe')
    s.add_argument('--spec', required=True, help='JSON layout specification')
    s.add_argument('--out', required=True)
    s = sub.add_parser('visual-setup', help='Explicitly download and verify the optional local FontCLIP checkpoint')
    s.add_argument('--directory', default=None)
    s = sub.add_parser('visual-index', help='Incrementally embed exact rendered faces; resume safely by rerunning')
    s.add_argument('--out', default=None)
    s.add_argument('--checkpoint', default=None)
    s.add_argument('--limit', type=int)
    s.add_argument('--device', choices=['cpu','mps','cuda'], default='cpu')
    s.add_argument('--batch-size', type=int, default=16)
    s.add_argument('--script', help='Embed this actual script, e.g. Arabic, Greek, Devanagari; uses a separate index')
    sub.add_parser('visual-status')
    s = sub.add_parser('pin-source', help='Add an official GitHub subset to a source lock by full commit and selected paths')
    s.add_argument('--repository', required=True)
    s.add_argument('--commit', required=True)
    s.add_argument('--paths', nargs='+', required=True)
    s.add_argument('--id', required=True)
    s.add_argument('--lock', default='sources.lock.json')
    s = sub.add_parser('project', help='Bounded existing typography inventory; project text stays local')
    s.add_argument('root')
    s = sub.add_parser('mcp', help='Local stdio MCP server; no listening network port')
    s.add_argument('--out', default='library/comparisons')
    sub.add_parser('doctor')
    return p


def _text(args):
    if args.text is not None and args.text_file:
        raise ValueError('Use either --text or --text-file')
    if args.text_file:
        path = Path(args.text_file)
        if path.stat().st_size > 20000:
            raise ValueError('Text file exceeds 20 KB; provide a representative specimen')
        return path.read_text(encoding='utf-8')
    return args.text


def run(args):
    if args.command == 'directory':
        from .directory import directory_stats, search_directory, directory_detail
        if args.id and args.stats:
            raise ValueError('Use either --id or --stats')
        if args.id:
            return directory_detail(args.id)
        if args.stats:
            return directory_stats()
        return search_directory(args.query, **{key:getattr(args, key) for key in
            ['category','provider','vendor','license_kind','access','tags','variable','limit','offset']})
    if args.command == 'packs':
        from .sources import source_packs
        return source_packs()
    if args.command == 'import-local':
        from .library import import_local
        result = import_local(args.root, args.id, args.library, args.url)
        if args.index:
            result['index'] = index_sources(json.loads(Path(result['sources_file']).read_text(encoding='utf-8')), args.catalog, args.workers)
        return result
    if args.command == 'visual-setup':
        from .visual import setup_model
        return setup_model(args.directory or Path(args.catalog).resolve().parent / 'models')
    if args.command == 'pin-source':
        from .sources import pin_github_source
        path = Path(args.lock)
        data = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'schema':2,'sources':[]}
        if any(s['id'] == args.id for s in data['sources']):
            raise ValueError('Source id already exists; use a new id or review/edit the existing lock explicitly')
        source = pin_github_source(args.repository,args.commit,args.paths,args.id)
        data['sources'].append(source)
        data['schema'] = 2
        path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
        return {'lock':str(path.resolve()),'added_source':source['id'],
                'next':'Fetch only added_source from this lock using --source and --lock, then index.',
                'next_argv':['type-evidence','fetch','--source',source['id'],'--lock',str(path.resolve())]}
    if args.command == 'fetch':
        from .sources import fetch, prepare, plan_fetch
        from .library import merge_sources
        selection = dict(source_ids=args.source_ids, packs=args.packs, families=args.families)
        if args.plan:
            return plan_fetch(args.lock, **selection)
        root = Path(args.library).resolve()
        sources = fetch(Path(args.lock), root, workers=args.workers, **selection)
        derived = [prepare(s['root'], root / 'derived' / s['id'], s['id'], s['commit'], s['url']) for s in sources]
        config = root / 'sources.local.json'
        registered = merge_sources(config, sources + derived)
        reports = [d.get('report') or {} for d in derived]
        summary = {key:sum(report.get(key, 0) for report in reports)
                   for key in ['base64_fonts','archive_fonts','license_sidecars','archives_seen','derived_files']}
        summary['issues'] = sum(len(report.get('issues', [])) for report in reports)
        return {'sources_file': str(config), 'sources': len(sources), 'registered_sources':len(registered),
                'preparation':reports[:30], 'preparation_total':len(reports), 'preparation_truncated':len(reports)>30,
                'preparation_summary':summary,
                'detail':'Complete per-source preparation reports are preserved in sources_file.',
                'next':'Index sources_file into the selected catalog.',
                'next_argv':['type-evidence','--catalog',str(Path(args.catalog).resolve()),'index','--sources',str(config)]}
    if args.command == 'index':
        return index_sources(json.loads(Path(args.sources).read_text(encoding='utf-8')), args.catalog, args.workers)
    if args.command == 'doctor':
        import platform, fontTools, PIL, uharfbuzz
        from PIL import features
        from .directory import directory_stats
        directory = directory_stats()
        return {'version':__version__, 'python':platform.python_version(), 'platform':platform.platform(),
                'fonttools':fontTools.__version__, 'pillow':PIL.__version__, 'harfbuzz':uharfbuzz.version_string(),
                'pillow_raqm':features.check_feature('raqm'), 'catalog_exists':Path(args.catalog).is_file(),
                'catalog_path':str(Path(args.catalog).resolve()),
                'directory':{key:directory[key] for key in ['total_families','open_families','commercial_families']},
                'next':(['Run stats and search with --catalog set to catalog_path before the subcommand.']
                        if Path(args.catalog).is_file() else
                        ['type-evidence directory --limit 6','type-evidence packs',
                         'type-evidence fetch --pack starter --plan',
                         'Register owned fonts with import-local, then index into catalog_path.']),
                'rights_policy':'Evidence is not permission. Unknown rights remain unknown.'}
    if args.command == 'project':
        from .discovery import project_context
        return project_context(args.root)
    if args.command == 'mcp':
        from .mcp import serve
        serve(args.catalog, args.out)
        return None
    catalog = Catalog(args.catalog)
    try:
        if args.command == 'stats':
            return catalog.stats()
        if args.command == 'issues':
            return {'issues':catalog.issues(args.limit), 'limit':args.limit}
        if args.command == 'inspect':
            return catalog.get(args.id)
        if args.command == 'resolve':
            return catalog.resolve(args.id)
        if args.command == 'family':
            from .operations import family
            return family(catalog, args.id)
        if args.command == 'search':
            from .operations import discover
            brief = json.loads(Path(args.brief).read_text(encoding='utf-8')) if args.brief else {}
            saved_visual = brief.pop('visual','auto')
            saved_reference = brief.pop('reference_image',None)
            for key in ['query','family','role','limit','weight','italic','min_styles','category','require_open_evidence','existing_id',
                        'offset','exclude','exclude_families','style','similar_to','avoid_like','audience','medium','tone',
                        'language','hierarchy','surroundings','density','size']:
                value = getattr(args, key)
                if value is not None:
                    brief[key] = value
            if args.required_styles is not None:
                brief['required_styles'] = json.loads(args.required_styles)
            text = _text(args)
            if text is not None:
                brief['text'] = text
            return discover(catalog, brief, visual=args.visual if args.visual is not None else saved_visual,
                            reference_image=args.reference_image if args.reference_image is not None else saved_reference)
        if args.command == 'compose':
            from .composition import compose
            path = Path(args.spec)
            if path.stat().st_size > 100000: raise ValueError('Composition spec exceeds 100 KB')
            return compose(catalog, json.loads(path.read_text(encoding='utf-8')), Path(args.out))
        if args.command == 'visual-index':
            from .visual import build_index
            return build_index(catalog, args.out, args.checkpoint, args.limit, args.device, args.batch_size,
                               progress=lambda data: print(json.dumps(data),file=sys.stderr,flush=True), script=args.script)
        if args.command == 'visual-status':
            from .operations import visual_status
            return visual_status(catalog)
        if args.command == 'compare':
            from .render import compare
            text = _text(args)
            if text is None:
                raise ValueError('Supply representative project text with --text or --text-file')
            return compare(catalog, args.ids, text, Path(args.out), sizes=args.sizes,
                           axes=json.loads(args.axes), features=args.features,
                           direction=args.direction, language=args.language)
        raise ValueError('Unknown command')
    finally:
        catalog.close()


def main():
    # JSON is UTF-8 across terminals and redirected pipes, including Windows
    # hosts whose legacy default code page cannot represent the requested text.
    for stream in (sys.stdout,sys.stderr):
        if hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    args = parser().parse_args()
    try:
        result = run(args)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({'error':str(exc), 'type':type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0
