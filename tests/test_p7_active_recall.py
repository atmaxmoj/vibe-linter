"""Test scenarios for Active Recall workflow (p7-active-recall.yaml).

Tests the Active Recall workflow including:
- Setup phase (define topics, create plan)
- Topic loop with pass/fail self-test
- Failed self-test retry loop
- Mock exam with pass/fail
- Mock fail re-enters topic loop from scratch
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


def _walk_to_topic_loop(h):
    """Start -> define topics -> create plan -> enter topic loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Study topic"
    assert h.status == "running"


def _complete_one_topic_pass(h):
    """Complete one topic: study -> self-test -> pass -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Topic loop")  # pass -> loop header


# ================================================================
# Scenario 1: Happy path all pass
# ================================================================


def test_happy_path_all_pass(harness_factory):
    """Preparing for AWS Cloud Practitioner exam: two topics pass, mock exam passes."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["cloud_concepts", "security_compliance"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define exam topics"
    assert h.status == "running"

    r = h.submit({
        "exam": "AWS Certified Cloud Practitioner (CLF-C02)",
        "topics": ["Cloud Concepts (26%)", "Security and Compliance (25%)"],
        "exam_date": "2024-04-15",
    })
    assert r
    assert r.new_step == "1.2 Create study plan"
    assert h.step == "1.2 Create study plan"

    r = h.submit({
        "plan": "Week 1: Cloud concepts (3 hrs/day). Week 2: Security (3 hrs/day). Week 3: Mock exams.",
        "resources": ["AWS Skill Builder", "Stephane Maarek Udemy course", "Tutorials Dojo practice exams"],
    })
    assert r
    assert r.new_step == "2.1 Study topic"
    assert h.step == "2.1 Study topic"

    # Topic 1: Cloud Concepts -- pass
    r = h.submit({
        "topic": "Cloud Concepts",
        "notes": "Studied IaaS/PaaS/SaaS, shared responsibility model, well-architected framework 6 pillars",
    })
    assert r
    assert r.new_step == "2.2 Self-test"
    assert h.step == "2.2 Self-test"
    r = h.submit({
        "questions_attempted": 20,
        "correct": 17,
        "score": "85%",
        "weak_areas": "Confusing CloudFront vs Global Accelerator",
    })
    assert r
    assert r.new_step == "2.3 Pass?"
    assert h.step == "2.3 Pass?"
    r = h.submit_goto("2.0 Topic loop")
    assert r
    assert r.new_step == "2.1 Study topic"
    assert h.step == "2.1 Study topic"

    # Topic 2: Security -- pass
    r = h.submit({
        "topic": "Security and Compliance",
        "notes": "IAM policies, KMS encryption, CloudTrail auditing, AWS Config compliance rules",
    })
    assert r
    r = h.submit({
        "questions_attempted": 20,
        "correct": 18,
        "score": "90%",
    })
    assert r
    assert h.step == "2.3 Pass?"
    r = h.submit_goto("2.0 Topic loop")
    assert r

    # Loop done
    assert h.step == "3.1 Take mock exam"

    r = h.submit({
        "mock_exam": "Tutorials Dojo Practice Exam #1",
        "questions": 65,
        "score": "82%",
        "passing_score": "70%",
    })
    assert r
    assert r.new_step == "3.2 Mock result"
    assert h.step == "3.2 Mock result"

    # Mock exam passed
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.submit({"topics": "calculus, algebra"})
    assert h.state.data["1.1 Define exam topics"]["topics"] == "calculus, algebra"

    h.submit({"plan": "2 hours per day"})
    assert h.state.data["1.2 Create study plan"]["plan"] == "2 hours per day"

    h.submit({"notes": "studied derivatives"})
    assert h.state.data["2.1 Study topic"]["notes"] == "studied derivatives"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Topic loop")
    h.submit({})
    h.submit_goto("Done")
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
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1", "t2"]},
    )
    _walk_to_topic_loop(h)
    h.submit({})
    assert h.step == "2.2 Self-test"

    h.new_executor()

    assert h.step == "2.2 Self-test"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Topic loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at study topic step."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    _walk_to_topic_loop(h)

    h.register_node(
        "2.1 Study topic",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("topic_name") else "must include topic_name",
        ),
    )

    r = h.submit({"notes": "forgot topic name"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"topic_name": "calculus"})
    assert r
    assert r.new_step == "2.2 Self-test"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes test results to SQLite table."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1", "t2"]},
    )
    _walk_to_topic_loop(h)

    h.register_node(
        "2.2 Self-test",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"topic": "string", "score": "string"}},
            archive={"table": "self_test_results"},
        ),
    )

    h.submit({})
    h.submit({"topic": "t1", "score": "85"})
    h.submit_goto("2.0 Topic loop")
    h.submit({})
    h.submit({"topic": "t2", "score": "92"})

    rows = h.get_archived_rows("self_test_results")
    assert len(rows) == 2
    assert rows[0]["topic"] == "t1"
    assert rows[1]["score"] == "92"


# ================================================================
# Scenario 2: Self-test fail retry
# ================================================================


def test_self_test_fail_retry(harness_factory):
    """Calculus exam prep: integration by parts fails twice, passes after working through examples."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["integration_by_parts"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "Calculus II Final Exam", "topics": ["Integration by parts"]})
    assert r
    r = h.submit({"plan": "Practice 10 problems per day, test after each study session"})
    assert r

    # First attempt: fails -- cannot choose u and dv correctly
    r = h.submit({"topic": "Integration by parts", "notes": "Read textbook section 7.1, memorized formula"})
    assert r
    r = h.submit({"questions": 10, "correct": 4, "score": "40%", "issue": "Cannot choose u and dv for ln(x)*x^2"})
    assert r
    assert h.step == "2.3 Pass?"
    r = h.submit_goto("2.1 Study topic")
    assert r
    assert r.new_step == "2.1 Study topic"
    assert h.step == "2.1 Study topic"

    # Second attempt: fails again -- LIATE rule helps but still struggling
    r = h.submit({"topic": "Integration by parts", "notes": "Learned LIATE rule (Log, Inverse trig, Algebraic, Trig, Exponential)"})
    assert r
    r = h.submit({"questions": 10, "correct": 6, "score": "60%", "issue": "Applying LIATE to nested functions"})
    assert r
    r = h.submit_goto("2.1 Study topic")
    assert r
    assert r.new_step == "2.1 Study topic"
    assert h.step == "2.1 Study topic"

    # Third attempt: passes -- worked through 20 examples with solutions
    r = h.submit({"topic": "Integration by parts", "notes": "Worked 20 textbook examples step-by-step, tabular method for repeated IBP"})
    assert r
    r = h.submit({"questions": 10, "correct": 9, "score": "90%", "note": "Tabular method made repeated IBP easy"})
    assert r
    r = h.submit_goto("2.0 Topic loop")
    assert r

    assert h.step == "3.1 Take mock exam"


# ================================================================
# Scenario 3: Mock exam fail redo topics
# ================================================================


def test_mock_exam_fail_redo_topics(harness_factory):
    """LSAT logic games: mock exam fails, restudy ordering games, retake and pass."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["logic_games"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "LSAT Logic Games Section", "topics": ["Ordering and grouping games"]})
    assert r
    r = h.submit({"plan": "2 weeks: 5 games/day, timed at 35 minutes per section"})
    assert r

    # Topic: logic games -- self-test passes
    r = h.submit({"topic": "Logic games", "notes": "Practiced sequencing, grouping, and hybrid game types"})
    assert r
    r = h.submit({"questions": 8, "correct": 6, "score": "75%"})
    assert r
    r = h.submit_goto("2.0 Topic loop")
    assert r
    assert h.step == "3.1 Take mock exam"

    # Mock exam: fail (time pressure caused errors)
    r = h.submit({
        "mock_exam": "LSAT PrepTest 92 Section 3",
        "questions": 23,
        "correct": 14,
        "score": "61%",
        "issue": "Ran out of time on last 2 games, guessed on 5 questions",
    })
    assert r
    assert r.new_step == "3.2 Mock result"
    assert h.step == "3.2 Mock result"
    r = h.submit_goto("2.0 Topic loop")
    assert r

    # Loop re-initialized
    assert h.step == "2.1 Study topic"

    # Restudy with focus on time management
    r = h.submit({"topic": "Logic games", "notes": "Focused on sketching game boards faster, learned 'limited options' strategy"})
    assert r
    r = h.submit({"questions": 8, "correct": 7, "score": "87.5%", "time": "Completed in 30 minutes"})
    assert r
    r = h.submit_goto("2.0 Topic loop")
    assert r
    assert h.step == "3.1 Take mock exam"

    # Mock exam: pass
    r = h.submit({
        "mock_exam": "LSAT PrepTest 93 Section 3",
        "questions": 23,
        "correct": 19,
        "score": "83%",
        "time": "Finished with 3 minutes to spare",
    })
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 4: Cross-phase fallback
# ================================================================


def test_cross_phase_fallback(harness_factory):
    """Bar exam prep: about to take mock but realize Constitutional Law needs more work."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["constitutional_law"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "Bar Exam: Constitutional Law Section", "topics": ["Due process, equal protection, First Amendment"]})
    assert r
    r = h.submit({"plan": "6 weeks: outline each topic, practice essays, take 3 mock exams"})
    assert r

    # Complete topic loop
    r = h.submit({"topic": "Constitutional Law", "notes": "Outlined substantive due process, equal protection tiers of scrutiny"})
    assert r
    r = h.submit({"questions": 15, "correct": 11, "score": "73%"})
    assert r
    r = h.submit_goto("2.0 Topic loop")
    assert r
    assert h.step == "3.1 Take mock exam"

    # Reading mock exam questions, realize First Amendment doctrine is shaky
    r = h.goto("2.1 Study topic")
    assert r
    assert r.new_step == "2.1 Study topic"
    assert h.step == "2.1 Study topic"
    assert h.status == "running"


# ================================================================
# Scenario 5: Stop and resume
# ================================================================


def test_stop_and_resume(harness_factory):
    """CPA exam prep: stop mid-study for a client emergency, resume next morning."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["financial_accounting", "audit_procedures"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "CPA Exam: Financial Accounting & Reporting", "topics": ["Revenue recognition, lease accounting, audit sampling"]})
    assert r
    r = h.submit({"plan": "8 weeks: Becker CPA review + 500 MCQs per section + 2 full mocks"})
    assert r
    r = h.submit({"topic": "Financial Accounting", "notes": "ASC 606 five-step revenue model, lease classification under ASC 842"})
    assert r
    assert h.step == "2.2 Self-test"

    # Emergency client call - stop studying
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Self-test"

    # Next morning, resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Self-test"

    # Continue self-test on revenue recognition
    r = h.submit({"questions": 25, "correct": 19, "score": "76%", "weak_areas": "Variable consideration estimates"})
    assert r
    assert r.new_step == "2.3 Pass?"
    assert h.step == "2.3 Pass?"


# ================================================================
# Scenario 6: Skip step
# ================================================================


def test_skip_step(harness_factory):
    """PMP exam: skip study for a topic already mastered in work experience."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["stakeholder_management"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "PMP Certification", "topics": ["Stakeholder engagement, risk management, agile delivery"]})
    assert r
    r = h.submit({"plan": "4 weeks: PMI study guide + Rita Mulcahy + 3 practice exams"})
    assert r
    assert h.step == "2.1 Study topic"

    # 10 years as project manager, skip stakeholder management study
    r = h.skip("Already know this topic - 10 years as PM, stakeholder management is daily work")
    assert r
    assert h.step == "2.2 Self-test"
    assert h.status == "running"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """CompTIA Security+ passed, reset to prep for CompTIA CySA+."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["network_security"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "CompTIA Security+ SY0-701", "topics": ["Network security, threat analysis, cryptography"]})
    assert r
    r = h.submit({"plan": "6 weeks: Professor Messer videos + Dion practice exams + labs"})
    assert r
    r = h.submit({"topic": "Network Security", "notes": "Firewalls, IDS/IPS, VPN protocols, 802.1X, network segmentation"})
    assert r
    r = h.submit({"questions": 30, "correct": 27, "score": "90%"})
    assert r
    r = h.submit_goto("2.0 Topic loop")
    assert r
    r = h.submit({"exam_score": "832/900", "passing": 750, "result": "PASSED", "time": "78 minutes"})
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Passed Security+, now reset to start CySA+ prep
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define exam topics"
    assert h.status == "running"


# ================================================================
# Scenario 8: Back
# ================================================================


def test_back(harness_factory):
    """MCAT prep: go back to redefine topics after realizing scope is too broad."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["biochemistry"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "MCAT", "topics": ["All of biology, chemistry, physics, psychology, sociology"]})
    assert r
    assert h.step == "1.2 Create study plan"

    # Realize topic list is too broad, go back to narrow it down
    r = h.back()
    assert r
    assert h.step == "1.1 Define exam topics"

    r = h.submit({"exam": "MCAT - Biological & Biochemical Foundations only", "topics": ["Amino acids, enzyme kinetics, metabolism pathways"]})
    assert r
    r = h.submit({"plan": "10 weeks: Kaplan books + AAMC practice materials + Anki deck"})
    assert r
    r = h.submit({"topic": "Biochemistry", "notes": "Amino acid structures, pKa values, enzyme inhibition types (competitive, uncompetitive, noncompetitive)"})
    assert r
    assert h.step == "2.2 Self-test"

    # Back to restudy - enzyme kinetics was harder than expected
    r = h.back()
    assert r
    assert h.step == "2.1 Study topic"


# ================================================================
# Scenario 9: Goto mock exam
# ================================================================


def test_goto_mock_exam(harness_factory):
    """GRE prep: already studied all topics via Magoosh, jump straight to practice test."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["quantitative_reasoning", "verbal_reasoning"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "GRE General Test", "topics": ["Quantitative reasoning, verbal reasoning, analytical writing"]})
    assert r
    r = h.submit({"plan": "3 weeks: already completed Magoosh course, just need practice tests"})
    assert r
    assert h.step == "2.1 Study topic"

    # Studied everything via Magoosh already, jump to mock exam
    r = h.goto("3.1 Take mock exam")
    assert r
    assert r.new_step == "3.1 Take mock exam"
    assert h.step == "3.1 Take mock exam"
    assert h.status == "running"

    r = h.submit({"exam_score": "Quant 168, Verbal 164, AWA 5.0", "total": "332/340", "time": "3h 45m"})
    assert r
    assert r.new_step == "3.2 Mock result"
    assert h.step == "3.2 Mock result"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML
# ================================================================


def test_modify_yaml(harness_factory):
    """CISSP exam: add a flashcard review step between study and self-test."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["security_architecture"]},
    )
    r = h.start()
    assert r

    r = h.submit({"exam": "CISSP Certification", "topics": ["Security architecture, access control, cryptography, network security"]})
    assert r
    r = h.submit({"plan": "12 weeks: Sybex study guide + Boson practice exams + 11th Hour review"})
    assert r
    assert h.step == "2.1 Study topic"

    modified_yaml = """名称: Active Recall
描述: Modified with review notes step

步骤:
  - 1.1 Define exam topics

  - 1.2 Create study plan

  - 2.0 Topic loop:
      遍历: "topics"
      子步骤:
        - 2.1 Study topic
        - 2.15 Review notes
        - 2.2 Self-test
        - 2.3 Pass?:
            下一步:
              - 如果: "passed self-test"
                去: 2.0 Topic loop
              - 去: 2.1 Study topic

  - 3.1 Take mock exam

  - 3.2 Mock result:
      下一步:
        - 如果: "passed mock exam"
          去: Done
        - 去: 2.0 Topic loop

  - Done:
      类型: terminate
      原因: Exam preparation complete
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("2.15 Review notes")
    assert r
    assert r.new_step == "2.15 Review notes"
    assert h.step == "2.15 Review notes"

    r = h.submit({"flashcards_reviewed": 40, "confidence": "high", "notes": "CIA triad, defense in depth, zero trust architecture - all solid"})
    assert r
    assert r.new_step == "2.2 Self-test"
    assert h.step == "2.2 Self-test"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
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
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.goto("3.2 Mock result")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
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
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.submit({"topics": "calculus"})
    h.submit({"plan": "study daily"})

    h.save_checkpoint("at_topic_loop")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Topic loop")
    assert h.step == "3.1 Take mock exam"

    restored = h.load_checkpoint("at_topic_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Study topic"
    assert "1.1 Define exam topics" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    assert h.step == "1.1 Define exam topics"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define exam topics"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define exam topics"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.goto("3.2 Mock result")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1", "t2", "t3"]},
    )
    _walk_to_topic_loop(h)

    loop_info = h.state.loop_state["2.0 Topic loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_topic_pass(h)

    loop_info = h.state.loop_state["2.0 Topic loop"]
    assert loop_info["i"] == 1


def test_empty_topics_skips_loop(harness_factory):
    """Empty topics list causes loop to be skipped."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": []},
    )
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "3.1 Take mock exam"
    assert h.status == "running"


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define exam topics",
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
        "p7-active-recall.yaml",
        loop_data={"topics": ["t1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define exam topics",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
