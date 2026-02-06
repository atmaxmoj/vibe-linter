"""Tests for Spike and Stabilize SOP (p1-spike.yaml).

Workflow structure:
- 1.1 Define spike goals
- 1.2 Build prototype
- 1.3 Spike evaluation (LLM: viable->2.0, else->1.4)
- 1.4 Pivot approach -> goes to 1.2
- 2.0 Development loop (iterate: "work_items")
  - 2.1 Implement feature
  - 2.2 Write tests
  - 2.3 Run tests
  - 2.4 Feature quality check (LLM: pass->2.0, else->2.1)
- 3.1 Demo to stakeholder (wait, LLM: approved->Done, else->1.4)
- Done (terminate)

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


def _walk_to_spike_eval(h):
    """Common helper: start -> submit 1.1 -> submit 1.2 -> arrive at 1.3."""
    h.start()
    h.submit({"goals": "validate caching approach"})
    h.submit({"prototype": "cache_poc.py"})
    assert h.step == "1.3 Spike evaluation"
    assert h.status == "running"


def _enter_dev_loop(h):
    """Common helper: get past spike into dev loop iteration 1."""
    _walk_to_spike_eval(h)
    h.submit_goto("2.0 Development loop")
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"


def _do_one_dev_pass(h, data=None):
    """Complete one implement-test-run-quality cycle ending at quality check."""
    h.submit(data or {"impl": "code"})      # 2.1 -> 2.2
    h.submit(data or {"tests": "written"})   # 2.2 -> 2.3
    h.submit(data or {"result": "pass"})     # 2.3 -> 2.4
    assert h.step == "2.4 Feature quality check"


# ===============================================================
# Scenario 1: Spike passes, develop 2 features (original)
# ===============================================================

def test_spike_pass_then_develop(harness_factory):
    """Real-time collaboration: spike WebSocket viability, then build cursor sync and live editing."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["cursor_sync", "live_editing"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"
    assert h.status == "running"

    # Spike phase: validate WebSocket approach for real-time collab
    r = h.submit({
        "goals": "Validate WebSocket for sub-100ms cursor sync between 50+ concurrent editors",
        "hypothesis": "WebSocket with binary frames can handle 50+ users at <100ms latency",
        "success_criteria": "P95 latency < 100ms with 50 simulated clients",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"
    assert h.status == "running"

    r = h.submit({
        "prototype": "spike/ws_collab_poc.py",
        "stack": "Python asyncio + websockets library",
        "benchmark": "P95 latency 42ms with 50 clients, 180 cursor updates/sec",
        "conclusion": "WebSocket approach is viable, proceed to formal development",
    })
    assert r
    assert r.new_step == "1.3 Spike evaluation"
    assert h.step == "1.3 Spike evaluation"
    assert h.status == "running"

    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"

    # Verify loop state initialized
    status = h.get_status()
    assert "[1/" in status["display_path"]

    # Feature 1: Cursor synchronization
    r = h.submit({
        "feature": "cursor_sync",
        "files": ["collab/cursor_manager.py", "collab/ws_handler.py"],
        "summary": "Broadcast cursor position via WS binary frames, debounce at 60fps",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    assert h.status == "running"

    r = h.submit({
        "test_file": "tests/test_cursor_sync.py",
        "test_count": 8,
        "notable": ["test_50_clients_latency_under_100ms", "test_cursor_debounce_60fps"],
    })
    assert r
    assert r.new_step == "2.3 Run tests"
    assert h.step == "2.3 Run tests"
    assert h.status == "running"

    r = h.submit({"passed": 8, "failed": 0, "coverage": "89%"})
    assert r
    assert r.new_step == "2.4 Feature quality check"
    assert h.step == "2.4 Feature quality check"
    assert h.status == "running"

    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"

    # Verify second iteration
    status = h.get_status()
    assert "[2/" in status["display_path"]

    # Feature 2: Live document editing with CRDT
    r = h.submit({
        "feature": "live_editing",
        "files": ["collab/crdt.py", "collab/document.py"],
        "summary": "CRDT-based text editing with operational transform fallback",
    })
    assert r
    r = h.submit({
        "test_file": "tests/test_live_editing.py",
        "test_count": 12,
    })
    assert r
    r = h.submit({"passed": 12, "failed": 0, "coverage": "91%"})
    assert r
    assert h.step == "2.4 Feature quality check"

    r = h.submit_goto("2.0 Development loop")
    assert r
    # Loop exhausted -> moves to after-loop step
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    # Verify loop state cleaned up
    assert "2.0 Development loop" not in h.state.loop_state

    # WAIT+LLM: approve first, then submit_goto
    r = h.approve()
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_spike_rejected_pivot(harness_factory):
    """Image processing pipeline: SQLite rejected (too slow), Redis rejected (no persistence), PostgreSQL wins."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["image_pipeline"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"
    assert h.status == "running"

    # First spike attempt: SQLite for job queue
    r = h.submit({
        "goals": "Find a job queue backend for image processing pipeline (100 jobs/sec, durable)",
        "approach_1": "SQLite as job queue with polling",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"

    r = h.submit({
        "prototype": "spike/sqlite_queue.py",
        "result": "Handles 12 jobs/sec -- too slow (need 100/sec), write contention on WAL",
    })
    assert r
    assert r.new_step == "1.3 Spike evaluation"
    assert h.step == "1.3 Spike evaluation"

    # SQLite too slow -- pivot
    r = h.submit_goto("1.4 Pivot approach")
    assert r
    assert r.new_step == "1.4 Pivot approach"
    assert h.step == "1.4 Pivot approach"
    assert h.status == "running"

    r = h.submit({
        "pivot_reason": "SQLite maxes out at 12 jobs/sec due to single-writer lock",
        "new_approach": "Redis Streams as job queue",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"
    assert h.status == "running"

    # Second spike attempt: Redis Streams
    r = h.submit({
        "prototype": "spike/redis_queue.py",
        "result": "250 jobs/sec but Redis is in-memory only -- jobs lost on restart",
    })
    assert r
    assert r.new_step == "1.3 Spike evaluation"
    assert h.step == "1.3 Spike evaluation"

    # Redis not durable enough -- pivot again
    r = h.submit_goto("1.4 Pivot approach")
    assert r
    assert r.new_step == "1.4 Pivot approach"
    assert h.step == "1.4 Pivot approach"

    r = h.submit({
        "pivot_reason": "Redis Streams fast but not durable without AOF (adds latency)",
        "new_approach": "PostgreSQL SKIP LOCKED as job queue",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"

    # Third spike attempt: PostgreSQL SKIP LOCKED -- works!
    r = h.submit({
        "prototype": "spike/pg_queue.py",
        "result": "145 jobs/sec with SKIP LOCKED, fully durable, ACID guarantees",
    })
    assert r
    assert r.new_step == "1.3 Spike evaluation"
    assert h.step == "1.3 Spike evaluation"

    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"


def test_three_rejections_then_stop(harness_factory):
    """PDF renderer: 3 quality rejections (font rendering bugs), team stops to re-evaluate approach."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["pdf_renderer"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"

    # Get through spike phase
    r = h.submit({
        "goals": "Spike PDF rendering with Cairo graphics library",
    })
    assert r
    r = h.submit({
        "prototype": "spike/cairo_pdf.py",
        "result": "Basic PDF output works, proceed to formal development",
    })
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"

    # Attempt 1: font metrics off by 2px
    r = h.submit({
        "files": ["pdf/renderer.py", "pdf/fonts.py"],
        "issue": "Font metrics off by 2px, text overflows bounding boxes",
    })
    assert r
    r = h.submit({"test_file": "tests/test_renderer.py", "count": 10})
    assert r
    r = h.submit({"passed": 7, "failed": 3, "failures": "test_font_metrics_*"})
    assert r
    assert h.step == "2.4 Feature quality check"

    r = h.submit_goto("2.1 Implement feature")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"

    # Attempt 2: fixed metrics but ligatures broken
    r = h.submit({
        "fix": "Corrected font metrics using FreeType, but ligatures not rendering",
    })
    assert r
    r = h.submit({"added_tests": ["test_ligatures_fi_fl"]})
    assert r
    r = h.submit({"passed": 9, "failed": 2, "failures": "test_ligatures_*"})
    assert r
    r = h.submit_goto("2.1 Implement feature")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"

    # Attempt 3: ligatures fixed but right-to-left text broken
    r = h.submit({
        "fix": "Added HarfBuzz shaping for ligatures, but RTL text reversed",
    })
    assert r
    r = h.submit({"added_tests": ["test_rtl_arabic", "test_rtl_hebrew"]})
    assert r
    r = h.submit({"passed": 10, "failed": 2, "failures": "test_rtl_*"})
    assert r
    assert h.step == "2.4 Feature quality check"

    # Team decides to stop and re-evaluate the Cairo approach
    r = h.stop()
    assert r
    assert h.status == "stopped"

    # Submit while stopped should fail
    result = h.executor.submit({})
    assert not result
    assert "stopped" in result.message


def test_dev_loop_stop_resume(harness_factory):
    """Search engine spike: stop after indexing feature for holiday break, resume with ranking."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["indexer", "ranker"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"

    # Get to dev loop
    r = h.submit({
        "goals": "Spike inverted index with BM25 ranking for 1M document corpus",
    })
    assert r
    r = h.submit({
        "prototype": "spike/search_poc.py",
        "result": "Inverted index builds in 8s for 1M docs, BM25 query in <50ms",
    })
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"

    # Feature 1: Document indexer
    r = h.submit({
        "feature": "indexer",
        "files": ["search/indexer.py", "search/tokenizer.py"],
        "summary": "Inverted index with stemming, stop-word removal, batch indexing",
    })
    assert r
    r = h.submit({"test_file": "tests/test_indexer.py", "count": 14})
    assert r
    r = h.submit({"passed": 14, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"

    # Holiday break -- stop workflow
    r = h.stop()
    assert r
    assert h.status == "stopped"

    # January: resume with ranking feature
    r = h.resume()
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.status == "running"
    assert h.step == "2.1 Implement feature"

    # Feature 2: BM25 ranker
    r = h.submit({
        "feature": "ranker",
        "files": ["search/bm25.py", "search/query.py"],
        "summary": "BM25 scoring with TF-IDF fallback, query expansion",
    })
    assert r
    r = h.submit({"test_file": "tests/test_bm25.py", "count": 10})
    assert r
    r = h.submit({"passed": 10, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"


def test_skip_spike_direct_dev(harness_factory):
    """Caching layer: team already validated Redis in previous project, skip eval and start coding."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["cache_layer"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"

    r = h.submit({
        "goals": "Validate Redis caching for API response memoization",
        "note": "Team already used Redis caching in Project Alpha -- low risk",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"

    r = h.submit({
        "prototype": "spike/redis_cache_poc.py",
        "result": "Cache hit ratio 94%, P99 latency 3ms -- as expected from prior experience",
    })
    assert r
    assert r.new_step == "1.3 Spike evaluation"
    assert h.step == "1.3 Spike evaluation"

    # Team already knows Redis works -- skip evaluation, go straight to development
    r = h.goto("2.1 Implement feature")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"


def test_goto_dev_loop(harness_factory):
    """Email templating: spike done externally, goto development loop to build production version."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["template_engine"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"
    assert h.status == "running"

    # Spike was done in a separate branch -- jump directly to development
    r = h.goto("2.1 Implement feature")
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"

    r = h.submit({
        "feature": "template_engine",
        "files": ["email/templates.py", "email/renderer.py"],
        "summary": "Jinja2-based email template engine with MJML compilation",
    })
    assert r
    r = h.submit({
        "test_file": "tests/test_templates.py",
        "count": 11,
    })
    assert r
    r = h.submit({"passed": 11, "failed": 0})
    assert r

    # Use goto to reach demo since loop counter was not initialized via the loop header
    r = h.goto("3.1 Demo to stakeholder")
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "running"


def test_dev_wrong_direction_back_spike(harness_factory):
    """Notification service: realize implementation approach wrong, use back() to revise."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["push_notifications"]})
    r = h.start()
    assert r

    r = h.submit({
        "goals": "Spike push notification delivery via FCM",
    })
    assert r
    r = h.submit({
        "prototype": "spike/fcm_poc.py",
        "result": "FCM delivers to 10k devices in <2s, viable",
    })
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r

    r = h.submit({
        "feature": "push_notifications",
        "files": ["notifications/fcm.py"],
        "summary": "Direct FCM HTTP v1 API calls per device",
    })
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    assert h.status == "running"

    # Realize we should batch FCM calls, not per-device -- go back
    r = h.back()
    assert r
    assert r.new_step == "2.1 Implement feature"
    assert h.step == "2.1 Implement feature"
    assert h.status == "running"

    # back from 2.1 -> the most recent different step in history before 2.1
    r = h.back()
    assert r
    assert r.new_step == "2.2 Write tests"
    assert h.step == "2.2 Write tests"
    assert h.status == "running"


def test_done_reset_new_approach(harness_factory):
    """Video transcoding V1 shipped with FFmpeg, reset to spike GPU-accelerated approach for V2."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["transcode_api"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"

    # Quick path to done: V1 with CPU-based FFmpeg
    r = h.submit({
        "goals": "Spike FFmpeg-based video transcoding for H.264 output",
    })
    assert r
    r = h.submit({
        "prototype": "spike/ffmpeg_transcode.py",
        "result": "FFmpeg transcodes 1080p at 2x realtime on 4-core VM",
    })
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"

    r = h.submit({
        "files": ["transcode/ffmpeg_worker.py", "transcode/api.py"],
        "summary": "REST API wrapping FFmpeg subprocess, S3 input/output",
    })
    assert r
    r = h.submit({"test_file": "tests/test_transcode.py", "count": 9})
    assert r
    r = h.submit({"passed": 9, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    r = h.approve()
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"

    # V1 shipped -- try to submit when done
    result = h.executor.submit({})
    assert not result
    assert "already completed" in result.message

    # Reset for V2: GPU-accelerated transcoding with NVENC
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"
    assert h.status == "running"


def test_demo_reject_then_approve(harness_factory):
    """Dashboard analytics: stakeholder rejects chart library, pivot to D3.js, approved on second demo."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["analytics_charts"]})
    r = h.start()
    assert r

    # Get to demo with Chart.js approach
    r = h.submit({
        "goals": "Spike interactive analytics dashboard with Chart.js",
    })
    assert r
    r = h.submit({
        "prototype": "spike/chartjs_dashboard.html",
        "result": "Basic bar/line charts render, but no drill-down or real-time updates",
    })
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"

    r = h.submit({
        "files": ["dashboard/charts.js", "dashboard/data_fetcher.py"],
        "summary": "Chart.js with REST API data source, 5 chart types",
    })
    assert r
    r = h.submit({"test_file": "tests/test_charts.py", "count": 7})
    assert r
    r = h.submit({"passed": 7, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    # Stakeholder rejects: "Need drill-down, real-time, and custom tooltips -- Chart.js too limited"
    r = h.approve()
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "running"

    r = h.submit_goto("1.4 Pivot approach")
    assert r
    assert r.new_step == "1.4 Pivot approach"
    assert h.step == "1.4 Pivot approach"
    assert h.status == "running"

    # Pivot to D3.js for full customization
    r = h.submit({
        "pivot_reason": "Chart.js lacks drill-down and custom interaction handlers",
        "new_approach": "D3.js with custom React wrapper for drill-down and real-time WebSocket updates",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"

    r = h.submit({
        "prototype": "spike/d3_dashboard.html",
        "result": "D3.js supports drill-down, custom tooltips, WebSocket live updates",
    })
    assert r
    assert r.new_step == "1.3 Spike evaluation"

    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "2.1 Implement feature"

    r = h.submit({
        "files": ["dashboard/d3_charts.js", "dashboard/websocket.py"],
        "summary": "D3.js charts with drill-down, WebSocket real-time data feed",
    })
    assert r
    r = h.submit({"test_file": "tests/test_d3_charts.py", "count": 12})
    assert r
    r = h.submit({"passed": 12, "failed": 0})
    assert r
    r = h.submit_goto("2.0 Development loop")
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    # Stakeholder approves: "This is exactly what we need"
    r = h.approve()
    assert r
    assert r.new_step == "3.1 Demo to stakeholder"
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.status == "done"


def test_modify_yaml_add_spike_step(harness_factory):
    """Rate limiter spike: team adds a peer-review step for spike goals after realizing scope creep."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["token_bucket"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define spike goals"

    r = h.submit({
        "goals": "Spike token-bucket rate limiter for API gateway (10k req/sec per tenant)",
        "scope": "Single-node in-memory, Redis sync deferred to production phase",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"

    # Team realizes spike goals are too broad -- add a review step to YAML
    new_yaml = """名称: Spike and Stabilize
描述: Modified with extra step

步骤:
  - 1.1 Define spike goals

  - 1.15 Review spike goals

  - 1.2 Build prototype

  - 1.3 Spike evaluation:
      下一步:
        - 如果: "spike proves the approach is viable"
          去: 2.0 Development loop
        - 去: 1.4 Pivot approach

  - 1.4 Pivot approach:
      下一步: 1.2 Build prototype

  - 2.0 Development loop:
      遍历: "work_items"
      子步骤:
        - 2.1 Implement feature
        - 2.2 Write tests
        - 2.3 Run tests
        - 2.4 Feature quality check:
            下一步:
              - 如果: "feature is complete and tests pass"
                去: 2.0 Development loop
              - 去: 2.1 Implement feature

  - 3.1 Demo to stakeholder:
      类型: wait
      下一步:
        - 如果: "demo approved"
          去: Done
        - 去: 1.4 Pivot approach

  - Done:
      类型: terminate
      原因: Spike validated and development complete
"""
    h.reload_yaml(new_yaml)

    # Jump to new review step so team lead can narrow scope
    r = h.goto("1.15 Review spike goals")
    assert r
    assert r.new_step == "1.15 Review spike goals"
    assert h.step == "1.15 Review spike goals"
    assert h.status == "running"

    r = h.submit({
        "review_notes": "Narrow spike to single-tenant token bucket only, defer multi-tenant",
        "revised_scope": "Token bucket for 1 tenant, fixed 10k/sec window, no Redis",
        "reviewer": "tech_lead",
    })
    assert r
    assert r.new_step == "1.2 Build prototype"
    assert h.step == "1.2 Build prototype"
    assert h.status == "running"


# ===============================================================
# Data accumulation tests
# ===============================================================

def test_data_accumulates_spike_goals(harness_factory):
    """Submit data at 1.1 persists in state.data."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()

    h.submit({"goals": "validate caching strategy"})
    data = h.state.data
    assert "1.1 Define spike goals" in data
    assert data["1.1 Define spike goals"]["goals"] == "validate caching strategy"


def test_data_accumulates_prototype(harness_factory):
    """Submit data at 1.2 persists in state.data."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})

    h.submit({"prototype": "cache_poc.py"})
    data = h.state.data
    assert "1.2 Build prototype" in data
    assert data["1.2 Build prototype"]["prototype"] == "cache_poc.py"


def test_data_accumulates_through_dev_loop(harness_factory):
    """Data submitted in dev loop iterations persists in state.data."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)

    h.submit({"impl": "feature_code.py"})
    data = h.state.data
    assert "2.1 Implement feature" in data
    assert data["2.1 Implement feature"]["impl"] == "feature_code.py"

    h.submit({"tests": "test_feature.py"})
    data = h.state.data
    assert "2.2 Write tests" in data
    assert data["2.2 Write tests"]["tests"] == "test_feature.py"


def test_data_accumulates_all_phases(harness_factory):
    """Data accumulates across spike and dev phases."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({"goals": "validate"})
    h.submit({"prototype": "poc"})
    h.submit_goto("2.0 Development loop")
    h.submit({"impl": "code"})

    data = h.state.data
    assert "1.1 Define spike goals" in data
    assert "1.2 Build prototype" in data
    assert "2.1 Implement feature" in data


# ===============================================================
# History audit trail tests
# ===============================================================

def test_history_audit_full_walkthrough(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Development loop")
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Development loop")
    h.approve()
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "approve" in actions
    assert "terminate" in actions[-1]


def test_history_records_goto(harness_factory):
    """History records goto action."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.goto("2.1 Implement feature")

    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


def test_history_records_skip(harness_factory):
    """Skip appears in history for non-LLM steps."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)

    h.skip("already implemented")
    history = h.get_history(10)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "already implemented"


def test_history_records_pivot(harness_factory):
    """History shows pivot path through 1.4."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _walk_to_spike_eval(h)

    h.submit_goto("1.4 Pivot approach")
    history = h.get_history(20)
    actions = [e["action"] for e in history]
    assert "submit" in actions
    assert "transition" in actions


# ===============================================================
# Cross-executor recovery tests
# ===============================================================

def test_cross_executor_at_spike_eval(harness_factory):
    """Close executor at spike evaluation, reopen, continue."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _walk_to_spike_eval(h)

    h.new_executor()

    assert h.step == "1.3 Spike evaluation"
    assert h.status == "running"

    r = h.submit_goto("2.0 Development loop")
    assert r
    assert h.step == "2.1 Implement feature"


def test_cross_executor_mid_dev_loop(harness_factory):
    """Close executor mid-dev-loop, reopen, loop_state preserved."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["a", "b"]})
    _enter_dev_loop(h)

    h.submit({"impl": "a_code"})
    assert h.step == "2.2 Write tests"

    h.new_executor()

    assert h.step == "2.2 Write tests"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Development loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_cross_executor_at_demo(harness_factory):
    """Close executor at demo, reopen, state persists."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)
    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    h.new_executor()

    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.goto("3.1 Demo to stakeholder")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)

    h.stop()
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "2.1 Implement feature"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


def test_cross_executor_preserves_loop_state(harness_factory):
    """Close executor mid-loop after one iteration, reopen, loop intact."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["a", "b", "c"]})
    _enter_dev_loop(h)

    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")

    h.submit({"impl": "mid_loop"})
    assert h.step == "2.2 Write tests"

    h.new_executor()

    assert h.step == "2.2 Write tests"
    loop_info = h.state.loop_state["2.0 Development loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


# ===============================================================
# Node validation tests
# ===============================================================

def test_node_validates_spike_goals(harness_factory):
    """Validate node rejects bad data at 1.1, accepts good data."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()

    h.register_node(
        "1.1 Define spike goals",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("goals") else "must include spike goals",
        ),
    )

    r = h.submit({"notes": "no goals"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"goals": "validate caching"})
    assert r
    assert r.new_step == "1.2 Build prototype"


def test_node_validates_prototype(harness_factory):
    """Validate node rejects missing prototype at 1.2."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Build prototype"

    h.register_node(
        "1.2 Build prototype",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("prototype") else "must include prototype",
        ),
    )

    r = h.submit({})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"prototype": "poc.py"})
    assert r
    assert r.new_step == "1.3 Spike evaluation"


def test_node_validates_feature_impl(harness_factory):
    """Validate node rejects missing impl at 2.1."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)

    h.register_node(
        "2.1 Implement feature",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("impl") else "must include impl",
        ),
    )

    r = h.submit({"notes": "no impl"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"impl": "feature.py"})
    assert r
    assert r.new_step == "2.2 Write tests"


# ===============================================================
# Node archival tests
# ===============================================================

def test_node_archives_spike_goals(harness_factory):
    """Archive node writes spike goals to SQLite."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()

    h.register_node(
        "1.1 Define spike goals",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"goal_name": "string"}},
            archive={"table": "spike_goals"},
        ),
    )

    r = h.submit({"goal_name": "validate caching"})
    assert r

    rows = h.get_archived_rows("spike_goals")
    assert len(rows) == 1
    assert rows[0]["goal_name"] == "validate caching"


def test_node_archives_per_dev_iteration(harness_factory):
    """Archive node accumulates one row per dev loop iteration."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1", "w2", "w3"]})
    _enter_dev_loop(h)

    h.register_node(
        "2.1 Implement feature",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"feature_name": "string"}},
            archive={"table": "feature_impls"},
        ),
    )

    for i in range(3):
        h.submit({"feature_name": f"feat_{i}"})
        h.submit({})
        h.submit({})
        h.submit_goto("2.0 Development loop")

    rows = h.get_archived_rows("feature_impls")
    assert len(rows) == 3


def test_node_archives_prototype(harness_factory):
    """Archive node at 1.2 writes prototype data to SQLite."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Build prototype"

    h.register_node(
        "1.2 Build prototype",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"proto_file": "string"}},
            archive={"table": "prototypes"},
        ),
    )

    r = h.submit({"proto_file": "cache_poc.py"})
    assert r

    rows = h.get_archived_rows("prototypes")
    assert len(rows) == 1
    assert rows[0]["proto_file"] == "cache_poc.py"


# ===============================================================
# Error boundary tests
# ===============================================================

def test_submit_on_waiting_fails(harness_factory):
    """Submit while waiting at demo returns failure."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)
    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    r = h.submit({"data": "should fail"})
    assert not r
    assert "waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.goto("3.1 Demo to stakeholder")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({})
    assert not r


def test_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.goto("3.1 Demo to stakeholder")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({"goals": "validate"})
    h.submit({"prototype": "poc"})
    assert h.step == "1.3 Spike evaluation"

    h.save_checkpoint("at_spike_eval")

    h.submit_goto("2.0 Development loop")
    assert h.step == "2.1 Implement feature"

    restored = h.load_checkpoint("at_spike_eval")
    assert restored is not None
    assert restored.current_step == "1.3 Spike evaluation"
    assert "1.2 Build prototype" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    assert h.step == "1.1 Define spike goals"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define spike goals"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define spike goals"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["a", "b", "c"]})
    _enter_dev_loop(h)

    loop_info = h.state.loop_state["2.0 Development loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")

    loop_info = h.state.loop_state["2.0 Development loop"]
    assert loop_info["i"] == 1

    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")

    loop_info = h.state.loop_state["2.0 Development loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["only"]})
    _enter_dev_loop(h)

    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")

    assert h.step == "3.1 Demo to stakeholder"
    assert "2.0 Development loop" not in h.state.loop_state


def test_reject_preserves_data(harness_factory):
    """Reject does not modify state.data."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    _enter_dev_loop(h)
    _do_one_dev_pass(h)
    h.submit_goto("2.0 Development loop")
    assert h.step == "3.1 Demo to stakeholder"
    assert h.status == "waiting"

    data_before = dict(h.state.data)
    h.reject("not ready")
    data_after = h.state.data
    assert data_before == data_after


def test_history_records_transition(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Development loop")
    assert h.step == "2.1 Implement feature"

    h.register_node(
        "2.1 Implement feature",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step by following Spike principles.\n\n## Steps\n1. Analyze requirements\n2. Implement feature\n3. Submit output",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-spike.yaml", loop_data={"work_items": ["w1"]})
    h.start()
    assert h.step == "1.1 Define spike goals"

    h.register_node(
        "1.1 Define spike goals",
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
