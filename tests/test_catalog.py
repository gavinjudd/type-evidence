import io
import json
from pathlib import Path

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

from type_evidence.catalog import Catalog, index_sources, file_hash


def make_font(path, family='Fixture', weight=400, license_text=None):
    builder = FontBuilder(1000, isTTF=True)
    chars = ' HxilMW0123456789abc'
    order = ['.notdef'] + [f'u{ord(c)}' for c in chars]
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap({ord(c):f'u{ord(c)}' for c in chars})
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        if name != 'u32':
            height = 500 if name == 'u120' else 700
            pen.moveTo((50,0)); pen.lineTo((450,0)); pen.lineTo((450,height)); pen.lineTo((50,height)); pen.closePath()
        glyphs[name] = pen.glyph()
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics({name:(600,50) for name in order})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    names = {'familyName':family,'styleName':'Regular','fullName':family+' Regular','psName':family.replace(' ','')+'-Regular','version':'Version 1.0'}
    if license_text:
        names['licenseDescription'] = license_text
    builder.setupNameTable(names)
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200, usWeightClass=weight)
    builder.setupPost()
    builder.setupMaxp()
    builder.save(path)


def build(tmp_path):
    source = tmp_path/'fonts'
    source.mkdir()
    make_font(source/'wrong-name.bin', license_text='SIL Open Font License, Version 1.1')
    (source/'duplicate.ttf').write_bytes((source/'wrong-name.bin').read_bytes())
    (source/'empty.otf').write_bytes(b'')
    (source/'LICENSE.txt').write_text('Local license evidence, applicability needs review.')
    target = tmp_path/'catalog.sqlite'
    report = index_sources([{'id':'fixture','root':str(source),'url':'https://example.test/fonts','commit':'a'*40}], target, workers=1)
    return source, target, report


def test_content_not_filename_duplicate_provenance_and_rights(tmp_path):
    source,target,report = build(tmp_path)
    assert report['faces'] == 1 and report['exact_duplicate_files'] == 1
    assert report['issue_counts']['invalid-signature'] == 1
    catalog = Catalog(target)
    font = catalog.all()[0]
    assert font['family'] == 'Fixture'
    assert len(font['origins']) == 2
    assert font['metrics']['x_height_em'] == .5
    assert font['metrics']['mono_measured'] is True
    assert font['rights']['status'] == 'embedded-open-license'
    assert font['rights']['review_required'] is True
    assert font['rights']['nearby_files'][0]['path'] == 'LICENSE.txt'
    assert catalog.resolve(font['id'])['sha256'] == file_hash(source/'duplicate.ttf')
    catalog.close()


def test_resolve_fails_closed_on_changed_all_copies(tmp_path):
    source,target,_ = build(tmp_path)
    catalog = Catalog(target)
    ident = catalog.all()[0]['id']
    (source/'wrong-name.bin').write_bytes(b'changed')
    (source/'duplicate.ttf').write_bytes(b'changed')
    with pytest.raises(ValueError, match='No verified copy'):
        catalog.resolve(ident)
    catalog.close()


def test_cache_and_deletion_refresh(tmp_path):
    source,target,_ = build(tmp_path)
    (source/'wrong-name.bin').unlink()
    report = index_sources([{'id':'fixture','root':str(source)}], target, workers=1)
    assert report['metadata_cache_hits'] == 1
    cat = Catalog(target)
    assert len(cat.all()[0]['origins']) == 1
    cat.close()
    (source/'duplicate.ttf').unlink()
    report = index_sources([{'id':'fixture','root':str(source)}], target, workers=1)
    assert report['faces'] == 0


def test_collection_faces_and_woff_equivalence(tmp_path):
    source = tmp_path/'fonts'; source.mkdir()
    make_font(source/'regular.ttf')
    make_font(source/'bold.ttf', weight=700)
    collection = TTCollection()
    collection.fonts = [TTFont(source/'regular.ttf'),TTFont(source/'bold.ttf')]
    collection.save(source/'family.ttc')
    for f in collection.fonts: f.close()
    font = TTFont(source/'regular.ttf'); font.flavor = 'woff2'; font.save(source/'mislabel.ttf'); font.close()
    target=tmp_path/'index.sqlite'
    report = index_sources([{'id':'fixture','root':str(source)}], target, workers=1)
    assert report['faces'] == 5
    catalog=Catalog(target)
    ttc = [f for f in catalog.all() if any(o['path']=='family.ttc' for o in f['origins'])]
    assert {f['face_index'] for f in ttc} == {0,1}
    assert report['equivalent_table_groups'] >= 1
    catalog.close()


def test_symlink_skipped_and_new_symlink_rejected(tmp_path):
    source,target,_ = build(tmp_path)
    cat=Catalog(target); ident=cat.all()[0]['id']
    payload=(source/'duplicate.ttf').read_bytes()
    external=tmp_path/'external.ttf'; external.write_bytes(payload)
    for name in ['duplicate.ttf','wrong-name.bin']:
        (source/name).unlink(); (source/name).symlink_to(external)
    with pytest.raises(ValueError, match='Symlink'):
        cat.resolve(ident)
    cat.close()


def test_same_name_different_version_not_collapsed(tmp_path):
    source=tmp_path/'fonts'; source.mkdir()
    make_font(source/'a.ttf')
    make_font(source/'b.ttf',weight=700)
    font=TTFont(source/'b.ttf'); font['name'].setName('Version 2.0',5,3,1,0x409); font['name'].setName('Version 2.0',5,1,0,0); font.save(source/'b.ttf'); font.close()
    report=index_sources([{'id':'f','root':str(source)}],tmp_path/'db.sqlite',workers=1)
    assert report['family_names']==1 and report['family_groups']==2


def test_duplicate_source_id_rejected(tmp_path):
    with pytest.raises(ValueError, match='unique id'):
        index_sources([{'id':'x','root':str(tmp_path)}]*2,tmp_path/'db.sqlite',workers=1)
