import json
from pathlib import Path

import pytest

from test_catalog import build
from type_evidence.catalog import Catalog
from type_evidence.operations import discover
from type_evidence.visual import _prompts, _render, _open_index, MODEL_SHA256, RENDER_VERSION


def test_optional_visual_absence_preserves_core_search(tmp_path):
    _, path, _ = build(tmp_path)
    with_catalog = Catalog(path)
    result = discover(with_catalog, {'query':'friendly','text':'abc'})
    assert result['candidates'] and result['visual_retrieval']['status'] == 'not_configured'
    assert discover(with_catalog, {'text':'abc'},visual='off')['visual_retrieval']['status'] == 'disabled'
    with_catalog.close()


def test_negation_removed_from_positive_model_prompt():
    positive, negative = _prompts({'query':'friendly, not condensed but humanist','tone':'warm'})
    assert 'condensed' not in positive and negative == ['condensed']
    assert 'friendly' in positive and 'humanist' in positive and 'warm' in positive
    assert _prompts({'query':'not playful'}) == ('',['playful'])


@pytest.mark.parametrize('query, positive, negative',[
    ('neither playful nor decorative','',['playful','decorative']),
    ('avoiding geometric stiffness','',['geometric','stiffness']),
    ('exclude serif','',['serif']),
    ('less mechanical','',['mechanical']),
    ('non-decorative serif','serif',['decorative']),
    ('not only formal but also friendly','formal friendly',[]),
    ('not high contrast','',['high contrast']),
    ('without losing warmth','warmth',[]),
])
def test_shared_polarity_for_learned_and_alias_search(query,positive,negative):
    assert _prompts({'query':query}) == (positive,negative)


def test_visual_render_uses_verified_bytes_and_no_fallback(tmp_path, monkeypatch):
    from type_evidence import visual
    monkeypatch.setattr(visual,'SAMPLES',{'Fixture':'abc'})
    source,path,_ = build(tmp_path)
    cat=Catalog(path); face=cat.all()[0]
    image,evidence=_render(cat,face)
    assert image.width==image.height and evidence['font_sha256']==face['sha256']
    assert image.getextrema()[0][0] < 100
    monkeypatch.setattr(visual,'SAMPLES',{'Missing':'Ω'})
    with pytest.raises(ValueError,match='No complete supported'):
        _render(cat,face)
    cat.close()


def test_visual_index_rejects_changed_model_configuration(tmp_path):
    path=tmp_path/'index.sqlite'
    db=_open_index(path)
    db.execute("UPDATE meta SET value=? WHERE key='config'",(json.dumps({'model_sha256':'bad'}),));db.commit();db.close()
    with pytest.raises(ValueError,match='different model'):
        _open_index(path)


def test_lora_folding_matches_official_projection_equations():
    torch=pytest.importorskip('torch')
    from type_evidence.visual import fold_lora
    torch.manual_seed(84)
    state={}
    for i in range(12):
        prefix=f'transformer.resblocks.{i}.attn.'
        state[prefix+'in_proj_weight']=torch.randn(12,4)
        state[prefix+'in_proj_bias']=torch.randn(12)
        state[prefix+'out_proj.weight']=torch.randn(4,4)
        state[prefix+'out_proj.bias']=torch.randn(4)
        for part in ('q','k','v','out'):
            state[prefix+part+'_lora_proj_weight_a']=torch.randn(4,2)
            state[prefix+part+'_lora_proj_weight_b']=torch.randn(2,4)
    folded=fold_lora(state)
    x=torch.randn(7,4)
    for i in range(12):
        prefix=f'transformer.resblocks.{i}.attn.'
        projected=x@state[prefix+'in_proj_weight'].T+state[prefix+'in_proj_bias']
        expected=projected+torch.cat([x@state[prefix+p+'_lora_proj_weight_a']@state[prefix+p+'_lora_proj_weight_b']*4 for p in ('q','k','v')],dim=1)
        torch.testing.assert_close(x@folded[prefix+'in_proj_weight'].T+folded[prefix+'in_proj_bias'],expected,atol=1e-5,rtol=1e-5)
        projected=x@state[prefix+'out_proj.weight'].T+state[prefix+'out_proj.bias']
        expected=projected+projected@state[prefix+'out_lora_proj_weight_a']@state[prefix+'out_lora_proj_weight_b']*4
        torch.testing.assert_close(x@folded[prefix+'out_proj.weight'].T+folded[prefix+'out_proj.bias'],expected,atol=2e-5,rtol=1e-5)
