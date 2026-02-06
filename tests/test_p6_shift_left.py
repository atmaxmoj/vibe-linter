"""Test scenarios for Shift-Left Testing workflow (p6-shift-left.yaml).

Tests the Shift-Left Testing workflow including:
- Linear flow with multiple wait-only steps (1.1, 1.3)
- E2E testing 2-way LLM branch (pass -> final report, fail -> unit testing)
- No loops -- purely sequential
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


def _walk_to_e2e(h):
    """Start -> approve waits, submit through to 1.7 E2E testing."""
    h.start()
    h.approve()        # 1.1 wait -> 1.2
    h.submit({})       # 1.2 -> 1.3
    h.approve()        # 1.3 wait -> 1.4
    h.submit({})       # 1.4 -> 1.5
    h.submit({})       # 1.5 -> 1.6
    h.submit({})       # 1.6 -> 1.7
    assert h.step == "1.7 E2E testing"
    assert h.status == "running"


# ================================================================
# Scenario 1: Happy path all pass
# ================================================================


def test_happy_path_all_pass(harness_factory):
    """Shift-left testing a microservices migration: test at every phase from requirements to E2E."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    # 1.1 Review requirements -- wait for stakeholder sign-off
    assert h.step == "1.1 Review requirements"
    assert h.status == "waiting"

    r = h.approve({
        "requirements": "Migrate user-service from monolith to standalone microservice",
        "acceptance_criteria": "Zero downtime, API backward compatible, latency < 100ms p99",
        "reviewer": "Sarah Chen, Tech Lead",
    })
    assert r
    assert r.new_step == "1.2 Requirements testing"
    assert h.step == "1.2 Requirements testing"
    assert h.status == "running"

    r = h.submit({
        "tests_run": "Validated all API contracts against OpenAPI spec",
        "ambiguities_found": 0,
        "missing_requirements": "None -- spec is comprehensive",
    })
    assert r
    assert r.new_step == "1.3 Review design"
    assert h.step == "1.3 Review design"
    assert h.status == "waiting"

    # 1.3 Review design -- wait for architecture review
    r = h.approve({
        "design": "gRPC internal + REST gateway, PostgreSQL, Redis cache, Kubernetes deployment",
        "reviewer": "Mike Torres, Principal Engineer",
    })
    assert r
    assert r.new_step == "1.4 Design testing"
    assert h.step == "1.4 Design testing"
    assert h.status == "running"

    r = h.submit({
        "static_analysis": "Ran SonarQube on proposed schema: 0 critical, 2 minor code smells",
        "architecture_review": "No single points of failure, circuit breaker pattern for downstream calls",
    })
    assert r
    assert r.new_step == "1.5 Unit testing"
    assert h.step == "1.5 Unit testing"

    r = h.submit({
        "framework": "pytest",
        "tests_written": 142,
        "coverage": "94%",
        "mocked_dependencies": ["PostgreSQL", "Redis", "downstream services"],
    })
    assert r
    assert r.new_step == "1.6 Integration testing"
    assert h.step == "1.6 Integration testing"

    r = h.submit({
        "environment": "Docker Compose with real PostgreSQL and Redis",
        "tests_run": 38,
        "passed": 38,
        "api_contract_tests": "All 15 endpoints match OpenAPI spec",
    })
    assert r
    assert r.new_step == "1.7 E2E testing"
    assert h.step == "1.7 E2E testing"

    # E2E tests pass -- route to final report
    r = h.submit_goto("1.8 Final report")
    assert r
    assert r.new_step == "1.8 Final report"
    assert h.step == "1.8 Final report"

    r = h.submit({
        "report_title": "Shift-Left Testing Report: user-service Migration",
        "verdict": "PASS at all levels -- ready for canary deployment",
        "total_tests": 180,
        "total_coverage": "94%",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve({"requirements": "user stories reviewed"})
    assert h.state.data["1.1 Review requirements"]["requirements"] == "user stories reviewed"

    h.submit({"req_tests": "5 tests passed"})
    assert h.state.data["1.2 Requirements testing"]["req_tests"] == "5 tests passed"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory("p6-shift-left.yaml")
    _walk_to_e2e(h)
    h.submit_goto("1.8 Final report")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "approve" in actions
    assert "submit" in actions
    assert "terminate" in actions[-1]


def test_happy_path_cross_executor_at_design(harness_factory):
    """Close executor at design review, reopen, continue."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    h.submit({})
    assert h.step == "1.3 Review design"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "1.3 Review design"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "1.4 Design testing"


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at requirements testing."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    assert h.step == "1.2 Requirements testing"

    h.register_node(
        "1.2 Requirements testing",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("test_count") else "must include test_count",
        ),
    )

    r = h.submit({"notes": "no count"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"test_count": "15"})
    assert r
    assert r.new_step == "1.3 Review design"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes test results to SQLite table."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    assert h.step == "1.2 Requirements testing"

    h.register_node(
        "1.2 Requirements testing",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"test_count": "string", "status": "string"}},
            archive={"table": "req_test_results"},
        ),
    )

    r = h.submit({"test_count": "10", "status": "pass"})
    assert r

    rows = h.get_archived_rows("req_test_results")
    assert len(rows) == 1
    assert rows[0]["test_count"] == "10"
    assert rows[0]["status"] == "pass"


# ================================================================
# Scenario 2: E2E fail retry loop
# ================================================================


def test_e2e_fail_retry_loop(harness_factory):
    """Testing a checkout redesign: E2E Cypress tests fail on payment flow, fix unit tests and retry."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    # Advance through waits and regular steps to E2E
    r = h.approve({"requirements": "Redesigned checkout with Apple Pay and Google Pay support"})
    assert r
    r = h.submit({"req_tests": "Payment method acceptance criteria verified"})
    assert r
    r = h.approve({"design": "Stripe Elements integration with fallback to card form"})
    assert r
    r = h.submit({"design_tests": "API contract validated against Stripe webhooks"})
    assert r
    r = h.submit({"unit_tests": 45, "coverage": "88%"})
    assert r
    r = h.submit({"integration_tests": 12, "stripe_sandbox": "connected"})
    assert r
    assert h.step == "1.7 E2E testing"

    # E2E Cypress test fails: Apple Pay button not rendered in Safari iframe
    r = h.submit_goto("1.5 Unit testing")
    assert r
    assert r.new_step == "1.5 Unit testing"
    assert h.step == "1.5 Unit testing"

    r = h.submit({
        "fix": "Added missing Safari Payment Request API polyfill",
        "new_unit_tests": 3,
        "total_coverage": "91%",
    })
    assert r
    assert r.new_step == "1.6 Integration testing"
    assert h.step == "1.6 Integration testing"

    r = h.submit({"integration_rerun": "All 12 tests pass with polyfill"})
    assert r
    assert r.new_step == "1.7 E2E testing"
    assert h.step == "1.7 E2E testing"

    # Second attempt: all E2E tests pass
    r = h.submit_goto("1.8 Final report")
    assert r
    assert r.new_step == "1.8 Final report"
    assert h.step == "1.8 Final report"

    r = h.submit({
        "report": "Checkout redesign: PASS after Apple Pay polyfill fix",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 3: Reject wait step
# ================================================================


def test_reject_wait_step(harness_factory):
    """Requirements doc incomplete for a data pipeline project: reject, revise, then approve."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    assert h.step == "1.1 Review requirements"
    assert h.status == "waiting"

    r = h.reject("Requirements missing error handling specs for upstream data source failures and SLA definitions")
    assert r
    assert h.step == "1.1 Review requirements"
    assert h.status == "waiting"

    # Requirements updated and resubmitted, now approve
    r = h.approve({
        "requirements": "ETL pipeline: ingest from Kafka, transform, load to Snowflake",
        "error_handling": "Dead letter queue for malformed records, retry with exponential backoff",
        "sla": "99.9% uptime, max 5 min data freshness",
    })
    assert r
    assert r.new_step == "1.2 Requirements testing"
    assert h.step == "1.2 Requirements testing"
    assert h.status == "running"


# ================================================================
# Scenario 4: E2E fail twice then pass
# ================================================================


def test_e2e_fail_twice_then_pass(harness_factory):
    """Real-time chat feature: E2E WebSocket tests fail twice due to race conditions, third attempt succeeds."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    r = h.approve({"requirements": "Real-time chat with WebSocket, typing indicators, read receipts"})
    assert r
    r = h.submit({"req_tests": "Chat protocol spec validated"})
    assert r
    r = h.approve({"design": "Socket.IO with Redis pub/sub for horizontal scaling"})
    assert r
    r = h.submit({"design_tests": "Sequence diagrams verified"})
    assert r
    r = h.submit({"unit_tests": 67, "coverage": "90%"})
    assert r
    r = h.submit({"integration_tests": 15, "websocket_tests": "connected"})
    assert r
    assert h.step == "1.7 E2E testing"

    # First failure: message ordering race condition
    r = h.submit_goto("1.5 Unit testing")
    assert r
    assert r.new_step == "1.5 Unit testing"
    assert h.step == "1.5 Unit testing"
    r = h.submit({"fix": "Added sequence numbers to messages, fixed ordering logic"})
    assert r
    r = h.submit({"integration_rerun": "15/15 pass"})
    assert r
    assert h.step == "1.7 E2E testing"

    # Second failure: typing indicator flickers during reconnect
    r = h.submit_goto("1.5 Unit testing")
    assert r
    assert r.new_step == "1.5 Unit testing"
    assert h.step == "1.5 Unit testing"
    r = h.submit({"fix": "Debounced typing indicator with 500ms cooldown on reconnect"})
    assert r
    r = h.submit({"integration_rerun": "15/15 pass"})
    assert r
    assert h.step == "1.7 E2E testing"

    # Third attempt: all E2E pass
    r = h.submit_goto("1.8 Final report")
    assert r
    assert r.new_step == "1.8 Final report"
    assert h.step == "1.8 Final report"
    r = h.submit({"report": "Chat feature: PASS after 2 rounds of WebSocket race condition fixes"})
    assert r
    assert h.status == "done"


# ================================================================
# Scenario 5: Stop and resume
# ================================================================


def test_stop_and_resume(harness_factory):
    """Testing an ML model serving pipeline: stop for model retraining, resume with new model."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    r = h.approve({"requirements": "ML model serving: real-time inference API with <50ms latency"})
    assert r
    r = h.submit({"req_tests": "Latency SLA and throughput requirements validated"})
    assert r
    r = h.approve({"design": "TensorFlow Serving behind Envoy proxy, gRPC interface"})
    assert r
    assert h.step == "1.4 Design testing"

    # Model retraining in progress -- stop testing until new model is deployed
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.4 Design testing"

    # New model deployed -- resume testing
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "1.4 Design testing"

    # Continue from where we left off
    r = h.submit({
        "design_tests": "Model serving architecture validated, gRPC schema correct",
        "new_model_version": "v2.3.1",
    })
    assert r
    assert r.new_step == "1.5 Unit testing"
    assert h.step == "1.5 Unit testing"


# ================================================================
# Scenario 6: Skip regular step
# ================================================================


def test_skip_regular_step(harness_factory):
    """Hotfix for a logging library: skip requirements and design testing since change is trivial."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    r = h.approve({"requirements": "Bump log4j from 2.14 to 2.17 to patch CVE-2021-44228"})
    assert r
    assert h.step == "1.2 Requirements testing"

    # Skip requirements testing -- it's a dependency version bump
    r = h.skip("Trivial version bump, no functional requirements change")
    assert r
    assert h.step == "1.3 Review design"
    assert h.status == "waiting"

    r = h.approve({"design": "No design change, dependency update only"})
    assert r
    assert h.step == "1.4 Design testing"

    r = h.skip("No architecture impact, pure dependency patch")
    assert r
    assert h.step == "1.5 Unit testing"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Complete shift-left testing for Sprint 14 release, reset for Sprint 15."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    r = h.approve({"requirements": "Sprint 14: user preferences API and notification settings"})
    assert r
    r = h.submit({"req_tests": "All user stories have testable acceptance criteria"})
    assert r
    r = h.approve({"design": "REST endpoints with PostgreSQL JSONB for flexible preferences"})
    assert r
    r = h.submit({"design_tests": "Schema validated, query performance benchmarked"})
    assert r
    r = h.submit({"unit_tests": 55, "coverage": "92%"})
    assert r
    r = h.submit({"integration_tests": 20, "api_tests": "all pass"})
    assert r
    r = h.submit_goto("1.8 Final report")
    assert r
    r = h.submit({"report": "Sprint 14 Shift-Left Report: PASS, ready for release"})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for Sprint 15
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Review requirements"
    assert h.status == "waiting"


# ================================================================
# Scenario 8: Back between steps
# ================================================================


def test_back_between_steps(harness_factory):
    """API gateway refactor: realize requirements testing missed rate limiting, go back to fix it."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    r = h.approve({
        "requirements": "Refactor API gateway to support rate limiting per tenant",
        "reviewer": "Lisa Park, API Team Lead",
    })
    assert r
    assert h.step == "1.2 Requirements testing"

    r = h.submit({
        "tests_run": "Validated endpoint contracts -- missed rate limiting acceptance criteria",
    })
    assert r
    assert h.step == "1.3 Review design"

    r = h.back()
    assert r
    assert h.step == "1.2 Requirements testing"

    # Consecutive back bounces between last two different steps
    r = h.back()
    assert r
    assert h.step == "1.3 Review design"


# ================================================================
# Scenario 9: Goto later step
# ================================================================


def test_goto_later_step(harness_factory):
    """Emergency prod hotfix: skip straight to E2E to validate a one-line config change."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    assert h.step == "1.1 Review requirements"

    # goto sets current_step and status=running (not waiting even for wait steps)
    r = h.goto("1.7 E2E testing")
    assert r
    assert r.new_step == "1.7 E2E testing"
    assert h.step == "1.7 E2E testing"
    assert h.status == "running"

    r = h.submit_goto("1.8 Final report")
    assert r
    assert r.new_step == "1.8 Final report"
    assert h.step == "1.8 Final report"

    r = h.submit({
        "report": "Emergency hotfix: CORS config change validated via E2E, PASS",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML add step
# ================================================================


def test_modify_yaml_add_step(harness_factory):
    """Hot-reload YAML to add a security review step after design testing for a payments service."""
    h = harness_factory("p6-shift-left.yaml")
    r = h.start()
    assert r

    r = h.approve({"requirements": "PCI-DSS compliant payment tokenization service"})
    assert r
    r = h.submit({"req_tests": "PCI compliance acceptance criteria verified"})
    assert r
    r = h.approve({"design": "Vault-based tokenization with HSM key management"})
    assert r
    assert h.step == "1.4 Design testing"

    modified_yaml = """名称: Shift-Left Testing Modified
步骤:
  - 1.1 Review requirements:
      类型: wait

  - 1.2 Requirements testing

  - 1.3 Review design:
      类型: wait

  - 1.4 Design testing

  - 1.4.5 Security review

  - 1.5 Unit testing

  - 1.6 Integration testing

  - 1.7 E2E testing:
      下一步:
        - 如果: "all E2E tests pass"
          去: 1.8 Final report
        - 去: 1.5 Unit testing

  - 1.8 Final report

  - Done:
      类型: terminate
      原因: Shift-left testing complete
"""

    h.reload_yaml(modified_yaml)

    r = h.submit({
        "design_tests": "Tokenization schema validated, HSM key rotation verified",
    })
    assert r
    assert r.new_step == "1.4.5 Security review"
    assert h.step == "1.4.5 Security review"

    r = h.submit({
        "security_review": "OWASP Top 10 checklist passed, PCI-DSS SAQ-D requirements met",
    })
    assert r
    assert r.new_step == "1.5 Unit testing"
    assert h.step == "1.5 Unit testing"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting returns failure."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    assert h.step == "1.1 Review requirements"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    h.stop()
    assert h.status == "stopped"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.goto("1.8 Final report")
    h.submit({})
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    assert h.step == "1.2 Requirements testing"
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


# ================================================================
# Generic / cross-cutting tests
# ================================================================


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve({"reqs": "reviewed"})
    h.submit({"tests": "passed"})

    h.save_checkpoint("at_design_review")

    h.approve()
    h.submit({})
    assert h.step == "1.5 Unit testing"

    restored = h.load_checkpoint("at_design_review")
    assert restored is not None
    assert restored.current_step == "1.3 Review design"
    assert "1.2 Requirements testing" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    assert h.step == "1.2 Requirements testing"

    r = h.retry()
    assert r
    assert h.step == "1.2 Requirements testing"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p6-shift-left.yaml")

    for _ in range(3):
        h.start()
        h.approve()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Review requirements"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.goto("1.8 Final report")
    h.submit({})
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()
    h.submit({})
    assert h.step == "1.3 Review design"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.3 Review design"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()  # Move from waiting to running at 1.2
    h.register_node(
        "1.2 Requirements testing",
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
    h = harness_factory("p6-shift-left.yaml")
    h.start()
    h.approve()  # Move from waiting to running at 1.2
    h.register_node(
        "1.2 Requirements testing",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
