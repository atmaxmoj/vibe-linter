"""Thematic Analysis workflow tests (p4-thematic-analysis.yaml).

Tests the 6-step linear flow with report review containing
3-way fallback (satisfactory/refinement/back to coding).
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---

def _advance_to_report_review(h):
    """Start and advance through 6 steps to reach 1.7 Report review (waiting)."""
    h.start()
    for _ in range(6):
        h.submit({})
    assert h.step == "1.7 Report review"
    assert h.status == "waiting"


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_complete_smoothly(harness_factory):
    """Thematic analysis of 22 nurse burnout interviews during COVID-19: full Braun & Clarke 6-step process."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Familiarize with data"
    assert h.status == "running"

    r = h.submit({
        "data_source": "Semi-structured interviews with ICU nurses",
        "participants": 22,
        "duration_range": "35-90 minutes",
        "transcription": "Verbatim, NVivo 14",
        "total_pages": 487,
        "initial_notes": "Strong emotional language around moral injury, staffing shortages recurring topic",
    })
    assert r
    assert r.new_step == "1.2 Generate initial codes"
    assert h.step == "1.2 Generate initial codes"
    assert h.status == "running"

    r = h.submit({
        "coding_approach": "Inductive, line-by-line",
        "total_codes": 147,
        "code_examples": [
            "moral_distress", "emotional_exhaustion", "staffing_inadequacy",
            "PPE_anxiety", "patient_death_guilt", "peer_support",
            "management_disconnect", "sense_of_duty", "leaving_profession",
            "coping_mechanisms", "family_strain", "PTSD_symptoms",
        ],
        "inter_rater_reliability": "Cohen's kappa = 0.82 (2 coders on 20% sample)",
    })
    assert r
    assert r.new_step == "1.3 Search for themes"
    assert h.step == "1.3 Search for themes"

    r = h.submit({
        "candidate_themes": [
            "Moral injury and ethical burden",
            "Systemic abandonment by leadership",
            "Collective trauma and peer solidarity",
            "Identity crisis: healer vs survivor",
            "Breaking point: leaving vs staying",
        ],
        "thematic_map": "Created using affinity diagramming in Miro",
        "codes_per_theme": {"moral_injury": 34, "systemic_abandonment": 28, "collective_trauma": 25, "identity_crisis": 31, "breaking_point": 29},
    })
    assert r
    assert r.new_step == "1.4 Review themes"
    assert h.step == "1.4 Review themes"

    r = h.submit({
        "review_outcome": "Merged 'identity crisis' and 'breaking point' into 'Professional identity dissolution'",
        "final_theme_count": 4,
        "themes_after_review": [
            "Moral injury and ethical burden",
            "Systemic abandonment by institutional leadership",
            "Collective trauma and peer solidarity",
            "Professional identity dissolution",
        ],
        "coherence_check": "All themes internally consistent, distinct from each other",
    })
    assert r
    assert r.new_step == "1.5 Define and name themes"
    assert h.step == "1.5 Define and name themes"

    r = h.submit({
        "theme_definitions": {
            "Moral Injury": "The psychological distress from being unable to provide care meeting personal ethical standards due to resource constraints",
            "Institutional Betrayal": "Perception that hospital administration prioritized financial metrics over frontline worker safety and wellbeing",
            "Trauma Bonds": "Deep interpersonal connections forged through shared extreme experiences, serving as primary coping mechanism",
            "Identity Erosion": "Progressive loss of professional identity and vocational purpose, manifesting as cynicism, depersonalization, and exit intentions",
        },
    })
    assert r
    assert r.new_step == "1.6 Write report"
    assert h.step == "1.6 Write report"

    r = h.submit({
        "report_structure": ["Introduction", "Literature Review", "Methodology", "Findings", "Discussion", "Implications", "Limitations"],
        "word_count": 9800,
        "participant_quotes": 34,
        "target_journal": "Qualitative Health Research",
    })
    assert r
    assert r.new_step == "1.7 Report review"
    assert h.step == "1.7 Report review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_review_unsatisfactory_back_to_themes(harness_factory):
    """Reviewer says remote work themes too surface-level; refine definitions and rewrite."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    # Advance to report review
    r = h.submit({"data_source": "Focus groups with remote workers post-pandemic", "participants": 36})
    r = h.submit({"total_codes": 98, "coding_approach": "Hybrid deductive-inductive"})
    r = h.submit({"candidate_themes": ["Flexibility paradox", "Digital fatigue", "Boundary erosion", "Autonomy vs isolation"]})
    r = h.submit({"review_outcome": "All 4 themes retained, no merging needed"})
    r = h.submit({"theme_definitions": {"Flexibility paradox": "Freedom in scheduling creates pressure to be always available"}})
    r = h.submit({"word_count": 7200, "target_journal": "Organization Studies"})
    assert r
    assert h.step == "1.7 Report review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("1.5 Define and name themes")
    assert r
    assert r.new_step == "1.5 Define and name themes"
    assert h.step == "1.5 Define and name themes"
    assert h.status == "running"

    # Redo from themes with sharper definitions
    r = h.submit({
        "theme_definitions": {
            "The Flexibility Trap": "Perceived autonomy masking increased work-life boundary dissolution",
            "Digital Presenteeism": "Compulsive screen engagement as proxy for productivity demonstration",
            "Engineered Isolation": "Organizational structures that inadvertently silo remote workers",
            "Autonomy Paradox": "Self-direction breeding anxiety about visibility and career progression",
        },
        "revision_note": "Sharpened definitions per reviewer feedback, added sub-themes",
    })
    assert r
    assert r.new_step == "1.6 Write report"
    assert h.step == "1.6 Write report"

    r = h.submit({
        "word_count": 8900,
        "revision_changes": "Deepened theme analysis, added counter-examples, strengthened theoretical framework",
    })
    assert r
    assert r.new_step == "1.7 Report review"
    assert h.step == "1.7 Report review"

    # Now satisfactory - WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_back_to_initial_coding(harness_factory):
    """Student dropout analysis fundamentally flawed: deductive codes missed key inductive patterns. Restart coding."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    # Advance to report review
    r = h.submit({"data_source": "Exit interviews with university dropouts", "participants": 45})
    r = h.submit({"total_codes": 62, "approach": "Deductive only based on Tinto's model"})
    r = h.submit({"candidate_themes": ["Academic unpreparedness", "Social isolation", "Financial hardship"]})
    r = h.submit({"review_outcome": "Themes too aligned with existing theory, missing novel patterns"})
    r = h.submit({"theme_definitions": {"Academic unpreparedness": "Inadequate study skills from secondary education"}})
    r = h.submit({"word_count": 5400, "reviewer_concern": "Feels like confirmation of existing theory rather than discovery"})
    assert r
    assert h.step == "1.7 Report review"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("1.2 Generate initial codes")
    assert r
    assert r.new_step == "1.2 Generate initial codes"
    assert h.step == "1.2 Generate initial codes"
    assert h.status == "running"

    # Redo entire coding phase with inductive approach
    r = h.submit({
        "total_codes": 134,
        "approach": "Inductive, open coding without predefined framework",
        "new_codes_discovered": ["institutional_gaslighting", "imposter_syndrome", "hidden_curriculum", "belonging_debt"],
        "note": "Switching to purely inductive approach revealed patterns Tinto's model cannot capture",
    })
    assert r
    assert r.new_step == "1.3 Search for themes"
    assert h.step == "1.3 Search for themes"


def test_stop_then_resume(harness_factory):
    """Pause teacher wellbeing analysis mid-theme-search for ethics board meeting, resume after."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "data_source": "Diary entries from K-12 teachers during standardized testing season",
        "participants": 18,
        "entries_per_participant": "14 daily entries over 2 weeks",
    })
    assert r
    r = h.submit({
        "total_codes": 89,
        "sample_codes": ["test_anxiety_transfer", "curriculum_narrowing", "performative_compliance", "student_advocacy_tension"],
    })
    assert r
    assert h.step == "1.3 Search for themes"

    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.3 Search for themes"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "1.3 Search for themes"

    r = h.submit({
        "candidate_themes": [
            "The testing industrial complex and teacher deprofessionalization",
            "Emotional labor of maintaining student morale",
            "Subversive pedagogy: teaching beyond the test",
        ],
    })
    assert r
    assert r.new_step == "1.4 Review themes"
    assert h.step == "1.4 Review themes"


def test_skip_a_step(harness_factory):
    """Skip theme search for patient experience study -- themes pre-identified from pilot study last quarter."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "data_source": "Patient experience interviews at Memorial Hospital oncology ward",
        "participants": 30,
        "note": "Extension of Q3 pilot study (n=8) which already identified preliminary themes",
    })
    assert r
    r = h.submit({
        "total_codes": 112,
        "note": "Codes mapped to pilot themes, 23 new codes emerged",
    })
    assert r
    assert h.step == "1.3 Search for themes"

    r = h.skip("Themes already identified from prior work")
    assert r
    assert r.new_step == "1.4 Review themes"
    assert h.step == "1.4 Review themes"
    assert h.status == "running"


def test_complete_then_reset(harness_factory):
    """Finish gig economy worker analysis, reset to begin new study on creator economy burnout."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    r = h.submit({"data_source": "Interviews with Uber/Lyft drivers", "participants": 25})
    r = h.submit({"total_codes": 76, "approach": "Inductive"})
    r = h.submit({"candidate_themes": ["Algorithmic control", "Entrepreneurial myth", "Precarity normalization"]})
    r = h.submit({"review_outcome": "3 themes retained"})
    r = h.submit({"theme_definitions": {"Algorithmic control": "Platform algorithms as invisible managers"}})
    r = h.submit({"word_count": 7800, "target_journal": "Work, Employment and Society"})
    assert r

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Familiarize with data"
    assert h.status == "running"


def test_back(harness_factory):
    """Coding refugee resettlement interviews -- realize coding scheme too narrow, go back to refine."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    r = h.submit({
        "data_source": "Interviews with Syrian refugees resettled in Germany",
        "participants": 16,
        "languages": ["Arabic (translated)", "German"],
    })
    assert r
    assert r.new_step == "1.2 Generate initial codes"
    assert h.step == "1.2 Generate initial codes"

    r = h.submit({
        "total_codes": 54,
        "note": "Realized cultural concepts like 'sumoud' (steadfastness) need emic codes, not just etic",
    })
    assert r
    assert r.new_step == "1.3 Search for themes"
    assert h.step == "1.3 Search for themes"

    r = h.back()
    assert r
    assert r.new_step == "1.2 Generate initial codes"
    assert h.step == "1.2 Generate initial codes"


def test_consecutive_backs(harness_factory):
    """Wavering between theme search and review on climate anxiety study -- back bounces between steps.

    back() finds the most recent different step in history.
    After one back, consecutive backs bounce between the last two steps
    because the back action itself adds to history.
    """
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    r = h.submit({"data_source": "Eco-anxiety journals from Gen Z participants", "participants": 20})
    assert r
    r = h.submit({"total_codes": 67, "sample_codes": ["climate_grief", "solastalgia", "activist_burnout"]})
    assert r
    r = h.submit({"candidate_themes": ["Ecological grief cycle", "Paralysis vs activism", "Intergenerational blame"]})
    assert r
    assert h.step == "1.4 Review themes"

    r = h.back()
    assert r
    assert r.new_step == "1.3 Search for themes"
    assert h.step == "1.3 Search for themes"

    # Second back finds "1.4" as the most recent different step (from transition history)
    r = h.back()
    assert r
    assert r.new_step == "1.4 Review themes"
    assert h.step == "1.4 Review themes"


def test_modify_yaml(harness_factory):
    """Hot-reload YAML to add a member-checking step."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r

    r = h.submit({})
    assert r
    r = h.submit({})
    assert r
    assert h.step == "1.3 Search for themes"

    modified_yaml = """\u540d\u79f0: Thematic Analysis
\u63cf\u8ff0: Modified with member checking

\u6b65\u9aa4:
  - 1.1 Familiarize with data

  - 1.2 Generate initial codes

  - 1.25 Member checking:
      \u4e0b\u4e00\u6b65: 1.3 Search for themes

  - 1.3 Search for themes

  - 1.4 Review themes

  - 1.5 Define and name themes

  - 1.6 Write report

  - 1.7 Report review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "report is satisfactory"
          \u53bb: Done
        - \u5982\u679c: "themes need refinement"
          \u53bb: 1.5 Define and name themes
        - \u53bb: 1.2 Generate initial codes

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("1.25 Member checking")
    assert r
    assert r.new_step == "1.25 Member checking"
    assert h.step == "1.25 Member checking"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "1.3 Search for themes"
    assert h.step == "1.3 Search for themes"


def test_goto(harness_factory):
    """Themes already finalized from workshop -- jump to writing report on healthcare worker resilience."""
    h = harness_factory("p4-thematic-analysis.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Familiarize with data"

    r = h.goto("1.6 Write report")
    assert r
    assert r.new_step == "1.6 Write report"
    assert h.step == "1.6 Write report"
    assert h.status == "running"

    r = h.submit({
        "title": "Resilience Narratives Among Frontline Healthcare Workers: A Thematic Analysis",
        "word_count": 8200,
        "sections": ["Introduction", "Methods", "Findings (4 themes)", "Discussion", "Clinical Implications"],
        "themes_presented": ["Adaptive coping", "Organizational resilience culture", "Post-traumatic growth", "Compassion sustainability"],
    })
    assert r
    assert r.new_step == "1.7 Report review"
    assert h.step == "1.7 Report review"
    assert h.status == "waiting"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_steps(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()

    h.submit({"transcripts": 15})
    data = h.state.data
    assert "1.1 Familiarize with data" in data
    assert data["1.1 Familiarize with data"]["transcripts"] == 15

    h.submit({"codes_count": 42})
    data = h.state.data
    assert "1.2 Generate initial codes" in data
    assert data["1.2 Generate initial codes"]["codes_count"] == 42

    h.submit({"themes_found": 5})
    data = h.state.data
    assert "1.3 Search for themes" in data
    assert data["1.3 Search for themes"]["themes_found"] == 5


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory("p4-thematic-analysis.yaml")
    _advance_to_report_review(h)
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_cross_executor_at_theme_search(harness_factory):
    """Close executor mid-analysis, reopen, state persists."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3
    assert h.step == "1.3 Search for themes"

    h.new_executor()

    assert h.step == "1.3 Search for themes"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "1.4 Review themes"


def test_cross_executor_at_report_review(harness_factory):
    """Close executor at report review wait step, reopen, state persists."""
    h = harness_factory("p4-thematic-analysis.yaml")
    _advance_to_report_review(h)

    h.new_executor()

    assert h.step == "1.7 Report review"
    assert h.status == "waiting"

    # Can continue
    h.approve()
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_node_validates_codes(harness_factory):
    """Validate node rejects bad data, accepts good data at coding step."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Generate initial codes"

    h.register_node(
        "1.2 Generate initial codes",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("codes") else "must include codes list",
        ),
    )

    r = h.submit({"notes": "no codes here"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"codes": ["resilience", "adaptation"]})
    assert r
    assert r.new_step == "1.3 Search for themes"


def test_node_archives_themes(harness_factory):
    """Archive node writes theme data to SQLite table."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3
    h.submit({})  # 1.3 -> 1.4
    h.submit({})  # 1.4 -> 1.5
    assert h.step == "1.5 Define and name themes"

    h.register_node(
        "1.5 Define and name themes",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"theme_name": "string", "definition": "string"}},
            archive={"table": "themes"},
        ),
    )

    r = h.submit({"theme_name": "Resilience", "definition": "Ability to recover"})
    assert r

    rows = h.get_archived_rows("themes")
    assert len(rows) == 1
    assert rows[0]["theme_name"] == "Resilience"


def test_submit_on_waiting_review_fails(harness_factory):
    """Submit while review step is waiting returns failure."""
    h = harness_factory("p4-thematic-analysis.yaml")
    _advance_to_report_review(h)

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({"transcripts": 10})
    h.submit({"codes": 20})
    assert h.step == "1.3 Search for themes"

    h.save_checkpoint("at_theme_search")

    # Continue working
    h.submit({})
    h.submit({})
    assert h.step == "1.5 Define and name themes"

    # Load checkpoint
    restored = h.load_checkpoint("at_theme_search")
    assert restored is not None
    assert restored.current_step == "1.3 Search for themes"
    assert "1.2 Generate initial codes" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Generate initial codes"

    r = h.retry()
    assert r
    assert h.step == "1.2 Generate initial codes"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({})
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p4-thematic-analysis.yaml")
    _advance_to_report_review(h)
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p4-thematic-analysis.yaml")

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Familiarize with data"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    assert h.step == "1.2 Generate initial codes"

    h.register_node(
        "1.2 Generate initial codes",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nGenerate initial codes from data.\n\n## Steps\n1. Read through transcripts\n2. Apply line-by-line coding",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy in status."""
    h = harness_factory("p4-thematic-analysis.yaml")
    h.start()
    assert h.step == "1.1 Familiarize with data"

    h.register_node(
        "1.1 Familiarize with data",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[
                    EditPolicyPattern(glob="transcripts/**", policy="silent"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
