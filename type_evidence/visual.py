"""Optional local FontCLIP retrieval over exact-font rendered content.

The core harness does not require torch. This adapter loads the released model
with the restricted weights-only loader, folds its text LoRA into ordinary CLIP
weights, and checks the complete resulting state. Search never downloads a model.
"""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import time

MODEL_SHA256 = 'c441277fbed4366d32d8fb65725189b97d3fe88bae5fe0648b969feea01bbb00'
MODEL_URL = 'https://drive.google.com/uc?id=1Tym7rAIuaGr6Gv-gZRSJmPstQjOWPgl1'
MODEL_REPO = 'https://github.com/yukistavailable/FontCLIP/tree/3d4c6af01f668800d8e4f9f4f753d29c74dad252'
RENDER_VERSION = 1
SAMPLES = {
    'Latin': 'The quick\nbrown fox\njumps over\nthe lazy dog',
    'Greek': 'Το γρήγορο\nκαφέ ζώο\nπάνω από\nτη γη',
    'Cyrillic': 'Съешь ещё\nэтих мягких\nфранцузских\nбулок',
    'Arabic': 'جمال الخط\nوالكتابة\nحروف عربية',
    'Devanagari': 'सुंदर अक्षर\nहमारी भाषा\nकला और जीवन',
    'Japanese': '美しい文字\n日本の文化\n今日の生活',
    'Chinese': '美丽的文字\n文化与生活\n今天的故事',
    'ChineseTraditional': '美麗的文字\n文化與生活\n今天的故事',
    'Hebrew': 'שלום עולם\nאותיות יפות\nסיפור חדש',
    'Ethiopic': 'የኢትዮጵያ\nባህል እና\nየዛሬ ሕይወት',
    'Bengali': 'সুন্দর অক্ষর\nআমাদের ভাষা\nশিল্প ও জীবন',
    'Tamil': 'அழகிய எழுத்து\nஎங்கள் மொழி\nகலை வாழ்க்கை',
    'Korean': '아름다운 글자\n우리의 문화\n오늘의 생활',
    'Thai': 'ตัวอักษรสวยงาม\nภาษาและชีวิต',
}
SAMPLE_LANGUAGES = {'Latin':'en','Greek':'el','Cyrillic':'ru','Arabic':'ar','Devanagari':'hi',
                    'Japanese':'ja','Chinese':'zh-Hans','ChineseTraditional':'zh-Hant','Hebrew':'he','Ethiopic':'am','Bengali':'bn',
                    'Tamil':'ta','Korean':'ko','Thai':'th'}
ATTRIBUTES = ('serif', 'sans serif', 'slab serif', 'humanist', 'geometric',
              'rounded', 'angular', 'condensed', 'wide', 'thin', 'heavy',
              'high contrast', 'low contrast', 'monospaced', 'calligraphic',
              'handwritten', 'formal', 'casual', 'friendly', 'playful',
              'elegant', 'expressive', 'restrained', 'futuristic', 'retro',
              'mechanical', 'organic', 'stencil', 'pixel', 'decorative',
              'serious', 'warm', 'sharp', 'soft', 'rough', 'clean')


def _dependencies():
    try:
        import numpy as np
        import torch
        import open_clip
    except ImportError as exc:
        raise ValueError("Visual retrieval needs the optional visual dependencies: pip install -e '.[visual]'") from exc
    return np, torch, open_clip


def fold_lora(state):
    """Match FontCLIP's released q/k/v and *post-output* LoRA algebra.

    Its out adapter acts on the projected output, not on the attention input.
    Consequently both the existing weight and bias must be transformed.
    """
    import torch
    result = {key: value.float() for key, value in state.items() if '_lora_' not in key}
    for layer in range(12):
        prefix = f'transformer.resblocks.{layer}.attn.'
        delta = []
        for projection in ('q', 'k', 'v'):
            a = state[prefix + projection + '_lora_proj_weight_a'].float()
            b = state[prefix + projection + '_lora_proj_weight_b'].float()
            delta.append((a @ b).T * 4.0)  # released alpha/r = 1024/256
        result[prefix + 'in_proj_weight'] = result[prefix + 'in_proj_weight'] + torch.cat(delta)
        a = state[prefix + 'out_lora_proj_weight_a'].float()
        b = state[prefix + 'out_lora_proj_weight_b'].float()
        transform = torch.eye(a.shape[0]) + (a @ b).T * 4.0
        result[prefix + 'out_proj.weight'] = transform @ result[prefix + 'out_proj.weight']
        result[prefix + 'out_proj.bias'] = transform @ result[prefix + 'out_proj.bias']
    for key in ('input_resolution', 'context_length', 'vocab_size'):
        result.pop(key, None)
    return result


@lru_cache(maxsize=1)
def load_model(checkpoint, device='cpu'):
    np, torch, open_clip = _dependencies()
    checkpoint = Path(checkpoint)
    if not checkpoint.is_file():
        raise ValueError('FontCLIP checkpoint not found. Run visual-setup explicitly first.')
    with checkpoint.open('rb') as source:
        actual = hashlib.file_digest(source, 'sha256').hexdigest() if hasattr(hashlib, 'file_digest') else hashlib.sha256(source.read()).hexdigest()
    if actual != MODEL_SHA256:
        raise ValueError('FontCLIP checkpoint checksum differs from the pinned released model.')
    if device not in ('cpu', 'mps', 'cuda'):
        raise ValueError('Visual device must be cpu, mps, or cuda')
    if device == 'mps' and not torch.backends.mps.is_available():
        raise ValueError('MPS is unavailable in this runtime; use cpu')
    if device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA is unavailable in this runtime; use cpu')
    torch.set_num_threads(min(4, torch.get_num_threads()))
    state = torch.load(checkpoint, map_location='cpu', weights_only=True)['model_state_dict']
    model = open_clip.create_model('ViT-B-32', pretrained=None, force_quick_gelu=True)
    model.load_state_dict(fold_lora(state), strict=True)
    model.float().eval().to(device)
    preprocess = open_clip.image_transform(224, is_train=False)
    return model, preprocess, open_clip.get_tokenizer('ViT-B-32')


def setup_model(directory):
    """Explicit user-invoked download, verified before it can be loaded."""
    _dependencies()
    try:
        import gdown
    except ImportError as exc:
        raise ValueError('Install the visual extra before downloading the model') from exc
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / 'fontclip-original.pt'
    if target.exists():
        with target.open('rb') as source:
            checksum = hashlib.sha256(source.read()).hexdigest()
        if checksum != MODEL_SHA256:
            raise ValueError('Existing model differs from the pinned checksum; preserve it and use a new directory')
    else:
        temporary = target.with_suffix('.download')
        gdown.download(MODEL_URL, str(temporary), quiet=True, use_cookies=False)
        if not temporary.exists() or hashlib.sha256(temporary.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('Downloaded checkpoint failed SHA-256 verification')
        temporary.replace(target)
    return {'path': str(target.resolve()), 'sha256': MODEL_SHA256, 'source': MODEL_REPO,
            'bytes': target.stat().st_size, 'next': 'type-evidence visual-index',
            'scope': 'Optional local inference. Model weights remain outside source/review archives.'}


def _sample(font, script=None):
    from .catalog import covers
    for script, text in ([(script,SAMPLES[script])] if script else SAMPLES.items()):
        if covers(font, text.replace('\n', '')):
            return script, text
    return None, None


def _render(catalog, font, sample_script=None):
    from PIL import Image
    from .render import _load, _specimen, _validate_text
    script, text = _sample(font, sample_script)
    if text is None:
        raise ValueError('No complete supported visual sample; exact text search remains available')
    _validate_text(text, None)
    asset = _load(catalog, font['id'], {}, text)
    language = SAMPLE_LANGUAGES.get(script,'und') if sample_script else 'und'
    mask, evidence = _specimen(asset, text, 100, {}, None, language, 1800)
    # Fit all ink into a square. No clipping or system-font substitution.
    square = Image.new('RGB', (max(mask.size) + 40,) * 2, 'white')
    square.paste('black', ((square.width-mask.width)//2, (square.height-mask.height)//2), mask)
    return square, {'script':script, 'text':text, 'language':language, 'axes':asset.axes,
                    'mask_sha256':evidence['mask_sha256'], 'font_sha256':asset.resolution['sha256']}


def _index_config(script=None):
    config = {'model_sha256':MODEL_SHA256, 'render_version':RENDER_VERSION, 'dimension':512}
    if script:
        config['sample_script'] = script
        config['sample_text_sha256'] = hashlib.sha256(SAMPLES[script].encode()).hexdigest()
        config['sample_language'] = SAMPLE_LANGUAGES[script]
    return config


def requested_script(brief):
    from collections import Counter
    from fontTools.unicodedata import script
    counts = Counter(script(c) for c in brief.get('text','') if script(c) not in {'Zyyy','Zinh','Zzzz','Latn'})
    if not counts: return None
    if counts.get('Hira') or counts.get('Kana'): return 'Japanese'
    code = counts.most_common(1)[0][0]
    locale = str(brief.get('language','')).lower().replace('_','-')
    if code == 'Hani' and (locale.startswith('zh-hant') or locale in {'zh-tw','zh-hk','zh-mo'}): return 'ChineseTraditional'
    if code == 'Hani' and str(brief.get('language','')).lower().split('-')[0] == 'ja': return 'Japanese'
    if code == 'Hani' and str(brief.get('language','')).lower().split('-')[0] == 'ko': return 'Korean'
    return {'Grek':'Greek','Cyrl':'Cyrillic','Arab':'Arabic','Deva':'Devanagari','Hani':'Chinese',
            'Hebr':'Hebrew','Ethi':'Ethiopic','Beng':'Bengali','Taml':'Tamil','Hang':'Korean','Thai':'Thai'}.get(code,code)


def _open_index(path, script=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path)
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS vectors (id TEXT PRIMARY KEY, canonical TEXT, vector BLOB NOT NULL, evidence TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS failures (id TEXT PRIMARY KEY, error TEXT NOT NULL)')
    config = _index_config(script)
    current = db.execute("SELECT value FROM meta WHERE key='config'").fetchone()
    if current and json.loads(current[0]) != config:
        db.close()
        raise ValueError('Visual index uses a different model/render version; use a new index path')
    db.execute("INSERT OR REPLACE INTO meta VALUES ('config',?)", (json.dumps(config),))
    db.commit()
    return db


def build_index(catalog, output=None, checkpoint=None, limit=None, device='cpu', batch_size=16, progress=None, script=None):
    """Incremental exact-face visual index; failed faces stay searchable by metadata."""
    np, torch, _ = _dependencies()
    if script is not None and script not in SAMPLES: raise ValueError('Unsupported sample script: '+str(script))
    output = Path(output or catalog.path.parent / (f'visual-{script}.sqlite' if script else 'visual.sqlite'))
    checkpoint = str(Path(checkpoint or catalog.path.parent / 'models/fontclip-original.pt').resolve())
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError('Visual indexing limit must be a positive integer')
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 64:
        raise ValueError('batch_size must be 1..64')
    model, preprocess, tokenizer = load_model(checkpoint, device)
    with torch.inference_mode():
        tag_vectors = model.encode_text(tokenizer([word+' font' for word in ATTRIBUTES]).to(device)).float()
        tag_vectors = (tag_vectors / tag_vectors.norm(dim=-1,keepdim=True)).cpu().numpy()
    db = _open_index(output, script)
    fonts = catalog.all()
    eligible = [font for font in fonts if _sample(font,script)[1] is not None] if script else fonts
    # Begin with broad family representatives, then fill every remaining face.
    # No popularity, rights, or PANOSE filter controls index membership.
    families = {}
    for f in eligible:
        families.setdefault(f.get('family_key', f['id']), []).append(f)
    chosen, rest = [], []
    for group in families.values():
        ordered = sorted(group, key=lambda f:(abs(f.get('weight',400)-400), bool(f.get('italic')), f['id']))
        chosen.append(ordered[0]); rest.extend(ordered[1:])
    queue = sorted(chosen, key=lambda f:f['id']) + sorted(rest, key=lambda f:f['id'])
    existing = {row[0] for row in db.execute('SELECT id FROM vectors')}
    equivalences = {row[0]:(row[1],row[2]) for row in db.execute('SELECT canonical,vector,evidence FROM vectors WHERE canonical IS NOT NULL')}
    done = 0; copied = 0; failed = 0; batch = []; started = time.monotonic()
    def flush():
        nonlocal done
        if not batch: return
        images = torch.stack([item[2] for item in batch]).to(device)
        with torch.inference_mode():
            vectors = model.encode_image(images).float()
            vectors = (vectors / vectors.norm(dim=-1, keepdim=True)).cpu().numpy()
        for (font, evidence, _), vector in zip(batch, vectors):
            tag_scores = tag_vectors @ vector
            evidence['model_associations'] = [{'term':ATTRIBUTES[i], 'cosine':round(float(tag_scores[i]),5)}
                                               for i in np.argsort(-tag_scores)[:4]]
            blob = vector.astype('<f4').tobytes()
            serialized = json.dumps(evidence)
            db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?,?)', (font['id'],font.get('canonical_hash'),blob,serialized))
            db.execute('DELETE FROM failures WHERE id=?', (font['id'],))
            if font.get('canonical_hash'): equivalences[font['canonical_hash']] = (blob,serialized)
            done += 1
        db.commit(); batch.clear()
        if progress: progress({'new_rendered':done, 'reused_equivalent':copied, 'new_failures':failed, 'seconds':round(time.monotonic()-started,1)})
    try:
        for font in queue:
            if font['id'] in existing: continue
            if limit is not None and done + copied + len(batch) >= limit: break
            canonical = font.get('canonical_hash')
            if canonical and canonical in equivalences:
                try:
                    catalog.resolve(font['id'])
                except (ValueError, OSError) as exc:
                    db.execute('INSERT OR REPLACE INTO failures VALUES (?,?)', (font['id'],str(exc)[:500]))
                    failed += 1
                    continue
                blob, serialized = equivalences[canonical]
                evidence = json.loads(serialized)
                evidence['equivalent_render_reuse'] = True
                evidence['font_sha256'] = font['sha256']
                db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?,?)', (font['id'],canonical,blob,json.dumps(evidence)))
                db.execute('DELETE FROM failures WHERE id=?', (font['id'],))
                copied += 1
                continue
            try:
                image, evidence = _render(catalog, font, script)
                batch.append((font,evidence,preprocess(image)))
            except (ValueError, OSError, RuntimeError) as exc:
                db.execute('INSERT OR REPLACE INTO failures VALUES (?,?)', (font['id'],str(exc)[:500]))
                failed += 1
            if len(batch) >= batch_size: flush()
        flush()
        db.commit()
        active_ids = {font['id'] for font in eligible}
        indexed = {row[0] for row in db.execute('SELECT id FROM vectors')} & active_ids
        report = {'model':'FontCLIP ViT-B/32', 'model_sha256':MODEL_SHA256, 'render_version':RENDER_VERSION,
                  'catalog_faces':len(fonts), 'eligible_sample_faces':len(eligible), 'sample_script':script or 'first complete supported sample',
                  'indexed_current_faces':len(indexed), 'remaining_faces':len(eligible)-len(indexed),
                  'new_rendered':done, 'reused_equivalent':copied, 'new_failures':failed,
                  'failures_recorded':db.execute('SELECT count(*) FROM failures').fetchone()[0],
                  'seconds':round(time.monotonic()-started,2), 'device':device,
                  'scope':'Actual default-axis rendered shapes. Similarity is learned interpretation, not readability or suitability proof.'}
        db.execute("INSERT OR REPLACE INTO meta VALUES ('report',?)", (json.dumps(report),)); db.commit()
        return report
    finally:
        db.close()


def _prompts(brief):
    from .discovery import interpret_query
    text = ', '.join(str(brief.get(k,'')) for k in ('query','tone')).strip(' ,')
    interpretation = interpret_query(text)
    positive = list(interpretation['positive']) + interpretation['unmodeled_positive']
    negative = list(interpretation['negative']) + interpretation['unmodeled_negative']
    return ' '.join(positive), negative


def scores(catalog, brief, index_path=None, checkpoint=None, reference_image=None):
    """Return per-ID learned evidence and an explicit corpus/model coverage report."""
    np, torch, _ = _dependencies()
    script = requested_script(brief)
    if script is not None and script not in SAMPLES:
        raise ValueError(f'No visual sample is configured for script {script}; use exact rendering and metadata discovery.')
    path = Path(index_path or catalog.path.parent / (f'visual-{script}.sqlite' if script else 'visual.sqlite')).resolve()
    if not path.is_file():
        raise ValueError('Visual index missing for '+(script or 'default samples')+'; run visual-index'+(f' --script {script}' if script else '')+' first')
    checkpoint = str(Path(checkpoint or catalog.path.parent / 'models/fontclip-original.pt').resolve())
    db = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
    try:
        config_row = db.execute("SELECT value FROM meta WHERE key='config'").fetchone()
        if not config_row: raise ValueError('Visual index has no model/render configuration')
        config = json.loads(config_row[0])
        if config != _index_config(script):
            raise ValueError('Visual index model/render version mismatch')
        rows = db.execute('SELECT id,vector,evidence FROM vectors ORDER BY id').fetchall()
    except sqlite3.DatabaseError as exc:
        raise ValueError('Visual index cannot be read: '+str(exc)) from exc
    finally:
        db.close()
    active_ids = {row[0] for row in catalog.db.execute('SELECT id FROM fonts')}
    eligible_ids = {font['id'] for font in catalog.all() if _sample(font,script)[1] is not None} if script else active_ids
    rows = [row for row in rows if row[0] in active_ids]
    if not rows: raise ValueError('Visual index has no successful faces in the current catalog')
    ids = [r[0] for r in rows]
    vectors = np.stack([np.frombuffer(r[1],dtype='<f4') for r in rows])
    if vectors.shape[1] != 512 or not np.isfinite(vectors).all():
        raise ValueError('Malformed visual vectors')
    if not np.allclose(np.linalg.norm(vectors,axis=1),1.0,atol=1e-3,rtol=1e-3):
        raise ValueError('Visual vectors must have unit norm for cosine similarity')
    similarities = []
    positive, negative = _prompts(brief)
    model = preprocess = tokenizer = None
    def ensure_model():
        nonlocal model, preprocess, tokenizer
        if model is None: model, preprocess, tokenizer = load_model(checkpoint, 'cpu')
    prompts = ([positive+' font'] if positive else []) + [word+' font' for word in negative]
    if prompts:
        ensure_model()
        with torch.inference_mode():
            embedding = model.encode_text(tokenizer(prompts)).float()
            embedding = (embedding / embedding.norm(dim=-1,keepdim=True)).cpu().numpy()
        offset = 0
        if positive:
            similarities.append(vectors @ embedding[0]); offset = 1
        for item in embedding[offset:]: similarities.append(-(vectors @ item))
    for name, direction in [('similar_to',1), ('avoid_like',-1)]:
        if brief.get(name):
            if brief[name] not in ids:
                raise ValueError(f'{name} has no visual vector yet; index this face or use metadata discovery')
            similarities.append(direction * (vectors @ vectors[ids.index(brief[name])]))
    if reference_image:
        from PIL import Image
        ensure_model()
        image_path = Path(reference_image)
        if image_path.stat().st_size > 20_000_000: raise ValueError('Reference image exceeds 20 MB')
        with Image.open(image_path) as image:
            if image.width * image.height > 20_000_000: raise ValueError('Reference image exceeds 20 million pixels')
            tensor = preprocess(image.convert('RGB')).unsqueeze(0)
        with torch.inference_mode():
            embedding = model.encode_image(tensor).float()
            embedding = (embedding / embedding.norm(dim=-1,keepdim=True)).cpu().numpy()[0]
        similarities.append(vectors @ embedding)
    if not similarities:
        return {}, {'status':'available', 'indexed_faces':len(ids), 'used':False, 'reason':'No aesthetic query, tone, reference, or visual neighbor requested.'}
    raw = np.mean(similarities,axis=0)
    # Standardize against this corpus, never label it probability/confidence.
    deviation = float(np.std(raw))
    normalized = np.clip((raw-float(np.mean(raw)))/max(deviation,1e-6)*5,-20,20)
    result = {}
    for ident, score, cosine, row in zip(ids, normalized, raw, rows):
        evidence = json.loads(row[2])
        if (not isinstance(evidence,dict) or not isinstance(evidence.get('script'),str)
            or not isinstance(evidence.get('axes'),dict) or not isinstance(evidence.get('model_associations',[]),list)
            or any(not isinstance(x,dict) or not isinstance(x.get('term'),str) for x in evidence.get('model_associations',[]))):
            raise ValueError('Malformed visual render evidence')
        result[ident] = {'score':round(float(score),4), 'basis':'learned-visual',
                         'description':f"Model-associated attributes: {', '.join(x['term'] for x in evidence.get('model_associations',[]))}. Exact {evidence['script']} sample; default axes.",
                         'matches':([positive] if positive else []) + ['avoid '+word for word in negative],
                         'raw_similarity':round(float(cosine),6), 'sample_script':evidence['script'],
                         'sample_language':evidence.get('language','und'), 'sample_axes':evidence['axes']}
    return result, {'status':'used', 'model':'FontCLIP ViT-B/32', 'model_sha256':MODEL_SHA256,
                    'indexed_faces':len(ids), 'catalog_faces':len(active_ids), 'eligible_sample_faces':len(eligible_ids),
                    'unindexed_faces':len(eligible_ids-set(ids)), 'requested_sample_script':script,
                    'positive_prompt':positive, 'negative_prompts':negative,
                    'reference_image_used':bool(reference_image), 'similar_to':brief.get('similar_to'), 'avoid_like':brief.get('avoid_like'),
                    'limitations':['Learned visual resemblance is not a quality, legibility, or audience-fit measurement.',
                                   'Only the recorded sample script and default variation axes were embedded.',
                                   'Unindexed faces remain eligible without a visual score.']}
