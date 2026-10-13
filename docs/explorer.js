/* Type Evidence web directory. No font requests occur until a preview is requested. */
(function (root) {
  'use strict';
  const CATEGORY_LABELS = { 'sans-serif': 'Sans serif', serif: 'Serif', display: 'Display', handwriting: 'Handwriting', monospace: 'Monospace', unknown: 'Unclassified' };
  const STARTING_POINTS = ['Instrument Serif', 'Inter', 'Neue Haas Grotesk', 'Space Grotesk', 'Fraunces', 'Söhne', 'IBM Plex Sans', 'DM Sans', 'GT America', 'Bodoni Moda', 'Atkinson Hyperlegible', 'Canela', 'Manrope', 'Newsreader', 'Futura', 'Space Mono', 'Bricolage Grotesque', 'Geist', 'Cormorant Garamond', 'Alegreya', 'DM Mono', 'Archivo', 'Spectral', 'Syne'];
  const DEFAULT_TEXT = 'The details make the difference.';
  const STORAGE_KEY = 'type-evidence.shortlist.v1';
  const PAGE_SIZE = 24;
  function safeURL(value) {
    try { const u = new URL(value); return u.protocol === 'https:' ? u.href : ''; } catch (_) { return ''; }
  }
  function normalizeSearch(value) {
    return String(value || '').normalize('NFKD').toLowerCase().replace(/ß/g, 'ss').replace(/ς/g, 'σ').replace(/\p{M}/gu, '');
  }
  function normalizeDirectory(data) {
    if (!data || data.schema_version !== 1 || !Array.isArray(data.families)) throw new Error('Unsupported directory format.');
    const seen = new Set();
    return data.families.filter(f => f && typeof f.id === 'string' && typeof f.family === 'string' && ['open', 'commercial'].includes(f.license_kind)).filter(f => {
      if (seen.has(f.id)) return false; seen.add(f.id); return true;
    }).map(f => ({ ...f, category: Object.hasOwn(CATEGORY_LABELS, f.category) ? f.category : 'unknown', provider: String(f.provider || 'Unknown source'), vendor: String(f.vendor || ''), tags: Array.isArray(f.tags) ? f.tags.map(String) : [], styles: Array.isArray(f.styles) ? f.styles.map(String) : [], source_url: safeURL(f.source_url), specimen_url: safeURL(f.specimen_url || f.acquisition_url || f.source_url), acquisition_url: safeURL(f.acquisition_url || f.source_url), search: normalizeSearch([f.family, f.provider, f.vendor, f.designer, f.category, ...(Array.isArray(f.designers) ? f.designers : []), ...(Array.isArray(f.subsets) ? f.subsets : []), ...(Array.isArray(f.tags) ? f.tags : [])].filter(Boolean).join(' ')) }));
  }
  function filterFonts(fonts, filters, saved = new Set()) {
    const terms = normalizeSearch(filters.query).trim().split(/\s+/).filter(Boolean);
    const filtered = fonts.filter(f => (!filters.savedOnly || saved.has(f.id)) && (filters.access === 'all' || !filters.access || f.license_kind === filters.access) && (filters.category === 'all' || !filters.category || f.category === filters.category) && (filters.provider === 'all' || !filters.provider || f.provider === filters.provider) && (!filters.variable || f.variable === true) && terms.every(t => f.search.includes(t)));
    const rank = new Map(STARTING_POINTS.map((name, i) => [normalizeSearch(name), i]));
    const query = terms.join(' ');
    const matchRank = font => { const name = normalizeSearch(font.family); return name === query ? 0 : name.startsWith(query) ? 1 : name.includes(query) ? 2 : 3; };
    return filtered.sort((a, b) => {
      if (filters.sort === 'provider') return a.provider.localeCompare(b.provider) || a.family.localeCompare(b.family);
      if (filters.sort !== 'name') {
        if (query) { const relevance = matchRank(a) - matchRank(b); if (relevance) return relevance; }
        const delta = (rank.get(normalizeSearch(a.family)) ?? 1000) - (rank.get(normalizeSearch(b.family)) ?? 1000);
        if (delta) return delta;
      }
      return a.family.localeCompare(b.family) || a.provider.localeCompare(b.provider);
    });
  }
  function previewStyle(font) {
    const upright = font.styles.map(s => /^\d+$/.test(s) ? Number(s) : NaN).filter(n => Number.isFinite(n) && n >= 1 && n <= 1000);
    const italic = font.styles.map(s => /^(\d+)i$/.test(s) ? Number(s.slice(0, -1)) : NaN).filter(n => Number.isFinite(n) && n >= 1 && n <= 1000);
    const weights = upright.length ? upright : italic;
    return { weight: weights.length ? [...weights].sort((a, b) => Math.abs(a - 400) - Math.abs(b - 400) || a - b)[0] : 400, italic: !upright.length && italic.length > 0 };
  }
  function previewURL(font) {
    if (font.license_kind !== 'open' || font.preview?.type !== 'google-fonts') return '';
    const style = previewStyle(font);
    const family = String(font.preview.family || font.family);
    return 'https://fonts.googleapis.com/css2?family=' + encodeURIComponent(family) + (style.italic ? ':ital,wght@1,' : ':wght@') + style.weight + '&display=swap';
  }
  function parseGoogleFaces(css) {
    const blocks = String(css).match(/@font-face\s*\{[^}]*\}/g) || [];
    return blocks.map(block => {
      const source = /src:\s*url\((['"]?)([^)'"\s]+)\1\)\s*(?:format\((['"]?)([^)'"\s]+)\3\))?/i.exec(block);
      if (!source) return null;
      const url = safeURL(source[2]);
      if (!url || new URL(url).hostname !== 'fonts.gstatic.com') return null;
      const get = (key, fallback) => new RegExp(key + ':\\s*([^;}]+)').exec(block)?.[1].trim() || fallback;
      const style = get('font-style', 'normal');
      const weight = get('font-weight', '400');
      const unicodeRange = get('unicode-range', 'U+0-10FFFF');
      if (!/^(normal|italic)$/.test(style) || !/^\d+(?:\s+\d+)?$/.test(weight) || !/^[Uu+\dA-Fa-f?,\s-]+$/.test(unicodeRange)) return null;
      return { source: 'url("' + url + '")', descriptors: { style, weight, unicodeRange, display: 'swap' } };
    }).filter(Boolean);
  }
  function restoreSaved(raw, validIds) {
    try {
      const value = JSON.parse(raw);
      if (!value || !Array.isArray(value.ids)) return { ids: [], note: '' };
      return { ids: [...new Set(value.ids.filter(id => typeof id === 'string' && validIds.has(id)))], note: typeof value.note === 'string' ? value.note.slice(0, 1500) : '' };
    } catch (_) { return { ids: [], note: '' }; }
  }
  function markdownText(value) { return String(value || '').replace(/[\r\n]+/g, ' ').replace(/([\\`*_{}\[\]<>])/g, '\\$1'); }
  function exportBrief(fonts, options = {}) {
    const lines = ['# Type Evidence — font shortlist', '', 'Created: ' + (options.date || new Date().toISOString().slice(0, 10)), '', '## Project direction', '', options.note ? markdownText(options.note) : 'Add the audience, medium, language, hierarchy, density, and intended use.', '', '## Specimen settings', '', '- Text: ' + markdownText(options.text || DEFAULT_TEXT), '- Display size: ' + Number(options.size || 48) + ' px', '', '## Selected families', ''];
    fonts.forEach(f => {
      const loaded = options.loaded?.has(f.id);
      const style = previewStyle(f);
      lines.push('### ' + markdownText(f.family), '', '- Directory ID: `' + f.id.replace(/`/g, '') + '`', '- Source / foundry: ' + markdownText(f.provider), '- Classification: ' + (CATEGORY_LABELS[f.category] || 'Unclassified'), '- Access: ' + (f.license_kind === 'open' ? 'Open source; verify current font terms.' : 'Commercial; obtain the required license.'), '- Browser preview: ' + (loaded ? 'A Google-hosted face loaded at weight ' + style.weight + (style.italic ? ' italic' : ' upright') + '; glyph coverage and target rendering still need review.' : 'Not loaded; this selection is based on directory metadata or an external provider specimen.'), '- Provider: ' + (f.specimen_url || f.source_url), '- Source record: ' + f.source_url, '');
    });
    lines.push('## Continue with the local toolkit', '', 'These are directory family IDs, not resolved local face IDs. No font files are included in this brief. Acquire authorized files, then inspect and compare the actual styles and project text.', '', '```sh', 'type-evidence directory --id ' + shellQuote(fonts[0]?.id || 'DIRECTORY_ID'), 'type-evidence import-local /absolute/path/to/authorized-fonts --id owned --index', '```', '', 'Resolve local face IDs after importing. Check required languages, styles, axes, features, and deployment rights before implementation. The browser preview does not establish suitability or licensing.', '');
    return lines.join('\n');
  }
  function shellQuote(value) { return "'" + String(value).replace(/'/g, "'\\''") + "'"; }
  const core = { normalizeDirectory, filterFonts, previewStyle, previewURL, parseGoogleFaces, restoreSaved, exportBrief, safeURL, PAGE_SIZE };
  if (typeof module === 'object' && module.exports) module.exports = core;
  root.TypeEvidenceExplorer = core;
  if (typeof document === 'undefined') return;

  const $ = id => document.getElementById(id);
  const state = { fonts: [], byId: new Map(), saved: new Set(), compare: new Set(), previews: new Map(), filters: { query: '', access: 'all', category: 'all', provider: 'all', variable: false, savedOnly: false, sort: 'explore' }, page: 0, text: DEFAULT_TEXT, size: 48, note: '', storageOK: true };
  let toastTimer;
  const icon = name => name === 'bookmark' ? '<svg class="bookmark" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 2h8v12L8 11l-4 3z"/></svg>' : '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2" y="3" width="4" height="10"/><rect x="10" y="3" width="4" height="10"/></svg>';
  function el(tag, className, content) { const node = document.createElement(tag); if (className) node.className = className; if (content !== undefined) node.textContent = content; return node; }
  function button(label, className, handler) { const b = el('button', className, label); b.type = 'button'; b.addEventListener('click', handler); return b; }
  function link(label, href, className) { const a = el('a', className, label); a.href = safeURL(href); a.target = '_blank'; a.rel = 'noopener noreferrer'; return a; }
  function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('toast').hidden = true; }, 3600); }
  function persist() {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ ids: [...state.saved], note: state.note })); }
    catch (_) { state.storageOK = false; document.querySelector('.local-note').textContent = 'Shortlist kept for this tab only'; toast('Browser storage is unavailable. Export your shortlist to keep it.'); }
  }
  function syncSaved() { $('saved-count').textContent = state.saved.size; $('export-shortlist').disabled = !state.saved.size; $('clear-shortlist').disabled = !state.saved.size; }
  function toggleSaved(font) { if (state.saved.has(font.id)) state.saved.delete(font.id); else state.saved.add(font.id); persist(); syncSaved(); renderResults(); if ($('compare-dialog').open) renderComparison(); }
  function toggleCompare(font) {
    if (state.compare.has(font.id)) state.compare.delete(font.id);
    else { if (state.compare.size >= 4) { toast('Compare up to four fonts at a time. Remove one to try another.'); return; } state.compare.add(font.id); }
    syncCompare(); renderResults();
  }
  function syncCompare() {
    $('compare-tray').hidden = !state.compare.size;
    $('compare-count').textContent = state.compare.size + ' selected';
    $('compare-names').textContent = [...state.compare].map(id => state.byId.get(id).family).join(' / ');
    $('open-compare').disabled = state.compare.size < 2;
    $('open-compare').title = state.compare.size < 2 ? 'Select at least two families' : 'Compare selected families';
  }
  function action(font, kind) {
    const saved = kind === 'save', selected = (saved ? state.saved : state.compare).has(font.id);
    const label = saved ? (selected ? 'Saved' : 'Save') : 'Compare';
    const b = button('', 'row-action', () => saved ? toggleSaved(font) : toggleCompare(font));
    b.innerHTML = icon(saved ? 'bookmark' : 'compare'); b.append(document.createTextNode(label)); b.setAttribute('aria-pressed', String(selected));
    b.setAttribute('aria-label', (saved ? (selected ? 'Remove ' : 'Save ') : (selected ? 'Remove ' : 'Compare ')) + font.family + (saved ? (selected ? ' from shortlist' : ' to shortlist') : (selected ? ' from comparison' : '')));
    b.dataset.action = kind; b.dataset.font = font.id; return b;
  }
  function heading(font, comparison) {
    const row = el('div', 'row-heading'), name = el('div', 'family-heading');
    name.append(el('h3', '', font.family), el('span', 'family-provider', font.provider)); row.append(name);
    const actions = el('div', 'row-actions'); actions.append(action(font, 'save')); if (!comparison) actions.append(action(font, 'compare')); row.append(actions); return row;
  }
  function metadata(font) {
    const row = el('div', 'metadata-line'); row.append(el('span', 'access-tag ' + font.license_kind, font.license_kind === 'open' ? 'Open source' : 'Commercial'));
    const values = [CATEGORY_LABELS[font.category]];
    if (Number.isInteger(font.style_count) && font.style_count > 0) values.push(font.style_count + (font.style_count === 1 ? ' style' : ' styles'));
    if (font.variable === true) values.push('Variable');
    if (font.vendor && font.vendor !== font.provider && font.vendor.length < 80) values.push(font.vendor);
    values.forEach(text => { row.append(el('span', 'dot', '·'), el('span', '', text)); }); return row;
  }
  function previewNode(font) {
    const slot = el('div', 'preview-slot'), preview = state.previews.get(font.id);
    if (preview?.status === 'loaded') {
      const sample = el('p', 'font-specimen', state.text || DEFAULT_TEXT); sample.style.fontFamily = '"' + preview.alias + '"'; sample.style.fontWeight = preview.weight; sample.style.fontStyle = preview.italic ? 'italic' : 'normal'; sample.dataset.preview = font.id; slot.append(sample); return slot;
    }
    const placeholder = el('div', 'preview-placeholder'), message = el('div', 'preview-message'), description = el('p');
    message.append(el('span', 'preview-initial', 'Aa'));
    const canPreview = Boolean(previewURL(font));
    description.append(document.createTextNode(preview?.status === 'loading' ? 'Loading font face…' : preview?.status === 'failed' ? 'Preview could not load' : canPreview ? 'A closer look, on request.' : 'Explore at the foundry.'));
    description.append(el('small', '', preview?.status === 'failed' ? 'Check your connection or try again.' : canPreview ? 'No font loaded · Google-hosted preview' : 'Provider specimen · no font served here'));
    message.append(description); placeholder.append(message);
    if (canPreview) {
      const load = button(preview?.status === 'loading' ? 'Loading…' : preview?.status === 'failed' ? 'Retry preview ↻' : 'Load Google preview ↗', 'preview-button', () => loadPreview(font));
      load.disabled = preview?.status === 'loading'; load.dataset.action = 'load'; load.dataset.font = font.id; load.setAttribute('aria-label', (preview?.status === 'failed' ? 'Retry' : 'Load Google') + ' preview for ' + font.family); placeholder.append(load);
    } else if (font.specimen_url) { placeholder.append(link('View specimen ↗', font.specimen_url, 'preview-button')); }
    slot.append(placeholder); return slot;
  }
  function statusNode(font) {
    const preview = state.previews.get(font.id), label = el('span', 'preview-status ' + (preview?.status || ''));
    if (preview?.status === 'loaded') { label.append(el('span', 'status-dot')); label.append(document.createTextNode('Font loaded · ' + preview.weight + (preview.italic ? ' italic' : ' upright') + ' · glyph coverage not verified')); }
    else if (preview?.status === 'loading') label.textContent = 'Fetching font from Google Fonts…';
    else if (preview?.status === 'failed') label.textContent = 'Not previewed · font request failed';
    else label.textContent = font.license_kind === 'commercial' ? 'License required · provider metadata' : 'Directory metadata · specimen not loaded';
    return label;
  }
  function fontRow(font) {
    const row = el('article', 'font-row'); row.dataset.font = font.id;
    row.append(heading(font, false), metadata(font), previewNode(font));
    const foot = el('div', 'row-foot'); foot.append(statusNode(font));
    if (font.source_url) foot.append(link('Source & details ↗', font.source_url)); row.append(foot); return row;
  }
  function rememberFocus() { const a = document.activeElement; return a?.dataset.action ? { action: a.dataset.action, font: a.dataset.font } : null; }
  function restoreFocus(focus) { if (!focus) return; [...document.querySelectorAll('[data-action]')].find(n => n.dataset.action === focus.action && n.dataset.font === focus.font)?.focus({ preventScroll: true }); }
  function renderResults() {
    const focus = $('font-results').contains(document.activeElement) ? rememberFocus() : null, results = filterFonts(state.fonts, state.filters, state.saved), pageCount = Math.ceil(results.length / PAGE_SIZE);
    state.page = Math.max(0, Math.min(state.page, pageCount - 1));
    const start = state.page * PAGE_SIZE, shown = results.slice(start, start + PAGE_SIZE), container = $('font-results'); container.replaceChildren();
    $('results-count').textContent = results.length.toLocaleString() + (results.length === 1 ? ' family' : ' families') + (state.filters.savedOnly ? ' in shortlist' : '') + (results.length > PAGE_SIZE ? ' · ' + (start + 1) + '–' + (start + shown.length) : '');
    if (!shown.length) {
      const empty = el('div', 'empty-state'); empty.append(el('span', 'empty-symbol', 'Aa'), el('h3', '', state.filters.savedOnly && !state.saved.size ? 'Keep a few possibilities.' : 'No families in this direction.'), el('p', '', state.filters.savedOnly && !state.saved.size ? 'Save the fonts that catch your eye. Your shortlist stays in this browser and exports as a brief for you or your agent.' : 'Try a broader search or reset the filters. Search matches family names and declared metadata.'));
      empty.append(button(state.filters.savedOnly && !state.saved.size ? 'Explore the directory →' : 'Reset filters', 'button secondary', () => { if (state.filters.savedOnly && !state.saved.size) setView(false); resetFilters(); })); container.append(empty);
    } else shown.forEach(font => container.append(fontRow(font)));
    $('pagination').hidden = pageCount <= 1; $('previous-page').disabled = state.page <= 0; $('next-page').disabled = state.page >= pageCount - 1; $('page-count').textContent = 'Page ' + (state.page + 1) + ' of ' + pageCount;
    restoreFocus(focus);
  }
  function renderComparison() {
    const grid = $('comparison-grid'), hadFocus = grid.contains(document.activeElement), focus = hadFocus ? rememberFocus() : null; grid.replaceChildren(); grid.style.setProperty('--compare-columns', Math.min(state.compare.size, 4));
    [...state.compare].forEach(id => {
      const font = state.byId.get(id), column = el('article', 'comparison-column'); column.append(heading(font, true), metadata(font), previewNode(font), statusNode(font));
      const preview = state.previews.get(id);
      if (preview?.status === 'loaded') {
        column.append(el('p', 'comparison-size-label', 'Reading size / 18 px'));
        const text = el('p', 'comparison-reading', state.text || DEFAULT_TEXT); text.style.fontFamily = '"' + preview.alias + '"'; text.style.fontWeight = preview.weight; text.style.fontStyle = preview.italic ? 'italic' : 'normal'; column.append(text);
      }
      if (font.specimen_url) column.append(link('Visit provider ↗', font.specimen_url, 'provider-link')); grid.append(column);
    });
    if (hadFocus) { const target = [...grid.querySelectorAll('[data-action]')].find(n => n.dataset.action === focus?.action && n.dataset.font === focus?.font && !n.disabled); (target || document.querySelector('[data-close="compare-dialog"]')).focus({ preventScroll: true }); }
  }
  function refreshPreviews() { renderResults(); if ($('compare-dialog').open) renderComparison(); }
  async function loadPreview(font) {
    if (state.previews.get(font.id)?.status === 'loading' || !previewURL(font)) return;
    const prior = state.previews.get(font.id), style = previewStyle(font);
    const preview = { status: 'loading', alias: prior?.alias || 'TypeEvidenceFace' + state.fonts.indexOf(font), ...style, faces: prior?.faces || [] };
    state.previews.set(font.id, preview); refreshPreviews();
    const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 18000);
    try {
      if (!preview.faces.length) {
        const response = await fetch(previewURL(font), { signal: controller.signal, referrerPolicy: 'no-referrer' });
        if (!response.ok) throw new Error('Font stylesheet unavailable.');
        const sources = parseGoogleFaces(await response.text());
        if (!sources.length) throw new Error('No supported font faces returned.');
        preview.faces = sources.map(s => { const face = new FontFace(preview.alias, s.source, s.descriptors); document.fonts.add(face); return face; });
      }
      const loaded = await Promise.race([document.fonts.load((style.italic ? 'italic ' : '') + style.weight + ' 48px "' + preview.alias + '"', state.text || DEFAULT_TEXT), new Promise((_, reject) => controller.signal.addEventListener('abort', () => reject(new Error('Font request timed out.')), { once: true }))]);
      if (!loaded.length || !loaded.every(face => face.status === 'loaded')) throw new Error('Font loading was not confirmed.');
      preview.status = 'loaded';
    } catch (_) { preview.status = 'failed'; preview.faces.forEach(face => document.fonts.delete(face)); preview.faces = []; }
    finally { clearTimeout(timeout); refreshPreviews(); }
  }
  function resetFilters() {
    Object.assign(state.filters, { query: '', access: 'all', category: 'all', provider: 'all', variable: false }); state.page = 0;
    $('search').value = ''; $('provider').value = 'all'; $('variable').checked = false;
    document.querySelector('input[name="access"][value="all"]').checked = true;
    document.querySelectorAll('[data-category]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.category === 'all'))); renderResults();
  }
  function setView(savedOnly) {
    state.filters.savedOnly = savedOnly; state.page = 0;
    $('view-all').classList.toggle('active', !savedOnly); $('view-all').setAttribute('aria-pressed', String(!savedOnly));
    $('view-saved').classList.toggle('active', savedOnly); $('view-saved').setAttribute('aria-pressed', String(savedOnly)); $('shortlist-note').hidden = !savedOnly;
    resetFilters();
  }
  function exportSaved() {
    const selected = [...state.saved].map(id => state.byId.get(id)).filter(Boolean); if (!selected.length) return;
    const body = exportBrief(selected, { text: state.text, size: state.size, note: state.note, loaded: new Set([...state.previews].filter(([, p]) => p.status === 'loaded').map(([id]) => id)) });
    const href = URL.createObjectURL(new Blob([body], { type: 'text/markdown;charset=utf-8' })), a = el('a'); a.href = href; a.download = 'type-evidence-shortlist.md'; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(href), 1000); toast('Shortlist exported with source links and next steps.');
  }
  function wireControls() {
    $('search').addEventListener('input', e => { state.filters.query = e.target.value; state.page = 0; renderResults(); });
    document.querySelectorAll('input[name="access"]').forEach(input => input.addEventListener('change', e => { state.filters.access = e.target.value; state.page = 0; renderResults(); }));
    $('provider').addEventListener('change', e => { state.filters.provider = e.target.value; state.page = 0; renderResults(); });
    $('variable').addEventListener('change', e => { state.filters.variable = e.target.checked; state.page = 0; renderResults(); });
    $('sort').addEventListener('change', e => { state.filters.sort = e.target.value; state.page = 0; renderResults(); });
    $('clear-filters').addEventListener('click', resetFilters);
    $('view-all').addEventListener('click', () => setView(false)); $('view-saved').addEventListener('click', () => setView(true));
    let specimenTimer;
    $('specimen-text').addEventListener('input', e => {
      state.text = e.target.value;
      document.querySelectorAll('.font-specimen,.comparison-reading').forEach(node => { node.textContent = state.text || DEFAULT_TEXT; });
      clearTimeout(specimenTimer);
      specimenTimer = setTimeout(() => { [...state.previews].filter(([, p]) => p.status === 'loaded').forEach(([id]) => loadPreview(state.byId.get(id))); }, 450);
    });
    $('specimen-size').addEventListener('input', e => { state.size = Number(e.target.value); document.documentElement.style.setProperty('--specimen-size', state.size + 'px'); $('size-output').textContent = state.size + ' px'; });
    $('project-note').addEventListener('input', e => { state.note = e.target.value; persist(); });
    $('export-shortlist').addEventListener('click', exportSaved);
    $('clear-shortlist').addEventListener('click', () => { state.saved.clear(); persist(); syncSaved(); renderResults(); toast('Shortlist cleared. Your project note is kept.'); });
    $('previous-page').addEventListener('click', () => { state.page--; renderResults(); $('results-count').scrollIntoView({ block: 'start' }); });
    $('next-page').addEventListener('click', () => { state.page++; renderResults(); $('results-count').scrollIntoView({ block: 'start' }); });
    $('clear-compare').addEventListener('click', () => { state.compare.clear(); syncCompare(); renderResults(); });
    $('open-compare').addEventListener('click', () => { if (state.compare.size < 2) return; renderComparison(); $('compare-dialog').showModal(); });
    $('preview-info').addEventListener('click', () => $('info-dialog').showModal());
    document.querySelectorAll('[data-close]').forEach(b => b.addEventListener('click', () => $(b.dataset.close).close()));
    document.querySelectorAll('dialog').forEach(dialog => dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
    document.addEventListener('keydown', e => { if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName) && !document.querySelector('dialog[open]') && !e.metaKey && !e.ctrlKey && !e.altKey) { e.preventDefault(); $('search').focus(); } });
    if (matchMedia('(max-width: 760px)').matches) $('filter-disclosure').open = false;
  }
  function buildFacets() {
    const categories = new Set(state.fonts.map(f => f.category));
    [['all', 'All classifications'], ...Object.entries(CATEGORY_LABELS).filter(([key]) => categories.has(key))].forEach(([key, name]) => {
      const b = button('', 'category-button', () => { state.filters.category = key; state.page = 0; document.querySelectorAll('[data-category]').forEach(item => item.setAttribute('aria-pressed', String(item === b))); renderResults(); });
      b.dataset.category = key; b.setAttribute('aria-pressed', String(key === 'all')); const symbol = el('span', 'category-symbol ' + key, key === 'all' ? '∞' : 'Aa'); symbol.setAttribute('aria-hidden', 'true'); b.append(symbol, el('span', '', name)); $('category-facets').append(b);
    });
    [...new Set(state.fonts.map(f => f.provider))].sort((a, b) => a.localeCompare(b)).forEach(provider => { const option = el('option', '', provider); option.value = provider; $('provider').append(option); });
    const count = type => state.fonts.filter(f => f.license_kind === type).length.toLocaleString();
    $('count-all').textContent = $('total-count').textContent = state.fonts.length.toLocaleString(); $('count-open').textContent = count('open'); $('count-commercial').textContent = count('commercial'); $('provider-count').textContent = new Set(state.fonts.map(f => f.provider)).size;
  }
  async function boot() {
    wireControls();
    try {
      const response = await fetch('font-directory.json', { cache: 'no-cache' }); if (!response.ok) throw new Error('Directory unavailable.');
      const data = await response.json(); state.fonts = normalizeDirectory(data); if (!state.fonts.length) throw new Error('Directory is empty.'); state.byId = new Map(state.fonts.map(f => [f.id, f]));
      let raw = null; try { raw = localStorage.getItem(STORAGE_KEY); } catch (_) { state.storageOK = false; document.querySelector('.local-note').textContent = 'Shortlist kept for this tab only'; }
      const saved = restoreSaved(raw, new Set(state.byId.keys())); state.saved = new Set(saved.ids); state.note = saved.note; $('project-note').value = saved.note;
      buildFacets(); syncSaved(); renderResults();
      if (data.snapshot?.retrieved_at) $('directory-footnote').textContent = 'Metadata snapshot: ' + String(data.snapshot.retrieved_at).slice(0, 10) + ' UTC. Check the provider’s current styles, language coverage and terms before use. “Starting points” is an editorial ordering, not a quality score.';
    } catch (_) {
      $('results-count').textContent = 'Directory unavailable'; const error = el('div', 'error-state'); error.append(el('h3', '', 'The directory could not load.'), el('p', '', 'Please reload the page. If you are opening a local copy, serve the docs folder over HTTP so the browser can read its metadata.')); error.append(button('Try again', 'button secondary', () => location.reload())); $('font-results').replaceChildren(error);
    }
  }
  boot();
})(typeof globalThis !== 'undefined' ? globalThis : this);
