"""Shared agent operations: the CLI and MCP take the same discovery path."""
from pathlib import Path


def discover(catalog, brief, visual='auto', reference_image=None):
    from .discovery import search, _validate_brief
    _validate_brief(brief)
    if visual not in ('auto', 'on', 'off'):
        raise ValueError('visual must be auto, on, or off')
    if reference_image is not None and (not isinstance(reference_image, str) or not reference_image):
        raise ValueError('reference_image must be a local image path')
    if reference_image and visual == 'off':
        raise ValueError('A reference image requires visual retrieval; omit visual:off or remove the reference image')
    mapping = None
    status = {'status':'disabled' if visual == 'off' else 'not_configured',
              'next':'Optional: install visual extra, run visual-setup then visual-index. Search works without it.'}
    from .visual import requested_script, SAMPLES
    sample_script = requested_script(brief)
    path = catalog.path.parent / (f'visual-{sample_script}.sqlite' if sample_script else 'visual.sqlite')
    if sample_script:
        status['requested_sample_script'] = sample_script
        status['next'] = (f'Optional: type-evidence visual-index --script {sample_script}; Latin glyph similarity is not used for this text.'
                          if sample_script in SAMPLES else 'No learned sample is configured for this script. Use exact-text comparisons and contextual rendering; metadata discovery remains available.')
    requested = any(brief.get(k) for k in ('query','tone','similar_to','avoid_like')) or reference_image
    exact_query = False
    if brief.get('query') and not any(brief.get(k) for k in ('tone','similar_to','avoid_like')) and not reference_image:
        clean = lambda value:' '.join(str(value or '').split()).casefold()
        query = clean(brief['query'])
        exact_query = any(query in {clean(value) for value in row}
                          for row in catalog.db.execute("SELECT json_extract(data,'$.family'),json_extract(data,'$.full_name'),json_extract(data,'$.postscript_name') FROM fonts"))
    if visual == 'auto' and exact_query:
        requested = False
        status = {'status':'name_lookup','reason':'An exact embedded name matched; automatic semantic scoring is reserved for aesthetic intent. Explicit visual:on still opts in.'}
    if visual != 'off' and (visual == 'on' or reference_image or (path.exists() and requested)):
        from .visual import scores
        try:
            mapping, status = scores(catalog, brief, reference_image=reference_image)
        except (ValueError, OSError, ImportError) as exc:
            if visual == 'on' or reference_image:
                raise
            status = {'status':'unavailable', 'error':str(exc), 'fallback':'Explicit constraints and measured/declared discovery remain active.'}
    result = search(catalog, brief, visual_index=mapping)
    result['visual_retrieval'] = status
    return result


def family(catalog, ident):
    chosen = catalog.get(ident)
    related = [f for f in catalog.all() if f['family'].casefold() == chosen['family'].casefold()]
    return {'family':chosen['family'], 'chosen_group':chosen['family_key'],
            'grouping':'Exact family + vendor + version + width class. Different groups are not silently merged.',
            'faces':[{k:f[k] for k in ['id','style','weight','italic','axes','family_key','version','vendor','family_limits']} for f in related][:200],
            'total_faces':len(related), 'truncated':len(related)>200}


def visual_status(catalog):
    import json
    import sqlite3
    path = catalog.path.parent / 'visual.sqlite'
    if not path.is_file():
        return {'status':'not_configured','next':'type-evidence visual-setup; type-evidence visual-index'}
    db = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        report = db.execute("SELECT value FROM meta WHERE key='report'").fetchone()
        stored = {row[0] for row in db.execute('SELECT id FROM vectors')}
        active = {row[0] for row in catalog.db.execute('SELECT id FROM fonts')}
        return {'status':'available', 'last_build':json.loads(report[0]) if report else None,
                'stored_vectors':len(stored), 'indexed_current_faces':len(stored & active),
                'catalog_faces':len(active), 'unindexed_current_faces':len(active-stored), 'stale_vectors':len(stored-active)}
    except (sqlite3.DatabaseError, ValueError) as exc:
        return {'status':'unavailable','error':str(exc),'next':'Preserve the invalid index and rebuild to a new path.'}
    finally:
        db.close()
