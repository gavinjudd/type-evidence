import copy

import pytest

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


@pytest.mark.parametrize('style,brief,reason', [
    ('Outline CondItalic', {'italic': False}, 'style_metadata_conflict'),
    ('BoldItalic', {'italic': False}, 'style_metadata_conflict'),
    ('Compact Extrabold', {'weight': 400}, 'weight_metadata_conflict'),
    ('ExtraBold', {'weight': 400}, 'weight_metadata_conflict'),
    ('Extra Bold', {'weight': 400}, 'weight_metadata_conflict'),
    ('Extra-Bold', {'weight': 400}, 'weight_metadata_conflict'),
    ('Light', {'weight': 700}, 'weight_metadata_conflict'),
])
def test_explicit_style_conflicts_reject_only_requested_dimension(style, brief, reason):
    font = face('conflict', 'Example', style=style, weight=brief.get('weight', 400))
    original = copy.deepcopy(font)
    result = search([font], dict(brief, existing_id=font['id']))
    assert result['status'] == 'no_matches'
    assert reason in result['constraint_rejections']
    assert reason in result['baseline']['reasons']
    manual = search([font], {'family': 'Example'})['candidates'][0]
    assert manual['style'] == style and manual['weight'] == font['weight']
    assert manual['italic'] is False
    assert font == original


@pytest.mark.parametrize('family', ['Black', 'Bold', 'Medium', 'Italic', 'Blackbird', 'ExtraBold Studio'])
def test_family_words_are_not_static_style_conflict_evidence(family):
    font = face('regular', family, style='Regular')
    result = search([font], {'family': family, 'weight': 400, 'italic': False})
    assert result['candidates'][0]['id'] == font['id']


def test_unknown_embedded_style_words_are_not_declarations():
    font = face('unknown', style='Blackbird Boldness Italicized')
    assert search([font], {'weight': 400, 'italic': False})['candidates']


def test_unrequested_style_dimension_does_not_reject_manual_discovery():
    slant = face('slant', style='Outline CondItalic')
    heavy = face('heavy', style='Compact Extrabold')
    assert search([slant], {'weight': 400})['candidates']
    assert search([heavy], {'italic': False})['candidates']


def test_supported_variable_axes_override_default_style_name_conflicts():
    font = face('variable', style='ExtraBold CondItalic', axes=[
        {'tag': 'wght', 'min': 100, 'default': 800, 'max': 900},
        {'tag': 'ital', 'min': 0, 'default': 1, 'max': 1},
    ])
    result = search([font], {'weight': 400, 'italic': False})
    chosen = result['candidates'][0]
    assert chosen['required_axes'] == {'wght': 400, 'ital': 0}
    assert chosen['style'] == 'ExtraBold CondItalic' and chosen['weight'] == 400


@pytest.mark.parametrize('axis,brief,reason', [
    ({'tag': 'wght', 'min': 500, 'default': 700, 'max': 900}, {'weight': 400}, 'requested_weight_unavailable'),
    ({'tag': 'ital', 'min': 1, 'default': 1, 'max': 1}, {'italic': False}, 'requested_italic_state_unavailable'),
])
def test_unsupported_axis_cannot_fall_back_to_default_numeric_metadata(axis, brief, reason):
    result = search([face('a', axes=[axis])], brief)
    assert result['status'] == 'no_matches'
    assert reason in result['constraint_rejections']


def test_conflicting_regular_companion_does_not_satisfy_required_styles():
    fonts = [face('wrong', style='Compact Extrabold'), face('bold', style='Bold', weight=700)]
    required = [{'weight': 400, 'italic': False}, {'weight': 700, 'italic': False}]
    result = search(fonts, {'weight': 700, 'required_styles': required})
    assert result['status'] == 'no_matches'
    assert result['constraint_rejections']['required_family_style_unavailable'] == 2
