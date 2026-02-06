"""Test scenarios for Spaced Repetition workflow (p7-spaced-repetition.yaml).

Tests the Spaced Repetition workflow including:
- Setup phase (create deck, set schedule)
- Session loop with 4-way rating (again/hard/good/easy)
- Hard-card review path
- Again-retry back to present cards
- Completion phase
- State transitions, gotos, stops/resumes, and hot-reload

Dimensions tested per scenario:
  - State machine transitions (happy path)
  - Data accumulation (submit data persists in state.data)
  - History audit trail (action sequence in get_history)
  - Cross-executor recovery (close + new_executor + resume)
  - Node validation (validate node rejects bad data)
  - Node archival (archive node writes to SQLite)
  - Error boundaries (wrong-state operations fail gracefully)
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, NodeDefinition

# --- Helpers ---


def _walk_to_session_loop(h):
    """Start -> create deck -> set schedule -> enter session loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Present cards"
    assert h.status == "running"


def _complete_one_session_good(h):
    """Complete one session: present -> self-assess -> rate good -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Session loop")  # good/easy -> loop header


# ================================================================
# Scenario 1: Happy path all good
# ================================================================


def test_happy_path_all_good(harness_factory):
    """Studying Japanese JLPT N3 vocabulary: 3 review sessions, all rated good."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["day_1_review", "day_3_review", "day_7_review"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Create flashcard deck"
    assert h.status == "running"

    r = h.submit({
        "deck_name": "JLPT N3 Vocabulary",
        "total_cards": 120,
        "categories": ["verbs (40)", "adjectives (30)", "nouns (50)"],
    })
    assert r
    assert r.new_step == "1.2 Set schedule"
    assert h.step == "1.2 Set schedule"

    r = h.submit({
        "schedule": "Day 1, Day 3, Day 7 (expanding intervals)",
        "daily_new_cards": 20,
        "daily_review_cards": 40,
    })
    assert r
    assert r.new_step == "2.1 Present cards"
    assert h.step == "2.1 Present cards"

    session_data = [
        {
            "present": {"session": "Day 1", "new_cards": 20, "review_cards": 0},
            "assess": {"correct": 16, "incorrect": 4, "accuracy": "80%"},
        },
        {
            "present": {"session": "Day 3", "new_cards": 20, "review_cards": 20},
            "assess": {"correct": 35, "incorrect": 5, "accuracy": "87.5%"},
        },
        {
            "present": {"session": "Day 7", "new_cards": 20, "review_cards": 40},
            "assess": {"correct": 54, "incorrect": 6, "accuracy": "90%"},
        },
    ]

    for i in range(3):
        r = h.submit(session_data[i]["present"])
        assert r
        assert r.new_step == "2.2 Self-assess"
        assert h.step == "2.2 Self-assess"
        r = h.submit(session_data[i]["assess"])
        assert r
        assert r.new_step == "2.3 Rate performance"
        assert h.step == "2.3 Rate performance"
        # All good -> continue loop
        r = h.submit_goto("2.0 Session loop")
        assert r
        if i < 2:
            assert r.new_step == "2.1 Present cards"
            assert h.step == "2.1 Present cards"

    assert h.step == "3.1 Review statistics"

    r = h.submit({
        "total_cards_reviewed": 180,
        "overall_accuracy": "86%",
        "cards_mastered": 95,
        "cards_learning": 25,
        "recommendation": "Focus on verb conjugation cards in next cycle",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({"deck": "vocabulary 100 cards"})
    assert h.state.data["1.1 Create flashcard deck"]["deck"] == "vocabulary 100 cards"

    h.submit({"schedule": "daily at 9am"})
    assert h.state.data["1.2 Set schedule"]["schedule"] == "daily at 9am"

    h.submit({"cards_presented": "20"})
    assert h.state.data["2.1 Present cards"]["cards_presented"] == "20"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Session loop")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_happy_path_cross_executor_in_loop(harness_factory):
    """Close executor mid-loop, reopen, state persists."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1", "s2", "s3"]},
    )
    _walk_to_session_loop(h)
    h.submit({})
    assert h.step == "2.2 Self-assess"

    h.new_executor()

    assert h.step == "2.2 Self-assess"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Session loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at present cards step."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    _walk_to_session_loop(h)

    h.register_node(
        "2.1 Present cards",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("card_count") else "must include card_count",
        ),
    )

    r = h.submit({"notes": "forgot count"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"card_count": "20"})
    assert r
    assert r.new_step == "2.2 Self-assess"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes session ratings to SQLite table."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1", "s2"]},
    )
    _walk_to_session_loop(h)

    h.register_node(
        "2.2 Self-assess",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"session": "string", "confidence": "string"}},
            archive={"table": "session_assessments"},
        ),
    )

    h.submit({})
    h.submit({"session": "s1", "confidence": "high"})
    h.submit_goto("2.0 Session loop")
    h.submit({})
    h.submit({"session": "s2", "confidence": "medium"})

    rows = h.get_archived_rows("session_assessments")
    assert len(rows) == 2
    assert rows[0]["session"] == "s1"
    assert rows[1]["confidence"] == "medium"


# ================================================================
# Scenario 2: Again rating retry
# ================================================================


def test_again_rating_retry(harness_factory):
    """Organic chemistry functional groups: rated 'again' twice (ketones vs aldehydes), third time gets it."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["functional_groups"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "Organic Chemistry: Functional Groups", "total_cards": 30})
    assert r
    r = h.submit({"schedule": "Review every 2 hours until mastered"})
    assert r
    assert h.step == "2.1 Present cards"

    # First attempt: confused ketones and aldehydes -- rated 'again'
    r = h.submit({"cards_presented": 30, "focus": "Ketones, aldehydes, esters, ethers"})
    assert r
    r = h.submit({"correct": 18, "incorrect": 12, "worst_cards": "ketone vs aldehyde distinction"})
    assert r
    assert h.step == "2.3 Rate performance"
    r = h.submit_goto("2.1 Present cards")
    assert r
    assert r.new_step == "2.1 Present cards"
    assert h.step == "2.1 Present cards"

    # Second attempt: still mixing up carbonyl positions -- rated 'again'
    r = h.submit({"cards_presented": 12, "focus": "Failed cards only: ketones and aldehydes"})
    assert r
    r = h.submit({"correct": 8, "incorrect": 4, "note": "Still confusing terminal vs internal carbonyl"})
    assert r
    assert h.step == "2.3 Rate performance"
    r = h.submit_goto("2.1 Present cards")
    assert r
    assert r.new_step == "2.1 Present cards"
    assert h.step == "2.1 Present cards"

    # Third attempt: used mnemonic (ALDEhyde = ALways at the END) -- rated 'good'
    r = h.submit({"cards_presented": 4, "focus": "Remaining failed cards with mnemonics"})
    assert r
    r = h.submit({"correct": 4, "incorrect": 0, "note": "Mnemonic helped: aldehyde = always at the end"})
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert h.step == "3.1 Review statistics"


# ================================================================
# Scenario 3: Hard cards review
# ================================================================


def test_hard_cards_review(harness_factory):
    """Spanish vocabulary: verb conjugations are hard, review them separately before next session."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["irregular_verbs", "common_phrases"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "Spanish B1 Vocabulary", "total_cards": 80})
    assert r
    r = h.submit({"schedule": "Daily morning reviews, 20 cards per session"})
    assert r

    # Session 1: irregular verbs are hard
    r = h.submit({"cards_presented": 20, "focus": "Irregular verb conjugations (ser, ir, tener, hacer)"})
    assert r
    r = h.submit({"correct": 12, "incorrect": 8, "hard_cards": "preterite tense of ir/ser (both 'fui')"})
    assert r
    assert h.step == "2.3 Rate performance"
    r = h.submit_goto("2.4 Review hard cards")
    assert r
    assert r.new_step == "2.4 Review hard cards"
    assert h.step == "2.4 Review hard cards"

    # Review hard cards with extra context and examples
    r = h.submit({
        "hard_cards_reviewed": 8,
        "technique": "Added example sentences: 'Fui al mercado' (ir) vs 'Fui estudiante' (ser)",
        "after_review_correct": 6,
    })
    assert r
    assert r.new_step == "2.1 Present cards"
    assert h.step == "2.1 Present cards"

    # Session 2: common phrases -- all good
    r = h.submit({"cards_presented": 20, "focus": "Common conversational phrases"})
    assert r
    r = h.submit({"correct": 19, "incorrect": 1, "accuracy": "95%"})
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert h.step == "3.1 Review statistics"


# ================================================================
# Scenario 4: Cross-phase fallback
# ================================================================


def test_cross_phase_fallback(harness_factory):
    """Medical terminology flashcards: statistics show low accuracy, go back for another round."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["anatomy_terms"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "Medical Terminology: Anatomy", "total_cards": 60})
    assert r
    r = h.submit({"schedule": "Twice daily before anatomy exam next week"})
    assert r

    # Complete session
    r = h.submit({"cards_presented": 60, "focus": "Full deck review"})
    assert r
    r = h.submit({"correct": 38, "incorrect": 22, "accuracy": "63%"})
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert h.step == "3.1 Review statistics"

    # 63% is too low for the exam -- need more practice
    r = h.goto("2.1 Present cards")
    assert r
    assert r.new_step == "2.1 Present cards"
    assert h.step == "2.1 Present cards"
    assert h.status == "running"


# ================================================================
# Scenario 5: Stop and resume
# ================================================================


def test_stop_and_resume(harness_factory):
    """GRE vocabulary prep: phone dies mid-session on the bus, resume when charged."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["gre_verbal_1", "gre_verbal_2"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "GRE High-Frequency Vocabulary", "total_cards": 200})
    assert r
    r = h.submit({"schedule": "Morning commute and evening, 50 cards per session"})
    assert r
    r = h.submit({"cards_presented": 50, "focus": "Words starting with A-D"})
    assert r
    assert h.step == "2.2 Self-assess"

    # Phone battery died on the bus -- stop
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Self-assess"

    # Phone charged -- resume on the way home
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Self-assess"

    # Continue from where we left off
    r = h.submit({"correct": 38, "incorrect": 12, "hard_words": "abstruse, circumlocution, deleterious"})
    assert r
    assert r.new_step == "2.3 Rate performance"
    assert h.step == "2.3 Rate performance"


# ================================================================
# Scenario 6: Skip step
# ================================================================


def test_skip_step(harness_factory):
    """History dates deck: cards auto-graded by the app, skip manual self-assessment."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["history_dates"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "World History Key Dates", "total_cards": 50})
    assert r
    r = h.submit({"schedule": "Every other day, full deck"})
    assert r
    r = h.submit({"cards_presented": 50, "focus": "Ancient to Medieval period"})
    assert r
    assert h.step == "2.2 Self-assess"

    # App auto-graded via typed-answer matching -- skip manual self-assessment
    r = h.skip("Auto-graded: app compared typed answers to correct dates")
    assert r
    assert h.step == "2.3 Rate performance"
    assert h.status == "running"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish French vocabulary deck, reset to start a German vocabulary deck."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["french_final"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "French A2 Vocabulary", "total_cards": 100})
    assert r
    r = h.submit({"schedule": "Final review before trip to Paris"})
    assert r
    r = h.submit({"cards_presented": 100, "focus": "Full deck final review"})
    assert r
    r = h.submit({"correct": 92, "incorrect": 8, "accuracy": "92%"})
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    r = h.submit({
        "total_accuracy": "92%",
        "cards_mastered": 92,
        "verdict": "Ready for Paris trip, 8 cards moved to review-again pile",
    })
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for German vocabulary
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Create flashcard deck"
    assert h.status == "running"


# ================================================================
# Scenario 8: Back
# ================================================================


def test_back(harness_factory):
    """Piano chord flashcards: schedule too aggressive, go back to adjust."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["chord_review"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "Piano Chords: Major, Minor, 7th", "total_cards": 36})
    assert r
    assert h.step == "1.2 Set schedule"

    # Schedule too aggressive -- go back to review deck size
    r = h.back()
    assert r
    assert h.step == "1.1 Create flashcard deck"

    r = h.submit({"deck_name": "Piano Chords: Major and Minor Only", "total_cards": 24, "note": "Dropped 7th chords for now"})
    assert r
    r = h.submit({"schedule": "Every other day, 12 cards per session"})
    assert r
    r = h.submit({"cards_presented": 12, "focus": "C, D, E, F major and minor chords"})
    assert r
    assert h.step == "2.2 Self-assess"

    # Forgot to include audio playback -- go back to re-present with audio
    r = h.back()
    assert r
    assert h.step == "2.1 Present cards"


# ================================================================
# Scenario 9: Goto statistics
# ================================================================


def test_goto_statistics(harness_factory):
    """AWS certification prep: sessions done offline, jump to statistics to record results."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["aws_services", "aws_networking"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "AWS Solutions Architect Associate", "total_cards": 150})
    assert r
    r = h.submit({"schedule": "Daily during commute using Anki mobile app"})
    assert r
    assert h.step == "2.1 Present cards"

    # Sessions completed offline in Anki -- jump to statistics
    r = h.goto("3.1 Review statistics")
    assert r
    assert r.new_step == "3.1 Review statistics"
    assert h.step == "3.1 Review statistics"
    assert h.status == "running"

    r = h.submit({
        "source": "Imported from Anki statistics export",
        "total_reviews": 300,
        "mature_cards": 120,
        "young_cards": 30,
        "retention_rate": "88%",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML
# ================================================================


def test_modify_yaml(harness_factory):
    """Mandarin tones flashcards: add a difficulty adjustment step to tune card intervals."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["tones_session"]},
    )
    r = h.start()
    assert r

    r = h.submit({"deck_name": "Mandarin Chinese: Four Tones", "total_cards": 40})
    assert r
    r = h.submit({"schedule": "Twice daily, listen and repeat"})
    assert r
    r = h.submit({"cards_presented": 40, "focus": "Tone pairs: ma1 vs ma3, shi1 vs shi4"})
    assert r
    assert h.step == "2.2 Self-assess"

    modified_yaml = """名称: Spaced Repetition
描述: Modified with difficulty adjustment

步骤:
  - 1.1 Create flashcard deck

  - 1.2 Set schedule

  - 2.0 Session loop:
      遍历: "sessions"
      子步骤:
        - 2.1 Present cards
        - 2.2 Self-assess
        - 2.25 Adjust difficulty
        - 2.3 Rate performance:
            下一步:
              - 如果: "all cards rated good or easy"
                去: 2.0 Session loop
              - 如果: "some cards rated hard"
                去: 2.4 Review hard cards
              - 如果: "some cards rated again"
                去: 2.1 Present cards
              - 去: 2.0 Session loop
        - 2.4 Review hard cards

  - 3.1 Review statistics

  - Done:
      类型: terminate
      原因: Spaced repetition cycle complete
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("2.25 Adjust difficulty")
    assert r
    assert r.new_step == "2.25 Adjust difficulty"
    assert h.step == "2.25 Adjust difficulty"

    r = h.submit({
        "adjustment": "Increased interval for tone 1 cards (easy), decreased for tone 2/3 confusion pairs",
        "new_intervals": {"easy": "4 days", "hard": "1 day", "again": "4 hours"},
    })
    assert r
    assert r.new_step == "2.3 Rate performance"
    assert h.step == "2.3 Rate performance"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({})
    h.stop()
    assert h.status == "stopped"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.goto("3.1 Review statistics")
    h.submit({})
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


# ================================================================
# Generic / cross-cutting tests
# ================================================================


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({"deck": "math deck"})
    h.submit({"schedule": "every 2 days"})

    h.save_checkpoint("at_session_loop")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Session loop")
    assert h.step == "3.1 Review statistics"

    restored = h.load_checkpoint("at_session_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Present cards"
    assert "1.1 Create flashcard deck" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    assert h.step == "1.1 Create flashcard deck"

    r = h.retry()
    assert r
    assert h.step == "1.1 Create flashcard deck"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Create flashcard deck"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.goto("3.1 Review statistics")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1", "s2", "s3"]},
    )
    _walk_to_session_loop(h)

    loop_info = h.state.loop_state["2.0 Session loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_session_good(h)

    loop_info = h.state.loop_state["2.0 Session loop"]
    assert loop_info["i"] == 1


def test_empty_sessions_skips_loop(harness_factory):
    """Empty sessions list causes loop to be skipped."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": []},
    )
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "3.1 Review statistics"
    assert h.status == "running"


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.register_node(
        "1.1 Create flashcard deck",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step.\n\n## Steps\n1. Analyze\n2. Implement",
            check=lambda data: True,
        ),
    )
    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory(
        "p7-spaced-repetition.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.register_node(
        "1.1 Create flashcard deck",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
