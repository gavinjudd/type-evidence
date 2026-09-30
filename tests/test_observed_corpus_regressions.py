from test_discovery import face
from type_evidence.discovery import search


def test_name_lookup_absence_does_not_fall_back():
    fonts=[face('a','Present')]
    assert search(fonts,{'family':'Absent'})['status']=='no_matches'
    broad=search(fonts,{'query':'Absent'})
    assert broad['query_interpretation']['exact_name_match_count']==0


def test_contradictory_italic_declaration_excluded_when_style_required():
    f=face('a',style='Grand Italic',italic=False)
    result=search([f],{'italic':False})
    assert result['status']=='no_matches'
    assert 'style_metadata_conflict' in result['constraint_rejections']


def test_no_unicode_never_recommended_as_text():
    assert search([face('a',coverage=[])],{})['status']=='no_matches'


def test_candidate_is_its_own_regular_companion():
    fonts=[face('z',canonical_hash='0'),face('a',canonical_hash='1')]
    result=search(fonts,{'required_styles':[{'weight':400,'italic':False}]})
    assert result['candidates'][0]['id']=='z'
    assert result['candidates'][0]['family_style_resolutions'][0]['id']=='z'
