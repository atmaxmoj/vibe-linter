"""Test scenarios for Exploratory Testing workflow (p6-exploratory.yaml).

Tests the Exploratory Testing workflow including:
- Setup phase (charter, time box)
- Explore loop with found-issue 2-way branching
- Deep dive path and log findings
- Summary phase
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


def _walk_to_explore(h):
    """Start -> submit setup steps -> arrive at 2.1 Explore area."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Explore area"
    assert h.status == "running"


def _complete_one_area_no_issue(h):
    """Complete one area with no issue found."""
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.0 Explore loop")  # no issue -> loop header


def _complete_one_area_deep_dive(h):
    """Complete one area with deep dive."""
    h.submit({})  # 2.1 -> 2.2
    h.submit_goto("2.3 Deep dive")  # found issue -> deep dive
    h.submit({})  # 2.3 -> 2.4
    h.submit({})  # 2.4 -> back to loop (2.1 next iter or exit)


# ================================================================
# Scenario 1: Full walkthrough (5 areas, no issues)
# ================================================================


def test_explore_5_areas(harness_factory):
    """Explore a mobile banking app: test 5 areas for usability and correctness."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["login_flow", "account_dashboard", "transfer_funds", "bill_pay", "settings"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define exploration charter"
    assert h.status == "running"

    r = h.submit({
        "charter": "Explore the mobile banking app for usability issues and edge cases",
        "target_app": "FinBank Mobile v3.2",
        "focus_areas": "authentication, money movement, account management",
    })
    assert r
    assert r.new_step == "1.2 Set time box"
    assert h.step == "1.2 Set time box"
    assert h.status == "running"

    r = h.submit({
        "duration": "90 minutes",
        "time_per_area": "15-20 minutes each",
        "note": "Use real device (iPhone 14) and Android emulator in parallel",
    })
    assert r
    assert r.new_step == "2.1 Explore area"
    assert h.step == "2.1 Explore area"

    area_notes = [
        {"area": "login_flow", "observations": "Biometric login smooth, password reset flow clear, no issues with 2FA"},
        {"area": "account_dashboard", "observations": "Balance loads in <1s, transaction list scrolls well, no stale data"},
        {"area": "transfer_funds", "observations": "Internal transfers instant, external wire form validates IBAN correctly"},
        {"area": "bill_pay", "observations": "Saved payees load correctly, scheduled payments calendar works, no duplicates"},
        {"area": "settings", "observations": "Notification preferences save correctly, PIN change flow works, language switch OK"},
    ]

    for i in range(5):
        r = h.submit(area_notes[i])
        assert r
        assert r.new_step == "2.2 Found issue?"
        assert h.step == "2.2 Found issue?"

        # No issue found, continue to next area
        r = h.submit_goto("2.0 Explore loop")
        assert r
        if i < 4:
            assert r.new_step == "2.1 Explore area"
            assert h.step == "2.1 Explore area"

    assert h.step == "3.1 Summarize findings"
    assert h.status == "running"

    r = h.submit({
        "total_areas_explored": 5,
        "issues_found": 0,
        "overall_quality": "App is stable and polished across all tested areas",
        "recommendation": "Ready for release, no blockers found",
    })
    assert r
    assert r.new_step == "3.2 Write exploration report"
    assert h.step == "3.2 Write exploration report"

    r = h.submit({
        "report_title": "Exploratory Testing Report: FinBank Mobile v3.2",
        "verdict": "PASS - All 5 areas explored with no issues found",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_explore_5_areas_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.submit({"charter": "test login flow"})
    assert h.state.data["1.1 Define exploration charter"]["charter"] == "test login flow"

    h.submit({"time_box": "30 min"})
    assert h.state.data["1.2 Set time box"]["time_box"] == "30 min"

    h.submit({"area_notes": "found slow query"})
    assert h.state.data["2.1 Explore area"]["area_notes"] == "found slow query"


def test_explore_5_areas_history_audit(harness_factory):
    """History contains start, submit, and transition actions."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Explore loop")
    h.submit({})
    h.submit({})

    assert h.status == "done"
    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_explore_5_areas_cross_executor_in_loop(harness_factory):
    """Close executor mid-loop, reopen, state persists."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1", "a2", "a3"]},
    )
    _walk_to_explore(h)
    h.submit({})
    assert h.step == "2.2 Found issue?"

    h.new_executor()

    assert h.step == "2.2 Found issue?"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Explore loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_explore_5_areas_node_validates(harness_factory):
    """Validate node rejects bad data at explore step."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    _walk_to_explore(h)

    h.register_node(
        "2.1 Explore area",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("area_name") else "must include area_name",
        ),
    )

    r = h.submit({"notes": "forgot area name"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"area_name": "login page"})
    assert r
    assert r.new_step == "2.2 Found issue?"


def test_explore_5_areas_node_archives(harness_factory):
    """Archive node writes findings to SQLite table."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1", "a2"]},
    )
    _walk_to_explore(h)

    h.register_node(
        "2.1 Explore area",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"area_name": "string", "severity": "string"}},
            archive={"table": "exploration_findings"},
        ),
    )

    h.submit({"area_name": "login", "severity": "low"})
    h.submit_goto("2.0 Explore loop")
    h.submit({"area_name": "dashboard", "severity": "high"})

    rows = h.get_archived_rows("exploration_findings")
    assert len(rows) == 2
    assert rows[0]["area_name"] == "login"
    assert rows[1]["area_name"] == "dashboard"


# ================================================================
# Scenario 2: Found issue, deep dive
# ================================================================


def test_found_issue_deep_dive(harness_factory):
    """Testing an e-commerce checkout: found a race condition in inventory, deep dive to investigate."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["shopping_cart", "payment_gateway"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define exploration charter"

    r = h.submit({
        "charter": "Explore checkout flow for concurrency and payment edge cases",
        "target": "ShopNow e-commerce platform v2.1",
    })
    assert r
    r = h.submit({
        "duration": "60 minutes",
        "tools": "Browser DevTools, Burp Suite for intercepting requests",
    })
    assert r
    assert h.step == "2.1 Explore area"

    # Area 1: Shopping cart -- found a race condition
    r = h.submit({
        "area": "shopping_cart",
        "actions": "Added same item from two tabs simultaneously",
        "observation": "Cart shows duplicate items with wrong quantity totals",
    })
    assert r
    assert r.new_step == "2.2 Found issue?"
    assert h.step == "2.2 Found issue?"

    r = h.submit_goto("2.3 Deep dive")
    assert r
    assert r.new_step == "2.3 Deep dive"
    assert h.step == "2.3 Deep dive"

    r = h.submit({
        "investigation": "Race condition in cart API: no optimistic locking on cart_items table",
        "steps_to_reproduce": "1. Open product page in 2 tabs, 2. Click Add to Cart simultaneously, 3. Cart shows qty=2 but DB has 2 separate rows",
        "root_cause": "Missing unique constraint on (cart_id, product_id), no atomic upsert",
        "severity": "high",
    })
    assert r
    assert r.new_step == "2.4 Log findings"
    assert h.step == "2.4 Log findings"

    r = h.submit({
        "bug_id": "SHOP-1847",
        "title": "Race condition: duplicate cart items when adding from multiple tabs",
        "priority": "P1",
        "assigned_to": "backend-team",
    })
    assert r
    assert r.new_step == "2.1 Explore area"
    assert h.step == "2.1 Explore area"

    # Area 2: Payment gateway -- no issues
    r = h.submit({
        "area": "payment_gateway",
        "actions": "Tested Visa, Mastercard, expired card, insufficient funds",
        "observation": "All payment flows handled correctly with proper error messages",
    })
    assert r
    r = h.submit_goto("2.0 Explore loop")
    assert r

    assert h.step == "3.1 Summarize findings"


def test_deep_dive_data_accumulates(harness_factory):
    """Data submitted during deep dive persists."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    _walk_to_explore(h)
    h.submit({})
    h.submit_goto("2.3 Deep dive")
    h.submit({"finding": "SQL injection vulnerability"})
    assert h.state.data["2.3 Deep dive"]["finding"] == "SQL injection vulnerability"

    h.submit({"log": "critical finding logged"})
    assert h.state.data["2.4 Log findings"]["log"] == "critical finding logged"


def test_deep_dive_cross_executor(harness_factory):
    """Close executor during deep dive, reopen, continue."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    _walk_to_explore(h)
    h.submit({})
    h.submit_goto("2.3 Deep dive")
    assert h.step == "2.3 Deep dive"

    h.new_executor()

    assert h.step == "2.3 Deep dive"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "2.4 Log findings"


# ================================================================
# Scenario 3: No issue continue
# ================================================================


def test_no_issue_continue(harness_factory):
    """Explore the user profile page of a social media app: everything looks fine, move on."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["user_profile"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore user profile editing and display on SocialConnect",
    })
    assert r
    r = h.submit({"duration": "20 minutes"})
    assert r
    assert h.step == "2.1 Explore area"

    r = h.submit({
        "area": "user_profile",
        "actions": "Edited bio, changed avatar, toggled privacy settings",
        "observation": "All changes saved and reflected immediately, no lag or errors",
    })
    assert r
    assert r.new_step == "2.2 Found issue?"
    assert h.step == "2.2 Found issue?"

    r = h.submit_goto("2.0 Explore loop")
    assert r
    assert h.step == "3.1 Summarize findings"
    assert h.status == "running"


# ================================================================
# Scenario 4: Skip to end loop
# ================================================================


def test_skip_to_end_loop(harness_factory):
    """Testing a healthcare portal: first area clean, skip remaining due to time pressure."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["patient_records", "appointment_booking", "lab_results"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore MedPortal patient-facing features before compliance audit",
    })
    assert r
    r = h.submit({"duration": "45 minutes", "note": "Audit deadline approaching"})
    assert r

    # Complete first area: patient records look fine
    r = h.submit({
        "area": "patient_records",
        "observation": "Records load correctly, HIPAA fields properly masked",
    })
    assert r
    r = h.submit_goto("2.0 Explore loop")
    assert r
    assert h.step == "2.1 Explore area"

    # Skip remaining areas -- audit deadline means we need the report now
    r = h.goto("3.1 Summarize findings")
    assert r
    assert r.new_step == "3.1 Summarize findings"
    assert h.step == "3.1 Summarize findings"
    assert h.status == "running"


# ================================================================
# Scenario 5: Need formal testing, stop
# ================================================================


def test_need_formal_testing_stop(harness_factory):
    """Exploring a financial trading platform: found potential data integrity issue, need formal regression testing."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["order_execution", "portfolio_view"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore TradePro order execution and portfolio display",
    })
    assert r
    r = h.submit({"duration": "60 minutes"})
    assert r
    assert h.step == "2.1 Explore area"

    r = h.submit({
        "area": "order_execution",
        "observation": "Noticed price discrepancy between order preview and execution confirmation -- possible stale price cache",
        "severity_hint": "This could cause financial loss, need formal regression suite",
    })
    assert r
    assert h.step == "2.2 Found issue?"

    # Found serious issues: stop exploratory and switch to formal risk-based testing
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Found issue?"


# ================================================================
# Scenario 6: Stop then resume
# ================================================================


def test_stop_then_resume(harness_factory):
    """Testing a ride-sharing app: stop for lunch break, resume afternoon session."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["ride_booking", "driver_matching"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore RideNow app ride booking and driver matching flows",
    })
    assert r
    r = h.submit({"duration": "2 hours with lunch break"})
    assert r
    assert h.step == "2.1 Explore area"

    # Lunch break -- stop the session
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.1 Explore area"

    # Back from lunch -- resume exploring
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.1 Explore area"

    # Continue from where we left off
    r = h.submit({
        "area": "ride_booking",
        "actions": "Booked rides to various destinations, tested surge pricing display",
        "observation": "Surge pricing multiplier not shown until confirmation step",
    })
    assert r
    assert r.new_step == "2.2 Found issue?"
    assert h.step == "2.2 Found issue?"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish exploring a CRM tool, reset to begin a fresh session on the mobile version."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["contact_management"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore SalesCRM desktop contact management features",
    })
    assert r
    r = h.submit({"duration": "30 minutes"})
    assert r
    r = h.submit({
        "area": "contact_management",
        "observation": "Contact merge works, dedup detection accurate, export to CSV clean",
    })
    assert r
    r = h.submit_goto("2.0 Explore loop")
    assert r
    r = h.submit({
        "summary": "Desktop CRM contact management is solid, no issues",
    })
    assert r
    r = h.submit({
        "report": "CRM Desktop v4.0 Exploratory Report: PASS",
    })
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset to start a fresh session for the mobile version
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define exploration charter"
    assert h.status == "running"


# ================================================================
# Scenario 8: Empty area list
# ================================================================


def test_empty_area_list(harness_factory):
    """Charter defined but no areas to explore yet -- loop exits immediately to summary."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": []},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore new analytics dashboard -- areas TBD after stakeholder meeting",
    })
    assert r
    r = h.submit({"duration": "TBD", "note": "Waiting for area list from product team"})
    assert r

    # Loop should exit immediately -- no areas defined
    assert h.step == "3.1 Summarize findings"
    assert h.status == "running"


# ================================================================
# Scenario 9: Back
# ================================================================


def test_back(harness_factory):
    """Exploring a food delivery app: realize charter needs revision, go back to fix it."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["restaurant_search"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore FoodDash search functionality",
    })
    assert r
    assert h.step == "1.2 Set time box"

    # Realize the charter scope is too narrow, go back
    r = h.back()
    assert r
    assert h.step == "1.1 Define exploration charter"

    r = h.submit({
        "charter": "Explore FoodDash search, filtering, and restaurant detail pages",
    })
    assert r
    r = h.submit({"duration": "45 minutes"})
    assert r
    r = h.submit({
        "area": "restaurant_search",
        "observation": "Search results show closed restaurants mixed with open ones",
    })
    assert r
    assert h.step == "2.2 Found issue?"

    # Want to re-examine the area before deciding
    r = h.back()
    assert r
    assert h.step == "2.1 Explore area"


# ================================================================
# Scenario 10: Goto summary
# ================================================================


def test_goto_summary(harness_factory):
    """Testing an internal admin panel: stakeholder requests immediate summary, skip remaining areas."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["user_management", "audit_logs"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "charter": "Explore AdminPanel user management and audit trail features",
    })
    assert r
    r = h.submit({"duration": "60 minutes"})
    assert r

    # Stakeholder needs results immediately -- jump to summary
    r = h.goto("3.1 Summarize findings")
    assert r
    assert r.new_step == "3.1 Summarize findings"
    assert h.step == "3.1 Summarize findings"
    assert h.status == "running"

    r = h.submit({
        "summary": "Session cut short by stakeholder request. Partial exploration only.",
        "areas_completed": 0,
        "recommendation": "Schedule follow-up session to cover all areas",
    })
    assert r
    assert r.new_step == "3.2 Write exploration report"
    assert h.step == "3.2 Write exploration report"

    r = h.submit({
        "report": "Partial Exploratory Report: AdminPanel -- incomplete, follow-up needed",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
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
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.goto("3.2 Write exploration report")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.goto("3.2 Write exploration report")
    h.submit({})
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_running_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
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
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.submit({"charter": "test auth"})
    h.submit({"time": "30m"})

    h.save_checkpoint("at_explore")

    h.submit({})
    h.submit_goto("2.0 Explore loop")
    assert h.step == "3.1 Summarize findings"

    restored = h.load_checkpoint("at_explore")
    assert restored is not None
    assert restored.current_step == "2.1 Explore area"
    assert "1.1 Define exploration charter" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    assert h.step == "1.1 Define exploration charter"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define exploration charter"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define exploration charter"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1", "a2", "a3"]},
    )
    _walk_to_explore(h)

    loop_info = h.state.loop_state["2.0 Explore loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_area_no_issue(h)

    loop_info = h.state.loop_state["2.0 Explore loop"]
    assert loop_info["i"] == 1

    _complete_one_area_no_issue(h)

    loop_info = h.state.loop_state["2.0 Explore loop"]
    assert loop_info["i"] == 2


def test_cross_executor_at_summary(harness_factory):
    """Close executor at summary, reopen, state persists."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    _walk_to_explore(h)
    _complete_one_area_no_issue(h)
    assert h.step == "3.1 Summarize findings"

    h.new_executor()

    assert h.step == "3.1 Summarize findings"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "3.2 Write exploration report"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.goto("3.2 Write exploration report")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_history_records_transitions(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.submit({})
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define exploration charter",
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
        "p6-exploratory.yaml",
        loop_data={"areas": ["a1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define exploration charter",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
