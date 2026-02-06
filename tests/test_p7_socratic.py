"""Test scenarios for Socratic Method workflow (p7-socratic.yaml).

Tests the Socratic Method workflow including:
- Setup phase (define topic, formulate questions)
- Nested loops: question loop > sub-question loop
- Conditional entry into inner loop via 2-way branch
- Sub-question retry loop
- Synthesis phase
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


def _walk_to_question_loop(h):
    """Start -> define topic -> formulate questions -> enter question loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Explore question"
    assert h.status == "running"


def _complete_one_question_understood(h):
    """Complete one question: explore -> fully understood -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.0 Question loop")  # fully understood -> loop header


# ================================================================
# Scenario 1: Happy path all understood
# ================================================================


def test_happy_path_all_understood(harness_factory):
    """Exploring ethics of AI: two questions about bias and accountability, both understood clearly."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["algorithmic_bias", "ai_accountability"], "sub_questions": ["sq1", "sq2"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define topic"
    assert h.status == "running"

    r = h.submit({
        "topic": "Ethics of Artificial Intelligence",
        "context": "Philosophy course exploring moral implications of AI systems in society",
    })
    assert r
    assert r.new_step == "1.2 Formulate initial questions"
    assert h.step == "1.2 Formulate initial questions"

    r = h.submit({
        "questions": [
            "Can an algorithm be biased if it has no intentions?",
            "Who is morally responsible when an AI system causes harm?",
        ],
    })
    assert r
    assert r.new_step == "2.1 Explore question"
    assert h.step == "2.1 Explore question"

    # Question 1: algorithmic bias -- fully understood
    r = h.submit({
        "exploration": "Bias is embedded through training data reflecting historical discrimination. The algorithm has no intent, but its outputs perpetuate systemic inequality. Example: COMPAS recidivism tool showed racial bias.",
        "conclusion": "Bias is a property of the system (data + model), not of intent. Responsibility falls on designers who chose the training data.",
    })
    assert r
    assert r.new_step == "2.2 Need deeper exploration?"
    assert h.step == "2.2 Need deeper exploration?"
    r = h.submit_goto("2.0 Question loop")
    assert r
    assert r.new_step == "2.1 Explore question"
    assert h.step == "2.1 Explore question"

    # Question 2: AI accountability -- fully understood
    r = h.submit({
        "exploration": "Four candidates for responsibility: developer, deploying organization, user, and the AI itself. Current legal frameworks assign liability to the deploying organization under product liability.",
        "conclusion": "Accountability is distributed: developers have duty of care, organizations bear deployment liability, regulators set guardrails. AI cannot be a moral agent.",
    })
    assert r
    assert r.new_step == "2.2 Need deeper exploration?"
    assert h.step == "2.2 Need deeper exploration?"
    r = h.submit_goto("2.0 Question loop")
    assert r

    # Loop exhausted -> synthesis
    assert h.step == "3.1 Synthesize understanding"

    r = h.submit({
        "synthesis": "AI bias is systemic (not intentional) and accountability is distributed among human stakeholders. Both questions converge on the need for governance frameworks.",
    })
    assert r
    assert r.new_step == "3.2 Create knowledge map"
    assert h.step == "3.2 Create knowledge map"

    r = h.submit({
        "knowledge_map": "AI Ethics -> [Bias (data-driven, systemic), Accountability (distributed: dev/org/regulator)] -> Governance needed",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.submit({"topic": "philosophy of science"})
    assert h.state.data["1.1 Define topic"]["topic"] == "philosophy of science"

    h.submit({"questions": "what is falsifiability?"})
    assert h.state.data["1.2 Formulate initial questions"]["questions"] == "what is falsifiability?"

    h.submit({"exploration": "Popper's criterion"})
    assert h.state.data["2.1 Explore question"]["exploration"] == "Popper's criterion"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Question loop")
    h.submit({})
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
        "p7-socratic.yaml",
        loop_data={"questions": ["q1", "q2"], "sub_questions": ["sq1"]},
    )
    _walk_to_question_loop(h)
    h.submit({})
    assert h.step == "2.2 Need deeper exploration?"

    h.new_executor()

    assert h.step == "2.2 Need deeper exploration?"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Question loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at explore question step."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    _walk_to_question_loop(h)

    h.register_node(
        "2.1 Explore question",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("answer") else "must include answer",
        ),
    )

    r = h.submit({"notes": "forgot answer"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"answer": "falsifiability is..."})
    assert r
    assert r.new_step == "2.2 Need deeper exploration?"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes exploration results to SQLite table."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1", "q2"], "sub_questions": ["sq1"]},
    )
    _walk_to_question_loop(h)

    h.register_node(
        "2.1 Explore question",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"question": "string", "depth": "string"}},
            archive={"table": "socratic_questions"},
        ),
    )

    h.submit({"question": "what is truth?", "depth": "surface"})
    h.submit_goto("2.0 Question loop")
    h.submit({"question": "what is knowledge?", "depth": "deep"})

    rows = h.get_archived_rows("socratic_questions")
    assert len(rows) == 2
    assert rows[0]["question"] == "what is truth?"
    assert rows[1]["depth"] == "deep"


# ================================================================
# Scenario 2: Deeper exploration sub-questions
# ================================================================


def test_deeper_exploration_sub_questions(harness_factory):
    """Exploring free will: main question leads to two sub-questions about determinism and compatibilism."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["free_will"], "sub_questions": ["determinism", "compatibilism"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Philosophy of Mind: Free Will"})
    assert r
    r = h.submit({"questions": ["Do humans have genuine free will or is it an illusion?"]})
    assert r
    assert h.step == "2.1 Explore question"

    # Main question: too complex, needs deeper exploration
    r = h.submit({
        "exploration": "Three positions exist: hard determinism (no free will), libertarian free will (genuine choice), and compatibilism (free will compatible with determinism). Need to explore the first two positions deeper.",
    })
    assert r
    assert r.new_step == "2.2 Need deeper exploration?"
    assert h.step == "2.2 Need deeper exploration?"
    r = h.submit_goto("2.0.1 Sub-question loop")
    assert r
    assert r.new_step == "2.3 Explore sub-question"
    assert h.step == "2.3 Explore sub-question"

    # Sub-question 1: determinism -- resolved
    r = h.submit({
        "sub_question": "If every event is caused by prior events (determinism), how can any choice be free?",
        "exploration": "Laplace's demon thought experiment: with perfect knowledge of all particles, every future state is predictable. But quantum mechanics introduces genuine randomness, undermining strict determinism.",
    })
    assert r
    assert r.new_step == "2.4 Sub-question resolved?"
    assert h.step == "2.4 Sub-question resolved?"
    r = h.submit_goto("2.0.1 Sub-question loop")
    assert r
    assert r.new_step == "2.3 Explore sub-question"
    assert h.step == "2.3 Explore sub-question"

    # Sub-question 2: compatibilism -- resolved
    r = h.submit({
        "sub_question": "Can free will and determinism coexist (compatibilism)?",
        "exploration": "Frankfurt cases show you can be morally responsible even if you could not have done otherwise. Free will reframed as acting from your own desires without external coercion, not requiring alternative possibilities.",
    })
    assert r
    assert r.new_step == "2.4 Sub-question resolved?"
    assert h.step == "2.4 Sub-question resolved?"
    r = h.submit_goto("2.0.1 Sub-question loop")
    assert r

    # Inner loop done -> outer loop advances -> loop exits
    assert h.step == "3.1 Synthesize understanding"


# ================================================================
# Scenario 3: Sub-question retry
# ================================================================


def test_sub_question_retry(harness_factory):
    """Exploring consciousness: sub-question about qualia not resolved on first try, revisit with new angle."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["consciousness"], "sub_questions": ["qualia"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Philosophy of Consciousness"})
    assert r
    r = h.submit({"questions": ["What is consciousness and can it be explained scientifically?"]})
    assert r

    # Enter question, needs deeper exploration
    r = h.submit({
        "exploration": "The hard problem of consciousness (Chalmers): why does subjective experience exist at all? Need to explore qualia specifically.",
    })
    assert r
    r = h.submit_goto("2.0.1 Sub-question loop")
    assert r
    assert h.step == "2.3 Explore sub-question"

    # First attempt at qualia: not resolved -- too abstract
    r = h.submit({
        "sub_question": "What are qualia and can they be reduced to physical processes?",
        "exploration": "Qualia are subjective experiences (redness of red, pain of pain). Mary's Room thought experiment suggests physical knowledge is insufficient. But this is circular.",
    })
    assert r
    assert r.new_step == "2.4 Sub-question resolved?"
    assert h.step == "2.4 Sub-question resolved?"
    r = h.submit_goto("2.3 Explore sub-question")
    assert r
    assert r.new_step == "2.3 Explore sub-question"
    assert h.step == "2.3 Explore sub-question"

    # Second attempt: resolved with functionalist rebuttal
    r = h.submit({
        "sub_question": "What are qualia and can they be reduced to physical processes?",
        "exploration": "Dennett's functionalist response: qualia as we imagine them do not exist. What exists are functional states (dispositions to behave). The felt quality of red IS the neural pattern that responds to 700nm light. Mary learns a new ability (recognition), not a new fact.",
    })
    assert r
    assert r.new_step == "2.4 Sub-question resolved?"
    assert h.step == "2.4 Sub-question resolved?"
    r = h.submit_goto("2.0.1 Sub-question loop")
    assert r

    # Inner loop done, outer loop done -> synthesis
    assert h.step == "3.1 Synthesize understanding"


# ================================================================
# Scenario 4: Cross-phase fallback goto loop
# ================================================================


def test_cross_phase_fallback_goto_loop(harness_factory):
    """Learning epistemology: synthesis reveals gap in understanding of a priori knowledge, go back."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["a_priori_knowledge"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Epistemology: Sources of Knowledge"})
    assert r
    r = h.submit({"questions": ["Is a priori knowledge possible, or is all knowledge empirical?"]})
    assert r

    # Complete question loop
    r = h.submit({
        "exploration": "Kant argues math is a priori synthetic (known without experience). Quine challenges this: all knowledge is revisable based on experience.",
    })
    assert r
    r = h.submit_goto("2.0 Question loop")
    assert r
    assert h.step == "3.1 Synthesize understanding"

    # While synthesizing, realize Kant-Quine debate needs deeper exploration
    r = h.goto("2.1 Explore question")
    assert r
    assert r.new_step == "2.1 Explore question"
    assert h.step == "2.1 Explore question"
    assert h.status == "running"


# ================================================================
# Scenario 5: Stop and resume
# ================================================================


def test_stop_and_resume(harness_factory):
    """Exploring political philosophy: stop for a class break, resume after."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["justice_rawls", "liberty_nozick"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Political Philosophy: Justice and Liberty"})
    assert r
    r = h.submit({"questions": ["What is Rawls' theory of justice?", "How does Nozick challenge it?"]})
    assert r
    r = h.submit({
        "exploration": "Rawls: behind the veil of ignorance, rational agents would choose equal basic liberties and the difference principle (inequalities only if they benefit the worst-off).",
    })
    assert r
    assert h.step == "2.2 Need deeper exploration?"

    # Class break -- stop
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Need deeper exploration?"

    # Resume after break
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Need deeper exploration?"

    # Question fully understood, move to next
    r = h.submit_goto("2.0 Question loop")
    assert r
    assert r.new_step == "2.1 Explore question"
    assert h.step == "2.1 Explore question"


# ================================================================
# Scenario 6: Skip step
# ================================================================


def test_skip_step(harness_factory):
    """Continuing a prior Socratic session on logic: skip topic definition (already defined last time)."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["logical_fallacies"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    assert h.step == "1.1 Define topic"
    r = h.skip("Topic 'Logical Fallacies in Everyday Arguments' already defined in prior session")
    assert r
    assert h.step == "1.2 Formulate initial questions"

    r = h.submit({"questions": ["Why do logical fallacies persist even when people know about them?"]})
    assert r
    assert h.step == "2.1 Explore question"

    # Already explored this question in reading -- skip to evaluation
    r = h.skip("Explored in Kahneman's Thinking Fast and Slow reading last week")
    assert r
    assert h.step == "2.2 Need deeper exploration?"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish Socratic inquiry on truth, reset for a new inquiry on beauty."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["nature_of_truth"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Philosophy: The Nature of Truth"})
    assert r
    r = h.submit({"questions": ["Is truth objective or constructed by social consensus?"]})
    assert r
    r = h.submit({
        "exploration": "Correspondence theory: truth matches facts. Coherence theory: truth fits within a consistent system. Pragmatist theory: truth is what works. Each has merits depending on domain.",
    })
    assert r
    r = h.submit_goto("2.0 Question loop")
    assert r
    assert h.step == "3.1 Synthesize understanding"

    r = h.submit({"synthesis": "Truth is multi-faceted: scientific truth is correspondence, mathematical truth is coherence, everyday truth is pragmatic."})
    assert r
    r = h.submit({"knowledge_map": "Truth -> [Correspondence (science), Coherence (math/logic), Pragmatism (daily life)]"})
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Reset for new topic: aesthetics and beauty
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define topic"
    assert h.status == "running"


# ================================================================
# Scenario 8: Back
# ================================================================


def test_back(harness_factory):
    """Exploring moral relativism: realized questions need reformulating, go back."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["moral_relativism"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Moral Relativism vs Universal Ethics"})
    assert r
    assert h.step == "1.2 Formulate initial questions"

    # Questions are too vague -- go back to refine the topic
    r = h.back()
    assert r
    assert h.step == "1.1 Define topic"

    r = h.submit({"topic": "Moral Relativism: Can morality be universal across cultures?"})
    assert r
    r = h.submit({"questions": ["If morality varies by culture, does that mean no moral claim is universally true?"]})
    assert r
    r = h.submit({
        "exploration": "Cultural relativism observes moral differences; moral relativism concludes no universal standard. But some practices (e.g., human rights) are widely endorsed across cultures.",
    })
    assert r
    assert h.step == "2.2 Need deeper exploration?"

    # Need to reconsider the exploration approach
    r = h.back()
    assert r
    assert h.step == "2.1 Explore question"


# ================================================================
# Scenario 9: Goto synthesis
# ================================================================


def test_goto_synthesis(harness_factory):
    """Already explored utilitarianism in class -- jump to synthesis to write up notes."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["utilitarian_calculus", "rule_vs_act"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Utilitarianism: Bentham vs Mill"})
    assert r
    r = h.submit({"questions": ["How does the utilitarian calculus work?", "Is rule utilitarianism superior to act utilitarianism?"]})
    assert r
    assert h.step == "2.1 Explore question"

    # Both questions explored in today's seminar -- skip to synthesis
    r = h.goto("3.1 Synthesize understanding")
    assert r
    assert r.new_step == "3.1 Synthesize understanding"
    assert h.step == "3.1 Synthesize understanding"
    assert h.status == "running"

    r = h.submit({
        "synthesis": "Bentham: maximize total pleasure (hedonic calculus). Mill: quality > quantity of pleasure. Rule utilitarianism avoids the 'utility monster' problem by applying rules that generally maximize welfare.",
    })
    assert r
    assert r.new_step == "3.2 Create knowledge map"
    assert h.step == "3.2 Create knowledge map"

    r = h.submit({
        "knowledge_map": "Utilitarianism -> [Act (Bentham, calculus) vs Rule (Mill, quality)] -> Converge on welfare maximization",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML
# ================================================================


def test_modify_yaml(harness_factory):
    """Exploring existentialism: add a reflection step after each question exploration."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["existence_precedes_essence"], "sub_questions": ["sq1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"topic": "Existentialism: Sartre and Camus"})
    assert r
    r = h.submit({"questions": ["What does Sartre mean by 'existence precedes essence'?"]})
    assert r
    assert h.step == "2.1 Explore question"

    modified_yaml = """name: Socratic Method
description: Modified with reflection step

steps:
  - 1.1 Define topic

  - 1.2 Formulate initial questions

  - 2.0 Question loop:
      iterate: "questions"
      children:
        - 2.1 Explore question
        - 2.15 Reflect on question
        - 2.2 Need deeper exploration?:
            next:
              - if: "question is fully understood"
                go: 2.0 Question loop
              - go: 2.0.1 Sub-question loop
        - 2.0.1 Sub-question loop:
            iterate: "sub_questions"
            children:
              - 2.3 Explore sub-question
              - 2.4 Sub-question resolved?:
                  next:
                    - if: "sub-question resolved"
                      go: 2.0.1 Sub-question loop
                    - go: 2.3 Explore sub-question

  - 3.1 Synthesize understanding

  - 3.2 Create knowledge map

  - Done:
      type: terminate
      reason: Socratic exploration complete
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("2.15 Reflect on question")
    assert r
    assert r.new_step == "2.15 Reflect on question"
    assert h.step == "2.15 Reflect on question"

    r = h.submit({
        "reflection": "Sartre's claim means humans are not born with a predetermined purpose -- we create meaning through our choices. This is both liberating and anxiety-inducing (existential angst).",
    })
    assert r
    assert r.new_step == "2.2 Need deeper exploration?"
    assert h.step == "2.2 Need deeper exploration?"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
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
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.goto("3.2 Create knowledge map")
    h.submit({})
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
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
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.submit({"topic": "epistemology"})
    h.submit({"questions": "what is knowledge?"})

    h.save_checkpoint("at_question_loop")

    h.submit({})
    h.submit_goto("2.0 Question loop")
    assert h.step == "3.1 Synthesize understanding"

    restored = h.load_checkpoint("at_question_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Explore question"
    assert "1.1 Define topic" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    assert h.step == "1.1 Define topic"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define topic"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define topic"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.goto("3.2 Create knowledge map")
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
        "p7-socratic.yaml",
        loop_data={"questions": ["q1", "q2", "q3"], "sub_questions": ["sq1"]},
    )
    _walk_to_question_loop(h)

    loop_info = h.state.loop_state["2.0 Question loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_question_understood(h)

    loop_info = h.state.loop_state["2.0 Question loop"]
    assert loop_info["i"] == 1


def test_empty_questions_skips_loop(harness_factory):
    """Empty questions list causes loop to be skipped."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": [], "sub_questions": ["sq1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "3.1 Synthesize understanding"
    assert h.status == "running"


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define topic",
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
        "p7-socratic.yaml",
        loop_data={"questions": ["q1"], "sub_questions": ["sq1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define topic",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
