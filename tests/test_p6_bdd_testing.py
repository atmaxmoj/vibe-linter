"""Test scenarios for BDD Testing Cucumber workflow (p6-bdd-testing.yaml).

Tests the BDD Testing workflow including:
- Feature setup phase (write feature file, define scenarios)
- Scenario loop with step definition 2-way branching (pass -> loop, fail -> rework)
- Acceptance wait+LLM step with 2-way branching
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


def _walk_to_scenario_loop(h):
    """Start -> feature file -> define scenarios -> enter scenario loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Write step definitions"
    assert h.status == "running"


def _complete_one_scenario_pass(h):
    """Complete one scenario: write steps -> run -> result -> pass -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Scenario loop")  # pass -> loop header


def _walk_to_acceptance(h):
    """Walk to 3.2 Acceptance (waiting)."""
    _walk_to_scenario_loop(h)
    _complete_one_scenario_pass(h)
    if h.step == "3.1 Run full feature":
        h.submit({})
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"


# ================================================================
# Scenario 1: Happy path all pass
# ================================================================


def test_happy_path_all_pass(harness_factory):
    """BDD testing for a user authentication feature: login and password reset scenarios both pass."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["login_scenario", "password_reset_scenario"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Write feature file"
    assert h.status == "running"

    r = h.submit({
        "feature_file": "authentication.feature",
        "feature_description": "Feature: User Authentication\n  As a registered user\n  I want to log in and reset my password\n  So that I can access my account securely",
    })
    assert r
    assert r.new_step == "1.2 Define scenarios"
    assert h.step == "1.2 Define scenarios"

    r = h.submit({
        "scenarios": [
            "Scenario: Successful login with valid credentials",
            "Scenario: Password reset via email link",
        ],
        "total_scenarios": 2,
    })
    assert r
    assert r.new_step == "2.1 Write step definitions"
    assert h.step == "2.1 Write step definitions"

    scenario_data = [
        {
            "steps": {
                "given": "Given a registered user with email 'alice@example.com'",
                "when": "When the user submits valid credentials",
                "then": "Then the user sees the dashboard and receives a JWT token",
            },
            "run_result": {"status": "PASS", "duration_ms": 450, "assertions": 3},
        },
        {
            "steps": {
                "given": "Given a user who forgot their password",
                "when": "When the user requests a password reset for 'alice@example.com'",
                "then": "Then an email with a reset link is sent within 30 seconds",
            },
            "run_result": {"status": "PASS", "duration_ms": 1200, "assertions": 4},
        },
    ]

    for i in range(2):
        r = h.submit(scenario_data[i]["steps"])
        assert r
        assert r.new_step == "2.2 Run scenario"
        assert h.step == "2.2 Run scenario"

        r = h.submit(scenario_data[i]["run_result"])
        assert r
        assert r.new_step == "2.3 Scenario result"
        assert h.step == "2.3 Scenario result"

        # Scenario passes -> continue loop
        r = h.submit_goto("2.0 Scenario loop")
        assert r
        if i < 1:
            assert r.new_step == "2.1 Write step definitions"
            assert h.step == "2.1 Write step definitions"

    assert h.step == "3.1 Run full feature"

    r = h.submit({
        "full_feature_result": "2/2 scenarios passed",
        "total_duration_ms": 1650,
        "cucumber_report": "All steps green, no pending or undefined steps",
    })
    assert r
    assert r.new_step == "3.2 Acceptance"
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Acceptance"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.submit({"feature": "login.feature"})
    assert h.state.data["1.1 Write feature file"]["feature"] == "login.feature"

    h.submit({"scenarios": "login success, login failure"})
    assert h.state.data["1.2 Define scenarios"]["scenarios"] == "login success, login failure"

    h.submit({"step_defs": "given/when/then"})
    assert h.state.data["2.1 Write step definitions"]["step_defs"] == "given/when/then"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Scenario loop")
    h.submit({})
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_happy_path_cross_executor_at_acceptance(harness_factory):
    """Close executor at acceptance wait, reopen, continue."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    _walk_to_acceptance(h)

    h.new_executor()

    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at step definitions."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    _walk_to_scenario_loop(h)

    h.register_node(
        "2.1 Write step definitions",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("steps") else "must include steps",
        ),
    )

    r = h.submit({"notes": "forgot steps"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"steps": "given I am logged in"})
    assert r
    assert r.new_step == "2.2 Run scenario"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes scenario results to SQLite table."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1", "s2"]},
    )
    _walk_to_scenario_loop(h)

    h.register_node(
        "2.1 Write step definitions",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"scenario_name": "string", "step_count": "string"}},
            archive={"table": "bdd_steps"},
        ),
    )

    h.submit({"scenario_name": "login_success", "step_count": "5"})
    h.submit({})
    h.submit_goto("2.0 Scenario loop")
    h.submit({"scenario_name": "login_failure", "step_count": "3"})

    rows = h.get_archived_rows("bdd_steps")
    assert len(rows) == 2
    assert rows[0]["scenario_name"] == "login_success"
    assert rows[1]["step_count"] == "3"


# ================================================================
# Scenario 2: Scenario fail rework
# ================================================================


def test_scenario_fail_rework(harness_factory):
    """Shopping cart scenario fails due to missing step definition for coupon codes, fix and rerun."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["apply_coupon"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "shopping_cart.feature",
        "feature_description": "Feature: Shopping Cart Coupon Application",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Apply a valid percentage coupon to cart"],
    })
    assert r
    assert h.step == "2.1 Write step definitions"

    r = h.submit({
        "given": "Given a cart with items totaling $100",
        "when": "When the user applies coupon 'SAVE20'",
        "then": "Then the cart total is $80",
    })
    assert r
    r = h.submit({
        "status": "FAIL",
        "error": "Undefined step: 'When the user applies coupon' -- no step definition matches",
    })
    assert r
    assert h.step == "2.3 Scenario result"

    # Scenario fails -> rework step definitions
    r = h.submit_goto("2.1 Write step definitions")
    assert r
    assert r.new_step == "2.1 Write step definitions"
    assert h.step == "2.1 Write step definitions"

    # Fix: add missing step definition for coupon application
    r = h.submit({
        "fix": "Added @when('the user applies coupon {coupon_code}') step definition",
        "step_definitions_file": "steps/cart_steps.py",
    })
    assert r
    r = h.submit({
        "status": "PASS",
        "duration_ms": 320,
        "cart_total_verified": "$80.00",
    })
    assert r
    assert h.step == "2.3 Scenario result"

    # Now passes
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "3.1 Run full feature"


# ================================================================
# Scenario 3: Acceptance rejected back to loop
# ================================================================


def test_acceptance_rejected_back_to_loop(harness_factory):
    """Product owner rejects checkout feature: missing 'guest checkout' scenario, add and re-verify."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["registered_checkout"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "checkout.feature",
        "feature_description": "Feature: E-Commerce Checkout",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Registered user completes checkout with saved address"],
    })
    assert r
    r = h.submit({
        "given": "Given a registered user with items in cart",
        "when": "When the user selects saved address and confirms order",
        "then": "Then an order confirmation email is sent",
    })
    assert r
    r = h.submit({
        "status": "PASS",
        "duration_ms": 800,
    })
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "3.1 Run full feature"

    r = h.submit({
        "full_feature_result": "1/1 scenarios passed",
        "note": "Only registered user path tested",
    })
    assert r
    assert r.new_step == "3.2 Acceptance"
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto back to loop
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert r.new_step == "2.1 Write step definitions"
    assert h.step == "2.1 Write step definitions"
    assert h.status == "running"

    # Rework: add guest checkout scenario
    r = h.submit({
        "given": "Given a guest user with items in cart",
        "when": "When the guest enters shipping address and payment",
        "then": "Then the order is placed and a tracking number is provided",
    })
    assert r
    r = h.submit({
        "status": "PASS",
        "duration_ms": 950,
    })
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r

    r = h.submit({
        "full_feature_result": "2/2 scenarios passed (registered + guest)",
    })
    assert r
    assert r.new_step == "3.2 Acceptance"
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"

    # Now accept
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


# ================================================================
# Scenario 4: Cross-phase fallback via goto
# ================================================================


def test_cross_phase_fallback_via_goto(harness_factory):
    """Notification feature file needs rewriting: from acceptance, goto back to feature setup."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["email_notification"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "notifications.feature",
        "feature_description": "Feature: Email Notifications",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Send order confirmation email"],
    })
    assert r
    r = h.submit({
        "given": "Given a completed order #12345",
        "when": "When the payment is captured",
        "then": "Then an email is sent to the customer within 60 seconds",
    })
    assert r
    r = h.submit({
        "status": "PASS",
        "duration_ms": 600,
    })
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    r = h.submit({
        "full_feature_result": "1/1 passed",
    })
    assert r
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"

    # Rewrite the entire feature file to include SMS alongside email
    r = h.goto("1.1 Write feature file")
    assert r
    assert r.new_step == "1.1 Write feature file"
    assert h.step == "1.1 Write feature file"
    assert h.status == "running"

    # Continue from there with expanded feature
    r = h.submit({
        "feature_file": "notifications.feature",
        "feature_description": "Feature: Multi-Channel Notifications (Email + SMS)",
    })
    assert r
    assert r.new_step == "1.2 Define scenarios"
    assert h.step == "1.2 Define scenarios"


# ================================================================
# Scenario 5: Stop and resume
# ================================================================


def test_stop_and_resume(harness_factory):
    """Testing a file upload feature: CI pipeline goes down mid-run, stop and resume when restored."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["large_file_upload"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "file_upload.feature",
        "feature_description": "Feature: Large File Upload with Progress Tracking",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Upload a 500MB file with progress bar"],
    })
    assert r
    r = h.submit({
        "given": "Given a logged-in user on the upload page",
        "when": "When the user selects a 500MB video file and clicks upload",
        "then": "Then the progress bar shows percentage and upload completes within 2 minutes",
    })
    assert r
    assert h.step == "2.2 Run scenario"

    # CI/CD pipeline is down -- stop execution
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Run scenario"

    # Pipeline restored -- resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Run scenario"

    # Continue from where we left off
    r = h.submit({
        "status": "PASS",
        "upload_time_sec": 95,
        "progress_bar_accurate": True,
    })
    assert r
    assert r.new_step == "2.3 Scenario result"
    assert h.step == "2.3 Scenario result"


# ================================================================
# Scenario 6: Skip regular step
# ================================================================


def test_skip_regular_step(harness_factory):
    """Search feature: reuse existing step definitions from a previous sprint, skip writing new ones."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["search_by_keyword"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "product_search.feature",
        "feature_description": "Feature: Product Search by Keyword",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Search returns relevant results for keyword 'laptop'"],
    })
    assert r
    assert h.step == "2.1 Write step definitions"

    # Skip step definitions -- reusing steps from Sprint 8 search feature
    r = h.skip("Reusing step definitions from steps/search_steps.py (Sprint 8)")
    assert r
    assert h.step == "2.2 Run scenario"

    r = h.submit({
        "status": "PASS",
        "results_count": 42,
        "relevance_score": "98% -- top 10 all contain 'laptop'",
    })
    assert r
    assert r.new_step == "2.3 Scenario result"
    assert h.step == "2.3 Scenario result"

    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "3.1 Run full feature"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish BDD testing for v3.0 user profiles, reset for v3.1 payment methods feature."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["view_profile"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "user_profile.feature",
        "feature_description": "Feature: User Profile Management v3.0",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: User views their profile page"],
    })
    assert r
    r = h.submit({
        "given": "Given a user with display name 'Alice'",
        "when": "When the user navigates to /profile",
        "then": "Then the profile shows name, email, and join date",
    })
    assert r
    r = h.submit({
        "status": "PASS",
        "duration_ms": 280,
    })
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    r = h.submit({
        "full_feature_result": "1/1 passed, user profile v3.0 verified",
    })
    assert r
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for v3.1 payment methods feature
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Write feature file"
    assert h.status == "running"


# ================================================================
# Scenario 8: Back in loop
# ================================================================


def test_back_in_loop(harness_factory):
    """Inventory feature: realized step definition has wrong regex, go back to fix before running."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["add_stock", "remove_stock"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "inventory.feature",
        "feature_description": "Feature: Warehouse Inventory Management",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Add stock to warehouse", "Scenario: Remove stock from warehouse"],
    })
    assert r
    assert h.step == "2.1 Write step definitions"

    r = h.submit({
        "step": "When {quantity} units of {sku} are added to warehouse {warehouse_id}",
        "note": "Oops -- regex for quantity should be integer not string",
    })
    assert r
    assert h.step == "2.2 Run scenario"

    # Go back to fix the step definition regex
    r = h.back()
    assert r
    assert h.step == "2.1 Write step definitions"

    # Move forward again with fixed step
    r = h.submit({
        "step": "When {quantity:d} units of {sku} are added to warehouse {warehouse_id}",
        "fix": "Changed {quantity} to {quantity:d} for integer parsing",
    })
    assert r
    assert h.step == "2.2 Run scenario"

    r = h.submit({
        "status": "PASS",
        "warehouse_id": "WH-001",
        "sku": "LAPTOP-15PRO",
        "quantity_added": 50,
    })
    assert r
    assert r.new_step == "2.3 Scenario result"
    assert h.step == "2.3 Scenario result"


# ================================================================
# Scenario 9: Goto acceptance directly
# ================================================================


def test_goto_acceptance_directly(harness_factory):
    """Regression suite already passes: jump directly to full feature run and acceptance."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["regression_login", "regression_signup"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "regression_auth.feature",
        "feature_description": "Feature: Authentication Regression Suite",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Login regression", "Scenario: Signup regression"],
    })
    assert r
    assert h.step == "2.1 Write step definitions"

    # Scenarios already verified in nightly CI -- jump to full feature run
    r = h.goto("3.1 Run full feature")
    assert r
    assert r.new_step == "3.1 Run full feature"
    assert h.step == "3.1 Run full feature"
    assert h.status == "running"

    r = h.submit({
        "full_feature_result": "2/2 regression scenarios passed (from nightly CI build #4521)",
    })
    assert r
    assert r.new_step == "3.2 Acceptance"
    assert h.step == "3.2 Acceptance"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML add step
# ================================================================


def test_modify_yaml_add_step(harness_factory):
    """Add a review step to inspect Cucumber output before evaluating the result."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["subscription_renewal"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "feature_file": "subscription.feature",
        "feature_description": "Feature: Subscription Auto-Renewal",
    })
    assert r
    r = h.submit({
        "scenarios": ["Scenario: Auto-renew monthly subscription"],
    })
    assert r
    r = h.submit({
        "given": "Given a user with an active monthly subscription expiring today",
        "when": "When the system runs the renewal job at midnight",
        "then": "Then the subscription is extended by 30 days and a receipt email is sent",
    })
    assert r
    assert h.step == "2.2 Run scenario"

    modified_yaml = """名称: BDD Testing Modified
步骤:
  - 1.1 Write feature file

  - 1.2 Define scenarios

  - 2.0 Scenario loop:
      遍历: "scenarios"
      子步骤:
        - 2.1 Write step definitions
        - 2.2 Run scenario
        - 2.2.5 Review output
        - 2.3 Scenario result:
            下一步:
              - 如果: "scenario passes"
                去: 2.0 Scenario loop
              - 去: 2.1 Write step definitions

  - 3.1 Run full feature

  - 3.2 Acceptance:
      类型: wait
      下一步:
        - 如果: "feature accepted"
          去: Done
        - 去: 2.0 Scenario loop

  - Done:
      类型: terminate
"""

    h.reload_yaml(modified_yaml)

    r = h.submit({
        "status": "PASS",
        "renewal_date": "2024-04-01",
        "receipt_email_sent": True,
    })
    assert r
    assert r.new_step == "2.2.5 Review output"
    assert h.step == "2.2.5 Review output"

    r = h.submit({
        "reviewer": "QA Lead",
        "output_review": "Cucumber HTML report looks clean, no pending steps, all assertions green",
    })
    assert r
    assert r.new_step == "2.3 Scenario result"
    assert h.step == "2.3 Scenario result"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting at acceptance returns failure."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    _walk_to_acceptance(h)

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
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
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.goto("3.2 Acceptance")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
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
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.submit({"feature": "login.feature"})
    h.submit({"scenarios": "login success"})

    h.save_checkpoint("at_loop")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Scenario loop")
    assert h.step == "3.1 Run full feature"

    restored = h.load_checkpoint("at_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Write step definitions"
    assert "1.1 Write feature file" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    assert h.step == "1.1 Write feature file"

    r = h.retry()
    assert r
    assert h.step == "1.1 Write feature file"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Write feature file"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.goto("3.2 Acceptance")
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
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1", "s2", "s3"]},
    )
    _walk_to_scenario_loop(h)

    loop_info = h.state.loop_state["2.0 Scenario loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_scenario_pass(h)

    loop_info = h.state.loop_state["2.0 Scenario loop"]
    assert loop_info["i"] == 1


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.register_node(
        "1.1 Write feature file",
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
        "p6-bdd-testing.yaml",
        loop_data={"scenarios": ["s1"]},
    )
    h.start()
    h.register_node(
        "1.1 Write feature file",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
