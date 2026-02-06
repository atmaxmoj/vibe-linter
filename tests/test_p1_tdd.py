"""Test scenarios for TDD SOP workflow (p1-tdd.yaml).

Tests the complete TDD workflow including:
- Design phase (gather, design, review)
- Feature loop (red-green-refactor-test-quality)
- Integration testing and final review
- State transitions, gotos, stops/resumes, and hot-reload

Workflow structure:
  1.1 Gather requirements (wait)
  1.2 Design architecture
  1.3 Design review (wait, LLM: approved->2.0, else->1.2)
  2.0 Feature loop (iterate: features)
    2.1 Write failing test (Red)
    2.2 Write minimal code (Green)
    2.3 Refactor
    2.4 Run test suite
    2.5 Quality check (LLM: pass->2.0, code bugs->2.2, wrong tests->2.1, design flaw->1.2)
  3.1 Integration testing
  3.2 Final review (wait, LLM: pass->Done, else->2.0)
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

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# ─── Helpers ───

def _walk_to_design_review(h):
    """Common helper: start -> approve 1.1 -> submit 1.2 -> arrive at 1.3 (waiting)."""
    h.start()
    h.approve({"requirements": "user auth, REST api, dashboard"})
    h.submit({"design": "microservices with JWT auth"})
    assert h.step == "1.3 Design review"
    assert h.status == "waiting"


def _enter_feature_loop(h):
    """Common helper: get past design review into loop iteration 1."""
    _walk_to_design_review(h)
    h.approve()
    h.submit_goto("2.0 Feature loop")
    assert h.step == "2.1 Write failing test (Red)"
    assert h.status == "running"


def _do_one_loop_pass(h, data=None):
    """Complete one Red-Green-Refactor-Test-Quality cycle ending at quality check."""
    h.submit(data or {"test": "test_x"})   # 2.1 -> 2.2
    h.submit(data or {"code": "impl"})      # 2.2 -> 2.3
    h.submit(data or {"refactored": True})  # 2.3 -> 2.4
    h.submit(data or {"result": "pass"})    # 2.4 -> 2.5
    assert h.step == "2.5 Quality check"


def _complete_loop_and_finish(h, n_features):
    """From inside the loop, exhaust all iterations and reach Done."""
    for _i in range(n_features):
        if h.step != "2.1 Write failing test (Red)":
            h.submit_goto("2.0 Feature loop")
        _do_one_loop_pass(h)
        h.submit_goto("2.0 Feature loop")
    assert h.step == "3.1 Integration testing"
    h.submit({"integration_tests": "all pass"})
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"
    h.approve()
    h.submit_goto("Done")
    assert h.step == "Done"
    assert h.status == "done"


# ═══════════════════════════════════════════════════════
# Scenario 1: Full walkthrough
# ═══════════════════════════════════════════════════════

def test_s1_happy_path(harness_factory):
    """Build a Todo App: full TDD cycle from requirements gathering to shipping."""
    h = harness_factory("p1-tdd.yaml", loop_data={
        "features": ["add_todo", "complete_todo", "delete_todo"],
    })
    r = h.start()
    assert r

    # 1.1 Product owner provides requirements for the todo app
    assert h.step == "1.1 Gather requirements"
    assert h.status == "waiting"

    r = h.approve({
        "project": "Todo App",
        "user_stories": [
            "As a user I can add a todo with a title",
            "As a user I can mark a todo as complete",
            "As a user I can delete a todo",
        ],
        "acceptance_criteria": "All CRUD operations work, input validation, 90%+ coverage",
    })
    assert r
    assert r.new_step == "1.2 Design architecture"
    assert h.status == "running"

    # 1.2 Architect designs the system
    r = h.submit({
        "stack": "React + Express + PostgreSQL",
        "data_model": {"Todo": {"id": "uuid", "title": "string", "done": "boolean", "created_at": "timestamp"}},
        "api_endpoints": ["POST /todos", "PATCH /todos/:id", "DELETE /todos/:id", "GET /todos"],
        "layers": "Controller -> TodoService -> TodoRepository",
    })
    assert r
    assert r.new_step == "1.3 Design review"
    assert h.status == "waiting"

    # 1.3 Design review: team approves the architecture
    r = h.approve()
    assert r
    assert h.status == "running"

    r = h.submit_goto("2.0 Feature loop")
    assert r
    assert r.new_step == "2.1 Write failing test (Red)"

    # Verify loop entry: iteration 1 of 3
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # ── Feature 1: add_todo ──
    # 2.1 Red: write a failing test for adding todos
    r = h.submit({
        "test_file": "tests/test_add_todo.py",
        "test_code": "def test_add_todo_returns_201(): resp = client.post('/todos', json={'title': 'Buy milk'}); assert resp.status_code == 201",
        "run_result": "FAILED - 404 Not Found (endpoint not implemented)",
    })
    assert r and r.new_step == "2.2 Write minimal code (Green)"

    # 2.2 Green: minimal implementation to make test pass
    r = h.submit({
        "file": "src/routes/todos.py",
        "implementation": "def add_todo(title): todo = Todo(title=title); db.session.add(todo); db.session.commit(); return todo, 201",
        "run_result": "PASSED - test_add_todo_returns_201",
    })
    assert r and r.new_step == "2.3 Refactor"

    # 2.3 Refactor: extract service layer
    r = h.submit({
        "changes": "Extracted TodoService.create(title) from route handler, added input validation for empty titles",
        "files_modified": ["src/services/todo_service.py", "src/routes/todos.py"],
    })
    assert r and r.new_step == "2.4 Run test suite"

    # 2.4 Run the full test suite
    r = h.submit({
        "command": "pytest tests/ -v --cov",
        "passed": 3, "failed": 0, "coverage": "85%",
    })
    assert r and h.step == "2.5 Quality check"

    # 2.5 Quality check: all good, advance to next feature
    r = h.submit_goto("2.0 Feature loop")
    assert r and r.new_step == "2.1 Write failing test (Red)"

    # Verify iteration 2 of 3
    status = h.get_status()
    assert "[2/" in status["display_path"]

    # ── Feature 2: complete_todo ──
    r = h.submit({
        "test_file": "tests/test_complete_todo.py",
        "test_code": "def test_complete_sets_done_true(): todo = create_todo('Laundry'); resp = client.patch(f'/todos/{todo.id}', json={'done': True}); assert resp.json()['done'] is True",
        "run_result": "FAILED - AttributeError: PATCH handler not found",
    })
    assert r and r.new_step == "2.2 Write minimal code (Green)"
    r = h.submit({
        "implementation": "def complete_todo(id): todo = TodoService.get(id); todo.done = True; db.session.commit()",
        "run_result": "PASSED",
    })
    assert r and r.new_step == "2.3 Refactor"
    r = h.submit({
        "changes": "Added 404 handling for non-existent todo, extracted update logic to TodoService.complete(id)",
    })
    assert r and r.new_step == "2.4 Run test suite"
    r = h.submit({"passed": 7, "failed": 0, "coverage": "89%"})
    assert r and h.step == "2.5 Quality check"
    r = h.submit_goto("2.0 Feature loop")
    assert r and r.new_step == "2.1 Write failing test (Red)"

    # Verify iteration 3 of 3
    status = h.get_status()
    assert "[3/" in status["display_path"]

    # ── Feature 3: delete_todo ──
    r = h.submit({
        "test_file": "tests/test_delete_todo.py",
        "run_result": "FAILED - 405 Method Not Allowed",
    })
    assert r and r.new_step == "2.2 Write minimal code (Green)"
    r = h.submit({
        "implementation": "def delete_todo(id): TodoService.delete(id); return '', 204",
    })
    assert r and r.new_step == "2.3 Refactor"
    r = h.submit({"changes": "Added cascade delete for related comments, soft-delete option"})
    assert r and r.new_step == "2.4 Run test suite"
    r = h.submit({"passed": 12, "failed": 0, "coverage": "94%"})
    assert r and h.step == "2.5 Quality check"
    r = h.submit_goto("2.0 Feature loop")
    assert r

    # All 3 features done, loop exhausted -> integration phase
    assert h.step == "3.1 Integration testing"
    assert h.status == "running"
    assert "2.0 Feature loop" not in h.state.loop_state

    # 3.1 Run end-to-end integration tests
    r = h.submit({
        "command": "pytest tests/integration/ -v",
        "scenarios_tested": ["full CRUD lifecycle", "concurrent requests", "input validation edge cases"],
        "passed": 18, "failed": 0,
    })
    assert r and r.new_step == "3.2 Final review"
    assert h.status == "waiting"

    # 3.2 Tech lead approves: ship it
    r = h.approve()
    assert r
    r = h.submit_goto("Done")
    assert r and h.step == "Done" and h.status == "done"

    # After shipping: no more work allowed
    r = h.submit({})
    assert not r


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["auth"]})
    h.start()

    # 1.1 approve with data
    h.approve({"requirements": "build auth"})
    data = h.state.data
    assert "1.1 Gather requirements" in data
    assert data["1.1 Gather requirements"]["requirements"] == "build auth"

    # 1.2 submit with data
    h.submit({"design": "jwt tokens"})
    data = h.state.data
    assert "1.2 Design architecture" in data
    assert data["1.2 Design architecture"]["design"] == "jwt tokens"

    # Approve design review and enter loop
    h.approve()
    h.submit_goto("2.0 Feature loop")
    h.submit({"test": "test_login"})
    data = h.state.data
    assert "2.1 Write failing test (Red)" in data
    assert data["2.1 Write failing test (Red)"]["test"] == "test_login"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Feature loop")

    # Do one loop pass (iteration 1 of 1)
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({})  # 2.3 -> 2.4
    h.submit({})  # 2.4 -> 2.5
    assert h.step == "2.5 Quality check"
    h.submit_goto("2.0 Feature loop")
    # n=1, i increments to 1, loop exhausted -> 3.1

    assert h.step == "3.1 Integration testing"
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


def test_s1_cross_executor_at_design(harness_factory):
    """Close executor at design review, reopen, continue."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    _walk_to_design_review(h)

    # Close and reopen
    h.new_executor()

    # State persisted: still at 1.3, waiting
    assert h.step == "1.3 Design review"
    assert h.status == "waiting"

    # Continue from where we left off
    h.approve()
    r = h.submit_goto("2.0 Feature loop")
    assert r
    assert h.step == "2.1 Write failing test (Red)"


def test_s1_cross_executor_at_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["a", "b"]})
    _enter_feature_loop(h)

    # Submit through first two steps of loop
    h.submit({"test": "test_a"})
    h.submit({"code": "a_code"})
    assert h.step == "2.3 Refactor"

    # Close and reopen
    h.new_executor()

    assert h.step == "2.3 Refactor"
    assert h.status == "running"
    # Loop state preserved
    loop_info = h.state.loop_state.get("2.0 Feature loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_test(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    _enter_feature_loop(h)

    # Register validate node for step 2.1 directly in the registry
    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("test") else "must include test name",
        ),
    )

    # Bad data: missing "test" key
    r = h.submit({"notes": "forgot the test"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"test": "test_feature_1"})
    assert r
    assert r.new_step == "2.2 Write minimal code (Green)"


def test_s1_node_archives_results(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    _enter_feature_loop(h)

    # Register archive node for step 2.1
    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"test_name": "string", "category": "string"}},
            archive={"table": "test_results"},
        ),
    )

    r = h.submit({"test_name": "test_login", "category": "auth"})
    assert r

    rows = h.get_archived_rows("test_results")
    assert len(rows) == 1
    assert rows[0]["test_name"] == "test_login"
    assert rows[0]["category"] == "auth"


# ═══════════════════════════════════════════════════════
# Scenario 2: Goto loop
# ═══════════════════════════════════════════════════════

def test_s2_happy_path(harness_factory):
    """Add product search to e-commerce app: skip design, goto straight to coding."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["product_search"]})
    r = h.start()
    assert r

    # Existing project with established architecture — jump to feature loop
    r = h.goto("2.1 Write failing test (Red)")
    assert r and r.new_step == "2.1 Write failing test (Red)"

    # Implement full-text product search
    r = h.submit({
        "test_file": "tests/test_product_search.py",
        "test_code": "def test_search_by_name(): results = search_products('wireless mouse'); assert any('wireless' in r.name.lower() for r in results)",
        "run_result": "FAILED - NameError: search_products not defined",
    })
    assert r
    r = h.submit({
        "file": "src/services/search.py",
        "implementation": "def search_products(q): return Product.query.filter(Product.name.ilike(f'%{q}%')).all()",
    })
    assert r
    r = h.submit({
        "changes": "Replace LIKE with PostgreSQL tsvector full-text search, add GIN index on products.name_tsv",
    })
    assert r
    r = h.submit({"passed": 5, "failed": 0, "coverage": "91%"})
    assert r
    r = h.submit_goto("2.0 Feature loop")
    assert r and r.new_step == "2.1 Write failing test (Red)"

    # Loop exhaustion pass (CI re-runs full suite)
    for _ in range(4):
        r = h.submit()
        assert r
    r = h.submit_goto("2.0 Feature loop")
    assert r and h.step == "3.1 Integration testing"
    assert "2.0 Feature loop" not in h.state.loop_state


def test_s2_data_after_goto(harness_factory):
    """Goto does not produce a data entry (only submit does)."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()

    h.goto("2.1 Write failing test (Red)")
    data = h.state.data
    # goto should not add any step data entry
    assert "2.1 Write failing test (Red)" not in data

    # But submit does
    h.submit({"test": "test_goto"})
    data = h.state.data
    assert "2.1 Write failing test (Red)" in data


def test_s2_history_shows_goto(harness_factory):
    """History records a goto action."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()

    h.goto("2.1 Write failing test (Red)")
    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


def test_s2_cross_executor_mid_loop(harness_factory):
    """Goto into loop, close executor mid-loop, reopen and continue."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.goto("2.1 Write failing test (Red)")
    h.submit({"test": "t1"})
    assert h.step == "2.2 Write minimal code (Green)"

    h.new_executor()

    assert h.step == "2.2 Write minimal code (Green)"
    assert h.status == "running"


# ═══════════════════════════════════════════════════════
# Scenario 3: Fix bug single pass
# ═══════════════════════════════════════════════════════

def test_s3_happy_path(harness_factory):
    """Fix login bug: users with uppercase emails can't sign in."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["email_case_fix"]})
    h.start()

    # Bug report in, skip to writing a regression test
    r = h.goto("2.1 Write failing test (Red)")
    assert r

    # 2.1 Red: write regression test reproducing the bug
    h.submit({
        "test_file": "tests/test_login_case_sensitivity.py",
        "test_code": "def test_login_with_uppercase_email(): user = create_user('Alice@Example.com', 'pass123'); assert login('ALICE@EXAMPLE.COM', 'pass123').success",
        "run_result": "FAILED - login returns None for uppercase variant",
    })
    # 2.2 Green: fix the case comparison
    h.submit({
        "file": "src/services/auth_service.py",
        "fix": "Normalize email to lowercase before DB lookup: user = User.query.filter_by(email=email.lower()).first()",
    })
    # 2.3 Refactor: also normalize on registration
    h.submit({
        "changes": "Added email.lower() normalization in register() and login(), added migration to lowercase existing emails",
    })
    # 2.4 Run full suite
    h.submit({
        "passed": 47, "failed": 0,
        "note": "All existing tests still pass, regression test now green",
    })
    assert h.step == "2.5 Quality check"

    # Quality OK -> loop header
    h.submit_goto("2.0 Feature loop")
    assert h.step == "2.1 Write failing test (Red)"

    # Loop exhaustion pass
    for _ in range(4):
        h.submit()
    h.submit_goto("2.0 Feature loop")
    assert h.step == "3.1 Integration testing"

    # 3.1 Run integration tests to verify fix in full stack
    h.submit({
        "scenarios": ["login with mixed-case email", "register then login with different casing"],
        "passed": 52, "failed": 0,
    })
    assert h.step == "3.2 Final review"
    assert h.status == "waiting"

    # Cannot submit while waiting for review
    r = h.submit({})
    assert not r
    assert "waiting" in r.message.lower()

    # 3.2 Reviewer approves the bugfix
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"


def test_s3_wait_step_rejects_submit(harness_factory):
    """At a wait step, submit is rejected with 'waiting' message."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_s3_data_persists_through_loop(harness_factory):
    """Data submitted during loop iterations is preserved after loop exit."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["bugfix"]})
    h.start()
    h.goto("2.1 Write failing test (Red)")

    h.submit({"test": "test_bug"})
    h.submit({"code": "fix_code"})
    h.submit({"refactored": True})
    h.submit({"result": "pass"})
    h.submit_goto("2.0 Feature loop")

    # Second pass to exhaust
    h.submit({"test": "test_bug_2"})
    h.submit({"code": "fix_code_2"})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Feature loop")

    assert h.step == "3.1 Integration testing"

    # Data from loop should still be in state
    data = h.state.data
    assert "2.1 Write failing test (Red)" in data


def test_s3_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


# ═══════════════════════════════════════════════════════
# Scenario 4: Hotfix skip design
# ═══════════════════════════════════════════════════════

def test_s4_happy_path(harness_factory):
    """Payment service outage: emergency hotfix, skip all design steps."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["payment_fix"]})
    h.start()
    assert h.status == "waiting"

    # Production is down — skip requirements gathering
    r = h.skip("P0 incident: payment webhook returning 500, customers can't complete orders")
    assert r and r.new_step == "1.2 Design architecture"

    # No time for architecture — we know the codebase
    r = h.skip("Root cause identified: Stripe API version mismatch after library upgrade")
    assert r and r.new_step == "1.3 Design review"
    assert h.status == "waiting"

    # Skip design review (WAIT+LLM: skip sets running, LLM conditions keep it here)
    r = h.skip("No review needed for version pinning fix")
    assert r and h.step == "1.3 Design review"
    assert h.status == "running"

    # Jump straight to writing a test
    r = h.goto("2.1 Write failing test (Red)")
    assert r

    # Write regression test and fix
    h.submit({
        "test_code": "def test_stripe_webhook_v2023(): payload = mock_stripe_event('2023-12-14'); assert process_webhook(payload).status == 200",
    })
    h.submit({
        "fix": "Pin stripe-python==7.9.0 in requirements.txt, update webhook signature verification to match API version",
    })
    h.submit({"changes": "Added Stripe API version constant, version check in webhook handler"})
    h.submit({"passed": 89, "failed": 0, "note": "All payment tests green"})
    h.submit_goto("2.0 Feature loop")
    # Loop exhaustion pass
    for _ in range(4):
        h.submit()
    h.submit_goto("2.0 Feature loop")
    assert h.step == "3.1 Integration testing"
    assert "2.0 Feature loop" not in h.state.loop_state


def test_s4_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()

    h.skip("emergency hotfix - no time")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "emergency hotfix - no time"


def test_s4_skip_on_llm_step_stays(harness_factory):
    """Skip on WAIT+LLM step sets running but LLM conditions keep it there."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.skip()  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3
    assert h.step == "1.3 Design review"
    assert h.status == "waiting"

    # skip on WAIT+LLM: sets running, _follow_transitions finds LLM -> stays
    r = h.skip()
    assert r
    assert h.step == "1.3 Design review"
    assert h.status == "running"


def test_s4_cross_executor_after_skip(harness_factory):
    """Skip multiple steps, close executor, reopen, state is correct."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.skip("skip 1.1")
    h.skip("skip 1.2")
    assert h.step == "1.3 Design review"

    h.new_executor()
    assert h.step == "1.3 Design review"
    assert h.status == "waiting"


# ═══════════════════════════════════════════════════════
# Scenario 5: Design review rejected
# ═══════════════════════════════════════════════════════

def test_s5_happy_path(harness_factory):
    """Architecture review: monolith rejected, microservices rejected, modular monolith approved."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["core_module"]})
    h.start()
    h.approve({
        "project": "Order Management System",
        "requirements": "Handle 10k orders/day, integrate with 3 payment providers, real-time inventory updates",
    })
    h.submit({
        "design": "Single Django monolith with all domains in one app",
        "deployment": "Single EC2 instance",
    })
    assert h.step == "1.3 Design review"

    # First reject: monolith won't scale
    r = h.reject("Monolith won't handle 10k orders/day. Payment and inventory are too tightly coupled — a payment provider outage would block all orders.")
    assert r and h.step == "1.3 Design review" and h.status == "waiting"

    # Second attempt: microservices
    h.approve()
    h.submit_goto("1.2 Design architecture")
    h.submit({
        "design": "Full microservices: order-service, payment-service, inventory-service, API gateway",
        "deployment": "Kubernetes cluster with 3 services",
    })
    assert h.step == "1.3 Design review"

    # Second reject: too complex for team of 4
    h.reject("Team of 4 can't maintain 3 services + API gateway + K8s. Operational overhead will kill velocity.")
    h.approve()
    h.submit_goto("1.2 Design architecture")

    # Third attempt: modular monolith (the sweet spot)
    h.submit({
        "design": "Modular monolith: Django with separate apps for orders, payments, inventory. Async Celery tasks for payment processing. Can extract to services later.",
        "deployment": "ECS with auto-scaling, RDS PostgreSQL",
    })

    # Third time's the charm
    h.approve()
    r = h.submit_goto("2.0 Feature loop")
    assert r and h.step == "2.1 Write failing test (Red)"


def test_s5_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve({"requirements": "build it"})
    h.submit({"design": "plan A"})

    data_before = dict(h.state.data)
    h.reject("nope")
    data_after = h.state.data
    assert data_before == data_after


def test_s5_reject_adds_history(harness_factory):
    """Reject action appears in history."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    h.submit({})
    h.reject("bad design")

    history = h.get_history(10)
    reject_entries = [e for e in history if e["action"] == "reject"]
    assert len(reject_entries) >= 1
    assert reject_entries[0]["data"] == "bad design"


def test_s5_reject_on_non_waiting_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    # Now at 1.2, status=running
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_s5_approve_on_non_waiting_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    # Now at 1.2, status=running
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


# ═══════════════════════════════════════════════════════
# Scenario 6: Test fails 5 rounds
# ═══════════════════════════════════════════════════════

def test_s6_happy_path(harness_factory):
    """Implement rate limiter: quality check fails 5 times before passing."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["rate_limiter"]})
    h.start()

    h.goto("2.5 Quality check")

    # Attempt 1: naive counter — race condition under load
    r = h.submit_goto("2.2 Write minimal code (Green)")
    assert r and h.step == "2.2 Write minimal code (Green)"
    h.submit({"approach": "Simple in-memory counter per IP", "issue": "Race condition under concurrent requests"})
    h.submit({"changes": "Added threading.Lock"})
    h.submit({"passed": 8, "failed": 2, "failures": "test_concurrent_requests, test_distributed_rate_limit"})
    assert h.step == "2.5 Quality check"

    # Attempt 2: Redis counter — window boundary bug
    h.submit_goto("2.2 Write minimal code (Green)")
    h.submit({"approach": "Redis INCR with TTL", "issue": "Requests at window boundary bypass limit"})
    h.submit({"changes": "Switch to sliding window"})
    h.submit({"passed": 9, "failed": 1, "failures": "test_burst_at_window_edge"})
    assert h.step == "2.5 Quality check"

    # Attempt 3: sliding window — memory overhead too high
    h.submit_goto("2.2 Write minimal code (Green)")
    h.submit({"approach": "Sliding window log", "issue": "Stores every request timestamp, OOM at 100k req/s"})
    h.submit({"changes": "Limit log size"})
    h.submit({"passed": 10, "failed": 1, "failures": "test_memory_under_high_load"})
    assert h.step == "2.5 Quality check"

    # Attempt 4: token bucket — refill rate wrong
    h.submit_goto("2.2 Write minimal code (Green)")
    h.submit({"approach": "Token bucket algorithm", "issue": "Refill rate calculation off by 1ms"})
    h.submit({"changes": "Fixed float precision in refill calculation"})
    h.submit({"passed": 11, "failed": 1, "failures": "test_sustained_throughput_at_limit"})
    assert h.step == "2.5 Quality check"

    # Attempt 5: token bucket with Redis Lua script — almost there
    h.submit_goto("2.2 Write minimal code (Green)")
    h.submit({"approach": "Token bucket with atomic Redis Lua script", "issue": "Lua script not handling negative tokens"})
    h.submit({"changes": "Added math.max(0, tokens) in Lua script"})
    h.submit({"passed": 12, "failed": 0, "note": "All rate limit tests passing!"})
    assert h.step == "2.5 Quality check"

    # 6th time: all tests pass, advance to next feature
    h.submit_goto("2.0 Feature loop")
    assert h.step == "2.1 Write failing test (Red)"

    # Loop exhaustion pass
    for _ in range(4):
        h.submit()
    h.submit_goto("2.0 Feature loop")
    assert h.step == "3.1 Integration testing"
    assert "2.0 Feature loop" not in h.state.loop_state


def test_s6_data_has_all_attempts(harness_factory):
    """All 5 submit attempts store data (last wins per step key)."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["complex"]})
    h.start()
    h.goto("2.2 Write minimal code (Green)")

    for i in range(5):
        h.submit({"code": f"attempt_{i}"})
        # After submit, step advances; go back to 2.2
        if h.step != "2.2 Write minimal code (Green)":
            h.goto("2.2 Write minimal code (Green)")

    # The last submit data for 2.2 should be the most recent
    data = h.state.data
    assert "2.2 Write minimal code (Green)" in data


def test_s6_history_depth(harness_factory):
    """5 rounds of failing produce many history entries."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["complex"]})
    h.start()
    h.goto("2.5 Quality check")

    for _ in range(5):
        h.submit_goto("2.2 Write minimal code (Green)")
        h.submit({})
        h.submit({})
        h.submit({})

    history = h.get_history(100)
    # start + goto + 5*(submit + transition*3 + submit*3) = many entries
    assert len(history) >= 20


def test_s6_cross_executor_mid_retry(harness_factory):
    """Close executor after 3 fails, reopen, continue from same step."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["complex"]})
    h.start()
    h.goto("2.5 Quality check")

    for _ in range(3):
        h.submit_goto("2.2 Write minimal code (Green)")
        h.submit({})
        h.submit({})
        h.submit({})
    assert h.step == "2.5 Quality check"

    h.new_executor()
    assert h.step == "2.5 Quality check"
    assert h.status == "running"

    # Continue with 4th attempt
    h.submit_goto("2.2 Write minimal code (Green)")
    assert h.step == "2.2 Write minimal code (Green)"


# ═══════════════════════════════════════════════════════
# Scenario 7: Feature loop 3 iterations
# ═══════════════════════════════════════════════════════

def test_s7_happy_path(harness_factory):
    """Build SaaS MVP: auth, REST API, admin dashboard — 3 iteration loop."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["jwt_auth", "rest_api", "admin_dashboard"]})
    h.start()
    _enter_feature_loop(h)

    # ── Iteration 1: JWT Authentication ──
    status = h.get_status()
    assert "[1/" in status["display_path"]
    h.submit({
        "test_code": "def test_login_returns_jwt(): resp = client.post('/auth/login', json={'email': 'a@b.com', 'password': 'secret'}); assert 'access_token' in resp.json()",
    })
    h.submit({"implementation": "JWT encode with HS256, 15min expiry, refresh token flow"})
    h.submit({"changes": "Extracted TokenService, added refresh token rotation"})
    h.submit({"passed": 8, "failed": 0})
    h.submit_goto("2.0 Feature loop")

    # ── Iteration 2: REST API endpoints ──
    status = h.get_status()
    assert "[2/" in status["display_path"]
    h.submit({
        "test_code": "def test_crud_resources(): resp = client.post('/api/projects', json={'name': 'My Project'}, headers=auth_header); assert resp.status_code == 201",
    })
    h.submit({"implementation": "RESTful CRUD for projects, tasks, and comments with auth middleware"})
    h.submit({"changes": "Added pagination, filtering, field selection via query params"})
    h.submit({"passed": 24, "failed": 0})
    h.submit_goto("2.0 Feature loop")

    # ── Iteration 3: Admin Dashboard ──
    status = h.get_status()
    assert "[3/" in status["display_path"]
    h.submit({
        "test_code": "def test_admin_sees_all_users(): resp = client.get('/admin/users', headers=admin_header); assert len(resp.json()['users']) > 0",
    })
    h.submit({"implementation": "Admin-only routes with role-based access, user/project management"})
    h.submit({"changes": "Added audit logging for all admin actions"})
    h.submit({"passed": 31, "failed": 0})
    h.submit_goto("2.0 Feature loop")

    # All 3 features done, loop exits to integration
    assert h.step == "3.1 Integration testing"
    assert "2.0 Feature loop" not in h.state.loop_state


def test_s7_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["a", "b", "c"]})
    _enter_feature_loop(h)

    # Iteration 1: i=0
    loop_info = h.state.loop_state["2.0 Feature loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_loop_pass(h)
    h.submit_goto("2.0 Feature loop")

    # Iteration 2: i=1
    loop_info = h.state.loop_state["2.0 Feature loop"]
    assert loop_info["i"] == 1

    _do_one_loop_pass(h)
    h.submit_goto("2.0 Feature loop")

    # Iteration 3: i=2
    loop_info = h.state.loop_state["2.0 Feature loop"]
    assert loop_info["i"] == 2


def test_s7_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["a", "b"]})
    _enter_feature_loop(h)

    h.submit({"test": "test_a"})
    h.submit({"code": "code_a"})
    h.submit()
    h.submit()
    h.submit_goto("2.0 Feature loop")

    h.submit({"test": "test_b"})
    data = h.state.data
    # Last submit for 2.1 is test_b
    assert data["2.1 Write failing test (Red)"]["test"] == "test_b"


def test_s7_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["only"]})
    _enter_feature_loop(h)

    _do_one_loop_pass(h)
    h.submit_goto("2.0 Feature loop")

    # Loop exhausted, now at 3.1
    assert h.step == "3.1 Integration testing"
    assert "2.0 Feature loop" not in h.state.loop_state


def test_s7_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["a", "b", "c"]})
    _enter_feature_loop(h)

    # Register archive node for step 2.1
    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"test_name": "string"}},
            archive={"table": "tests_written"},
        ),
    )

    for i in range(3):
        h.submit({"test_name": f"test_{i}"})
        h.submit({})
        h.submit({})
        h.submit({})
        h.submit_goto("2.0 Feature loop")

    rows = h.get_archived_rows("tests_written")
    assert len(rows) == 3


def test_s7_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["a", "b", "c"]})
    _enter_feature_loop(h)

    # Complete iteration 1
    _do_one_loop_pass(h)
    h.submit_goto("2.0 Feature loop")

    # Mid iteration 2
    h.submit({"test": "mid_loop"})
    assert h.step == "2.2 Write minimal code (Green)"

    h.new_executor()

    assert h.step == "2.2 Write minimal code (Green)"
    loop_info = h.state.loop_state["2.0 Feature loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


# ═══════════════════════════════════════════════════════
# Scenario 8: Stop then resume
# ═══════════════════════════════════════════════════════

def test_s8_happy_path(harness_factory):
    """Sprint boundary: stop mid-design Friday evening, resume Monday morning."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["notification_system"]})
    h.start()
    h.approve({
        "requirements": "Email + push notifications for order updates, delivery tracking, promotional campaigns",
    })
    h.submit({
        "design": "Event-driven: OrderService emits events, NotificationService consumes via RabbitMQ, templates stored in S3",
    })
    assert h.step == "1.3 Design review" and h.status == "waiting"

    # Friday 6pm: sprint ends, stop the workflow
    r = h.stop()
    assert r and h.status == "stopped"

    # Monday 9am: resume where we left off
    r = h.resume()
    assert r and h.status == "waiting" and h.step == "1.3 Design review"

    # Team approves the design, start coding
    h.approve()
    h.submit_goto("2.0 Feature loop")
    h.submit({
        "test_code": "def test_order_placed_sends_email(): place_order(); assert email_service.sent[-1].template == 'order_confirmation'",
    })
    assert h.step == "2.2 Write minimal code (Green)"

    # Wednesday: team standup reveals blocker, pause again
    r = h.stop()
    assert r and h.status == "stopped"

    # Thursday: blocker resolved, resume
    r = h.resume()
    assert r and h.status == "running" and h.step == "2.2 Write minimal code (Green)"

    h.submit({"implementation": "NotificationService with Jinja2 templates, SES for email, FCM for push"})
    assert h.step == "2.3 Refactor"


def test_s8_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s8_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s8_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    assert h.status == "running"

    r = h.resume()
    assert not r


def test_s8_resume_wait_step_restores_waiting(harness_factory):
    """Resuming on a wait step restores waiting status."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    assert h.step == "1.1 Gather requirements" and h.status == "waiting"

    h.stop()
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"
    assert h.step == "1.1 Gather requirements"


def test_s8_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    h.submit({})
    assert h.step == "1.3 Design review"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.3 Design review"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "waiting"


# ═══════════════════════════════════════════════════════
# Scenario 9: Complete then reset
# ═══════════════════════════════════════════════════════

def test_s9_happy_path(harness_factory):
    """V1 shipped successfully, reset workflow to start V2 planning."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["v1_release"]})
    h.start()

    # Fast-forward to final review (V1 is done)
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    status = h.get_status()
    assert status["status"] == "done"

    # V1 is shipped — can't submit more work
    r = h.submit({})
    assert not r

    # Product decides to start V2: reset the workflow
    h.reset()
    assert h.state is None

    # V2 begins: fresh requirements gathering
    r = h.start()
    assert r
    assert h.step == "1.1 Gather requirements"
    assert h.status == "waiting"


def test_s9_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_s9_reset_clears_data(harness_factory):
    """After reset, state is None."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve({"requirements": "stuff"})
    h.submit({"design": "plan"})

    h.reset()
    assert h.state is None


def test_s9_fresh_start_after_reset(harness_factory):
    """Reset then start gives a clean initial state."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.goto("2.3 Refactor")
    h.submit({})

    h.reset()
    h.start()

    assert h.step == "1.1 Gather requirements"
    assert h.status == "waiting"
    # Data should only contain initial loop data
    data = h.state.data
    assert "2.3 Refactor" not in data


# ═══════════════════════════════════════════════════════
# Scenario 10: Modify YAML
# ═══════════════════════════════════════════════════════

def test_s10_happy_path(harness_factory):
    """Team decides mid-sprint to add mandatory PR review before running tests."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["user_profile"]})
    h.start()
    h.goto("2.3 Refactor")

    # Tech lead: "After the security incident, all code must have PR review before CI runs"
    modified_yaml = """名称: TDD Development Modified
描述: TDD with mandatory PR review step added mid-sprint

步骤:
  - 1.1 Gather requirements:
      类型: wait
  - 1.2 Design architecture
  - 1.3 Design review:
      类型: wait
      下一步:
        - 如果: "design is approved"
          去: 2.0 Feature loop
        - 去: 1.2 Design architecture
  - 2.0 Feature loop:
      遍历: "features"
      子步骤:
        - 2.1 Write failing test (Red)
        - 2.2 Write minimal code (Green)
        - 2.3 Refactor
        - 2.3.5 Code review:
            类型: wait
        - 2.4 Run test suite
        - 2.5 Quality check:
            下一步:
              - 如果: "all tests pass"
                去: 2.0 Feature loop
              - 去: 2.2 Write minimal code (Green)
  - 3.1 Integration testing
  - 3.2 Final review:
      类型: wait
      下一步:
        - 如果: "all integration tests pass"
          去: Done
        - 去: 2.0 Feature loop
  - Done:
      类型: terminate
      原因: All features implemented and tests pass
"""
    h.reload_yaml(modified_yaml)

    # Continue from 2.3 Refactor — now the next step is 2.3.5 Code review
    r = h.submit({
        "changes": "Extracted ProfileService, added avatar upload with S3 presigned URL",
        "pr_link": "https://github.com/acme/app/pull/142",
    })
    assert r and r.new_step == "2.3.5 Code review"
    assert h.status == "waiting"

    # Can't skip review — must wait for approval
    r = h.submit({})
    assert not r
    assert "waiting" in r.message.lower()

    # Reviewer approves the PR
    r = h.approve()
    assert r and r.new_step == "2.4 Run test suite"

    h.submit({"passed": 15, "failed": 0})
    assert h.step == "2.5 Quality check"


def test_s10_cross_executor_after_reload(harness_factory):
    """After YAML reload, close executor, reopen, state persists."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["mod"]})
    h.start()
    h.goto("2.3 Refactor")

    h.new_executor()
    assert h.step == "2.3 Refactor"
    assert h.status == "running"


def test_s10_node_on_new_step(harness_factory):
    """Install validate node for a step added by YAML reload."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["mod"]})
    h.start()
    h.goto("2.3 Refactor")

    modified_yaml = """名称: TDD Development Modified
描述: TDD with code review

步骤:
  - 1.1 Gather requirements:
      类型: wait
  - 1.2 Design architecture
  - 1.3 Design review:
      类型: wait
      下一步:
        - 如果: "design is approved"
          去: 2.0 Feature loop
        - 去: 1.2 Design architecture
  - 2.0 Feature loop:
      遍历: "features"
      子步骤:
        - 2.1 Write failing test (Red)
        - 2.2 Write minimal code (Green)
        - 2.3 Refactor
        - 2.3.5 Code review:
            类型: wait
        - 2.4 Run test suite
        - 2.5 Quality check:
            下一步:
              - 如果: "all tests pass"
                去: 2.0 Feature loop
              - 去: 2.2 Write minimal code (Green)
  - 3.1 Integration testing
  - 3.2 Final review:
      类型: wait
      下一步:
        - 如果: "all integration tests pass"
          去: Done
        - 去: 2.0 Feature loop
  - Done:
      类型: terminate
      原因: All features implemented and tests pass
"""
    h.reload_yaml(modified_yaml)

    h.submit({})
    assert h.step == "2.3.5 Code review"

    # Register validate node for the new step
    h.register_node(
        "2.3.5 Code review",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("approved") else "review not approved",
        ),
    )

    # Approve wait step first, then submit will go through validation
    h.approve()
    r = h.submit({"not_approved": True})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"approved": True})
    assert r


# ═══════════════════════════════════════════════════════
# Generic / cross-cutting tests
# ═══════════════════════════════════════════════════════

def test_expr_conditions_auto_advance(harness_factory):
    """Expression conditions auto-evaluate using initial_data flags."""
    h = harness_factory(
        "p1-tdd-expr.yaml",
        loop_data={"features": ["f1"], "design_approved": True, "integration_pass": True},
    )
    h.start()
    assert h.step == "1.1 Gather requirements"

    # Approve 1.1 -> 1.2
    h.approve()
    assert h.step == "1.2 Design architecture"

    # Submit 1.2 -> 1.3 (waiting)
    h.submit({})
    assert h.step == "1.3 Design review"
    assert h.status == "waiting"

    # Approve 1.3 -> expression condition "design_approved == true" is checked
    # After approve, submit runs; it calls _follow_transitions which checks conditions
    # design_approved is in state.data (from initial_data), should auto-route to 2.0
    h.approve()
    # After approve, submit({}) is called, which calls _follow_transitions
    # The expression "design_approved == true" checks context which includes state.data
    # design_approved=True was set in initial_data, so it should match
    assert h.step == "2.1 Write failing test (Red)"


def test_expr_condition_false_takes_default(harness_factory):
    """When expression condition is false, follows default path."""
    h = harness_factory(
        "p1-tdd-expr.yaml",
        loop_data={"features": ["f1"], "design_approved": False},
    )
    h.start()
    h.approve()
    h.submit({})
    assert h.step == "1.3 Design review"

    # Approve 1.3 -> expression "design_approved == true" is false -> default goes to 1.2
    h.approve()
    assert h.step == "1.2 Design architecture"


def test_eval_node_condition(harness_factory):
    """Expression conditions auto-evaluate quality_pass at step 2.5."""
    h = harness_factory(
        "p1-tdd-expr.yaml",
        loop_data={"features": ["f1", "f2"], "design_approved": True, "quality_pass": True},
    )
    h.start()
    h.approve()
    h.submit({})
    h.approve()
    # design_approved == true -> auto-advance past 1.3 to 2.0 -> 2.1
    assert h.step == "2.1 Write failing test (Red)"

    # Do a loop pass: 2.1 -> 2.2 -> 2.3 -> 2.4 -> 2.5
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.5 Quality check"

    # Submit at 2.5: "quality_pass == true" is true -> go to 2.0 Feature loop
    # Loop is at i=0, n=2 -> increments to i=1, enters next iteration child
    h.submit({})
    assert h.step == "2.1 Write failing test (Red)"
    # Verify we're on iteration 2
    status = h.get_status()
    assert "[2/" in status["display_path"]


def test_edit_policy_reported_in_status(harness_factory):
    """get_status() includes edit_policy from registered node."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.goto("2.1 Write failing test (Red)")

    # Register node with edit policy using the step name as key
    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="warn",
                patterns=[
                    EditPolicyPattern(glob="tests/**", policy="silent"),
                    EditPolicyPattern(glob="src/**", policy="block"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["current_step"] == "2.1 Write failing test (Red)"
    assert status["node"] is not None
    assert status["node"]["edit_policy"]["default"] == "warn"


def test_edit_policy_block_pattern(harness_factory):
    """Edit policy glob matching works for block patterns."""
    from vibe_linter.engine.policy import check_edit_policy
    from vibe_linter.types import EditPolicy, EditPolicyPattern

    policy = EditPolicy(
        default="silent",
        patterns=[
            EditPolicyPattern(glob="src/**", policy="block"),
            EditPolicyPattern(glob="tests/**", policy="warn"),
        ],
    )
    assert check_edit_policy("src/main.py", policy) == "block"
    assert check_edit_policy("tests/test_foo.py", policy) == "warn"
    assert check_edit_policy("README.md", policy) == "silent"


def test_empty_features_skips_loop(harness_factory):
    """Empty features list causes loop to be skipped."""
    h = harness_factory(
        "p1-tdd-expr.yaml",
        loop_data={"features": [], "design_approved": True},
    )
    h.start()
    h.approve()
    h.submit({})
    h.approve()
    # design_approved == true -> go to 2.0 Feature loop
    # Empty features -> loop skipped -> exits to next step after loop
    # In p1-tdd-expr.yaml, the loop's second transition goes to 3.1
    # Actually, loop step only has sub-steps as transitions. Let's check...
    # The iterate step transitions[0] is first child, transitions[1] is next after loop
    # For empty list, _handle_loop checks transitions[1] which should be "3.1 Integration testing"
    assert h.step == "3.1 Integration testing"


def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve({"requirements": "build it"})
    h.submit({"design": "plan"})

    # Save checkpoint at design review
    h.save_checkpoint("at_design_review")

    # Continue working
    h.approve()
    h.submit_goto("2.0 Feature loop")
    assert h.step == "2.1 Write failing test (Red)"

    # Load checkpoint
    restored = h.load_checkpoint("at_design_review")
    assert restored is not None
    assert restored.current_step == "1.3 Design review"
    assert "1.2 Design architecture" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Design architecture"

    r = h.retry()
    assert r
    assert h.step == "1.2 Design architecture"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    # History has only "start" and the initial step, both for 1.1
    # back() looks for a different step in history
    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Design architecture"

    h.submit({})
    assert h.step == "1.3 Design review"

    r = h.back()
    assert r
    assert h.step == "1.2 Design architecture"


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.goto("3.2 Final review")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})

    for _ in range(3):
        h.start()
        h.approve()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Gather requirements"


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    h.submit({})
    h.approve()
    h.submit_goto("2.0 Feature loop")
    assert h.step == "2.1 Write failing test (Red)"

    h.register_node(
        "2.1 Write failing test (Red)",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step by following TDD principles.\n\n## Steps\n1. Analyze requirements\n2. Write test\n3. Submit output",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-tdd.yaml", loop_data={"features": ["f1"]})
    h.start()
    h.approve()
    assert h.step == "1.2 Design architecture"

    h.register_node(
        "1.2 Design architecture",
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
