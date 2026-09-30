"""Rehash one resolvable source copy for every indexed face. No font installation."""
import argparse
import json
import time
from type_evidence.catalog import Catalog


def verify(path):
    started=time.perf_counter()
    catalog=Catalog(path)
    checked=0; failures=[]; files=set()
    try:
        for row in catalog.db.execute('SELECT id FROM fonts ORDER BY id'):
            try:
                asset=catalog.resolve(row[0])
                checked+=1; files.add(asset['sha256'])
            except (ValueError,OSError) as exc:
                failures.append({'id':row[0],'error':str(exc)})
        return {'indexed_faces':catalog.stats()['faces'],'verified_faces':checked,
                'unique_resolved_file_hashes':len(files),'failures':failures,
                'elapsed_seconds':round(time.perf_counter()-started,3),
                'scope':'One exact hash-verified source copy per indexed face, including collection face indices. Not a full-glyph rendering test.'}
    finally:
        catalog.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('catalog');args=parser.parse_args()
    result=verify(args.catalog);print(json.dumps(result,indent=2));raise SystemExit(bool(result['failures']))
