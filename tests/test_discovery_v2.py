"""Behavioral regressions for intent, exploration, and actual-content adapters."""
import copy
import json

import pytest

from type_evidence.discovery import interpret_brief, interpret_query, search


def face(identifier, family=None, **overrides):
    item = dict(id=identifier, family=family or identifier, family_key=family or identifier,
                style='Regular', weight=400, italic=False, width_class=5, category='sans',
                canonical_hash=identifier, coverage=[[32, 126]], axes=[], render_probe=True,
                metrics={'x_height_em': .5, 'cap_height_em': .7, 'average_advance_em': .56})
    item.update(overrides)
    return item


def ids(result):
    return [font['id'] for font in result['candidates']]


@pytest.mark.parametrize('query', ['not condensed', 'avoid narrow', 'without a condensed look',
                                   'non-condensed', 'less condensed'])
def test_negative_preference_never_rewards_a_condensed_face(query):
    fonts = [face('narrow', width_class=3), face('regular')]
    result = search(fonts, {'query': query})
    assert ids(result)[0] == 'regular'
    narrow = next(item for item in result['candidates'] if item['id'] == 'narrow')
    assert any(reason['points'] < 0 and 'condensed' in reason['reason'] for reason in narrow['reasons'])
    assert not result['query_interpretation']['aliases']
    assert result['query_interpretation']['negated_aliases']


def test_negation_scopes_coordinated_terms_and_resets_at_contrast():
    terms = interpret_query('no condensed or script but bold and friendly; not playful')
    assert set(terms['negative'].values()) == {'metadata:condensed', 'category:script'}
    assert terms['positive'] == {'bold': 'metadata:bold'}
    assert terms['unmodeled_positive'] == ['friendly']
    assert terms['unmodeled_negative'] == ['playful']
    assert interpret_query('not only condensed but also bold')['negative'] == {}


def test_sans_serif_is_one_preference_and_can_be_negated():
    terms = interpret_query('sans serif, not high x-height')
    assert terms['positive'] == {'sans-serif': 'category:sans'}
    assert terms['negative'] == {'high x-height': 'measured:high-x-height'}


@pytest.mark.parametrize('query,positive,negative', [
    ('not playful, ornate or delicate', [], ['playful', 'ornate', 'delicate']),
    ('avoid playful, ornate, and delicate', [], ['playful', 'ornate', 'delicate']),
    ('not playful, but humanist and open', ['humanist', 'open'], ['playful']),
    ('avoid ornate, prefer humanist', ['humanist'], ['ornate']),
    ('not delicate, use sturdy', ['sturdy'], ['delicate']),
    ('not playful; humanist', ['humanist'], ['playful']),
    ('humanist, open and clear', ['humanist', 'open', 'clear'], []),
    ('not use ornate', [], ['ornate']),
])
def test_comma_lists_and_explicit_positive_clauses(query, positive, negative):
    terms = interpret_query(query)
    assert terms['unmodeled_positive'] == positive
    assert terms['unmodeled_negative'] == negative


def test_tone_is_independent_of_terminal_query_negation_in_every_ranker():
    from type_evidence.visual import _prompts
    brief = {'query': 'open humanist sans. Not childish, ornate or delicate',
             'tone': 'patient clear capable and human'}
    terms = interpret_brief(brief)
    assert terms['unmodeled_negative'] == ['childish', 'ornate', 'delicate']
    assert terms['unmodeled_positive'] == ['open', 'humanist', 'patient', 'clear', 'capable', 'human']
    positive, negative = _prompts(brief)
    assert positive.split() == list(terms['positive']) + terms['unmodeled_positive']
    assert negative == list(terms['negative']) + terms['unmodeled_negative']
    result = search([face('a')], brief)['query_interpretation']
    assert result['aliases'] == terms['positive']
    assert result['unmodeled_positive'] == terms['unmodeled_positive']
    assert result['unmodeled_negative'] == terms['unmodeled_negative']


def test_small_size_and_density_change_measured_preferences_without_category_exclusion():
    fonts = [face('small', metrics={'x_height_em': .38, 'average_advance_em': .65}),
             face('unknown', category='unknown', metrics={'x_height_em': .58, 'average_advance_em': .51})]
    result = search(fonts, {'size': 12, 'density': 'dense', 'audience': 'older readers'})
    assert ids(result)[0] == 'unknown'
    assert 'visual_category_unknown' in result['candidates'][0]['evidence_gaps']
    assert any(reason['basis'] == 'measured+context' for reason in result['candidates'][0]['reasons'])
    assert result['counts']['eligible_faces'] == 2


def test_family_exclusion_is_case_insensitive_and_applies_to_baseline():
    fonts = [face('a', 'First'), face('b', 'Second')]
    result = search(fonts, {'exclude_families': [' FIRST '], 'existing_id': 'a'})
    assert ids(result) == ['b']
    assert result['baseline']['reasons'] == ['explicitly_excluded_family']


def test_successive_pages_cover_distinct_families_without_repeats():
    fonts = [face(str(i), f'Family {i}', category='serif' if i % 3 else 'sans',
                  width_class=3 if i % 2 else 5) for i in range(13)]
    fonts += [face('a-copy', 'Alias', canonical_hash='0'), face('b-style', 'Family 2', weight=700)]
    baseline = copy.deepcopy(fonts)
    full = search(fonts, {'limit': 20})
    result_ids = []
    offset = 0
    for _ in range(5):
        result = search(fonts[::-1], {'limit': 3, 'offset': offset})
        result_ids += ids(result)
        offset = result['pagination']['next_offset']
        if offset is None:
            break
    assert result_ids == ids(full)
    assert len(result_ids) == len(set(result_ids)) == 13
    assert fonts == baseline


def test_pagination_keeps_baseline_and_counts_only_alternatives():
    fonts = [face(str(i)) for i in range(9)]
    first = search(fonts, {'limit': 3, 'existing_id': '8'})
    second = search(fonts, {'limit': 3, 'existing_id': '8', 'offset': first['pagination']['next_offset']})
    assert ids(first)[0] == ids(second)[0] == '8'
    assert len(set(ids(first)[1:] + ids(second)[1:])) == 4
    assert first['pagination']['next_offset'] == 2
    assert search(fonts, {'limit': 3, 'offset': 99})['pagination']['next_offset'] is None


def test_measured_neighbors_and_avoidance_reverse_direction():
    fonts = [face('reference'), face('close', metrics={'x_height_em': .51, 'cap_height_em': .69, 'average_advance_em': .55}),
             face('distant', metrics={'x_height_em': .7, 'cap_height_em': .9, 'average_advance_em': .9})]
    near = search(fonts, {'similar_to': 'reference', 'exclude': ['reference']})
    far = search(fonts, {'avoid_like': 'reference', 'exclude': ['reference']})
    assert ids(near)[0] == 'close'
    assert ids(far)[0] == 'distant'
    assert any(reason['basis'] == 'measured-similarity' for reason in near['candidates'][0]['reasons'])


def test_actual_content_scores_can_surface_unknown_categories_and_replace_coarse_neighbors():
    fonts = [face('reference'), face('known'), face('unknown', category='unknown')]
    visual = {'unknown': {'score': 14, 'description': 'Rounded terminals observed in rendered sample',
                          'basis': 'learned-visual', 'matches': ['rounded', 'friendly'], 'raw_similarity': .38, 'sample_script': 'Latin', 'sample_axes': {'wght': 400}}}
    result = search(fonts, {'query': 'friendly humanist', 'similar_to': 'reference', 'exclude': ['reference']}, visual)
    assert ids(result)[0] == 'unknown'
    chosen = result['candidates'][0]
    assert chosen['visual_evidence']['basis'] == 'learned-visual'
    assert chosen['visual_evidence']['matches'] == ['rounded', 'friendly']
    assert chosen['visual_evidence']['sample_axes'] == {'wght': 400}
    assert chosen['visual_evidence']['sample_script'] == 'Latin'
    assert chosen['visual_evidence']['raw_similarity'] == .38
    assert not any(r['basis'] == 'measured-similarity' for r in chosen['reasons'])
    assert result['query_interpretation']['unmodeled_terms'] == ['friendly', 'humanist']
    assert result['query_interpretation']['visual_scoring_active'] is True
    assert result['counts']['visual_scored_faces'] == 1


def test_visual_output_is_bounded_and_nonfinite_scores_are_ignored():
    fonts = [face('a'), face('b'), face('c')]
    visual = {'a': {'score': 99999, 'description': 'sample\n' * 1000, 'matches': ['word' * 500] * 100},
              'b': {'score': float('nan')}, 'c': {'score': float('inf')}}
    result = search(fonts, {}, visual)
    first = result['candidates'][0]
    assert first['visual_evidence']['score'] == 20
    assert len(first['visual_evidence']['description']) <= 400
    assert len(first['visual_evidence']['matches']) == 12
    assert result['counts']['visual_scored_faces'] == 1
    json.dumps(result, allow_nan=False)


def test_unknown_context_fields_remain_visible_without_leaking_project_text():
    result = search([face('a')], {'audience': 'children', 'language': 'en', 'surroundings': 'Project secret',
                                'imaginary_preference': 'sample', 'text': 'Confidential copy'})
    assert result['query_interpretation']['unrecognized_brief_fields'] == ['imaginary_preference']
    assert result['context_interpretation']['handoff_fields'] == ['language', 'surroundings']
    assert 'Confidential copy' not in json.dumps(result)
    assert 'Project secret' not in json.dumps(result)


@pytest.mark.parametrize('brief', [{'offset': -1}, {'offset': True}, {'offset': 5001},
                                   {'size': float('nan')}, {'size': 0}, {'size': True},
                                   {'density': 'arbitrary'}, {'exclude_families': 'Family'},
                                   {'exclude_families': ['x' * 301]}, {'audience': 'x' * 301},
                                   {'similar_to': 'missing'}, {'avoid_like': 'missing'}])
def test_invalid_new_brief_fields_fail_clearly(brief):
    with pytest.raises(ValueError):
        search([face('a')], brief)


def test_slant_conflict_in_full_name_prevents_silent_upright_selection():
    fonts = [face('ambiguous', full_name='Example Condensed Obl', style='Regular', italic=False)]
    result = search(fonts, {'italic': False, 'existing_id': 'ambiguous'})
    assert result['status'] == 'no_matches'
    assert 'style_metadata_conflict' in result['baseline']['reasons']
