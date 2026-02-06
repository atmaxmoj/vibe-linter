"""Grounded Theory workflow tests (p4-grounded-theory.yaml).

Tests the coding loop with saturation check 2-way branching,
where not-saturated goes back to data collection.
"""
from __future__ import annotations

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---

def _advance_to_coding_loop(h):
    """Start -> submit 1.1 -> arrive at 2.1 Open coding."""
    h.start()
    h.submit({})  # 1.1 -> 2.1 (enters coding loop)
    assert h.step == "2.1 Open coding"


def _do_one_coding_round(h):
    """At 2.1, complete one coding round (2.1 -> 2.2 -> 2.3 -> 2.4)."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({})  # 2.3 -> 2.4
    assert h.step == "2.4 Saturation check"


# ===============================================================
# Existing tests (unchanged)
# ===============================================================

def test_3_rounds_reach_saturation(harness_factory):
    """Study trust formation in remote-first startup teams: 3 rounds of field observation reach theoretical saturation."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1", "r2", "r3"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Collect initial data"
    assert h.status == "running"

    r = h.submit({
        "method": "Ethnographic observation of 4 remote-first startups",
        "data_sources": ["Slack channel archives", "Video standup recordings", "1-on-1 interview transcripts"],
        "participants": 32,
        "observation_period": "3 months",
        "field_notes_pages": 245,
    })
    assert r
    assert r.new_step == "2.1 Open coding"
    assert h.step == "2.1 Open coding"

    open_coding_rounds = [
        {"codes": ["async_trust_signals", "emoji_as_affect", "camera_on_norms", "timezone_empathy", "documentation_as_trust"], "new_codes": 47, "total_incidents": 312},
        {"codes": ["vulnerability_disclosure", "slack_thread_depth", "pair_programming_bonding", "coffee_chat_rituals"], "new_codes": 18, "total_incidents": 198},
        {"codes": ["trust_repair_after_conflict", "onboarding_buddy_system", "async_decision_transparency"], "new_codes": 4, "total_incidents": 89},
    ]
    axial_coding_rounds = [
        {"categories": ["Digital affect display", "Temporal coordination", "Knowledge transparency"], "relationships": 12, "paradigm_model": "Conditions -> Strategies -> Consequences"},
        {"categories": ["Vulnerability cascade", "Ritual maintenance", "Boundary negotiation"], "relationships": 8, "paradigm_model": "Refined causal conditions"},
        {"categories": ["Trust repair mechanisms", "Institutional memory building"], "relationships": 3, "paradigm_model": "Saturating relationships"},
    ]
    selective_coding_rounds = [
        {"core_category_candidate": "Digital trust scaffolding", "storyline_draft": "Remote teams build trust through deliberate digital rituals that scaffold emotional connection"},
        {"core_category_candidate": "Digital trust scaffolding", "storyline_draft": "Refined: Trust in remote teams emerges through layered scaffolding of async signals, temporal empathy, and vulnerability cascades"},
        {"core_category_candidate": "Digital trust scaffolding", "storyline_draft": "Final: The theory of Digital Trust Scaffolding explains how remote teams construct interpersonal trust through three interlocking mechanisms"},
    ]

    # All 3 rounds reach saturation
    for i in range(3):
        assert h.step == "2.1 Open coding"
        r = h.submit(open_coding_rounds[i])
        assert r
        assert r.new_step == "2.2 Axial coding"
        assert h.step == "2.2 Axial coding"
        r = h.submit(axial_coding_rounds[i])
        assert r
        assert r.new_step == "2.3 Selective coding"
        assert h.step == "2.3 Selective coding"
        r = h.submit(selective_coding_rounds[i])
        assert r
        assert r.new_step == "2.4 Saturation check"
        assert h.step == "2.4 Saturation check"

        # Saturation reached -> continue loop
        r = h.submit_goto("2.0 Coding loop")
        assert r
        if i < 2:
            assert h.step == "2.1 Open coding"

    assert h.step == "3.1 Write theory"

    r = h.submit({
        "theory_name": "Digital Trust Scaffolding Theory",
        "core_category": "Digital trust scaffolding",
        "propositions": [
            "Remote teams construct trust through three interlocking mechanisms: digital affect display, temporal coordination, and vulnerability cascades",
            "Trust scaffolding requires intentional ritual maintenance; teams that rely on emergent trust formation experience longer ramp-up periods",
            "Documentation-as-trust serves as institutional memory that reduces trust decay during team member transitions",
        ],
        "theoretical_model": "Three-layer scaffolding model with feedback loops",
        "saturation_evidence": "Round 3 produced only 4 new codes (vs 47 in round 1), no new categories emerged",
    })
    assert r
    assert r.new_step == "3.2 Theory review"
    assert h.step == "3.2 Theory review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    assert h.status == "running"
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_not_saturated_back_to_collection(harness_factory):
    """Patient decision-making study: first coding round reveals major gaps, return to collect more interview data.

    With 1 coding_round, after going back to collection and re-entering
    the loop, the loop counter increments past n and the loop completes.
    """
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "method": "Semi-structured interviews with cancer patients about treatment decisions",
        "participants": 8,
        "note": "Initial purposive sample from oncology clinic",
    })
    assert r

    # Round 1: not saturated -> back to data collection
    r = h.submit({
        "codes": ["information_seeking", "family_consultation", "doctor_trust", "online_research"],
        "new_codes": 28,
        "note": "Many codes around emotional decision-making not captured yet",
    })
    assert r
    r = h.submit({
        "categories": ["Information gatekeeping", "Emotional regulation"],
        "note": "Only 2 categories emerging -- need data from different patient demographics",
    })
    assert r
    r = h.submit({
        "core_category_candidate": "Too early to identify",
        "note": "Insufficient variation -- all participants were early-stage patients",
    })
    assert r
    assert h.step == "2.4 Saturation check"

    r = h.submit_goto("1.1 Collect initial data")
    assert r
    assert r.new_step == "1.1 Collect initial data"
    assert h.step == "1.1 Collect initial data"
    assert h.status == "running"

    # Re-enter from collection with expanded sample
    r = h.submit({
        "method": "Theoretical sampling: added late-stage patients and patients who refused treatment",
        "participants": 14,
        "note": "Expanded to include diverse decision outcomes per theoretical sampling",
    })
    assert r
    assert h.step == "3.1 Write theory"


def test_stop_then_resume(harness_factory):
    """Pause immigrant entrepreneurship coding for conference travel, resume after."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "method": "Life history interviews with immigrant entrepreneurs in Berlin",
        "participants": 20,
        "data_sources": ["Interview transcripts", "Business plan documents", "Social media profiles"],
    })
    assert r
    r = h.submit({
        "codes": ["cultural_capital_transfer", "network_bridging", "institutional_navigation", "identity_negotiation"],
        "new_codes": 56,
    })
    assert r
    assert h.step == "2.2 Axial coding"

    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Axial coding"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Axial coding"

    r = h.submit({
        "categories": ["Transnational resource mobilization", "Legitimacy construction", "Bicultural advantage"],
        "relationships": 7,
    })
    assert r
    assert r.new_step == "2.3 Selective coding"
    assert h.step == "2.3 Selective coding"


def test_complete_then_reset(harness_factory):
    """Finish open-source maintainer burnout theory, reset to study developer onboarding."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({"method": "Interviews with 15 burned-out OSS maintainers", "participants": 15})
    assert r
    r = h.submit({"codes": ["unpaid_labor", "entitlement_demands", "guilt_abandonment"], "new_codes": 38})
    assert r
    r = h.submit({"categories": ["Emotional debt accumulation", "Community obligation spiral"]})
    assert r
    r = h.submit({"core_category_candidate": "Invisible labor extraction"})
    assert r
    r = h.submit_goto("2.0 Coding loop")
    assert r

    assert h.step == "3.1 Write theory"
    r = h.submit({
        "theory_name": "Invisible Labor Extraction in Open Source",
        "propositions": ["Maintainer burnout is driven by asymmetric labor extraction masked by community rhetoric"],
    })
    assert r
    # WAIT+LLM: approve first, then goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Collect initial data"
    assert h.status == "running"


def test_skip_a_round(harness_factory):
    """Skip axial coding in teacher identity study -- relationships already mapped in previous project."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "method": "Classroom observations and teacher reflections on identity formation",
        "participants": 12,
    })
    assert r
    r = h.submit({
        "codes": ["role_conflict", "institutional_identity", "pedagogical_autonomy"],
        "new_codes": 31,
    })
    assert r
    assert h.step == "2.2 Axial coding"

    r = h.skip("Axial coding not needed for this round")
    assert r
    assert r.new_step == "2.3 Selective coding"
    assert h.step == "2.3 Selective coding"
    assert h.status == "running"


def test_goto_write_theory(harness_factory):
    """Coding complete from offline analysis -- jump to writing theory on algorithmic hiring bias."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.goto("3.1 Write theory")
    assert r
    assert r.new_step == "3.1 Write theory"
    assert h.step == "3.1 Write theory"
    assert h.status == "running"

    r = h.submit({
        "theory_name": "Algorithmic Gatekeeping in Hiring",
        "core_category": "Automated exclusion normalization",
        "propositions": [
            "AI hiring tools create invisible barriers that disproportionately exclude non-traditional candidates",
            "Recruiters transfer moral responsibility for exclusion to the algorithm, reducing accountability",
        ],
    })
    assert r
    assert r.new_step == "3.2 Theory review"
    assert h.step == "3.2 Theory review"
    assert h.status == "waiting"


def test_back(harness_factory):
    """Realize open codes for platform cooperativism study need refinement -- go back from axial."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "method": "Participatory observation in platform cooperatives (Stocksy, Up & Go)",
        "participants": 18,
    })
    assert r
    assert r.new_step == "2.1 Open coding"
    assert h.step == "2.1 Open coding"

    r = h.submit({
        "codes": ["democratic_governance", "surplus_distribution", "member_ownership_pride"],
        "new_codes": 42,
        "note": "Need to revisit -- some codes conflate governance with ownership",
    })
    assert r
    assert r.new_step == "2.2 Axial coding"
    assert h.step == "2.2 Axial coding"

    r = h.back()
    assert r
    assert r.new_step == "2.1 Open coding"
    assert h.step == "2.1 Open coding"


def test_modify_yaml(harness_factory):
    """Hot-reload YAML to add memo writing step."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({})
    assert r
    r = h.submit({})
    assert r
    assert h.step == "2.2 Axial coding"

    modified_yaml = """\u540d\u79f0: Grounded Theory
\u63cf\u8ff0: Modified with memo writing

\u6b65\u9aa4:
  - 1.1 Collect initial data

  - 2.0 Coding loop:
      \u904d\u5386: "coding_rounds"
      \u5b50\u6b65\u9aa4:
        - 2.1 Open coding
        - 2.15 Write memos
        - 2.2 Axial coding
        - 2.3 Selective coding
        - 2.4 Saturation check:
            \u4e0b\u4e00\u6b65:
              - \u5982\u679c: "theoretical saturation reached"
                \u53bb: 2.0 Coding loop
              - \u53bb: 1.1 Collect initial data

  - 3.1 Write theory

  - 3.2 Theory review:
      \u7c7b\u578b: wait
      \u4e0b\u4e00\u6b65:
        - \u5982\u679c: "theory is well-grounded"
          \u53bb: Done
        - \u53bb: 2.0 Coding loop

  - Done:
      \u7c7b\u578b: terminate
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("2.15 Write memos")
    assert r
    assert r.new_step == "2.15 Write memos"
    assert h.step == "2.15 Write memos"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "2.2 Axial coding"
    assert h.step == "2.2 Axial coding"


def test_wrong_direction_reset(harness_factory):
    """Studying gig economy solidarity -- realize research question is wrong, scrap and restart with new focus."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1", "r2"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "method": "Interviews with food delivery couriers about workplace solidarity",
        "participants": 10,
        "note": "Started with solidarity but data keeps pointing to surveillance instead",
    })
    assert r
    r = h.submit({
        "codes": ["algorithmic_surveillance", "GPS_tracking_anxiety", "rating_fear", "customer_surveillance"],
        "note": "95% of codes relate to surveillance, not solidarity -- wrong research question",
    })
    assert r
    r = h.submit({"categories": ["Panoptic platform control"], "note": "This is a surveillance study, not solidarity"})
    assert r
    r = h.submit({"core_category_candidate": "Algorithmic panopticon", "note": "Completely different direction"})
    assert r
    assert h.step == "2.4 Saturation check"

    # Wrong direction, reset everything
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Collect initial data"
    assert h.status == "running"


def test_modify_yaml_delete_current_step_stop_reset(harness_factory):
    """Modify YAML to remove current step, stop, and reset."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    r = h.start()
    assert r

    r = h.submit({})
    assert r
    r = h.submit({})
    assert r
    r = h.submit({})
    assert r
    assert h.step == "2.3 Selective coding"

    # Stop before modifying
    r = h.stop()
    assert r
    assert h.status == "stopped"

    # Reset to clean state
    h.reset()
    assert h.state is None

    # Start fresh
    r = h.start()
    assert r
    assert h.step == "1.1 Collect initial data"
    assert h.status == "running"


# ===============================================================
# New multi-dimension tests
# ===============================================================

def test_data_accumulates_through_phases(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()

    h.submit({"interviews": 12, "source": "field notes"})
    data = h.state.data
    assert "1.1 Collect initial data" in data
    assert data["1.1 Collect initial data"]["interviews"] == 12


def test_data_accumulates_in_loop(harness_factory):
    """Data submitted during coding rounds persists."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    _advance_to_coding_loop(h)

    h.submit({"codes": ["resilience", "adaptation"]})
    data = h.state.data
    assert "2.1 Open coding" in data
    assert data["2.1 Open coding"]["codes"] == ["resilience", "adaptation"]


def test_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected actions."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    _advance_to_coding_loop(h)
    _do_one_coding_round(h)
    h.submit_goto("2.0 Coding loop")  # loop exhausted -> 3.1
    assert h.step == "3.1 Write theory"
    h.submit({})  # 3.1 -> 3.2
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


def test_cross_executor_in_coding_loop(harness_factory):
    """Close executor mid-coding, reopen, loop_state persists."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1", "r2"]},
    )
    _advance_to_coding_loop(h)

    h.submit({})  # 2.1 -> 2.2
    assert h.step == "2.2 Axial coding"

    h.new_executor()

    assert h.step == "2.2 Axial coding"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Coding loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_theory_review(harness_factory):
    """Close executor at theory review wait step, reopen, state persists."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    _advance_to_coding_loop(h)
    _do_one_coding_round(h)
    h.submit_goto("2.0 Coding loop")
    assert h.step == "3.1 Write theory"
    h.submit({})
    assert h.step == "3.2 Theory review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "3.2 Theory review"
    assert h.status == "waiting"


def test_node_validates_open_coding(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    _advance_to_coding_loop(h)

    h.register_node(
        "2.1 Open coding",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("codes") else "must include codes list",
        ),
    )

    r = h.submit({"notes": "some notes"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"codes": ["trust", "agency"]})
    assert r
    assert r.new_step == "2.2 Axial coding"


def test_node_archives_saturation_data(harness_factory):
    """Archive node writes saturation check data to SQLite table."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1", "r2"]},
    )
    _advance_to_coding_loop(h)

    h.register_node(
        "2.4 Saturation check",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"round": "string", "saturated": "string"}},
            archive={"table": "saturation_checks"},
        ),
    )

    # Round 1
    _do_one_coding_round(h)
    h.submit({"round": "r1", "saturated": "no"})
    # submit advances, but we need to check archive
    # The submit_goto was not needed since the archive happens on submit at 2.4

    rows = h.get_archived_rows("saturation_checks")
    assert len(rows) >= 1
    assert rows[0]["round"] == "r1"


def test_submit_on_waiting_review_fails(harness_factory):
    """Submit while theory review is waiting returns failure."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()
    h.goto("3.1 Write theory")
    h.submit({})
    assert h.step == "3.2 Theory review"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    _advance_to_coding_loop(h)

    h.save_checkpoint("at_open_coding")

    _do_one_coding_round(h)
    assert h.step == "2.4 Saturation check"

    restored = h.load_checkpoint("at_open_coding")
    assert restored is not None
    assert restored.current_step == "2.1 Open coding"


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()
    assert h.step == "1.1 Collect initial data"

    r = h.retry()
    assert r
    assert h.step == "1.1 Collect initial data"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()
    h.goto("3.2 Theory review")
    h.submit_goto("Done")
    assert h.step == "Done"
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Collect initial data"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    _advance_to_coding_loop(h)
    assert h.step == "2.1 Open coding"

    h.register_node(
        "2.1 Open coding",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nPerform open coding on the data.\n\n## Steps\n1. Read through data\n2. Generate initial codes",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy in status."""
    h = harness_factory(
        "p4-grounded-theory.yaml",
        loop_data={"coding_rounds": ["r1"]},
    )
    h.start()
    assert h.step == "1.1 Collect initial data"

    h.register_node(
        "1.1 Collect initial data",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[
                    EditPolicyPattern(glob="data/**", policy="silent"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
