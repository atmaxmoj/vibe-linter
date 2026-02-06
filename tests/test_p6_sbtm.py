"""Test scenarios for SBTM Testing workflow (p6-sbtm.yaml).

Tests the Session-Based Test Management workflow including:
- Planning phase (create charters)
- Session loop with need-more-sessions 2-way branching
- Debrief wait step with 2-way branching
- Report phase
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
    """Start -> submit charter -> arrive at 2.1 Execute test session."""
    h.start()
    h.submit({})  # 1.1 -> 2.1 (loop entry)
    assert h.step == "2.1 Execute test session"
    assert h.status == "running"


def _complete_one_session(h):
    """Complete one session: execute -> record -> need-more -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Session loop")  # 2.3 -> loop header


def _walk_to_debrief(h):
    """Walk to 3.2 Debrief (waiting) after completing all sessions."""
    _walk_to_session_loop(h)
    _complete_one_session(h)
    # After loop exhausted -> 3.1 -> 3.2
    if h.step == "2.1 Execute test session":
        # still in loop, need to exhaust
        _complete_one_session(h)
    if h.step == "3.1 Compile session results":
        h.submit({})
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"


# ================================================================
# Scenario 1: Three sessions complete
# ================================================================


def test_three_sessions_complete(harness_factory):
    """Test a hotel booking platform: 3 SBTM sessions covering search, booking, and cancellation."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["search_session", "booking_session", "cancellation_session"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Create initial charters"
    assert h.status == "running"

    r = h.submit({
        "charters": [
            "Session 1: Explore hotel search with filters (location, dates, price, rating)",
            "Session 2: Explore booking flow end-to-end (guest info, payment, confirmation)",
            "Session 3: Explore cancellation and refund policies across booking types",
        ],
        "target": "StayEasy Hotel Booking Platform v5.0",
    })
    assert r
    assert r.new_step == "2.1 Execute test session"
    assert h.step == "2.1 Execute test session"

    session_data = [
        {
            "execute": {"charter": "Hotel search filters", "duration_min": 45, "tester": "Alice Chen"},
            "findings": {"bugs_found": 2, "notes": "Date picker allows check-out before check-in; price filter max resets on page refresh"},
        },
        {
            "execute": {"charter": "Booking flow E2E", "duration_min": 50, "tester": "Alice Chen"},
            "findings": {"bugs_found": 1, "notes": "Guest name field accepts special chars but confirmation email garbles them"},
        },
        {
            "execute": {"charter": "Cancellation and refunds", "duration_min": 40, "tester": "Alice Chen"},
            "findings": {"bugs_found": 0, "notes": "Free cancellation policy applied correctly, refund timeline displayed accurately"},
        },
    ]

    for i in range(3):
        r = h.submit(session_data[i]["execute"])
        assert r
        assert r.new_step == "2.2 Record findings"
        assert h.step == "2.2 Record findings"

        r = h.submit(session_data[i]["findings"])
        assert r
        assert r.new_step == "2.3 Need more sessions?"
        assert h.step == "2.3 Need more sessions?"

        # Coverage sufficient, continue to next session
        r = h.submit_goto("2.0 Session loop")
        assert r
        if i < 2:
            assert r.new_step == "2.1 Execute test session"
            assert h.step == "2.1 Execute test session"

    assert h.step == "3.1 Compile session results"

    r = h.submit({
        "total_sessions": 3,
        "total_bugs": 3,
        "coverage": "Search, Booking, Cancellation all covered",
        "total_time_min": 135,
    })
    assert r
    assert r.new_step == "3.2 Debrief"
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    # WAIT+LLM: approve first (sets running, submit returns "needs judgment")
    r = h.approve()
    assert r
    assert h.step == "3.2 Debrief"
    assert h.status == "running"

    # Testing is sufficient -- now submit_goto to choose path
    r = h.submit_goto("3.3 Write test report")
    assert r
    assert r.new_step == "3.3 Write test report"
    assert h.step == "3.3 Write test report"

    r = h.submit({
        "report_title": "SBTM Report: StayEasy v5.0",
        "verdict": "3 bugs found (2 medium, 1 low). Recommend fixing before release.",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_three_sessions_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({"charters": "test login, test signup"})
    assert h.state.data["1.1 Create initial charters"]["charters"] == "test login, test signup"

    h.submit({"session_result": "found 2 bugs"})
    assert h.state.data["2.1 Execute test session"]["session_result"] == "found 2 bugs"

    h.submit({"findings": "bug #123, bug #456"})
    assert h.state.data["2.2 Record findings"]["findings"] == "bug #123, bug #456"


def test_three_sessions_history_audit(harness_factory):
    """History contains start, submit, transition, and terminate actions."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Session loop")
    h.submit({})
    h.approve()
    h.submit_goto("3.3 Write test report")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_three_sessions_cross_executor_in_loop(harness_factory):
    """Close executor mid-loop, reopen, state persists."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1", "s2", "s3"]},
    )
    _walk_to_session_loop(h)
    h.submit({})
    assert h.step == "2.2 Record findings"

    h.new_executor()

    assert h.step == "2.2 Record findings"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Session loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_three_sessions_node_validates(harness_factory):
    """Validate node rejects bad data at session execution step."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    _walk_to_session_loop(h)

    h.register_node(
        "2.1 Execute test session",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("session_id") else "must include session_id",
        ),
    )

    r = h.submit({"notes": "no id"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"session_id": "s1"})
    assert r
    assert r.new_step == "2.2 Record findings"


def test_three_sessions_node_archives(harness_factory):
    """Archive node writes session results to SQLite table."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1", "s2"]},
    )
    _walk_to_session_loop(h)

    h.register_node(
        "2.2 Record findings",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"bug_count": "string", "session": "string"}},
            archive={"table": "session_findings"},
        ),
    )

    h.submit({})
    h.submit({"bug_count": "3", "session": "s1"})
    h.submit_goto("2.0 Session loop")
    h.submit({})
    h.submit({"bug_count": "1", "session": "s2"})

    rows = h.get_archived_rows("session_findings")
    assert len(rows) == 2
    assert rows[0]["bug_count"] == "3"
    assert rows[1]["session"] == "s2"


# ================================================================
# Scenario 2: Need more sessions continue
# ================================================================


def test_need_more_sessions_continue(harness_factory):
    """Testing a payment API: single session reveals gaps in error handling coverage, need more sessions."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["error_handling_session"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Explore payment API error responses and edge cases"],
    })
    assert r
    r = h.submit({
        "charter": "Payment API error handling",
        "duration_min": 40,
        "findings": "Tested timeout, invalid card, network failure -- only covered 40% of error codes",
    })
    assert r
    r = h.submit({
        "findings": "Missing coverage for 3DS authentication failures, currency conversion errors",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r

    assert h.step == "3.1 Compile session results"

    r = h.submit({
        "coverage_pct": 40,
        "verdict": "Insufficient -- need sessions for 3DS and currency edge cases",
    })
    assert r
    assert r.new_step == "3.2 Debrief"
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Debrief"
    assert h.status == "running"

    # Need more sessions - go back to session loop
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert r.new_step == "2.1 Execute test session"
    assert h.step == "2.1 Execute test session"
    assert h.status == "running"


# ================================================================
# Scenario 3: First round sufficient exit early
# ================================================================


def test_first_round_sufficient_exit_early(harness_factory):
    """Testing a simple landing page: first session covers everything, skip remaining sessions."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["landing_page", "contact_form", "newsletter_signup"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": [
            "Landing page layout and responsiveness",
            "Contact form validation",
            "Newsletter signup flow",
        ],
    })
    assert r

    # Complete first session -- landing page is trivial, covers contact form and newsletter too
    r = h.submit({
        "charter": "Landing page layout and responsiveness",
        "duration_min": 20,
        "note": "Page is simple enough that I tested all three features in one session",
    })
    assert r
    r = h.submit({
        "findings": "All working correctly. Contact form validates email, newsletter saves to DB.",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert h.step == "2.1 Execute test session"

    # Jump directly to compile results -- one session was enough
    r = h.goto("3.1 Compile session results")
    assert r
    assert r.new_step == "3.1 Compile session results"
    assert h.step == "3.1 Compile session results"

    r = h.submit({
        "total_sessions": 1,
        "total_bugs": 0,
        "note": "Simple page, full coverage in single session",
    })
    assert r
    assert r.new_step == "3.2 Debrief"
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Debrief"
    assert h.status == "running"

    r = h.submit_goto("3.3 Write test report")
    assert r
    assert r.new_step == "3.3 Write test report"
    assert h.step == "3.3 Write test report"

    r = h.submit({
        "report": "Landing page SBTM report: PASS, 0 bugs, full coverage",
    })
    assert r
    assert h.status == "done"


# ================================================================
# Scenario 4: Debrief needs more, back to loop
# ================================================================


def test_debrief_needs_more_back_to_loop(harness_factory):
    """Testing an inventory management system: debrief reveals untested barcode scanning, run another session."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["stock_management"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Explore stock management: add, remove, transfer inventory"],
    })
    assert r
    r = h.submit({
        "charter": "Stock management CRUD operations",
        "duration_min": 45,
    })
    assert r
    r = h.submit({
        "findings": "CRUD works but barcode scanning integration was not tested",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r

    r = h.submit({
        "summary": "Stock CRUD covered, barcode scanning gap identified",
    })
    assert r
    assert r.new_step == "3.2 Debrief"
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Debrief"
    assert h.status == "running"

    # Not sufficient -- need to test barcode scanning
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert r.new_step == "2.1 Execute test session"
    assert h.step == "2.1 Execute test session"

    # Second session: barcode scanning
    r = h.submit({
        "charter": "Barcode scanning integration",
        "duration_min": 30,
        "device": "Zebra TC21 handheld scanner",
    })
    assert r
    r = h.submit({
        "findings": "Barcode scanning works for UPC-A and EAN-13, QR codes also supported",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r

    r = h.submit({
        "summary": "Full coverage: stock CRUD + barcode scanning",
        "total_sessions": 2,
    })
    assert r
    assert r.new_step == "3.2 Debrief"
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Debrief"
    assert h.status == "running"

    # Now sufficient
    r = h.submit_goto("3.3 Write test report")
    assert r
    assert r.new_step == "3.3 Write test report"
    assert h.step == "3.3 Write test report"


# ================================================================
# Scenario 5: Stop then resume
# ================================================================


def test_stop_then_resume(harness_factory):
    """Testing a CI/CD pipeline dashboard: environment goes down mid-session, resume when it's back."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["pipeline_monitoring", "deployment_history"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Pipeline monitoring dashboard", "Deployment history and rollback"],
    })
    assert r
    r = h.submit({
        "charter": "Pipeline monitoring",
        "duration_min": 30,
        "note": "Staging environment went down mid-session",
    })
    assert r
    assert h.step == "2.2 Record findings"

    # Environment is down -- stop the session
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Record findings"

    # Environment restored -- resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Record findings"

    r = h.submit({
        "findings": "Pipeline status badges update in real-time, build logs stream correctly",
    })
    assert r
    assert r.new_step == "2.3 Need more sessions?"
    assert h.step == "2.3 Need more sessions?"


# ================================================================
# Scenario 6: Skip session
# ================================================================


def test_skip_session(harness_factory):
    """Testing a notification service: skip first session (already tested via API), run second normally."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["email_notifications", "push_notifications"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Email notification delivery", "Push notification delivery"],
    })
    assert r
    assert h.step == "2.1 Execute test session"

    # Skip email session -- already tested thoroughly via API tests last sprint
    r = h.skip("Email notifications fully covered by automated API tests from Sprint 12")
    assert r
    assert h.step == "2.2 Record findings"

    r = h.submit({
        "findings": "Skipped -- covered by existing automated suite (47 tests, all passing)",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert h.step == "2.1 Execute test session"

    # Complete push notification session normally
    r = h.submit({
        "charter": "Push notification delivery",
        "duration_min": 35,
        "devices": "iOS 17, Android 14, web (Chrome, Firefox)",
    })
    assert r
    r = h.submit({
        "findings": "Push works on all platforms, badge count updates correctly",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    assert h.step == "3.1 Compile session results"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish SBTM for v2.0 release, reset to begin fresh testing cycle for v2.1."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["regression_session"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["v2.0 regression: verify all P1 bug fixes from last sprint"],
    })
    assert r
    r = h.submit({
        "charter": "Regression session",
        "duration_min": 60,
        "bugs_verified": ["BUG-201", "BUG-215", "BUG-220"],
    })
    assert r
    r = h.submit({
        "findings": "All 3 P1 bugs verified fixed, no regressions found",
    })
    assert r
    r = h.submit_goto("2.0 Session loop")
    assert r
    r = h.submit({
        "summary": "v2.0 regression complete, all fixes verified",
    })
    assert r
    # 3.2 Debrief is WAIT+LLM: approve first, then submit_goto
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"
    r = h.approve()
    assert r
    r = h.submit_goto("3.3 Write test report")
    assert r
    r = h.submit({
        "report": "v2.0 Regression SBTM Report: PASS, ready for release",
    })
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for v2.1 testing cycle
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Create initial charters"
    assert h.status == "running"


# ================================================================
# Scenario 8: Empty session list
# ================================================================


def test_empty_session_list(harness_factory):
    """Charters created but no sessions scheduled yet -- loop exits immediately."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": []},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Placeholder -- sessions to be scheduled after sprint planning"],
    })
    assert r

    # Loop should exit immediately -- no sessions defined yet
    assert h.step == "3.1 Compile session results"
    assert h.status == "running"


# ================================================================
# Scenario 9: Back
# ================================================================


def test_back(harness_factory):
    """Testing a document editor: recorded findings prematurely, go back to continue executing."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["collaborative_editing"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Explore real-time collaborative editing in DocFlow"],
    })
    assert r
    assert h.step == "2.1 Execute test session"

    r = h.submit({
        "charter": "Collaborative editing",
        "duration_min": 30,
        "note": "Testing with 3 concurrent users",
    })
    assert r
    assert h.step == "2.2 Record findings"

    # Realized we forgot to test conflict resolution -- go back
    r = h.back()
    assert r
    assert h.step == "2.1 Execute test session"

    r = h.submit({
        "charter": "Collaborative editing + conflict resolution",
        "duration_min": 45,
        "additional_test": "Two users editing same paragraph simultaneously",
    })
    assert r
    assert h.step == "2.2 Record findings"


# ================================================================
# Scenario 10: Modify YAML
# ================================================================


def test_modify_yaml_add_session(harness_factory):
    """Testing an e-commerce search feature: mid-flow, add a peer review step after recording findings."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["search_relevance"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charters": ["Explore search relevance and autocomplete on ShopMart"],
    })
    assert r
    r = h.submit({
        "charter": "Search relevance for product queries",
        "duration_min": 35,
    })
    assert r
    assert h.step == "2.2 Record findings"

    modified_yaml = """name: SBTM Testing Modified
steps:
  - 1.1 Create initial charters

  - 2.0 Session loop:
      iterate: "sessions"
      children:
        - 2.1 Execute test session
        - 2.2 Record findings
        - 2.2.5 Peer review findings
        - 2.3 Need more sessions?:
            next:
              - if: "coverage is sufficient, no more sessions needed"
                go: 2.0 Session loop
              - go: 2.0 Session loop

  - 3.1 Compile session results

  - 3.2 Debrief:
      type: wait
      next:
        - if: "testing is sufficient"
          go: 3.3 Write test report
        - go: 2.0 Session loop

  - 3.3 Write test report

  - Done:
      type: terminate
"""

    h.reload_yaml(modified_yaml)

    r = h.submit({
        "findings": "Misspelled queries return no results; autocomplete does not suggest corrections",
    })
    assert r
    assert r.new_step == "2.2.5 Peer review findings"
    assert h.step == "2.2.5 Peer review findings"

    r = h.submit({
        "reviewer": "David Kim",
        "review_notes": "Confirmed: typo tolerance is missing, autocomplete dictionary needs expansion",
    })
    assert r
    assert r.new_step == "2.3 Need more sessions?"
    assert h.step == "2.3 Need more sessions?"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p6-sbtm.yaml",
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
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.goto("3.3 Write test report")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting returns failure."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Session loop")
    h.submit({})
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p6-sbtm.yaml",
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
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.submit({"charters": "test login"})

    h.save_checkpoint("at_session")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Session loop")
    assert h.step == "3.1 Compile session results"

    restored = h.load_checkpoint("at_session")
    assert restored is not None
    assert restored.current_step == "2.1 Execute test session"
    assert "1.1 Create initial charters" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    assert h.step == "1.1 Create initial charters"

    r = h.retry()
    assert r
    assert h.step == "1.1 Create initial charters"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Create initial charters"


def test_cross_executor_at_debrief(harness_factory):
    """Close executor at debrief wait step, reopen, continue."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    _walk_to_session_loop(h)
    _complete_one_session(h)
    assert h.step == "3.1 Compile session results"
    h.submit({})
    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "3.2 Debrief"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.status == "running"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.goto("3.3 Write test report")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1", "s2", "s3"]},
    )
    _walk_to_session_loop(h)

    loop_info = h.state.loop_state["2.0 Session loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_session(h)

    loop_info = h.state.loop_state["2.0 Session loop"]
    assert loop_info["i"] == 1


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.register_node(
        "1.1 Create initial charters",
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
        "p6-sbtm.yaml",
        loop_data={"sessions": ["s1"]},
    )
    h.start()
    h.register_node(
        "1.1 Create initial charters",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
