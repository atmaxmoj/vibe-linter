"""Test scenarios for Project-Based Learning workflow (p7-project-based.yaml).

Tests the Project-Based Learning workflow including:
- Setup phase (define goals, break into milestones)
- Milestone loop with pass/fail 2-way branching
- Retry path when milestone not met
- Presentation phase
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


def _walk_to_milestone_loop(h):
    """Start -> define goals -> break into milestones -> enter loop."""
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 2.1 (loop entry)
    assert h.step == "2.1 Study required concepts"
    assert h.status == "running"


def _complete_one_milestone_pass(h):
    """Complete one milestone: study -> implement -> test -> met -> loop header."""
    h.submit({})  # 2.1 -> 2.2
    h.submit({})  # 2.2 -> 2.3
    h.submit({})  # 2.3 -> 2.4
    h.submit_goto("2.0 Milestone loop")  # met -> loop header


# ================================================================
# Scenario 1: Happy path 2 milestones
# ================================================================


def test_happy_path_2_milestones(harness_factory):
    """Building a personal finance tracker: authentication and transaction milestones both pass."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["authentication", "transactions"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define project goals"
    assert h.status == "running"

    r = h.submit({
        "project": "Personal Finance Tracker Web App",
        "goals": "Track income/expenses, categorize transactions, show monthly summaries",
        "tech_stack": "React, Node.js, PostgreSQL",
    })
    assert r
    assert r.new_step == "1.2 Break into milestones"
    assert h.step == "1.2 Break into milestones"

    r = h.submit({
        "milestones": [
            "M1: User authentication (signup, login, JWT sessions)",
            "M2: Transaction CRUD (add, edit, delete, categorize)",
        ],
    })
    assert r
    assert r.new_step == "2.1 Study required concepts"
    assert h.step == "2.1 Study required concepts"

    milestone_data = [
        {
            "study": {"concepts": "JWT tokens, bcrypt password hashing, HTTP-only cookies"},
            "implement": {"code": "Built /auth/signup and /auth/login endpoints, bcrypt for passwords, JWT in HTTP-only cookie"},
            "test": {"tests_written": 12, "coverage": "95%", "result": "All auth flows pass including token expiry"},
        },
        {
            "study": {"concepts": "REST API design, PostgreSQL JSONB for categories, input validation"},
            "implement": {"code": "Built /transactions CRUD endpoints with category tagging and amount validation"},
            "test": {"tests_written": 18, "coverage": "91%", "result": "CRUD + category filter + date range queries all pass"},
        },
    ]

    for i in range(2):
        assert h.step == "2.1 Study required concepts"
        r = h.submit(milestone_data[i]["study"])
        assert r
        assert r.new_step == "2.2 Implement milestone"
        assert h.step == "2.2 Implement milestone"
        r = h.submit(milestone_data[i]["implement"])
        assert r
        assert r.new_step == "2.3 Test milestone"
        assert h.step == "2.3 Test milestone"
        r = h.submit(milestone_data[i]["test"])
        assert r
        assert r.new_step == "2.4 Milestone met?"
        assert h.step == "2.4 Milestone met?"

        # Milestone met -> next milestone / exit loop
        r = h.submit_goto("2.0 Milestone loop")
        assert r
        if i < 1:
            assert r.new_step == "2.1 Study required concepts"
            assert h.step == "2.1 Study required concepts"

    assert h.step == "3.1 Present project"

    r = h.submit({
        "presentation": "Demo: signup, login, add transactions, view categorized spending for March",
        "audience_feedback": "Clean UI, consider adding CSV export for tax season",
    })
    assert r
    assert r.new_step == "3.2 Reflection"
    assert h.step == "3.2 Reflection"

    r = h.submit({
        "reflection": "Learned JWT auth patterns and REST design. Next iteration: add CSV export and budget alerts.",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_happy_path_data_accumulates(harness_factory):
    """Data submitted at each step persists in state.data."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.submit({"goals": "build a web app"})
    assert h.state.data["1.1 Define project goals"]["goals"] == "build a web app"

    h.submit({"milestones": "auth, api, ui"})
    assert h.state.data["1.2 Break into milestones"]["milestones"] == "auth, api, ui"

    h.submit({"concepts": "REST, JWT"})
    assert h.state.data["2.1 Study required concepts"]["concepts"] == "REST, JWT"


def test_happy_path_history_audit(harness_factory):
    """History contains expected action types for full walkthrough."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Milestone loop")
    h.submit({})
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_happy_path_cross_executor_in_loop(harness_factory):
    """Close executor mid-loop, reopen, state persists."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1", "m2"]},
    )
    _walk_to_milestone_loop(h)
    h.submit({})
    assert h.step == "2.2 Implement milestone"

    h.new_executor()

    assert h.step == "2.2 Implement milestone"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Milestone loop")
    assert loop_info is not None
    assert loop_info["i"] == 0


def test_happy_path_node_validates(harness_factory):
    """Validate node rejects bad data at study concepts step."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    _walk_to_milestone_loop(h)

    h.register_node(
        "2.1 Study required concepts",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("concepts") else "must include concepts",
        ),
    )

    r = h.submit({"notes": "forgot concepts"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"concepts": "REST, JWT"})
    assert r
    assert r.new_step == "2.2 Implement milestone"


def test_happy_path_node_archives(harness_factory):
    """Archive node writes milestone results to SQLite table."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1", "m2"]},
    )
    _walk_to_milestone_loop(h)

    h.register_node(
        "2.3 Test milestone",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"milestone": "string", "result": "string"}},
            archive={"table": "milestone_tests"},
        ),
    )

    h.submit({})
    h.submit({})
    h.submit({"milestone": "m1", "result": "pass"})
    h.submit_goto("2.0 Milestone loop")
    h.submit({})
    h.submit({})
    h.submit({"milestone": "m2", "result": "pass"})

    rows = h.get_archived_rows("milestone_tests")
    assert len(rows) == 2
    assert rows[0]["milestone"] == "m1"
    assert rows[1]["result"] == "pass"


# ================================================================
# Scenario 2: Milestone fail retry
# ================================================================


def test_milestone_fail_retry(harness_factory):
    """Building a chat app: WebSocket milestone fails due to reconnection bugs, fix and retry."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["websocket_chat"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Real-Time Chat Application", "goals": "1-on-1 messaging with typing indicators"})
    assert r
    r = h.submit({"milestones": ["M1: WebSocket-based real-time messaging"]})
    assert r
    assert h.step == "2.1 Study required concepts"

    # First attempt: study, implement, test, fail
    r = h.submit({"concepts": "WebSocket protocol, Socket.IO library, event-driven architecture"})
    assert r
    r = h.submit({"code": "Basic WebSocket server with message broadcasting, no reconnection handling"})
    assert r
    r = h.submit({"result": "FAIL: messages lost when client disconnects and reconnects, no message queue"})
    assert r
    assert h.step == "2.4 Milestone met?"
    r = h.submit_goto("2.1 Study required concepts")
    assert r
    assert r.new_step == "2.1 Study required concepts"
    assert h.step == "2.1 Study required concepts"

    # Second attempt: add message queue and reconnection logic
    r = h.submit({"concepts": "Message queuing with Redis pub/sub, Socket.IO auto-reconnect, message acknowledgment"})
    assert r
    r = h.submit({"code": "Added Redis message buffer, Socket.IO reconnect with exponential backoff, ACK-based delivery"})
    assert r
    r = h.submit({"result": "PASS: messages delivered reliably after reconnect, typing indicators work, 0 lost messages in 100 disconnect/reconnect cycles"})
    assert r
    assert h.step == "2.4 Milestone met?"
    r = h.submit_goto("2.0 Milestone loop")
    assert r
    assert h.step == "3.1 Present project"


# ================================================================
# Scenario 3: Review rejected rework
# ================================================================


def test_review_rejected_rework(harness_factory):
    """Weather app: data visualization milestone fails twice (chart lib issues), dashboard passes immediately."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["data_visualization", "dashboard_layout"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Weather Dashboard App", "goals": "Show 7-day forecast with interactive charts"})
    assert r
    r = h.submit({"milestones": ["M1: Interactive temperature/humidity charts", "M2: Responsive dashboard layout"]})
    assert r

    # Milestone 1: first attempt fails -- wrong chart library
    r = h.submit({"concepts": "Chart.js basics, canvas rendering"})
    assert r
    r = h.submit({"code": "Chart.js line chart for temperature, but no zoom/pan support"})
    assert r
    r = h.submit({"result": "FAIL: Chart.js does not support pinch-to-zoom on mobile"})
    assert r
    r = h.submit_goto("2.1 Study required concepts")
    assert r
    assert r.new_step == "2.1 Study required concepts"
    assert h.step == "2.1 Study required concepts"

    # Milestone 1: second attempt fails -- D3 too complex
    r = h.submit({"concepts": "D3.js SVG rendering, custom zoom behavior"})
    assert r
    r = h.submit({"code": "D3 SVG chart with zoom, but 500ms render time on mobile"})
    assert r
    r = h.submit({"result": "FAIL: D3 SVG rendering too slow on low-end devices"})
    assert r
    r = h.submit_goto("2.1 Study required concepts")
    assert r
    assert r.new_step == "2.1 Study required concepts"
    assert h.step == "2.1 Study required concepts"

    # Milestone 1: third attempt passes -- Recharts (React wrapper with canvas)
    r = h.submit({"concepts": "Recharts library, responsive containers, canvas-based rendering"})
    assert r
    r = h.submit({"code": "Recharts ResponsiveContainer with Line chart, renders in <100ms"})
    assert r
    r = h.submit({"result": "PASS: interactive zoom works on mobile, renders under 100ms"})
    assert r
    r = h.submit_goto("2.0 Milestone loop")
    assert r
    assert r.new_step == "2.1 Study required concepts"
    assert h.step == "2.1 Study required concepts"

    # Milestone 2: dashboard layout passes immediately
    r = h.submit({"concepts": "CSS Grid, media queries, Tailwind responsive utilities"})
    assert r
    r = h.submit({"code": "Tailwind CSS grid layout with breakpoints for mobile/tablet/desktop"})
    assert r
    r = h.submit({"result": "PASS: layout adapts correctly across all screen sizes"})
    assert r
    r = h.submit_goto("2.0 Milestone loop")
    assert r
    assert h.step == "3.1 Present project"


# ================================================================
# Scenario 4: Cross-phase fallback
# ================================================================


def test_back_to_loop_cross_phase_fallback(harness_factory):
    """Blog engine: during presentation, realized search indexing is broken, go back to fix."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["full_text_search"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Blog Engine with Full-Text Search", "goals": "Create, edit, search blog posts"})
    assert r
    r = h.submit({"milestones": ["M1: Full-text search with PostgreSQL tsvector"]})
    assert r

    # Complete loop
    r = h.submit({"concepts": "PostgreSQL tsvector, GIN indexes, ts_query"})
    assert r
    r = h.submit({"code": "Added tsvector column with GIN index, search endpoint uses plainto_tsquery"})
    assert r
    r = h.submit({"result": "PASS: search returns relevant posts within 10ms"})
    assert r
    r = h.submit_goto("2.0 Milestone loop")
    assert r
    assert h.step == "3.1 Present project"

    # During presentation demo, search fails on posts with special characters
    r = h.goto("2.1 Study required concepts")
    assert r
    assert r.new_step == "2.1 Study required concepts"
    assert h.step == "2.1 Study required concepts"
    assert h.status == "running"

    # Redo: handle special characters in search queries
    r = h.submit({"concepts": "websearch_to_tsquery for user input sanitization, unaccent extension"})
    assert r
    r = h.submit({"code": "Switched to websearch_to_tsquery, added unaccent for diacritic-insensitive search"})
    assert r
    r = h.submit({"result": "Search now handles quotes, hyphens, and accented characters correctly"})
    assert r
    assert h.step == "2.4 Milestone met?"


# ================================================================
# Scenario 5: Stop then resume
# ================================================================


def test_stop_then_resume(harness_factory):
    """Building an e-commerce API: stop implementation for a job interview, resume the next day."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["product_catalog", "shopping_cart"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "E-Commerce REST API", "goals": "Product catalog, cart, and checkout"})
    assert r
    r = h.submit({"milestones": ["M1: Product catalog with search", "M2: Shopping cart management"]})
    assert r
    r = h.submit({"concepts": "REST resource design, pagination, filtering with query params"})
    assert r
    assert h.step == "2.2 Implement milestone"

    # Have a job interview -- stop working
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Implement milestone"

    # Next day -- resume implementation
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Implement milestone"

    # Continue from where we left off
    r = h.submit({"code": "GET /products with pagination, GET /products/:id, search via ?q= query param"})
    assert r
    assert r.new_step == "2.3 Test milestone"
    assert h.step == "2.3 Test milestone"


# ================================================================
# Scenario 6: Skip a step
# ================================================================


def test_skip_a_step(harness_factory):
    """Task manager app: second milestone reuses auth code from prior project, skip study and implement."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["task_crud", "user_auth"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Task Manager App", "goals": "CRUD tasks with user authentication"})
    assert r
    r = h.submit({"milestones": ["M1: Task CRUD operations", "M2: User authentication (reuse from finance tracker)"]})
    assert r

    # Milestone 1: task CRUD -- complete normally
    r = h.submit({"concepts": "REST CRUD patterns, input validation with Joi"})
    assert r
    r = h.submit({"code": "POST/GET/PUT/DELETE /tasks endpoints with Joi schema validation"})
    assert r
    r = h.submit({"result": "PASS: all CRUD operations work, validation rejects invalid input"})
    assert r
    r = h.submit_goto("2.0 Milestone loop")
    assert r

    # Milestone 2: auth -- already built in finance tracker project, skip study and implement
    assert h.step == "2.1 Study required concepts"
    r = h.skip("JWT auth concepts already mastered in finance tracker project")
    assert r
    assert h.step == "2.2 Implement milestone"
    r = h.skip("Copied auth module from finance tracker, only changed DB connection string")
    assert r
    assert h.step == "2.3 Test milestone"

    r = h.submit({"result": "PASS: auth tests from finance tracker all pass in new context"})
    assert r
    assert r.new_step == "2.4 Milestone met?"
    assert h.step == "2.4 Milestone met?"

    r = h.submit_goto("2.0 Milestone loop")
    assert r
    assert h.step == "3.1 Present project"


# ================================================================
# Scenario 7: Complete then reset
# ================================================================


def test_complete_then_reset(harness_factory):
    """Finish URL shortener project, reset for a new project (recipe sharing app)."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["url_shortening"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "URL Shortener Service", "goals": "Shorten URLs, track clicks, custom aliases"})
    assert r
    r = h.submit({"milestones": ["M1: URL shortening with Base62 encoding and click tracking"]})
    assert r
    r = h.submit({"concepts": "Base62 encoding, Redis caching for hot URLs, click counter with atomic increment"})
    assert r
    r = h.submit({"code": "POST /shorten, GET /:alias redirects, click count via Redis INCR"})
    assert r
    r = h.submit({"result": "PASS: shortened URLs redirect correctly, click counts accurate under load"})
    assert r
    r = h.submit_goto("2.0 Milestone loop")
    assert r
    r = h.submit({"presentation": "Demo: shorten github.com, custom alias, view click analytics dashboard"})
    assert r
    r = h.submit({"reflection": "Learned Base62 encoding and Redis atomic operations. Project complete."})
    assert r

    assert h.step == "Done"
    assert h.status == "done"

    # Reset for a new project
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define project goals"
    assert h.status == "running"


# ================================================================
# Scenario 8: Back
# ================================================================


def test_back(harness_factory):
    """Pomodoro timer app: milestones too granular, go back to redefine them."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["timer_core"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Pomodoro Timer Desktop App", "goals": "25-min work, 5-min break, with stats"})
    assert r
    assert h.step == "1.2 Break into milestones"

    # Milestones too granular -- go back and redefine project scope
    r = h.back()
    assert r
    assert h.step == "1.1 Define project goals"

    r = h.submit({"project": "Pomodoro Timer CLI Tool", "goals": "Simple CLI timer with notification sound"})
    assert r
    r = h.submit({"milestones": ["M1: Timer core with terminal countdown and system notification"]})
    assert r
    r = h.submit({"concepts": "Python asyncio for timer, plyer for desktop notifications"})
    assert r
    r = h.submit({"code": "asyncio countdown loop with plyer.notification on completion"})
    assert r
    assert h.step == "2.3 Test milestone"

    # Realized implementation missed the notification sound -- go back
    r = h.back()
    assert r
    assert h.step == "2.2 Implement milestone"


# ================================================================
# Scenario 9: Goto to presentation
# ================================================================


def test_goto_to_presentation(harness_factory):
    """Portfolio website already built last semester: jump straight to presentation for grade."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["portfolio_layout", "project_gallery"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Developer Portfolio Website", "goals": "Showcase projects, resume, and contact form"})
    assert r
    r = h.submit({"milestones": ["M1: Responsive layout", "M2: Project gallery with filters"]})
    assert r

    # Already built and deployed last semester -- jump to presentation
    r = h.goto("3.1 Present project")
    assert r
    assert r.new_step == "3.1 Present project"
    assert h.step == "3.1 Present project"
    assert h.status == "running"

    r = h.submit({
        "presentation": "Live demo at portfolio.dev: responsive design, filterable project gallery, working contact form",
        "url": "https://myportfolio.dev",
    })
    assert r
    assert r.new_step == "3.2 Reflection"
    assert h.step == "3.2 Reflection"

    r = h.submit({
        "reflection": "Portfolio built with Next.js and Tailwind. Learned SSG, image optimization, and Vercel deployment.",
    })
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ================================================================
# Scenario 10: Modify YAML hot reload
# ================================================================


def test_modify_yaml_hot_reload(harness_factory):
    """Note-taking app: add a code review step before presentation to get mentor feedback."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["markdown_editor"]},
    )
    r = h.start()
    assert r

    r = h.submit({"project": "Markdown Note-Taking App", "goals": "Create, edit, and preview markdown notes"})
    assert r
    assert h.step == "1.2 Break into milestones"

    modified_yaml = """name: Project-Based Learning
description: Modified with code review step

steps:
  - 1.1 Define project goals

  - 1.2 Break into milestones

  - 2.0 Milestone loop:
      iterate: "milestones"
      children:
        - 2.1 Study required concepts
        - 2.2 Implement milestone
        - 2.3 Test milestone
        - 2.4 Milestone met?:
            next:
              - if: "milestone requirements met"
                go: 2.0 Milestone loop
              - go: 2.1 Study required concepts

  - 3.05 Code review:
      next: 3.1 Present project

  - 3.1 Present project

  - 3.2 Reflection

  - Done:
      type: terminate
      reason: Project complete
"""
    h.reload_yaml(modified_yaml)

    r = h.goto("3.05 Code review")
    assert r
    assert r.new_step == "3.05 Code review"
    assert h.step == "3.05 Code review"

    r = h.submit({
        "reviewer": "Mentor Dr. Johnson",
        "feedback": "Clean code structure. Suggestion: add keyboard shortcuts for bold/italic/code formatting.",
    })
    assert r
    assert r.new_step == "3.1 Present project"
    assert h.step == "3.1 Present project"


# ================================================================
# Error boundaries
# ================================================================


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
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
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.goto("3.2 Reflection")
    h.submit({})
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
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
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.submit({"goals": "build app"})
    h.submit({"milestones": "m1, m2"})

    h.save_checkpoint("at_milestone_loop")

    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Milestone loop")
    assert h.step == "3.1 Present project"

    restored = h.load_checkpoint("at_milestone_loop")
    assert restored is not None
    assert restored.current_step == "2.1 Study required concepts"
    assert "1.1 Define project goals" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    assert h.step == "1.1 Define project goals"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define project goals"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define project goals"


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.goto("3.2 Reflection")
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
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1", "m2", "m3"]},
    )
    _walk_to_milestone_loop(h)

    loop_info = h.state.loop_state["2.0 Milestone loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _complete_one_milestone_pass(h)

    loop_info = h.state.loop_state["2.0 Milestone loop"]
    assert loop_info["i"] == 1


def test_empty_milestones_skips_loop(harness_factory):
    """Empty milestones list causes loop to be skipped."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": []},
    )
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "3.1 Present project"
    assert h.status == "running"


# ================================================================
# Turing Machine Condition Checker tests
# ================================================================


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory(
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define project goals",
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
        "p7-project-based.yaml",
        loop_data={"milestones": ["m1"]},
    )
    h.start()
    h.register_node(
        "1.1 Define project goals",
        NodeDefinition(
            types=["auto"],
            check=lambda data: True,
            edit_policy=EditPolicy(default="block", patterns=[]),
        ),
    )
    status = h.get_status()
    assert status["node"]["edit_policy"]["default"] == "block"
