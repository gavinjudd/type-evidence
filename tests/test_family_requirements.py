import pytest
from test_discovery import face
from type_evidence.discovery import search

NEEDS = [{'weight':400,'italic':False},{'weight':700,'italic':False}]

def test_companion_bold_is_exact_and_covers_text():
    fonts=[face('r'),face('b',weight=700,style='Bold')]
    found=search(fonts,{'text':'Retry 08','weight':400,'required_styles':NEEDS})
    assert [s['id'] for s in found['candidates'][0]['family_style_resolutions']]==['r','b']
    fonts[1]['coverage']=[[65,90]]
    assert search(fonts,{'text':'Retry 08','required_styles':NEEDS})['status']=='no_matches'

def test_version_groups_not_combined_for_required_style():
    fonts=[face('r',family_key='v1'),face('b',weight=700,family_key='v2')]
    assert search(fonts,{'required_styles':NEEDS})['status']=='no_matches'

def test_variable_face_satisfies_multiple_weights_but_not_missing_italic():
    fonts=[face('v',axes=[{'tag':'wght','min':100,'default':400,'max':900}])]
    result=search(fonts,{'required_styles':NEEDS})
    assert [s['required_axes'] for s in result['candidates'][0]['family_style_resolutions']]==[{'wght':400},{'wght':700}]
    assert search(fonts,{'required_styles':[{'weight':400,'italic':True}]})['status']=='no_matches'

def test_rights_filter_applies_to_companion():
    fonts=[face('r',rights={'status':'embedded-open-license'}),face('b',weight=700)]
    assert search(fonts,{'required_styles':NEEDS,'require_open_evidence':True})['status']=='no_matches'

def test_invalid_required_style_rejected():
    with pytest.raises(ValueError): search([],{'required_styles':[{'weight':False,'italic':False}]})
