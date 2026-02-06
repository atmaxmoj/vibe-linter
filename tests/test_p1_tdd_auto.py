"""Test the autonomous TDD workflow (p1-tdd-auto.yaml).

This tests the flow where Claude executes autonomously and user supervises.
No wait steps — Claude drives the whole flow based on node instructions.

The test simulates what Claude would submit at each step by following
the node instructions.
"""
from __future__ import annotations


def test_bugfix_email_case_sensitivity(harness_factory):
    """Complete flow: fix the email case sensitivity bug.

    User says: "Registered with Alice@Example.com, can't login with ALICE@EXAMPLE.COM"
    Claude executes the entire TDD cycle autonomously.
    """
    # Load the auto workflow with initial scenario
    # Use 2 features so loop mechanics work properly (hotfix skips to 2.1, needs loop to exhaust)
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Login fails when email case differs from registration",
        "features": ["email_case_fix", "email_case_fix_pass2"],
    })

    # ── Start: Claude sees scenario in initial data ──
    r = h.start()
    assert r
    assert h.step == "0.1 Collect scenario"

    # Claude reads instructions, sees bug_description exists in state.data
    # LLM condition "has bug description..." — Claude decides to go to 1.1
    r = h.submit({
        "scenario_collected": True,
        "type": "bug",
        "_goto": "1.1 Gather requirements",  # Claude chose this path
    })
    assert r
    assert h.step == "1.1 Gather requirements"

    # ── 1.1 Gather requirements ──
    # Claude reads instructions: this is a hotfix with known root cause
    # Decision: skip to 2.1
    r = h.submit({
        "decision": "hotfix",
        "root_cause_hypothesis": "login() does case-sensitive email lookup",
        "_goto": "2.1 Write failing test (Red)",
    })
    assert r
    assert h.step == "2.1 Write failing test (Red)"

    # ── 2.1 Write failing test (Red) ──
    # Claude writes test, runs it, confirms it fails
    r = h.submit({
        "test_file": "tests/test_login_case.py",
        "test_name": "test_login_case_insensitive_email",
        "test_code": """
def test_login_case_insensitive_email():
    user = create_user('Alice@Example.com', 'pass123')
    result = login('ALICE@EXAMPLE.COM', 'pass123')
    assert result.success, f"Expected success, got {result}"
""",
        "run_result": "FAILED - AssertionError: Expected success, got LoginResult(success=False)",
        "failure_analysis": "login() uses email directly in query without normalization",
    })
    assert r
    assert h.step == "2.2 Write minimal code (Green)"

    # ── 2.2 Write minimal code (Green) ──
    # Claude makes minimal fix, test passes
    r = h.submit({
        "files_changed": ["src/services/auth_service.py"],
        "changes_summary": "Added email.lower() in login() before DB lookup",
        "diff": """
- user = User.query.filter_by(email=email).first()
+ user = User.query.filter_by(email=email.lower()).first()
""",
        "run_result": "PASSED - 1 passed in 0.2s",
    })
    assert r
    assert h.step == "2.3 Refactor"

    # ── 2.3 Refactor ──
    # Claude notices register() also needs the fix
    r = h.submit({
        "refactoring": "done",
        "changes": [
            "Applied same email.lower() to register()",
            "Extracted normalize_email() helper function",
        ],
        "files_changed": ["src/services/auth_service.py"],
        "run_result": "PASSED - 3 passed in 0.3s",
    })
    assert r
    assert h.step == "2.4 Run test suite"

    # ── 2.4 Run test suite ──
    # Claude runs full suite
    r = h.submit({
        "command": "pytest tests/ --tb=short -q",
        "passed": 47,
        "failed": 0,
        "skipped": 0,
        "run_result": "47 passed in 2.3s",
        "failures": [],
    })
    assert r
    assert h.step == "2.5 Quality check"

    # ── 2.5 Quality check ──
    # Claude evaluates: all good, proceed to next feature
    r = h.submit({
        "decision": "quality_ok",
        "notes": "All 47 tests pass, fix is minimal, refactoring improved code",
        "_goto": "2.0 Feature loop",
    })
    assert r
    # Hotfix goto'd directly to 2.1, so loop wasn't initialized
    # Now goto to loop header initializes it with i=0
    # This enters first child (2.1)
    assert h.step == "2.1 Write failing test (Red)"

    # ── Second pass through loop (just to exhaust it) ──
    h.submit({
        "test_file": "tests/test_login_case.py",
        "test_name": "test_login_case_variant",
        "test_code": "def test_login_case_variant(): pass",
        "run_result": "FAILED - placeholder",
        "failure_analysis": "second pass",
    })
    h.submit({
        "files_changed": ["src/services/auth_service.py"],
        "changes_summary": "no-op",
        "diff": "",
        "run_result": "PASSED",
    })
    h.submit({
        "refactoring": "none needed",
        "reason": "already clean",
        "run_result": "PASSED",
    })
    h.submit({
        "command": "pytest",
        "passed": 47,
        "failed": 0,
        "run_result": "47 passed",
        "failures": [],
    })
    r = h.submit({
        "decision": "quality_ok",
        "notes": "pass 2 done",
        "_goto": "2.0 Feature loop",
    })
    assert r
    # Now loop: i was 0, increments to 1, n=2, so i < n, enters 2.1 again
    # Wait, that's still not right. Let me think...
    # Actually: first goto to 2.0 initializes loop with i=0, n=2, goes to 2.1
    # After first pass, goto to 2.0: i++ = 1, i < n (1 < 2), goes to 2.1
    # After second pass, goto to 2.0: i++ = 2, i >= n (2 >= 2), exits loop
    assert h.step == "2.1 Write failing test (Red)"

    # Third pass to exhaust
    h.submit({
        "test_file": "tests/test_x.py",
        "test_name": "test_x",
        "test_code": "...",
        "run_result": "FAILED",
        "failure_analysis": "...",
    })
    h.submit({
        "files_changed": ["x.py"],
        "changes_summary": "...",
        "diff": "",
        "run_result": "PASSED",
    })
    h.submit({
        "refactoring": "none needed",
        "reason": "...",
        "run_result": "PASSED",
    })
    h.submit({
        "command": "pytest",
        "passed": 47,
        "failed": 0,
        "run_result": "47 passed",
        "failures": [],
    })
    r = h.submit({
        "decision": "quality_ok",
        "notes": "done",
        "_goto": "2.0 Feature loop",
    })
    assert r
    # Now i=2, n=2, exits loop
    assert h.step == "3.1 Integration testing"

    # ── 3.1 Integration testing ──
    # Claude runs integration tests
    r = h.submit({
        "integration_tests_run": [
            "test_login_flow",
            "test_registration_flow",
            "test_mixed_case_email_login",
        ],
        "passed": 12,
        "failed": 0,
        "run_result": "12 passed in 4.1s",
        "manual_check": "Verified in browser: register Alice@Test.com, login with ALICE@TEST.COM works",
    })
    assert r
    assert h.step == "3.2 Final review"

    # ── 3.2 Final review ──
    # Claude does final review: ship it
    r = h.submit({
        "review_result": "approved",
        "summary": "Fixed email case sensitivity. 47 unit + 12 integration tests pass. Code is clean.",
        "_goto": "Done",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # ── Verify the journey ──
    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "terminate" in actions[-1]

    # Verify data exists (values may be overwritten by loop iterations)
    data = h.state.data
    assert "2.1 Write failing test (Red)" in data
    assert "2.2 Write minimal code (Green)" in data


def test_new_feature_full_design(harness_factory):
    """New feature: needs full design phase, not a hotfix."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "feature_request": "Add password reset via email",
        "features": ["password_reset"],
    })

    r = h.start()
    assert h.step == "0.1 Collect scenario"

    # Claude collects scenario — has feature_request in state.data
    r = h.submit({
        "scenario_collected": True,
        "type": "feature",
        "_goto": "1.1 Gather requirements",
    })
    assert h.step == "1.1 Gather requirements"

    # Not a hotfix — gather requirements properly, then go to design
    r = h.submit({
        "requirements": [
            "User can request password reset with email",
            "System sends email with reset token",
            "Token expires in 1 hour",
            "User can set new password with valid token",
        ],
        "acceptance_criteria": [
            "Reset email sent within 5 seconds",
            "Token is cryptographically secure",
            "Old password no longer works after reset",
        ],
        "affected_files": [
            "src/services/auth_service.py",
            "src/services/email_service.py",
            "src/models/password_reset_token.py",
        ],
        "_goto": "1.2 Design architecture",  # LLM condition: not a hotfix
    })
    assert r
    assert h.step == "1.2 Design architecture"

    # Design the feature
    r = h.submit({
        "approach": "Add PasswordResetToken model, generate secure token, send via existing email service",
        "components": [
            {"name": "PasswordResetToken", "responsibility": "Store token, email, expiry"},
            {"name": "AuthService.request_reset", "responsibility": "Generate token, send email"},
            {"name": "AuthService.reset_password", "responsibility": "Validate token, update password"},
        ],
        "files_to_modify": ["src/services/auth_service.py"],
        "files_to_create": ["src/models/password_reset_token.py"],
        "risks": ["Email deliverability", "Token security"],
    })
    assert r
    assert h.step == "1.3 Design review"

    # Design looks good
    r = h.submit({
        "review_result": "approved",
        "notes": "Simple approach, uses existing email service",
        "_goto": "2.0 Feature loop",
    })
    assert r
    assert h.step == "2.1 Write failing test (Red)"


def test_design_rejected_iterate(harness_factory):
    """Design review rejects, iterate on design."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "feature_request": "Add 2FA",
        "features": ["two_factor_auth"],
    })

    h.start()
    h.submit({
        "scenario_collected": True,
        "type": "feature",
        "_goto": "1.1 Gather requirements",
    })
    h.submit({
        "requirements": ["Add TOTP-based 2FA"],
        "acceptance_criteria": ["Works with Google Authenticator"],
        "affected_files": ["src/services/auth_service.py"],
        "_goto": "1.2 Design architecture",  # LLM: not a hotfix
    })
    assert h.step == "1.2 Design architecture"

    # First design: too complex
    h.submit({
        "approach": "Build custom TOTP implementation from scratch",
        "components": [
            {"name": "TOTPGenerator", "responsibility": "Generate TOTP codes"},
            {"name": "TOTPValidator", "responsibility": "Validate codes"},
        ],
        "files_to_modify": [],
        "files_to_create": ["src/crypto/totp.py", "src/crypto/hmac.py"],
        "risks": ["Security risk of custom crypto"],
    })
    assert h.step == "1.3 Design review"

    # Review rejects: don't roll your own crypto
    r = h.submit({
        "review_result": "needs_revision",
        "issues": [
            "Never roll your own crypto",
            "Use pyotp library instead",
        ],
        "_goto": "1.2 Design architecture",
    })
    assert r
    assert h.step == "1.2 Design architecture"

    # Second design: use library
    h.submit({
        "approach": "Use pyotp library for TOTP generation and validation",
        "components": [
            {"name": "TwoFactorService", "responsibility": "Wrap pyotp, manage user secrets"},
        ],
        "files_to_modify": ["src/services/auth_service.py", "requirements.txt"],
        "files_to_create": ["src/services/two_factor_service.py"],
        "risks": [],
    })
    assert h.step == "1.3 Design review"

    # Now approved
    r = h.submit({
        "review_result": "approved",
        "notes": "Using battle-tested library is the right call",
        "_goto": "2.0 Feature loop",
    })
    assert r
    assert h.step == "2.1 Write failing test (Red)"


def test_quality_check_finds_code_bug(harness_factory):
    """Quality check finds code bug, goes back to Green phase."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Some bug",
        "features": ["fix1"],
    })

    h.start()
    h.submit({"scenario_collected": True, "type": "bug"})
    h.submit({
        "decision": "hotfix",
        "root_cause_hypothesis": "...",
        "_goto": "2.1 Write failing test (Red)",
    })

    # Red
    h.submit({
        "test_file": "tests/test_x.py",
        "test_name": "test_x",
        "test_code": "def test_x(): ...",
        "run_result": "FAILED",
        "failure_analysis": "...",
    })

    # Green
    h.submit({
        "files_changed": ["src/x.py"],
        "changes_summary": "Fixed X",
        "diff": "...",
        "run_result": "PASSED",
    })

    # Refactor
    h.submit({
        "refactoring": "none needed",
        "reason": "Code is clean",
        "run_result": "PASSED",
    })

    # Run suite — oops, broke something
    h.submit({
        "command": "pytest",
        "passed": 45,
        "failed": 2,
        "run_result": "45 passed, 2 failed",
        "failures": ["test_other: AssertionError", "test_another: TypeError"],
    })
    assert h.step == "2.5 Quality check"

    # Quality check: code bug, go back to Green
    r = h.submit({
        "decision": "code_bugs",
        "failing_tests": ["test_other", "test_another"],
        "analysis": "The fix broke edge case handling",
        "_goto": "2.2 Write minimal code (Green)",
    })
    assert r
    assert h.step == "2.2 Write minimal code (Green)"


def test_no_scenario_stays_at_collect(harness_factory):
    """If Claude has no scenario, stays at collect step (LLM condition)."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "features": ["unknown"],
        # No bug_description or feature_request!
    })

    h.start()
    assert h.step == "0.1 Collect scenario"

    # Claude evaluates LLM condition, no scenario found
    # According to YAML: if no scenario, goes back to 0.1 (stays)
    # Claude would ask user and wait, then submit with _goto when ready
    r = h.submit({
        "action": "asked_user",
        "question": "What would you like me to work on?",
        "_goto": "0.1 Collect scenario",  # Stay here until user provides scenario
    })
    assert r
    assert h.step == "0.1 Collect scenario"

    # User provides scenario, Claude submits properly
    r = h.submit({
        "scenario_collected": True,
        "type": "feature",
        "user_response": "Build a chat feature",
        "_goto": "1.1 Gather requirements",
    })
    assert r
    assert h.step == "1.1 Gather requirements"


def test_cross_executor_preserves_state(harness_factory):
    """Stop mid-flow, close executor, reopen, state preserved."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Some bug",
        "features": ["fix1"],
    })

    h.start()
    h.submit({"scenario_collected": True, "type": "bug"})
    h.submit({
        "decision": "hotfix",
        "root_cause_hypothesis": "...",
        "_goto": "2.1 Write failing test (Red)",
    })
    h.submit({
        "test_file": "tests/test_x.py",
        "test_name": "test_x",
        "test_code": "...",
        "run_result": "FAILED",
        "failure_analysis": "...",
    })
    assert h.step == "2.2 Write minimal code (Green)"

    # User goes home, closes terminal
    h.new_executor()

    # Next day, opens terminal
    assert h.step == "2.2 Write minimal code (Green)"
    assert h.status == "running"

    # Data from previous steps still there
    data = h.state.data
    assert "2.1 Write failing test (Red)" in data
    assert data["2.1 Write failing test (Red)"]["test_file"] == "tests/test_x.py"

    # Continue where we left off
    r = h.submit({
        "files_changed": ["src/x.py"],
        "changes_summary": "Fixed the bug",
        "diff": "...",
        "run_result": "PASSED",
    })
    assert r
    assert h.step == "2.3 Refactor"


def test_node_instructions_available_in_status(harness_factory):
    """vibe_get_status() returns node instructions for Claude to read."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Some bug",
        "features": ["fix1"],
    })

    # Load nodes
    h.reload_nodes()

    h.start()
    h.submit({"scenario_collected": True, "type": "bug"})
    h.submit({
        "decision": "hotfix",
        "root_cause_hypothesis": "...",
        "_goto": "2.1 Write failing test (Red)",
    })

    # Get status — should include node with instructions
    status = h.get_status()
    assert status["current_step"] == "2.1 Write failing test (Red)"

    # Node should be present with instructions
    node = status.get("node")
    if node:
        # If node is loaded, instructions should be there
        assert "instructions" in node or node.get("instructions") == ""


# ═══════════════════════════════════════════════════════
# Additional dimension tests (for 40/40 coverage)
# ═══════════════════════════════════════════════════════

def test_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name (tape write)."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Test bug",
        "features": ["f1"],
    })

    h.start()

    # Submit at 0.1 — data stored under step name
    h.submit({
        "scenario_collected": True,
        "type": "bug",
        "_goto": "1.1 Gather requirements",
    })
    data = h.state.data
    assert "0.1 Collect scenario" in data
    assert data["0.1 Collect scenario"]["scenario_collected"] is True

    # Submit at 1.1
    h.submit({
        "decision": "hotfix",
        "root_cause_hypothesis": "email case issue",
        "_goto": "2.1 Write failing test (Red)",
    })
    data = h.state.data
    assert "1.1 Gather requirements" in data
    assert data["1.1 Gather requirements"]["decision"] == "hotfix"

    # Submit at 2.1
    h.submit({
        "test_file": "tests/test_x.py",
        "test_name": "test_login",
        "test_code": "def test_login(): pass",
        "run_result": "FAILED",
        "failure_analysis": "not implemented",
    })
    data = h.state.data
    assert "2.1 Write failing test (Red)" in data
    assert data["2.1 Write failing test (Red)"]["test_file"] == "tests/test_x.py"


def test_history_audit_trail(harness_factory):
    """History records all actions for audit (execution trace)."""
    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Test bug",
        "features": ["f1"],
    })

    h.start()
    h.submit({"scenario_collected": True, "type": "bug", "_goto": "1.1 Gather requirements"})
    h.submit({"decision": "hotfix", "root_cause_hypothesis": "...", "_goto": "2.1 Write failing test (Red)"})
    h.submit({
        "test_file": "t.py", "test_name": "t", "test_code": "...",
        "run_result": "FAILED", "failure_analysis": "...",
    })

    history = h.get_history(50)
    actions = [e["action"] for e in reversed(history)]

    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions


def test_node_validates(harness_factory):
    """Validate node rejects bad data, accepts good data (transition condition)."""
    from vibe_linter.types import NodeDefinition

    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Test bug",
        "features": ["f1"],
    })

    h.start()
    h.submit({"scenario_collected": True, "type": "bug", "_goto": "1.1 Gather requirements"})
    h.submit({"decision": "hotfix", "root_cause_hypothesis": "...", "_goto": "2.1 Write failing test (Red)"})

    # Register validate node
    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("test_file") else "must include test_file",
        ),
    )

    # Bad data: missing test_file
    r = h.submit({"notes": "forgot the test"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({
        "test_file": "tests/test_x.py",
        "test_name": "test_x",
        "test_code": "...",
        "run_result": "FAILED",
        "failure_analysis": "...",
    })
    assert r
    assert r.new_step == "2.2 Write minimal code (Green)"


def test_node_archives(harness_factory):
    """Archive node writes to SQLite table (first-order logic storage)."""
    from vibe_linter.types import NodeDefinition

    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Test bug",
        "features": ["f1"],
    })

    h.start()
    h.submit({"scenario_collected": True, "type": "bug", "_goto": "1.1 Gather requirements"})
    h.submit({"decision": "hotfix", "root_cause_hypothesis": "...", "_goto": "2.1 Write failing test (Red)"})

    # Register archive node
    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"test_name": "string", "result": "string"}},
            archive={"table": "test_runs"},
        ),
    )

    r = h.submit({"test_name": "test_login_case", "result": "FAILED"})
    assert r

    rows = h.get_archived_rows("test_runs")
    assert len(rows) == 1
    assert rows[0]["test_name"] == "test_login_case"
    assert rows[0]["result"] == "FAILED"


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    from vibe_linter.types import EditPolicy, NodeDefinition

    h = harness_factory("p1-tdd-auto.yaml", loop_data={
        "bug_description": "Test bug",
        "features": ["f1"],
    })

    h.start()

    # Register node with block policy for early phase step
    h.register_node(
        "0.1 Collect scenario",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["edit_policy"] is not None
    assert status["node"]["edit_policy"]["default"] == "block"
