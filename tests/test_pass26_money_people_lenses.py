from engine.meaning import MeaningPacket
from engine import pass26_intelligence


def packet(**kw):
    base=dict(source_kind='money', actor='Congress', action='provides funds', target='eligible States', amounts=['$250,000,000'], recipient='eligible States', purpose='grants for treatment programs', authority_type=None, exception=None, plain_statement='Congress provides $250,000,000 as grants to eligible States for treatment programs.', why_it_matters='Why it matters: money moves.', missing_context=['The provision does not say how much each State ultimately receives.'], completeness_score=.9)
    base.update(kw)
    return MeaningPacket(**base)


def test_money_public_names_recipient_purpose_and_unknowns():
    text, why = pass26_intelligence.money_public(packet())
    assert '$250,000,000' in text
    assert 'Direct recipient named in the text: eligible States.' in why
    assert 'Stated purpose: grants for treatment programs.' in why
    assert 'Still unknown from this provision alone:' in why


def test_power_public_names_directly_affected_target():
    p=packet(source_kind='power', actor='the Attorney General', action='must notify the registrant', target='the registrant', amounts=[], recipient=None, purpose=None, authority_type='enforcement', plain_statement='The Attorney General must notify the registrant.', why_it_matters='Why it matters: this makes notice mandatory.', missing_context=[])
    text, why = pass26_intelligence.power_public(p)
    assert 'Attorney General' in text
    assert 'Directly affected: the registrant.' in why
    assert 'Type of power or duty: enforcement.' in why


def test_substantive_money_lenses_use_same_concrete_amount_and_recipient():
    left, right = pass26_intelligence.substantive_lens_pair(packet())
    assert '$250,000,000' in left and '$250,000,000' in right
    assert 'eligible States' in left and 'eligible States' in right
    assert 'progressive' in left.lower() and 'conservative' in right.lower()


def test_substantive_power_lenses_use_same_concrete_effect():
    p=packet(source_kind='power', actor='the Attorney General', action='may enforce the requirements', target='the registrant', amounts=[], recipient=None, purpose=None, authority_type='enforcement', plain_statement='The Attorney General may enforce the requirements affecting the registrant.', why_it_matters='Why it matters: enforcement authority changes.', missing_context=[])
    left, right = pass26_intelligence.substantive_lens_pair(p)
    assert 'Attorney General may enforce' in left
    assert 'Attorney General may enforce' in right
    assert 'registrant' in left and 'registrant' in right


def test_lens_pair_refuses_missing_effect():
    p=packet(plain_statement=None)
    assert pass26_intelligence.substantive_lens_pair(p) == (None, None)
