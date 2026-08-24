from engine import meaning, topic_expert, translator


def _anchor(exact_text: str) -> dict:
    return {
        "anchor_id": "a1",
        "bill_id": "demo",
        "segment_id": "s1",
        "section_label": "SEC. 3",
        "location_marker": "lines 1-5",
        "document_ref": "demo.txt",
        "source_url": "https://example.test/demo",
        "source_sha256": "a" * 64,
        "text_sha256": "b" * 64,
        "exact_text": exact_text,
        "verified": True,
    }


def test_qualifier_integrity_accepts_only_authorized_modal_rewrites():
    result = translator.translate_anchor_payload(_anchor(
        "SEC. 3. RESEARCH.\nExcept as provided in paragraph (3), a researcher may perform the activity. "
        "The Attorney General shall publish the list."
    ))
    assert result.status == "translated"
    assert "is allowed to perform" in result.plain_english
    assert "must publish" in result.plain_english


def test_qualifier_integrity_still_fails_when_substance_disappears(monkeypatch):
    original = translator._translate_sentence

    def bad(sentence: str):
        text, confidence, reason = original(sentence)
        if text:
            text = text.replace("Except as provided in paragraph (3), ", "")
        return text, confidence, reason

    monkeypatch.setattr(translator, "_translate_sentence", bad)
    result = translator.translate_anchor_payload(_anchor(
        "SEC. 3. RESEARCH.\nExcept as provided in paragraph (3), the Attorney General shall publish the list."
    ))
    assert result.status == "needs_expert_review"
    assert "legally material qualifier" in result.review_reason


def test_meaning_does_not_borrow_actor_from_another_clause():
    packet = meaning.from_power({
        "actors": ["the Attorney General"],
        "authority_types": ["delegated_discretion"],
        "operative_excerpt": (
            "A practitioner may conduct research with a schedule I substance. "
            "Later, the Attorney General shall publish a list."
        ),
    })
    assert packet is not None
    assert packet.actor is None
    assert packet.action.startswith("may conduct research")
    assert not packet.plain_statement.lower().startswith("the attorney general may conduct research")


def test_topic_routing_uses_lexical_terms_not_substrings():
    scores = topic_expert.score_domains(
        "The researcher may use the current registration and report results."
    )
    matched = {term for score in scores for term in score.matched_terms}
    assert "search" not in matched  # research is not search
    assert "rent" not in matched    # current is not rent
    assert "port" not in matched    # report is not port
