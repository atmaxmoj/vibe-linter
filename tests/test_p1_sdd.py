"""SDD Development workflow tests.

Workflow structure:
  1.1 Write specification (wait)
  1.2 Generate implementation plan
  1.3 Plan review (wait, LLM: approved->2.0, else->1.2)
  2.0 Phase loop (iterate: phases)
    2.1 Implement phase
    2.2 Run phase tests
    2.3 Compliance check (LLM: conforms->2.0, needs fixes->2.1, spec issues->1.1)
  3.1 Integration testing
  3.2 Final verification (LLM: conforms->Done, else->2.0)
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


def _walk_to_plan_review(h):
    """Common helper: start -> approve 1.1 -> submit 1.2 -> arrive at 1.3 (waiting)."""
    h.start()
    h.approve({"spec": "detailed specification"})
    h.submit({"plan": "implementation plan v1"})
    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"


def _enter_phase_loop(h):
    """Common helper: get past plan review into loop iteration 1."""
    _walk_to_plan_review(h)
    h.approve()
    h.submit_goto("2.0 Phase loop")
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"


def _do_one_phase_pass(h, data=None):
    """Complete one implement-test-compliance cycle ending at compliance check."""
    h.submit(data or {"impl": "code"})    # 2.1 -> 2.2
    h.submit(data or {"tests": "pass"})   # 2.2 -> 2.3
    assert h.step == "2.3 Compliance check"


# ===============================================================
# Scenario 1: Four phases complete (original)
# ===============================================================

def test_four_phases_complete(harness_factory):
    """Build OAuth2 server per RFC 6749: 4-phase implementation from formal spec."""
    h = harness_factory(
        "p1-sdd.yaml",
        loop_data={"phases": [
            "authorization_endpoint", "token_endpoint",
            "resource_protection", "token_revocation",
        ]},
    )
    r = h.start()
    assert r

    assert h.step == "1.1 Write specification"
    assert h.status == "waiting"

    # Wait step arrival: submit is rejected
    r = h.submit({})
    assert not r
    assert "waiting" in r.message.lower()

    # Approve the specification
    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"
    assert h.status == "running"

    r = h.submit({
        "plan": "4-phase implementation of OAuth2 Authorization Server",
        "phases": [
            "Phase 1: Authorization endpoint (GET /authorize, consent screen, auth code grant)",
            "Phase 2: Token endpoint (POST /token, auth code exchange, refresh token)",
            "Phase 3: Resource protection (Bearer token validation middleware)",
            "Phase 4: Token revocation (POST /revoke per RFC 7009)",
        ],
        "tech_stack": "Python + FastAPI + SQLAlchemy + PyJWT",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert h.step == "1.3 Plan review"
    assert h.status == "running"

    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert r.new_step == "2.1 Implement phase"
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    # Verify loop first entry
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Phase implementation data for each iteration
    phase_data = [
        {
            "impl": {
                "files": ["oauth2/endpoints/authorize.py", "oauth2/models/auth_code.py"],
                "summary": "GET /authorize with PKCE support, consent screen, auth code storage",
            },
            "tests": {
                "file": "tests/test_authorize.py",
                "passed": 12, "failed": 0,
                "coverage": "91%",
            },
        },
        {
            "impl": {
                "files": ["oauth2/endpoints/token.py", "oauth2/models/token.py"],
                "summary": "POST /token with authorization_code and refresh_token grant types",
            },
            "tests": {
                "file": "tests/test_token.py",
                "passed": 18, "failed": 0,
                "coverage": "89%",
            },
        },
        {
            "impl": {
                "files": ["oauth2/middleware/bearer.py", "oauth2/introspection.py"],
                "summary": "Bearer token validation middleware with JWT signature verification",
            },
            "tests": {
                "file": "tests/test_bearer.py",
                "passed": 10, "failed": 0,
                "coverage": "94%",
            },
        },
        {
            "impl": {
                "files": ["oauth2/endpoints/revoke.py"],
                "summary": "POST /revoke per RFC 7009, invalidates access and refresh tokens",
            },
            "tests": {
                "file": "tests/test_revoke.py",
                "passed": 6, "failed": 0,
                "coverage": "97%",
            },
        },
    ]

    for i in range(4):
        r = h.submit(phase_data[i]["impl"])
        assert r
        assert r.new_step == "2.2 Run phase tests"
        assert h.step == "2.2 Run phase tests"
        assert h.status == "running"

        r = h.submit(phase_data[i]["tests"])
        assert r
        assert h.step == "2.3 Compliance check"
        assert h.status == "running"

        r = h.submit_goto("2.0 Phase loop")
        assert r
        if i < 3:
            assert r.new_step == "2.1 Implement phase"
            assert h.step == "2.1 Implement phase"
            # Verify iteration count
            status = h.get_status()
            assert f"[{i + 2}/" in status["display_path"]

    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Phase loop" not in h.state.loop_state

    r = h.submit({
        "command": "pytest tests/integration/ -v",
        "scenarios": ["full auth code flow", "token refresh cycle", "revocation cascade"],
        "passed": 46, "failed": 0,
    })
    assert r
    assert h.step == "3.2 Final verification"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state: further submits rejected
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message


def test_code_not_conforming(harness_factory):
    """JWT library: implementation fails compliance twice (missing nbf claim, wrong alg header)."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["jwt_signing"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"

    r = h.submit({
        "plan": "Implement JWT signing per RFC 7519 Section 7.1",
        "spec_requirements": [
            "MUST include iss, sub, aud, exp, nbf, iat claims",
            "MUST support RS256 and ES256 algorithms",
            "alg header MUST match the key type",
        ],
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    # Attempt 1: missing nbf claim
    r = h.submit({
        "files": ["jwt_lib/signer.py"],
        "note": "Implemented RS256 signing with iss, sub, exp, iat but forgot nbf",
    })
    assert r
    r = h.submit({
        "passed": 8, "failed": 1,
        "failure": "test_nbf_claim_present: AssertionError: 'nbf' not in token claims",
    })
    assert r
    assert h.step == "2.3 Compliance check"
    r = h.submit_goto("2.1 Implement phase")
    assert r
    assert r.new_step == "2.1 Implement phase"
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    # Attempt 2: nbf fixed but alg header says RS256 when using ES256 key
    r = h.submit({
        "files_modified": ["jwt_lib/signer.py"],
        "fix": "Added nbf = iat (issued-at time), but alg header hardcoded to RS256",
    })
    assert r
    r = h.submit({
        "passed": 9, "failed": 1,
        "failure": "test_es256_alg_header: alg='RS256' but key is EC P-256",
    })
    assert r
    assert h.step == "2.3 Compliance check"
    r = h.submit_goto("2.1 Implement phase")
    assert r
    assert r.new_step == "2.1 Implement phase"
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    # Attempt 3: all compliance checks pass
    r = h.submit({
        "files_modified": ["jwt_lib/signer.py"],
        "fix": "Derive alg header from key type: RSAKey->RS256, ECKey->ES256",
    })
    assert r
    r = h.submit({
        "passed": 12, "failed": 0,
        "note": "All RFC 7519 Section 7.1 requirements satisfied",
    })
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Phase loop" not in h.state.loop_state


def test_spec_has_issues(harness_factory):
    """GraphQL API spec: discover contradictory pagination spec mid-phase, rewrite spec."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["queries", "mutations"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"

    r = h.submit({
        "plan": "GraphQL API in 2 phases: queries (read) then mutations (write)",
        "spec_issue_later": "Pagination spec says both offset and cursor-based, contradictory",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    # Phase 1 (queries): implement and test
    r = h.submit({
        "files": ["graphql/queries/users.py", "graphql/queries/products.py"],
        "note": "Implemented cursor-based pagination per spec Section 3.2",
    })
    assert r
    r = h.submit({"passed": 14, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    # Increments to i=1 (mutations)
    assert h.step == "2.1 Implement phase"

    # Phase 2 (mutations): hit the spec contradiction
    r = h.submit({
        "files": ["graphql/mutations/create_order.py"],
        "note": "Spec Section 5.1 says use offset pagination for order history, "
               "but Section 3.2 mandates cursor-based for all list endpoints",
    })
    assert r
    r = h.submit({
        "passed": 8, "failed": 3,
        "failures": "Pagination tests fail: spec contradicts itself on offset vs cursor",
    })
    assert r
    assert h.step == "2.3 Compliance check"

    # Spec issue discovered mid-phase2, jump back to spec
    r = h.submit_goto("1.1 Write specification")
    assert r
    assert r.new_step == "1.1 Write specification"
    assert h.step == "1.1 Write specification"
    assert h.status == "waiting"

    # Rewrite spec to use cursor-based pagination everywhere
    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"
    assert h.status == "running"

    r = h.submit({
        "plan": "Updated plan: cursor-based pagination for ALL list endpoints (Sections 3.2, 5.1 unified)",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM again
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    # Loop state still has i=1, n=2 from before.
    # _handle_loop increments i from 1 to 2, which equals n=2, so loop exits.
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Phase loop" not in h.state.loop_state

    r = h.submit({
        "command": "pytest tests/integration/ -v",
        "passed": 22, "failed": 0,
    })
    assert r
    assert h.step == "3.2 Final verification"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_plan_review_rejected(harness_factory):
    """RBAC system: plan rejected twice (missing audit trail, wrong granularity), approved on 3rd."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["rbac_core"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"

    # Plan V1: no audit trail
    r = h.submit({
        "plan": "Simple role-based access: User -> Role -> Permission mapping",
        "missing": "No audit trail for permission changes",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto -- rejected
    r = h.approve()
    assert r
    assert h.step == "1.3 Plan review"
    assert h.status == "running"

    r = h.submit_goto("1.2 Generate implementation plan")
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"
    assert h.status == "running"

    # Plan V2: added audit but wrong granularity (role-level instead of permission-level)
    r = h.submit({
        "plan": "RBAC with audit trail: role assignments logged, but checks at role level only",
        "missing": "Spec requires permission-level checks, not role-level",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"

    # Back at 1.3 Plan review (waiting again) -- rejected again
    r = h.approve()
    assert r
    assert h.step == "1.3 Plan review"
    assert h.status == "running"

    r = h.submit_goto("1.2 Generate implementation plan")
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"

    # Plan V3: audit trail + permission-level granularity
    r = h.submit({
        "plan": (
            "RBAC with permission-level checks and full audit trail:\n"
            "User -> Role -> Permission (fine-grained)\n"
            "AuditLog records every grant/revoke with actor, target, timestamp"
        ),
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert r.new_step == "2.1 Implement phase"
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"


def test_mid_spec_update_stop_resume(harness_factory):
    """Encryption library: stop mid-test, add code review step via YAML, resume."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["aes_encryption"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    r = h.submit({
        "plan": "Implement AES-256-GCM encryption per NIST SP 800-38D",
    })
    assert r
    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    r = h.submit({
        "files": ["crypto/aes_gcm.py"],
        "summary": "AES-256-GCM with 96-bit nonce, 128-bit auth tag",
    })
    assert r

    assert h.step == "2.2 Run phase tests"
    assert h.status == "running"

    # Security team mandates: all crypto code must have code review before testing
    r = h.stop()
    assert r
    assert r.message
    assert h.status == "stopped"
    assert h.step == "2.2 Run phase tests"

    modified_yaml = """名称: SDD Development
描述: Spec-Driven Development with code review

步骤:
  - 1.1 Write specification:
      类型: wait

  - 1.2 Generate implementation plan

  - 1.3 Plan review:
      类型: wait
      下一步:
        - 如果: "plan is approved"
          去: 2.0 Phase loop
        - 去: 1.2 Generate implementation plan

  - 2.0 Phase loop:
      遍历: "phases"
      子步骤:
        - 2.1 Implement phase
        - 2.1b Code review
        - 2.2 Run phase tests
        - 2.3 Compliance check:
            下一步:
              - 如果: "implementation conforms to spec"
                去: 2.0 Phase loop
              - 如果: "implementation does not conform, code needs fixes"
                去: 2.1 Implement phase
              - 如果: "spec itself has issues"
                去: 1.1 Write specification

  - 3.1 Integration testing

  - 3.2 Final verification:
      下一步:
        - 如果: "all phases conform to spec"
          去: Done
        - 去: 2.0 Phase loop

  - Done:
      类型: terminate
      原因: All phases conform to specification
"""

    h.reload_yaml(modified_yaml)

    # 2.2 is NOT a wait step, so resume sets "running"
    r = h.resume()
    assert r
    assert r.new_step == "2.2 Run phase tests"
    assert h.status == "running"
    assert h.step == "2.2 Run phase tests"


def test_skip_phase(harness_factory):
    """WebSocket protocol: skip testing phase 1 (handshake already validated by external tool)."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["ws_handshake", "ws_framing"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"

    r = h.submit({
        "plan": "WebSocket implementation per RFC 6455 in 2 phases: handshake, then framing",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    # Phase 1: handshake -- implement it
    r = h.submit({
        "files": ["ws/handshake.py"],
        "summary": "HTTP Upgrade with Sec-WebSocket-Key validation per RFC 6455 Section 4",
    })
    assert r
    assert r.new_step == "2.2 Run phase tests"
    assert h.step == "2.2 Run phase tests"

    # Skip testing handshake -- already validated with Autobahn test suite externally
    r = h.skip("Handshake validated by Autobahn|Testsuite (external compliance tool)")
    assert r
    assert h.step == "2.3 Compliance check"
    assert h.status == "running"

    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert r.new_step == "2.1 Implement phase"
    assert h.step == "2.1 Implement phase"

    # Phase 2: framing -- full implementation and testing
    r = h.submit({
        "files": ["ws/framing.py"],
        "summary": "Frame parsing: opcode, masking, payload length (7/16/64-bit)",
    })
    assert r
    r = h.submit({
        "passed": 24, "failed": 0,
        "note": "All frame types tested: text, binary, ping, pong, close",
    })
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r

    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    # Verify loop_state is cleaned up
    assert "2.0 Phase loop" not in h.state.loop_state

    r = h.submit({
        "command": "pytest tests/integration/test_websocket.py -v",
        "passed": 31, "failed": 0,
    })
    assert r
    assert h.step == "3.2 Final verification"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_empty_phase_list(harness_factory):
    """Spec-only documentation project: no implementation phases, skip to integration."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": []})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"

    r = h.submit({
        "plan": "Spec validation only -- no implementation phases needed",
        "note": "This is a documentation-only spec review, implementation handled by partner team",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r

    assert h.step == "3.1 Integration testing"
    assert h.status == "running"


def test_back(harness_factory):
    """Message queue protocol: use back() to revise spec and re-implement after finding ambiguity."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["message_publish"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"

    # Realize spec needs clarification on message ordering guarantees -- go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Write specification"
    assert h.step == "1.1 Write specification"
    assert h.status == "running"

    # 1.1 is a wait step but back() sets status to "running"
    r = h.submit({
        "spec_update": "Added Section 4.3: Messages MUST be delivered in FIFO order per partition",
    })
    assert r
    assert r.new_step == "1.2 Generate implementation plan"
    assert h.step == "1.2 Generate implementation plan"

    r = h.submit({
        "plan": "Message publish with partition-level FIFO ordering, WAL for durability",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "2.1 Implement phase"

    r = h.submit({
        "files": ["mq/publisher.py", "mq/partition.py"],
        "summary": "Partition-aware publisher with WAL append",
    })
    assert r
    assert r.new_step == "2.2 Run phase tests"
    assert h.step == "2.2 Run phase tests"

    # Realize the partition logic is wrong, go back
    r = h.back()
    assert r
    assert r.new_step == "2.1 Implement phase"
    assert h.step == "2.1 Implement phase"
    assert h.status == "running"

    r = h.submit({
        "files_modified": ["mq/partition.py"],
        "fix": "Fixed partition assignment: use consistent hashing instead of round-robin",
    })
    assert r
    r = h.submit({"passed": 16, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r

    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    r = h.submit({"passed": 22, "failed": 0})
    assert r
    assert h.step == "3.2 Final verification"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_done_then_reset(harness_factory):
    """DNS resolver V1 complete, reset for V2 with DoH (DNS-over-HTTPS) support."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["dns_resolution"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    r = h.submit({
        "plan": "V1: Standard DNS resolver per RFC 1035 (UDP/TCP, A/AAAA/CNAME records)",
    })
    assert r
    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    r = h.submit({
        "files": ["dns/resolver.py", "dns/packet.py"],
        "summary": "UDP-first with TCP fallback, A/AAAA/CNAME query types",
    })
    assert r
    r = h.submit({"passed": 18, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r

    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    r = h.submit({"passed": 24, "failed": 0})
    assert r
    assert h.step == "3.2 Final verification"

    r = h.submit_goto("Done")
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Verify done state: further submits rejected
    r = h.submit({})
    assert not r
    assert "completed" in r.message.lower() or "Workflow is already completed" in r.message

    # V1 shipped. Reset for V2: add DNS-over-HTTPS per RFC 8484
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Write specification"
    assert h.status == "waiting"


def test_goto_integration(harness_factory):
    """TLS handshake library: phases done offline, goto integration to verify the full stack."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["tls_handshake", "tls_record"]})
    r = h.start()
    assert r

    r = h.approve()
    assert r
    assert r.new_step == "1.2 Generate implementation plan"

    r = h.submit({
        "plan": "TLS 1.3 per RFC 8446 in 2 phases: handshake protocol, record layer",
    })
    assert r
    assert r.new_step == "1.3 Plan review"
    assert h.status == "waiting"

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "2.1 Implement phase"

    # Both phases were already implemented and unit-tested offline -- jump to integration
    r = h.goto("3.1 Integration testing")
    assert r
    assert r.new_step == "3.1 Integration testing"
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"

    r = h.submit({
        "command": "pytest tests/integration/test_tls13.py -v",
        "scenarios": ["full handshake with ECDHE", "0-RTT early data", "session resumption"],
        "passed": 34, "failed": 0,
    })
    assert r
    assert h.step == "3.2 Final verification"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Data accumulation tests
# ===============================================================

def test_data_accumulates_spec(harness_factory):
    """Approve data at 1.1 persists in state.data."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()

    h.approve({"spec": "detailed spec document"})
    data = h.state.data
    assert "1.1 Write specification" in data
    assert data["1.1 Write specification"]["spec"] == "detailed spec document"


def test_data_accumulates_plan(harness_factory):
    """Submit data at 1.2 persists in state.data."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()

    h.submit({"plan": "3-phase plan"})
    data = h.state.data
    assert "1.2 Generate implementation plan" in data
    assert data["1.2 Generate implementation plan"]["plan"] == "3-phase plan"


def test_data_accumulates_through_loop(harness_factory):
    """Data submitted in loop iterations persists in state.data."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)

    h.submit({"impl": "auth module"})
    data = h.state.data
    assert "2.1 Implement phase" in data
    assert data["2.1 Implement phase"]["impl"] == "auth module"

    h.submit({"test_result": "all pass"})
    data = h.state.data
    assert "2.2 Run phase tests" in data
    assert data["2.2 Run phase tests"]["test_result"] == "all pass"


# ===============================================================
# History audit trail tests
# ===============================================================

def test_history_audit_full_walkthrough(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Phase loop")
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Phase loop")
    h.submit({})
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
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.goto("3.1 Integration testing")

    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


def test_history_records_skip(harness_factory):
    """Skip reason appears in history."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)
    h.submit({})
    assert h.step == "2.2 Run phase tests"

    h.skip("already tested")
    history = h.get_history(10)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "already tested"


def test_history_records_reject(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _walk_to_plan_review(h)

    h.reject("plan incomplete")
    history = h.get_history(10)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "plan incomplete"


# ===============================================================
# Cross-executor recovery tests
# ===============================================================

def test_cross_executor_at_plan_review(harness_factory):
    """Close executor at plan review, reopen, continue."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _walk_to_plan_review(h)

    h.new_executor()

    assert h.step == "1.3 Plan review"
    assert h.status == "waiting"

    h.approve()
    r = h.submit_goto("2.0 Phase loop")
    assert r
    assert h.step == "2.1 Implement phase"


def test_cross_executor_mid_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["a", "b"]})
    _enter_phase_loop(h)

    h.submit({"impl": "a_code"})
    assert h.step == "2.2 Run phase tests"

    h.new_executor()

    assert h.step == "2.2 Run phase tests"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Phase loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_integration(harness_factory):
    """Close executor at integration, reopen, continue."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)
    _do_one_phase_pass(h)
    h.submit_goto("2.0 Phase loop")
    assert h.step == "3.1 Integration testing"

    h.new_executor()

    assert h.step == "3.1 Integration testing"
    assert h.status == "running"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.goto("3.2 Final verification")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "2.1 Implement phase"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Node validation tests
# ===============================================================

def test_node_validates_implementation(harness_factory):
    """Validate node rejects bad data at 2.1, accepts good data."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)

    h.register_node(
        "2.1 Implement phase",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("impl") else "must include implementation",
        ),
    )

    r = h.submit({"notes": "no impl"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"impl": "auth_module.py"})
    assert r
    assert r.new_step == "2.2 Run phase tests"


def test_node_validates_tests(harness_factory):
    """Validate node rejects missing test data at 2.2."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)
    h.submit({"impl": "code"})
    assert h.step == "2.2 Run phase tests"

    h.register_node(
        "2.2 Run phase tests",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("result") else "must include test result",
        ),
    )

    r = h.submit({})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"result": "all pass"})
    assert r
    assert r.new_step == "2.3 Compliance check"


def test_node_validates_plan(harness_factory):
    """Validate node rejects bad plan data at 1.2."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Generate implementation plan"

    h.register_node(
        "1.2 Generate implementation plan",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("plan") else "must include plan",
        ),
    )

    r = h.submit({})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"plan": "detailed 3-phase plan"})
    assert r
    assert r.new_step == "1.3 Plan review"


# ===============================================================
# Node archival tests
# ===============================================================

def test_node_archives_implementation(harness_factory):
    """Archive node writes implementation data to SQLite."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _enter_phase_loop(h)

    h.register_node(
        "2.1 Implement phase",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"module": "string", "phase": "string"}},
            archive={"table": "phase_implementations"},
        ),
    )

    r = h.submit({"module": "auth.py", "phase": "phase1"})
    assert r

    rows = h.get_archived_rows("phase_implementations")
    assert len(rows) == 1
    assert rows[0]["module"] == "auth.py"
    assert rows[0]["phase"] == "phase1"


def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1", "p2", "p3"]})
    _enter_phase_loop(h)

    h.register_node(
        "2.1 Implement phase",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"phase_name": "string"}},
            archive={"table": "phase_log"},
        ),
    )

    for i in range(3):
        h.submit({"phase_name": f"phase_{i}"})
        h.submit({})
        h.submit_goto("2.0 Phase loop")

    rows = h.get_archived_rows("phase_log")
    assert len(rows) == 3


def test_node_archives_plan(harness_factory):
    """Archive node at 1.2 writes plan data to SQLite."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Generate implementation plan"

    h.register_node(
        "1.2 Generate implementation plan",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"plan_version": "string"}},
            archive={"table": "plans"},
        ),
    )

    r = h.submit({"plan_version": "v1"})
    assert r

    rows = h.get_archived_rows("plans")
    assert len(rows) == 1
    assert rows[0]["plan_version"] == "v1"


# ===============================================================
# Error boundary tests
# ===============================================================

def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting returns failure."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    assert h.step == "1.1 Write specification"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Generate implementation plan"
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.goto("3.2 Final verification")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.goto("3.2 Final verification")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve({"spec": "my spec"})
    h.submit({"plan": "my plan"})
    assert h.step == "1.3 Plan review"

    h.save_checkpoint("at_plan_review")

    h.approve()
    h.submit_goto("2.0 Phase loop")
    assert h.step == "2.1 Implement phase"

    restored = h.load_checkpoint("at_plan_review")
    assert restored is not None
    assert restored.current_step == "1.3 Plan review"
    assert "1.2 Generate implementation plan" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Generate implementation plan"

    r = h.retry()
    assert r
    assert h.step == "1.2 Generate implementation plan"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})

    for _ in range(3):
        h.start()
        h.approve()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Write specification"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["a", "b", "c"]})
    _enter_phase_loop(h)

    loop_info = h.state.loop_state["2.0 Phase loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_phase_pass(h)
    h.submit_goto("2.0 Phase loop")

    loop_info = h.state.loop_state["2.0 Phase loop"]
    assert loop_info["i"] == 1

    _do_one_phase_pass(h)
    h.submit_goto("2.0 Phase loop")

    loop_info = h.state.loop_state["2.0 Phase loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["only"]})
    _enter_phase_loop(h)

    _do_one_phase_pass(h)
    h.submit_goto("2.0 Phase loop")

    assert h.step == "3.1 Integration testing"
    assert "2.0 Phase loop" not in h.state.loop_state


def test_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    _walk_to_plan_review(h)

    data_before = dict(h.state.data)
    h.reject("incomplete plan")
    data_after = h.state.data
    assert data_before == data_after


def test_history_records_transition(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Phase loop")
    assert h.step == "2.1 Implement phase"

    h.register_node(
        "2.1 Implement phase",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step by following SDD principles.\n\n## Steps\n1. Analyze requirements\n2. Implement code\n3. Submit output",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-sdd.yaml", loop_data={"phases": ["p1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Generate implementation plan"

    h.register_node(
        "1.2 Generate implementation plan",
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
