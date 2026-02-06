"""Test scenarios for Risk-Based Testing workflow (p6-risk-based.yaml).

Tests the Risk-Based Testing workflow including:
- Risk assessment phase (identify, prioritize)
- Risk loop with 3-way branching (high/medium-low/no defect)
- Inner wait step for high severity fixes
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


def _walk_to_risk_loop(h):
    """Start -> identify risks -> prioritize -> enter risk loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Design risk test"
    assert h.status == "running"


def _complete_one_risk_no_defect(h):
    """Complete one risk test with no defect found."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit_goto("2.0 Risk loop")  # no defect -> loop header


# ================================================================
# Scenario 1: Five risk points tested (all pass)
# ================================================================


def test_five_risk_points_tested(harness_factory):
    """Test an online banking platform: 5 security risk areas, all pass penetration testing."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["sql_injection", "xss_attacks", "auth_bypass", "session_hijacking", "api_rate_abuse"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Identify risks"
    assert h.status == "running"

    r = h.submit({
        "application": "NetBank Online Banking v4.0",
        "risk_areas": [
            "SQL injection on login and search endpoints",
            "Cross-site scripting in user-generated content",
            "Authentication bypass via token manipulation",
            "Session hijacking through cookie theft",
            "API rate limiting abuse for brute-force attacks",
        ],
    })
    assert r
    assert r.new_step == "1.2 Prioritize by severity"
    assert h.step == "1.2 Prioritize by severity"

    r = h.submit({
        "risk_matrix": {
            "sql_injection": {"severity": "critical", "likelihood": "medium"},
            "xss_attacks": {"severity": "high", "likelihood": "high"},
            "auth_bypass": {"severity": "critical", "likelihood": "low"},
            "session_hijacking": {"severity": "high", "likelihood": "medium"},
            "api_rate_abuse": {"severity": "medium", "likelihood": "high"},
        },
    })
    assert r
    assert r.new_step == "2.1 Design risk test"
    assert h.step == "2.1 Design risk test"

    risk_tests = [
        {"design": "Parameterized query injection attempts on /login, /search, /transfer", "result": "All inputs properly sanitized, prepared statements used"},
        {"design": "Inject script tags in transaction memos, profile bio, support messages", "result": "Content Security Policy blocks inline scripts, output encoding applied"},
        {"design": "Tamper JWT tokens, replay expired tokens, forge admin claims", "result": "Token signature verification strict, expiry enforced, role claims validated"},
        {"design": "Steal session cookies via XSS (blocked), test SameSite/Secure flags", "result": "Cookies set with SameSite=Strict, Secure, HttpOnly flags"},
        {"design": "Send 1000 login attempts in 60 seconds from single IP", "result": "Rate limiter kicks in at 10 attempts, CAPTCHA after 5 failures"},
    ]

    for i in range(5):
        r = h.submit({"test_design": risk_tests[i]["design"]})
        assert r
        assert r.new_step == "2.2 Execute test"
        assert h.step == "2.2 Execute test"

        r = h.submit({"result": risk_tests[i]["result"]})
        assert r
        assert r.new_step == "2.3 Evaluate result"
        assert h.step == "2.3 Evaluate result"

        # No defect found
        r = h.submit_goto("2.0 Risk loop")
        assert r
        if i < 4:
            assert r.new_step == "2.1 Design risk test"
            assert h.step == "2.1 Design risk test"

    assert h.step == "3.1 Risk test report"

    r = h.submit({
        "report": "NetBank v4.0 Security Risk Assessment: ALL PASS",
        "total_risks_tested": 5,
        "defects_found": 0,
        "recommendation": "Security posture is strong, approve for production deployment",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_five_risks_data_accumulates(harness_factory):
    """Data submitted at risk steps persists in state.data."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.submit({"risks": "SQL injection, XSS"})
    assert h.state.data["1.1 Identify risks"]["risks"] == "SQL injection, XSS"

    h.submit({"priority": "high"})
    assert h.state.data["1.2 Prioritize by severity"]["priority"] == "high"

    h.submit({"test_design": "penetration test"})
    assert h.state.data["2.1 Design risk test"]["test_design"] == "penetration test"


def test_five_risks_history_audit(harness_factory):
    """History contains expected actions for full walkthrough."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Risk loop")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_five_risks_cross_executor_in_loop(harness_factory):
    """Close executor mid-loop, reopen, state persists."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1", "r2", "r3"]},
    )
    _walk_to_risk_loop(h)
    h.submit({})
    assert h.step == "2.2 Execute test"

    h.new_executor()

    assert h.step == "2.2 Execute test"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Risk loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_five_risks_node_validates(harness_factory):
    """Validate node rejects bad data at risk test design."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    _walk_to_risk_loop(h)

    h.register_node(
        "2.1 Design risk test",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("test_type") else "must include test_type",
        ),
    )

    r = h.submit({"notes": "forgot test_type"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"test_type": "penetration"})
    assert r
    assert r.new_step == "2.2 Execute test"


def test_five_risks_node_archives(harness_factory):
    """Archive node writes test results to SQLite table."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1", "r2"]},
    )
    _walk_to_risk_loop(h)

    h.register_node(
        "2.2 Execute test",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"result": "string", "risk_id": "string"}},
            archive={"table": "risk_results"},
        ),
    )

    h.submit({})
    h.submit({"result": "pass", "risk_id": "r1"})
    h.submit_goto("2.0 Risk loop")
    h.submit({})
    h.submit({"result": "fail", "risk_id": "r2"})

    rows = h.get_archived_rows("risk_results")
    assert len(rows) == 2
    assert rows[0]["result"] == "pass"
    assert rows[1]["risk_id"] == "r2"


# ================================================================
# Scenario 2: High risk found, wait for fix
# ================================================================


def test_high_risk_found_wait_for_fix(harness_factory):
    """Testing a medical records system: found critical data exposure vulnerability, wait for hotfix then retest."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["patient_data_exposure"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["Patient data exposed via unauthenticated API endpoint"],
        "compliance": "HIPAA violation risk",
    })
    assert r
    r = h.submit({
        "priority": "critical",
        "impact": "PHI (Protected Health Information) accessible without authentication",
    })
    assert r

    r = h.submit({
        "test_design": "Attempt to access /api/v2/patients without auth token, test with expired token, test with wrong role",
    })
    assert r
    assert r.new_step == "2.2 Execute test"
    assert h.step == "2.2 Execute test"

    r = h.submit({
        "result": "CRITICAL: /api/v2/patients returns full patient records without any authentication",
        "evidence": "curl -X GET https://medapp.example.com/api/v2/patients returns 200 with PHI data",
    })
    assert r
    assert r.new_step == "2.3 Evaluate result"
    assert h.step == "2.3 Evaluate result"

    # High severity defect -- HIPAA violation
    r = h.submit_goto("2.4 Wait for fix")
    assert r
    assert r.new_step == "2.4 Wait for fix"
    assert h.step == "2.4 Wait for fix"
    assert h.status == "waiting"

    # Dev team deployed emergency fix: added auth middleware
    r = h.approve({
        "fix_description": "Added JWT authentication middleware to all /api/v2/ endpoints",
        "fix_commit": "abc123def",
        "deployed_at": "2024-03-15T14:30:00Z",
    })
    assert r
    assert r.new_step == "2.2 Execute test"
    assert h.step == "2.2 Execute test"
    assert h.status == "running"

    # Retest -- endpoint now returns 401 without auth
    r = h.submit({
        "result": "PASS: /api/v2/patients returns 401 Unauthorized without valid JWT",
        "additional_checks": "Expired tokens return 401, wrong role returns 403",
    })
    assert r
    assert r.new_step == "2.3 Evaluate result"
    assert h.step == "2.3 Evaluate result"

    r = h.submit_goto("2.0 Risk loop")
    assert r
    assert h.step == "3.1 Risk test report"


def test_high_risk_submit_on_waiting_fails(harness_factory):
    """Submit while at wait-for-fix step fails."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    _walk_to_risk_loop(h)
    h.submit({})
    h.submit({})
    h.submit_goto("2.4 Wait for fix")
    assert h.step == "2.4 Wait for fix"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_high_risk_cross_executor_at_wait(harness_factory):
    """Close executor at wait-for-fix, reopen, still waiting."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    _walk_to_risk_loop(h)
    h.submit({})
    h.submit({})
    h.submit_goto("2.4 Wait for fix")
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "2.4 Wait for fix"
    assert h.status == "waiting"

    r = h.approve({})
    assert r
    assert r.new_step == "2.2 Execute test"


# ================================================================
# Scenario 3: Medium/low defect record
# ================================================================


def test_medium_low_defect_record(harness_factory):
    """Testing an e-commerce platform: medium-severity XSS in product reviews, log it and continue to next risk."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["xss_in_reviews", "payment_validation"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["XSS in product reviews", "Payment amount validation bypass"],
    })
    assert r
    r = h.submit({
        "priority_order": "XSS first (high likelihood), payment validation second (high impact)",
    })
    assert r

    # Risk 1: XSS in reviews -- medium defect (stored XSS but behind auth)
    r = h.submit({
        "test_design": "Submit review with <script>alert(1)</script> and <img onerror=alert(1) src=x>",
    })
    assert r
    r = h.submit({
        "result": "MEDIUM: <img> tag renders unescaped in review display, but requires authenticated user",
    })
    assert r
    assert h.step == "2.3 Evaluate result"

    r = h.submit_goto("2.5 Record defect")
    assert r
    assert r.new_step == "2.5 Record defect"
    assert h.step == "2.5 Record defect"

    r = h.submit({
        "defect_id": "SEC-442",
        "severity": "medium",
        "title": "Stored XSS via product review image tags",
        "mitigation": "Apply HTML entity encoding to review content before rendering",
    })
    assert r
    assert r.new_step == "2.1 Design risk test"
    assert h.step == "2.1 Design risk test"

    # Risk 2: payment validation -- no defect
    r = h.submit({
        "test_design": "Intercept checkout request, modify price to $0.01, submit with tampered payload",
    })
    assert r
    r = h.submit({
        "result": "PASS: Server recalculates total from cart items, tampered amount rejected",
    })
    assert r
    r = h.submit_goto("2.0 Risk loop")
    assert r

    assert h.step == "3.1 Risk test report"


# ================================================================
# Scenario 4: No defects
# ================================================================


def test_no_defects(harness_factory):
    """Test a file storage service: both encryption-at-rest and access control risks pass cleanly."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["encryption_at_rest", "access_control"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["Data not encrypted at rest in S3 buckets", "Broken access control on shared files"],
    })
    assert r
    r = h.submit({
        "priority_order": "Both critical for SOC 2 compliance audit next month",
    })
    assert r

    for _i in range(2):
        r = h.submit({"test_design": "Verify encryption and ACL enforcement"})
        assert r
        r = h.submit({"result": "PASS: properly configured and enforced"})
        assert r
        r = h.submit_goto("2.0 Risk loop")
        assert r

    assert h.step == "3.1 Risk test report"
    r = h.submit({
        "report": "CloudStore Risk Assessment: PASS, SOC 2 compliant",
    })
    assert r
    assert h.status == "done"


# ================================================================
# Scenario 5: Empty risk list
# ================================================================


def test_empty_risk_list(harness_factory):
    """New internal tool with no external attack surface: risk list is empty, skip testing entirely."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": []},
    )
    r = h.start()
    assert r

    r = h.submit({
        "application": "Internal Slack Bot for PTO Tracking",
        "risk_areas": "None identified -- no external endpoints, no PII, internal-only OAuth",
    })
    assert r
    r = h.submit({
        "priority_order": "N/A -- no risks to prioritize, tool runs in sandboxed environment",
    })
    assert r

    # Loop should exit immediately
    assert h.step == "3.1 Risk test report"
    assert h.status == "running"


# ================================================================
# Scenario 6: Stop then resume
# ================================================================


def test_stop_then_resume(harness_factory):
    """Penetration testing a VPN service: stop when test environment is recycled, resume with fresh env."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["tunnel_escape", "dns_leak"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["VPN tunnel escape via IPv6 fallback", "DNS leak exposing real IP"],
    })
    assert r
    r = h.submit({
        "priority_order": "Tunnel escape first (critical), DNS leak second (high)",
    })
    assert r
    r = h.submit({
        "test_design": "Force IPv6 traffic while VPN tunnel is active, monitor for non-tunnel packets",
    })
    assert r
    assert h.step == "2.2 Execute test"

    # Test environment recycled by DevOps -- stop testing
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Execute test"

    # Fresh test environment provisioned -- resume
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Execute test"

    r = h.submit({
        "result": "PASS: All IPv6 traffic properly routed through VPN tunnel, kill switch activates on disconnect",
    })
    assert r
    assert r.new_step == "2.3 Evaluate result"
    assert h.step == "2.3 Evaluate result"


# ================================================================
# Scenario 7: Skip low risk
# ================================================================


def test_skip_low_risk(harness_factory):
    """Testing a blog platform: skip low-risk CSS injection test, focus on CSRF vulnerability."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["css_injection", "csrf_vulnerability"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["CSS injection in theme customizer", "CSRF on account settings"],
    })
    assert r
    r = h.submit({
        "priority": "CSS injection is low-risk (sandboxed iframe), CSRF is high-risk",
    })
    assert r

    # Skip CSS injection design -- low risk, sandboxed
    assert h.step == "2.1 Design risk test"
    r = h.skip("CSS injection is sandboxed in iframe, risk is negligible")
    assert r
    assert h.step == "2.2 Execute test"

    r = h.submit({"result": "PASS: CSS is sandboxed, no escape possible"})
    assert r
    r = h.submit_goto("2.0 Risk loop")
    assert r
    assert h.step == "2.1 Design risk test"

    # Complete CSRF test normally
    r = h.submit({
        "test_design": "Craft forged POST to /api/settings from external page, check CSRF token enforcement",
    })
    assert r
    r = h.submit({
        "result": "PASS: CSRF token required and validated on all state-changing requests",
    })
    assert r
    r = h.submit_goto("2.0 Risk loop")
    assert r
    assert h.step == "3.1 Risk test report"


# ================================================================
# Scenario 8: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish Q3 risk assessment for a SaaS platform, reset for Q4 reassessment."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["data_breach_risk"]},
    )
    r = h.start()
    assert r

    r = h.submit({"risks": ["Q3 data breach risk assessment for CloudApp SaaS"]})
    assert r
    r = h.submit({"priority": "critical -- required for insurance renewal"})
    assert r
    r = h.submit({"test_design": "Attempt data exfiltration via API, file download, and export features"})
    assert r
    r = h.submit({"result": "PASS: All data access properly gated by role-based ACL"})
    assert r
    r = h.submit_goto("2.0 Risk loop")
    assert r
    r = h.submit({"report": "Q3 Risk Assessment: PASS, data breach risk mitigated"})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for Q4 reassessment
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Identify risks"
    assert h.status == "running"


# ================================================================
# Scenario 9: Goto
# ================================================================


def test_goto(harness_factory):
    """Emergency audit request: skip risk testing, jump directly to report with existing findings."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["compliance_gap", "infrastructure_risk"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["SOC 2 compliance gaps", "Infrastructure single points of failure"],
    })
    assert r
    r = h.submit({
        "priority": "Auditor arriving tomorrow, need report from previous assessment",
    })
    assert r

    # Skip testing -- use findings from last month's assessment
    r = h.goto("3.1 Risk test report")
    assert r
    assert r.new_step == "3.1 Risk test report"
    assert h.step == "3.1 Risk test report"
    assert h.status == "running"

    r = h.submit({
        "report": "Using prior assessment findings for emergency audit -- full reassessment scheduled for next quarter",
    })
    assert r
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML
# ================================================================


def test_modify_yaml(harness_factory):
    """Testing a healthcare API: add a coverage verification step to the risk loop mid-execution."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["phi_exposure"]},
    )
    r = h.start()
    assert r

    r = h.submit({
        "risks": ["PHI exposure via HL7 FHIR API"],
        "compliance": "HIPAA",
    })
    assert r
    r = h.submit({
        "priority": "critical -- PHI exposure is a reportable breach",
    })
    assert r
    r = h.submit({
        "test_design": "Attempt to access /fhir/Patient without OAuth2 bearer token",
    })
    assert r
    assert h.step == "2.2 Execute test"

    modified_yaml = """名称: Risk-Based Testing Modified
步骤:
  - 1.1 Identify risks
  - 1.2 Prioritize by severity

  - 2.0 Risk loop:
      遍历: "risks"
      子步骤:
        - 2.1 Design risk test
        - 2.2 Execute test
        - 2.2.5 Verify test coverage
        - 2.3 Evaluate result:
            下一步:
              - 如果: "high severity defect found"
                去: 2.4 Wait for fix
              - 如果: "medium or low defect found"
                去: 2.5 Record defect
              - 去: 2.0 Risk loop
        - 2.4 Wait for fix:
            类型: wait
            下一步: 2.2 Execute test
        - 2.5 Record defect

  - 3.1 Risk test report

  - Done:
      类型: terminate
"""

    h.reload_yaml(modified_yaml)

    r = h.submit({
        "result": "PASS: /fhir/Patient returns 401 without valid OAuth2 token",
    })
    assert r
    assert r.new_step == "2.2.5 Verify test coverage"
    assert h.step == "2.2.5 Verify test coverage"

    r = h.submit({
        "coverage_check": "All 12 FHIR endpoints tested, token expiry and scope enforcement verified",
    })
    assert r
    assert r.new_step == "2.3 Evaluate result"
    assert h.step == "2.3 Evaluate result"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
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
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.goto("3.1 Risk test report")
    h.submit({})
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
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
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.submit({"risks_found": "SQL injection"})
    h.submit({"priority": "critical"})

    h.save_checkpoint("at_risk_loop")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Risk loop")
    assert h.step == "3.1 Risk test report"

    restored = h.load_checkpoint("at_risk_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Design risk test"
    assert "1.1 Identify risks" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    assert h.step == "1.1 Identify risks"

    r = h.retry()
    assert r
    assert h.step == "1.1 Identify risks"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Identify risks"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.goto("3.1 Risk test report")
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
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1", "r2", "r3"]},
    )
    _walk_to_risk_loop(h)

    loop_info = h.state.loop_state["2.0 Risk loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_risk_no_defect(h)

    loop_info = h.state.loop_state["2.0 Risk loop"]
    assert loop_info["i"] == 1


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.register_node(
        "1.1 Identify risks",
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
        "p6-risk-based.yaml",
        loop_data={"risks": ["r1"]},
    )
    h.start()
    h.register_node(
        "1.1 Identify risks",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
