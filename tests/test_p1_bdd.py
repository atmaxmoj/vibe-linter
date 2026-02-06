"""Test scenarios for BDD SOP workflow (p1-bdd.yaml).

Tests the complete BDD workflow including:
- Feature definition and Gherkin scenario writing
- Scenario loop (implement, run, check result)
- Acceptance review with fallback to scenario loop
- State transitions, gotos, stops/resumes, and resets

Workflow structure:
  1.1 Define feature behavior
  1.2 Write Gherkin scenarios (wait)
  1.3 Gherkin review (wait, LLM: approved->2.0, else->1.2)
  2.0 Scenario loop (iterate: scenarios)
    2.1 Implement step definitions
    2.2 Run scenario
    2.3 Scenario result (LLM: passes->2.0, else->2.1)
  3.1 Run all scenarios
  3.2 Acceptance review (wait, LLM: pass->Done, else->2.0)
  Done (terminate)

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

# ─── Helpers ───


def _walk_to_gherkin_review(h):
    """Common helper: start -> submit 1.1 -> approve 1.2 -> arrive at 1.3 (waiting)."""
    h.start()
    h.submit({"feature": "user auth"})
    h.approve({"scenarios_written": True})
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"


def _enter_scenario_loop(h):
    """Common helper: get past gherkin review into loop iteration 1."""
    _walk_to_gherkin_review(h)
    h.approve()
    h.submit_goto("2.0 Scenario loop")
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"


def _do_one_scenario_pass(h, data=None):
    """Complete one implement-run-result cycle ending at scenario result."""
    h.submit(data or {"step_defs": "impl"})  # 2.1 -> 2.2
    h.submit(data or {"result": "green"})     # 2.2 -> 2.3
    assert h.step == "2.3 Scenario result"


def _complete_loop_and_finish(h, n_scenarios):
    """From inside the loop, exhaust all iterations and reach Done."""
    for _i in range(n_scenarios):
        if h.step != "2.1 Implement step definitions":
            h.submit_goto("2.0 Scenario loop")
        _do_one_scenario_pass(h)
        h.submit_goto("2.0 Scenario loop")
    assert h.step == "3.1 Run all scenarios"
    h.submit({"all_pass": True})
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"
    h.approve()
    h.submit_goto("Done")
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 1: Five scenarios all pass (original happy path)
# ===============================================================

def test_scenario_1_five_scenarios_all_pass(harness_factory):
    """E-commerce checkout: 5 Gherkin scenarios covering the full purchase flow."""
    h = harness_factory(
        "p1-bdd.yaml",
        loop_data={"scenarios": [
            "add_to_cart", "apply_coupon", "enter_shipping",
            "process_payment", "order_confirmation",
        ]},
    )
    r = h.start()
    assert r

    # Phase 1: Feature definition
    assert h.step == "1.1 Define feature behavior"
    assert h.status == "running"

    r = h.submit({
        "feature": "E-commerce Checkout Flow",
        "description": "Complete purchase flow from cart to order confirmation",
        "personas": ["guest shopper", "registered customer", "returning member"],
        "business_rules": [
            "Cart must have at least 1 item to proceed",
            "Coupons cannot be stacked",
            "Shipping is free over $50",
            "Payment via Stripe with 3D Secure",
        ],
    })
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    # Wait step arrival: submit is rejected
    r = h.submit({})
    assert not r
    assert "waiting" in r.message.lower()

    # Approve Gherkin scenarios (WAIT-only -> follows default to 1.3)
    r = h.approve({
        "gherkin_file": "features/checkout.feature",
        "scenarios_count": 5,
        "coverage": ["happy path", "edge cases", "error handling"],
    })
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "1.3 Gherkin review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Scenario 1: Add to cart
    scenario_data = [
        {
            "step_defs": {
                "file": "steps/test_add_to_cart.py",
                "given": "Given a product 'Wireless Mouse' priced at $29.99",
                "when": "When the customer clicks 'Add to Cart'",
                "then": "Then the cart should contain 1 item with total $29.99",
            },
            "run_result": {
                "scenario": "add_to_cart",
                "status": "passed",
                "duration_ms": 120,
            },
        },
        {
            "step_defs": {
                "file": "steps/test_apply_coupon.py",
                "given": "Given a cart with total $80.00 and a valid coupon 'SAVE20'",
                "when": "When the customer applies the coupon",
                "then": "Then the total should be $64.00 (20% off)",
            },
            "run_result": {
                "scenario": "apply_coupon",
                "status": "passed",
                "duration_ms": 95,
            },
        },
        {
            "step_defs": {
                "file": "steps/test_enter_shipping.py",
                "given": "Given the customer is on the shipping page",
                "when": "When they enter address '123 Main St, Springfield, IL 62701'",
                "then": "Then shipping cost should be $0.00 (free over $50)",
            },
            "run_result": {
                "scenario": "enter_shipping",
                "status": "passed",
                "duration_ms": 150,
            },
        },
        {
            "step_defs": {
                "file": "steps/test_process_payment.py",
                "given": "Given the order total is $64.00 with Stripe test card 4242424242424242",
                "when": "When the customer submits payment",
                "then": "Then a Stripe PaymentIntent should be created with amount 6400 cents",
            },
            "run_result": {
                "scenario": "process_payment",
                "status": "passed",
                "duration_ms": 340,
            },
        },
        {
            "step_defs": {
                "file": "steps/test_order_confirmation.py",
                "given": "Given payment succeeded for order #ORD-2024-0042",
                "when": "When the confirmation page loads",
                "then": "Then the customer sees order summary and receives confirmation email",
            },
            "run_result": {
                "scenario": "order_confirmation",
                "status": "passed",
                "duration_ms": 210,
            },
        },
    ]

    for i in range(5):
        r = h.submit(scenario_data[i]["step_defs"])
        assert r
        assert r.new_step == "2.2 Run scenario"
        assert h.step == "2.2 Run scenario"

        r = h.submit(scenario_data[i]["run_result"])
        assert r
        assert h.step == "2.3 Scenario result"

        r = h.submit_goto("2.0 Scenario loop")
        assert r
        if i < 4:
            # Still have more scenarios
            assert h.step == "2.1 Implement step definitions"
            # Verify iteration count
            status = h.get_status()
            assert f"[{i + 2}/" in status["display_path"]

    # All 5 iterations exhausted, exits loop
    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Scenario loop" not in h.state.loop_state

    r = h.submit({
        "command": "behave features/checkout.feature --format progress",
        "scenarios_run": 5,
        "passed": 5,
        "failed": 0,
        "duration_s": 1.2,
    })
    assert r
    assert r.new_step == "3.2 Acceptance review"
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"

    # 3.2 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Acceptance review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state: further submits rejected
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message


def test_scenario_2_scenario_keeps_failing_retry(harness_factory):
    """File upload scenario keeps failing due to multipart boundary parsing -- 3 retries before green."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["file_upload"]})
    r = h.start()
    assert r

    # Get through Gherkin phase
    r = h.submit({
        "feature": "File Upload",
        "description": "Users can upload profile avatars up to 5MB in PNG/JPG format",
    })
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    # 1.2 is WAIT-only -> approve moves to 1.3
    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "1.3 Gherkin review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Retry 1: multipart boundary not parsed correctly
    r = h.submit({
        "step_file": "steps/test_file_upload.py",
        "approach": "Use requests.post with files= parameter",
        "issue": "Multipart boundary not recognized by server",
    })
    assert r
    assert h.step == "2.2 Run scenario"
    r = h.submit({
        "status": "failed",
        "error": "400 Bad Request: Invalid multipart/form-data boundary",
    })
    assert r
    assert h.step == "2.3 Scenario result"
    r = h.submit_goto("2.1 Implement step definitions")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Retry 2: Content-Type header set manually but conflicts with requests lib
    r = h.submit({
        "approach": "Manually set Content-Type: multipart/form-data",
        "issue": "Double Content-Type header -- requests adds its own",
    })
    assert r
    assert h.step == "2.2 Run scenario"
    r = h.submit({
        "status": "failed",
        "error": "Missing boundary in Content-Type header",
    })
    assert r
    assert h.step == "2.3 Scenario result"
    r = h.submit_goto("2.1 Implement step definitions")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"

    # Retry 3: file size validation missing
    r = h.submit({
        "approach": "Let requests handle headers, add file size pre-check",
        "issue": "Server rejects files > 5MB but step def sends 10MB fixture",
    })
    assert r
    assert h.step == "2.2 Run scenario"
    r = h.submit({
        "status": "failed",
        "error": "413 Payload Too Large",
    })
    assert r
    assert h.step == "2.3 Scenario result"
    r = h.submit_goto("2.1 Implement step definitions")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"

    # Finally passes on 4th attempt: correct fixture and proper multipart handling
    r = h.submit({
        "approach": "Use 2MB PNG fixture, let requests handle Content-Type",
        "step_code": "resp = client.post('/upload', files={'avatar': ('photo.png', small_png, 'image/png')}); assert resp.status_code == 200",
    })
    assert r
    r = h.submit({
        "status": "passed",
        "duration_ms": 450,
    })
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r

    # Loop exhausted (1 scenario), exits
    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Scenario loop" not in h.state.loop_state


def test_scenario_3_gherkin_review_rejected_rewrite(harness_factory):
    """Password reset: Gherkin scenarios rejected twice for missing edge cases, approved on 3rd."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["password_reset"]})
    r = h.start()
    assert r

    r = h.submit({
        "feature": "Password Reset via Email",
        "description": "Users receive a time-limited reset link and can set a new password",
    })
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # First rejection: scenarios only cover happy path, missing expiry/invalid token
    r = h.approve()
    assert r
    assert h.step == "1.3 Gherkin review"
    assert h.status == "running"

    r = h.submit_goto("1.2 Write Gherkin scenarios")
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # Second rejection: added edge cases but missing rate-limiting scenario
    r = h.approve()
    assert r
    assert h.step == "1.3 Gherkin review"
    assert h.status == "running"

    r = h.submit_goto("1.2 Write Gherkin scenarios")
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # Third time approved: covers happy path, expired token, invalid token, rate limiting
    r = h.approve()
    assert r
    assert h.step == "1.3 Gherkin review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"


def test_scenario_4_acceptance_fails_back_to_loop(harness_factory):
    """User notification preferences: acceptance fails, scenarios reworked, then approved."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["email_prefs", "push_prefs"]})
    r = h.start()
    assert r

    # Get through Gherkin phase
    r = h.submit({
        "feature": "Notification Preferences",
        "description": "Users can configure email and push notification settings per channel",
    })
    assert r
    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "2.1 Implement step definitions"

    # Complete both scenarios in the loop (first pass)
    for _ in range(2):
        r = h.submit({
            "step_defs": "steps/test_notification_prefs.py",
            "note": "Initial implementation with in-memory store",
        })
        assert r
        r = h.submit({"status": "passed", "note": "Green in isolation"})
        assert r
        r = h.submit_goto("2.0 Scenario loop")
        assert r

    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    r = h.submit({
        "command": "behave features/notification_prefs.feature",
        "passed": 2, "failed": 0,
        "note": "Scenarios pass but acceptance criteria require DB persistence and API contract",
    })
    assert r
    assert r.new_step == "3.2 Acceptance review"
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"

    # 3.2 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Acceptance review"
    assert h.status == "running"

    # Acceptance fails: scenarios use in-memory state, need real DB persistence
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    # Loop was exhausted (cleared), so _handle_loop re-initializes with i=0, n=2
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Fix the scenarios - now with PostgreSQL and proper API calls
    r = h.submit({
        "step_defs": "steps/test_email_prefs.py",
        "fix": "Replaced in-memory dict with SQLAlchemy UserPreference model",
    })
    assert r
    r = h.submit({"status": "passed", "db_checked": True})
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    # i increments to 1
    assert h.step == "2.1 Implement step definitions"

    # Second pass
    r = h.submit({
        "step_defs": "steps/test_push_prefs.py",
        "fix": "Added FCM token registration in step definitions",
    })
    assert r
    r = h.submit({"status": "passed", "fcm_verified": True})
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    # i increments to 2 = n, loop exits

    # Run all again
    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Scenario loop" not in h.state.loop_state

    r = h.submit({
        "command": "behave features/notification_prefs.feature",
        "passed": 2, "failed": 0,
        "note": "All scenarios pass with real DB and FCM integration",
    })
    assert r
    assert r.new_step == "3.2 Acceptance review"
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"

    # This time acceptance passes: approve + submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Acceptance review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message


def test_scenario_5_empty_scenario_list(harness_factory):
    """Feature spike with no scenarios yet -- empty list causes loop to skip."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": []})
    r = h.start()
    assert r

    assert h.step == "1.1 Define feature behavior"
    assert h.status == "running"

    r = h.submit({
        "feature": "Dark Mode Toggle",
        "description": "Allow users to switch between light and dark themes",
        "note": "Exploratory phase -- no scenarios defined yet, skip to acceptance",
    })
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "1.3 Gherkin review"
    assert h.status == "running"

    # Enter loop with empty list -> should exit immediately to 2nd transition (3.1)
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"


def test_scenario_6_skip_a_scenario(harness_factory):
    """Search autocomplete: skip running first scenario (external API not ready), run second normally."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["instant_search", "search_filters"]})
    r = h.start()
    assert r

    # Get through Gherkin phase
    r = h.submit({
        "feature": "Product Search with Autocomplete",
        "description": "Real-time search suggestions as user types, with category filters",
    })
    assert r
    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # First scenario: implement step defs for instant search, skip running (Elasticsearch not ready)
    r = h.submit({
        "step_file": "steps/test_instant_search.py",
        "step_code": "Given('the search index contains {count:d} products')",
        "note": "Step defs written but Elasticsearch cluster not provisioned yet",
    })
    assert r
    assert r.new_step == "2.2 Run scenario"
    assert h.step == "2.2 Run scenario"

    r = h.skip("Elasticsearch cluster not provisioned in CI yet -- will run in integration")
    assert r
    assert h.step == "2.3 Scenario result"
    assert h.status == "running"

    # Scenario passes (move to next iteration)
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Second scenario: search filters -- runs normally
    r = h.submit({
        "step_file": "steps/test_search_filters.py",
        "step_code": "When('the user filters by category {category}')",
    })
    assert r
    assert h.step == "2.2 Run scenario"
    r = h.submit({
        "status": "passed",
        "note": "Filter scenario uses SQLite fallback, no ES needed",
    })
    assert r
    assert h.step == "2.3 Scenario result"
    r = h.submit_goto("2.0 Scenario loop")
    assert r

    # Loop exhausted
    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Scenario loop" not in h.state.loop_state


def test_scenario_7_back_to_previous_scenario(harness_factory):
    """Two-factor auth: realize feature description was wrong, use back() to fix it."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["totp_setup"]})
    r = h.start()
    assert r

    # Quick path into scenario loop
    r = h.submit({
        "feature": "Two-Factor Authentication",
        "description": "SMS-based 2FA for login",
    })
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"

    # Realize we should use TOTP, not SMS -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Define feature behavior"
    assert h.step == "1.1 Define feature behavior"
    assert h.status == "running"

    # Go forward again with corrected feature description
    r = h.submit({
        "feature": "Two-Factor Authentication",
        "description": "TOTP-based 2FA using authenticator apps (Google Authenticator, Authy)",
        "note": "Changed from SMS to TOTP for better security and no carrier dependency",
    })
    assert r
    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # In the loop -- implement TOTP setup steps
    r = h.submit({
        "step_file": "steps/test_totp_setup.py",
        "step_code": "Given('the user scans the QR code with Google Authenticator')",
    })
    assert r
    assert r.new_step == "2.2 Run scenario"
    assert h.step == "2.2 Run scenario"

    # Realize step definitions need pyotp library -- go back
    r = h.back()
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Re-implement with pyotp dependency added
    r = h.submit({
        "step_file": "steps/test_totp_setup.py",
        "dependencies_added": ["pyotp==2.9.0"],
        "step_code": "totp = pyotp.TOTP(secret); assert totp.verify(user_code)",
    })
    assert r
    assert r.new_step == "2.2 Run scenario"
    assert h.step == "2.2 Run scenario"
    r = h.submit({"status": "passed", "duration_ms": 85})
    assert r
    assert h.step == "2.3 Scenario result"


def test_scenario_8_stop_then_resume(harness_factory):
    """Inventory management BDD: stop Friday for sprint boundary, resume Monday."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["stock_deduction", "reorder_alert"]})
    r = h.start()
    assert r

    r = h.submit({
        "feature": "Inventory Management",
        "description": "Track stock levels, deduct on sale, alert when below reorder threshold",
    })
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    # Friday 5pm: sprint ends, stop the workflow
    r = h.stop()
    assert r
    assert r.message
    assert h.status == "stopped"
    assert h.step == "1.2 Write Gherkin scenarios"

    # Monday 9am: resume where we left off
    r = h.resume()
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"
    assert h.step == "1.2 Write Gherkin scenarios"

    # Now approve Gherkin scenarios
    r = h.approve({
        "gherkin_file": "features/inventory.feature",
        "scenarios": [
            "Scenario: Stock deducted when order placed",
            "Scenario: Reorder alert sent when stock below threshold",
        ],
    })
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert r.new_step == "2.1 Implement step definitions"
    assert h.step == "2.1 Implement step definitions"
    assert h.status == "running"

    # Work on stock deduction scenario
    r = h.submit({
        "step_file": "steps/test_stock_deduction.py",
        "step_code": "When('an order for {qty:d} units of SKU {sku} is placed')",
    })
    assert r
    assert r.new_step == "2.2 Run scenario"
    assert h.step == "2.2 Run scenario"

    # Wednesday standup: blocker discovered, DB migration not applied -- stop
    r = h.stop()
    assert r
    assert r.message
    assert h.status == "stopped"
    assert h.step == "2.2 Run scenario"

    # Thursday: migration applied, resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Run scenario"

    r = h.submit({"status": "passed", "stock_before": 100, "stock_after": 97})
    assert r
    assert h.step == "2.3 Scenario result"
    assert h.status == "running"


def test_scenario_9_complete_then_reset(harness_factory):
    """Shipping calculator V1 shipped, reset to start V2 with international zones."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["domestic_shipping"]})
    r = h.start()
    assert r

    # V1: basic domestic shipping calculator
    r = h.submit({
        "feature": "Shipping Calculator V1",
        "description": "Calculate domestic shipping based on weight and zone",
    })
    assert r
    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    # 1.3 is WAIT+LLM
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "2.1 Implement step definitions"

    r = h.submit({
        "step_file": "steps/test_domestic_shipping.py",
        "step_code": "Then('shipping for {weight}kg to zone {zone} costs ${cost}')",
    })
    assert r
    r = h.submit({"status": "passed", "cases_covered": 12})
    assert r
    r = h.submit_goto("2.0 Scenario loop")
    assert r

    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    r = h.submit({
        "command": "behave features/shipping.feature",
        "passed": 12, "failed": 0,
    })
    assert r
    assert r.new_step == "3.2 Acceptance review"
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"

    # 3.2 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state
    status = h.get_status()
    assert status["status"] == "done"

    # Verify done state: further submits rejected
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message

    # V1 shipped -- reset for V2 with international shipping zones
    h.reset()
    assert h.state is None

    # Start V2
    r = h.start()
    assert r
    assert h.step == "1.1 Define feature behavior"
    assert h.status == "running"


def test_scenario_10_goto_acceptance_step(harness_factory):
    """Regression suite: scenarios already implemented, goto acceptance for final sign-off."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["login_sso", "logout_sso"]})
    r = h.start()
    assert r

    # Get past the Gherkin review (minimum required steps)
    r = h.submit({
        "feature": "SSO Login/Logout via SAML",
        "description": "Enterprise SSO integration with Okta SAML provider",
    })
    assert r
    r = h.approve()
    assert r
    assert r.new_step == "1.3 Gherkin review"
    assert h.step == "1.3 Gherkin review"

    # Scenarios were already implemented in a previous sprint -- jump to acceptance
    r = h.goto("3.1 Run all scenarios")
    assert r
    assert r.new_step == "3.1 Run all scenarios"
    assert h.step == "3.1 Run all scenarios"
    assert h.status == "running"

    r = h.submit({
        "command": "behave features/sso.feature --tags=@regression",
        "scenarios_run": 8,
        "passed": 8, "failed": 0,
        "note": "All SSO scenarios pass against Okta sandbox IdP",
    })
    assert r
    assert r.new_step == "3.2 Acceptance review"
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"

    # 3.2 is WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "3.2 Acceptance review"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message


# ===============================================================
# Data accumulation tests
# ===============================================================

def test_data_accumulates_feature_definition(harness_factory):
    """Submit data at 1.1 persists in state.data."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()

    h.submit({"feature": "shopping cart"})
    data = h.state.data
    assert "1.1 Define feature behavior" in data
    assert data["1.1 Define feature behavior"]["feature"] == "shopping cart"


def test_data_accumulates_through_loop(harness_factory):
    """Data submitted in loop iterations persists in state.data."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    _enter_scenario_loop(h)

    h.submit({"step_defs": "login_steps"})
    data = h.state.data
    assert "2.1 Implement step definitions" in data
    assert data["2.1 Implement step definitions"]["step_defs"] == "login_steps"

    h.submit({"run_result": "pass"})
    data = h.state.data
    assert "2.2 Run scenario" in data
    assert data["2.2 Run scenario"]["run_result"] == "pass"


def test_data_accumulates_approve_gherkin(harness_factory):
    """Approve data at 1.2 persists in state.data."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({"feature": "auth"})

    h.approve({"reviewed": True, "scenarios_count": 5})
    data = h.state.data
    assert "1.2 Write Gherkin scenarios" in data
    assert data["1.2 Write Gherkin scenarios"]["reviewed"] is True


# ===============================================================
# History audit trail tests
# ===============================================================

def test_history_audit_full_walkthrough(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})
    h.approve()
    h.approve()
    h.submit_goto("2.0 Scenario loop")
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
    assert "approve" in actions
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_history_records_goto(harness_factory):
    """History records goto action."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.goto("3.1 Run all scenarios")

    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


def test_history_records_skip(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})
    h.approve()
    h.approve()
    h.submit_goto("2.0 Scenario loop")
    h.submit({})
    assert h.step == "2.2 Run scenario"

    h.skip("already tested")
    history = h.get_history(10)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "already tested"


# ===============================================================
# Cross-executor recovery tests
# ===============================================================

def test_cross_executor_at_gherkin_review(harness_factory):
    """Close executor at gherkin review, reopen, continue."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    _walk_to_gherkin_review(h)

    h.new_executor()

    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.0 Scenario loop")
    assert r
    assert h.step == "2.1 Implement step definitions"


def test_cross_executor_mid_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["a", "b"]})
    _enter_scenario_loop(h)

    h.submit({"step_defs": "a_steps"})
    assert h.step == "2.2 Run scenario"

    h.new_executor()

    assert h.step == "2.2 Run scenario"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Scenario loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_acceptance(harness_factory):
    """Close executor at acceptance review, reopen, state persists."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    _enter_scenario_loop(h)
    _do_one_scenario_pass(h)
    h.submit_goto("2.0 Scenario loop")
    assert h.step == "3.1 Run all scenarios"
    h.submit({})
    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "3.2 Acceptance review"
    assert h.status == "waiting"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.goto("3.2 Acceptance review")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Write Gherkin scenarios"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ===============================================================
# Node validation tests
# ===============================================================

def test_node_validates_step_definitions(harness_factory):
    """Validate node rejects bad data at 2.1, accepts good data."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    _enter_scenario_loop(h)

    h.register_node(
        "2.1 Implement step definitions",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("step_defs") else "must include step_defs",
        ),
    )

    r = h.submit({"notes": "forgot step defs"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"step_defs": "login_steps.py"})
    assert r
    assert r.new_step == "2.2 Run scenario"


def test_node_validates_scenario_run(harness_factory):
    """Validate node rejects missing result at 2.2."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    _enter_scenario_loop(h)
    h.submit({"step_defs": "impl"})
    assert h.step == "2.2 Run scenario"

    h.register_node(
        "2.2 Run scenario",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("result") else "must include result",
        ),
    )

    r = h.submit({"no_result": True})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"result": "green"})
    assert r
    assert r.new_step == "2.3 Scenario result"


def test_node_validates_feature_definition(harness_factory):
    """Validate node rejects missing feature at 1.1."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()

    h.register_node(
        "1.1 Define feature behavior",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("feature") else "must include feature name",
        ),
    )

    r = h.submit({})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"feature": "user login"})
    assert r
    assert r.new_step == "1.2 Write Gherkin scenarios"


# ===============================================================
# Node archival tests
# ===============================================================

def test_node_archives_step_definitions(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    _enter_scenario_loop(h)

    h.register_node(
        "2.1 Implement step definitions",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"step_file": "string", "scenario": "string"}},
            archive={"table": "step_definitions"},
        ),
    )

    r = h.submit({"step_file": "login_steps.py", "scenario": "login"})
    assert r

    rows = h.get_archived_rows("step_definitions")
    assert len(rows) == 1
    assert rows[0]["step_file"] == "login_steps.py"
    assert rows[0]["scenario"] == "login"


def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1", "s2", "s3"]})
    _enter_scenario_loop(h)

    h.register_node(
        "2.1 Implement step definitions",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"scenario_name": "string"}},
            archive={"table": "scenario_impls"},
        ),
    )

    for i in range(3):
        h.submit({"scenario_name": f"scenario_{i}"})
        h.submit({})
        h.submit_goto("2.0 Scenario loop")

    rows = h.get_archived_rows("scenario_impls")
    assert len(rows) == 3


def test_node_archives_feature_data(harness_factory):
    """Archive node at 1.1 writes feature definition to SQLite."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()

    h.register_node(
        "1.1 Define feature behavior",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"feature_name": "string"}},
            archive={"table": "features"},
        ),
    )

    r = h.submit({"feature_name": "user authentication"})
    assert r

    rows = h.get_archived_rows("features")
    assert len(rows) == 1
    assert rows[0]["feature_name"] == "user authentication"


# ===============================================================
# Error boundary tests
# ===============================================================

def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting returns failure."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Write Gherkin scenarios"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    assert h.step == "1.1 Define feature behavior"
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.goto("3.2 Acceptance review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.goto("3.2 Acceptance review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({"feature": "checkout"})
    h.approve({"gherkin": "written"})
    assert h.step == "1.3 Gherkin review"

    h.save_checkpoint("at_gherkin_review")

    h.approve()
    h.submit_goto("2.0 Scenario loop")
    assert h.step == "2.1 Implement step definitions"

    restored = h.load_checkpoint("at_gherkin_review")
    assert restored is not None
    assert restored.current_step == "1.3 Gherkin review"
    assert "1.1 Define feature behavior" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    assert h.step == "1.1 Define feature behavior"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define feature behavior"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define feature behavior"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["a", "b", "c"]})
    _enter_scenario_loop(h)

    loop_info = h.state.loop_state["2.0 Scenario loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_scenario_pass(h)
    h.submit_goto("2.0 Scenario loop")

    loop_info = h.state.loop_state["2.0 Scenario loop"]
    assert loop_info["i"] == 1

    _do_one_scenario_pass(h)
    h.submit_goto("2.0 Scenario loop")

    loop_info = h.state.loop_state["2.0 Scenario loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["only"]})
    _enter_scenario_loop(h)

    _do_one_scenario_pass(h)
    h.submit_goto("2.0 Scenario loop")

    assert h.step == "3.1 Run all scenarios"
    assert "2.0 Scenario loop" not in h.state.loop_state


def test_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({"feature": "auth"})
    h.approve({"gherkin": "done"})
    assert h.step == "1.3 Gherkin review"

    data_before = dict(h.state.data)
    h.reject("bad scenarios")
    data_after = h.state.data
    assert data_before == data_after


def test_reject_adds_history(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})
    h.approve()
    assert h.step == "1.3 Gherkin review"
    assert h.status == "waiting"

    h.reject("scenarios not specific enough")

    history = h.get_history(10)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "scenarios not specific enough"


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_history_records_transition(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    h.submit({})
    h.approve()
    h.approve()
    h.submit_goto("2.0 Scenario loop")
    assert h.step == "2.1 Implement step definitions"

    h.register_node(
        "2.1 Implement step definitions",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step by following BDD principles.\n\n## Steps\n1. Analyze requirements\n2. Write step definitions\n3. Submit output",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-bdd.yaml", loop_data={"scenarios": ["s1"]})
    h.start()
    assert h.step == "1.1 Define feature behavior"

    h.register_node(
        "1.1 Define feature behavior",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="block",
                patterns=[],
            ),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
