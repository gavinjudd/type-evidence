/* Run with: node --test tests/test_explorer.js */
'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { normalizeDirectory, filterFonts, previewStyle, previewURL, parseGoogleFaces, restoreSaved, exportBrief, safeURL } = require('../docs/explorer.js');
const raw = [
  { id: 'directory:google-fonts:inter', family: 'Inter', provider: 'Google Fonts', vendor: 'Rasmus Andersson', category: 'sans-serif', license_kind: 'open', variable: true, styles: ['100','300','500','400i'], tags: ['grotesque'], source_url: 'https://example.com/inter', preview: { type: 'google-fonts', family: 'Inter' } },
  { id: 'directory:commercial:sohne', family: 'Söhne', provider: 'Klim', category: 'sans-serif', license_kind: 'commercial', source_url: 'https://example.com/sohne', preview: { type: 'provider-only' } },
  { id: 'directory:google-fonts:newsreader', family: 'Newsreader', provider: 'Google Fonts', category: 'serif', license_kind: 'open', styles: ['400', '400i'], tags: ['reading'], source_url: 'https://example.com/newsreader', preview: { type: 'google-fonts' } }
];
const fonts = normalizeDirectory({ schema_version: 1, families: raw });
test('normalization rejects unsupported schemas and removes duplicate/invalid records', () => {
  assert.throws(() => normalizeDirectory({ families: [] }));
  const entries = normalizeDirectory({ schema_version: 1, families: [...raw, raw[0], { family:'Bad' }, { id:'new',family:'Safe',license_kind:'open',category:'bogus', source_url:'javascript:alert(1)' }] });
  assert.equal(entries.length, 4); assert.equal(entries[3].category, 'unknown'); assert.equal(entries[3].source_url, '');
});
test('search composes metadata terms with independent license, category, provider, and variable facets', () => {
  assert.deepEqual(filterFonts(fonts, { query:'rasmus grotesque', access:'open', category:'sans-serif', provider:'Google Fonts', variable:true }).map(f => f.family), ['Inter']);
  assert.equal(filterFonts(fonts, { query:'rasmus', access:'commercial' }).length, 0);
  assert.deepEqual(filterFonts(fonts, { access:'commercial' }).map(f => f.family), ['Söhne']);
  assert.deepEqual(filterFonts(fonts, { query:'reading', category:'serif' }).map(f => f.family), ['Newsreader']);
});
test('shortlist is a strict intersection and sort does not mutate the directory', () => {
  const original = fonts.map(f => f.id);
  assert.deepEqual(filterFonts(fonts, { savedOnly:true, sort:'name' }, new Set([fonts[2].id])).map(f => f.family), ['Newsreader']);
  assert.deepEqual(filterFonts(fonts, { sort:'name' }).map(f => f.family), ['Inter','Newsreader','Söhne']);
  assert.deepEqual(fonts.map(f => f.id), original);
});
test('commercial records cannot produce a Google preview URL even if metadata requests one', () => {
  assert.equal(previewURL({ ...fonts[1], preview: { type:'google-fonts' } }), '');
  assert.equal(previewURL(fonts[0]), 'https://fonts.googleapis.com/css2?family=Inter:wght@300&display=swap');
  assert.equal(previewURL(fonts[2]), 'https://fonts.googleapis.com/css2?family=Newsreader:wght@400&display=swap');
});
test('preview chooses an actual declared upright weight, or italic when no upright exists', () => {
  assert.deepEqual(previewStyle({ styles:['400i','700i'] }), { weight:400,italic:true });
  assert.deepEqual(previewStyle({ styles:['900','300','500'] }), { weight:300,italic:false });
  assert.deepEqual(previewStyle({ styles:['invalid'] }), { weight:400,italic:false });
});
test('stylesheet parsing accepts only Google font-file URLs and constrained face descriptors', () => {
  const good = '@font-face { font-family: \'Example\'; font-style: normal; font-weight: 400; src: url(https://fonts.gstatic.com/s/example.woff2) format(\'woff2\'); unicode-range: U+0000-00FF, U+0131; }';
  const parsed = parseGoogleFaces(good); assert.equal(parsed.length,1); assert.equal(parsed[0].descriptors.weight,'400');
  assert.equal(parseGoogleFaces(good.replace('fonts.gstatic.com','evil.example')).length,0);
  assert.equal(parseGoogleFaces(good.replace('https://','http://')).length,0);
  assert.equal(parseGoogleFaces(good.replace('normal;','oblique;')).length,0);
  assert.equal(safeURL('javascript:alert(1)'), '');
});
test('saved state drops stale IDs, deduplicates, caps notes, and recovers from damaged storage', () => {
  const valid = new Set(fonts.map(f => f.id));
  const restored = restoreSaved(JSON.stringify({ ids:[fonts[0].id,'old',fonts[0].id],note:'x'.repeat(2000) }), valid);
  assert.deepEqual(restored.ids,[fonts[0].id]); assert.equal(restored.note.length,1500);
  assert.deepEqual(restoreSaved('{broken',valid),{ ids:[],note:'' });
  assert.deepEqual(restoreSaved('null',valid),{ ids:[],note:'' });
});
test('brief separates directory IDs from local files and records real preview state and rights', () => {
  const brief = exportBrief([fonts[0],fonts[1]], { text:'Build [something]',size:36,note:'Editorial project',date:'2026-10-13',loaded:new Set([fonts[0].id]) });
  assert.match(brief,/Display size: 36 px/); assert.match(brief,/Google-hosted face loaded at weight 300/); assert.match(brief,/Commercial; obtain the required license/); assert.match(brief,/Not loaded/); assert.match(brief,/not resolved local face IDs/); assert.match(brief,/type-evidence directory --id 'directory:google-fonts:inter'/); assert.match(brief,/import-local/); assert.ok(brief.includes('Build \\[something\\]'));
});

test('search relevance places exact and prefix family matches before incidental metadata', () => {
  const directory = normalizeDirectory({ schema_version:1, families:[...raw, { ...raw[0],id:'tight',family:'Inter Tight' },{ ...raw[0],id:'other',family:'Andika',vendor:'SIL International' }] });
  assert.deepEqual(filterFonts(directory,{query:'Inter'}).map(f => f.family),['Inter','Inter Tight','Andika']);
  assert.deepEqual(filterFonts(directory,{query:'Inter',sort:'name'}).map(f => f.family),['Andika','Inter','Inter Tight']);
});

test('published directory is byte-identical to packaged metadata and provides open/commercial breadth', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const web = fs.readFileSync(path.join(__dirname,'../docs/font-directory.json'),'utf8');
  const packaged = fs.readFileSync(path.join(__dirname,'../type_evidence/font_directory.json'),'utf8');
  assert.equal(web,packaged);
  const entries = normalizeDirectory(JSON.parse(web));
  assert.ok(entries.filter(f => f.license_kind === 'open').length >= 1900);
  assert.ok(entries.filter(f => f.license_kind === 'commercial').length >= 100);
  assert.ok(entries.filter(f => f.license_kind === 'commercial').every(f => previewURL(f) === ''));
});

test('unaccented and decomposed searches preserve exact/prefix family relevance and explicit sorts', () => {
  const directory = normalizeDirectory({ schema_version:1, families:[raw[1], { ...raw[1],id:'prefix',family:'Söhne Mono',provider:'A Foundry' }, { ...raw[0],id:'metadata',family:'A Different Font',vendor:'Söhne Studio' }] });
  for (const query of ['SOHNE','sÖhne','so\u0308hne']) {
    assert.deepEqual(filterFonts(directory,{query}).map(f => f.family),['Söhne','Söhne Mono','A Different Font']);
  }
  assert.deepEqual(filterFonts(directory,{query:'sohne',sort:'name'}).map(f => f.family),['A Different Font','Söhne','Söhne Mono']);
  assert.deepEqual(filterFonts(directory,{query:'sohne',sort:'provider'}).map(f => f.family),['Söhne Mono','A Different Font','Söhne']);
});

test('designer and subset metadata are searchable with accent/case normalization', () => {
  const directory = normalizeDirectory({ schema_version:1, families:[{ ...raw[0],designers:['René Noël'],subsets:['Latin-Ext','Arabic'] },raw[1]] });
  assert.deepEqual(filterFonts(directory,{query:'RENE noel Arabic'}).map(f => f.family),['Inter']);
  assert.deepEqual(filterFonts(directory,{query:'latin-ext'}).map(f => f.family),['Inter']);
  assert.equal(filterFonts(directory,{query:'Arabic',access:'commercial'}).length,0);
});
