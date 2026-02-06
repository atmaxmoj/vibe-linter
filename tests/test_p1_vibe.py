"""Tests for Vibe Coding SOP (p1-vibe.yaml).

Workflow structure:
- 1.1 Describe what you want
- 1.2 Write code
- 1.3 Try it out
- 1.4 Evaluate result (LLM: works->2.1, tweaks->1.2, else->1.1)
- 2.1 Ship it -> Done (implicit next)
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

from vibe_linter.types import EditPolicy, EditPolicyPattern, NodeDefinition

# --- Helpers ---


def _walk_to_evaluate(h):
    """Common helper: start -> submit 1.1 -> submit 1.2 -> submit 1.3 -> arrive at 1.4."""
    h.start()
    h.submit({})   # 1.1 -> 1.2
    h.submit({})   # 1.2 -> 1.3
    h.submit({})   # 1.3 -> 1.4
    assert h.step == "1.4 Evaluate result"
    assert h.status == "running"


def _quick_ship(h):
    """From 1.4, ship immediately and reach Done."""
    h.submit_goto("2.1 Ship it")
    assert h.step == "2.1 Ship it"
    h.submit({})
    assert h.status == "done"


# ===============================================================
# Scenario 1: Prototype to ship (full walkthrough)
# ===============================================================

def test_prototype_to_ship(harness_factory):
    """Build a landing page for a weekend hackathon: describe, code, test, ship in one pass."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"
    assert h.status == "running"

    # 1.1 Describe: weekend hackathon landing page
    r = h.submit({
        "idea": "Single-page countdown landing page for HackWeekend 2025",
        "vibe": "Minimal, dark mode, big timer in the center, email signup form",
        "tech": "Just HTML + Tailwind CDN + vanilla JS, no build step",
    })
    assert r
    assert r.new_step == "1.2 Write code"
    assert h.step == "1.2 Write code"
    assert h.status == "running"

    # 1.2 Write: bang out the landing page
    r = h.submit({
        "file": "index.html",
        "code": "<html><head><script src='https://cdn.tailwindcss.com'></script></head>"
                "<body class='bg-gray-900 text-white flex items-center justify-center h-screen'>"
                "<div class='text-center'><h1 class='text-6xl font-bold'>HackWeekend 2025</h1>"
                "<div id='timer' class='text-4xl mt-8'></div>"
                "<input placeholder='your@email.com' class='mt-8 p-3 rounded bg-gray-800'/>"
                "<button class='ml-2 p-3 bg-blue-600 rounded'>Notify me</button></div></body></html>",
        "lines_of_code": 42,
    })
    assert r
    assert r.new_step == "1.3 Try it out"
    assert h.step == "1.3 Try it out"
    assert h.status == "running"

    # 1.3 Try: open in browser, looks great
    r = h.submit({
        "method": "open index.html in Chrome",
        "result": "Countdown timer ticking, dark background, email input renders, responsive on mobile",
        "screenshots": ["desktop_ok.png", "mobile_ok.png"],
    })
    assert r
    assert r.new_step == "1.4 Evaluate result"
    assert h.step == "1.4 Evaluate result"
    assert h.status == "running"

    # 1.4 Evaluate: works perfectly, ship it
    r = h.submit_goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"
    assert h.step == "2.1 Ship it"
    assert h.status == "running"

    # 2.1 Ship: deploy to Vercel
    r = h.submit({
        "deploy_target": "Vercel",
        "url": "https://hackweekend2025.vercel.app",
        "deploy_time": "12 seconds",
    })
    assert r
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    h.submit({"description": "build a chat app"})
    data = h.state.data
    assert "1.1 Describe what you want" in data
    assert data["1.1 Describe what you want"]["description"] == "build a chat app"

    h.submit({"code": "import flask"})
    data = h.state.data
    assert "1.2 Write code" in data
    assert data["1.2 Write code"]["code"] == "import flask"

    h.submit({"result": "renders OK"})
    data = h.state.data
    assert "1.3 Try it out" in data
    assert data["1.3 Try it out"]["result"] == "renders OK"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.1 Ship it")
    h.submit({})
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_write_code(harness_factory):
    """Close executor at write code step, reopen, continue."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({"description": "build a widget"})
    assert h.step == "1.2 Write code"

    h.new_executor()

    assert h.step == "1.2 Write code"
    assert h.status == "running"

    r = h.submit({"code": "def widget(): pass"})
    assert r
    assert r.new_step == "1.3 Try it out"


def test_s1_cross_executor_at_evaluate(harness_factory):
    """Close executor at evaluate step, reopen, continue to ship."""
    h = harness_factory("p1-vibe.yaml")
    _walk_to_evaluate(h)

    h.new_executor()

    assert h.step == "1.4 Evaluate result"
    assert h.status == "running"

    r = h.submit_goto("2.1 Ship it")
    assert r
    assert h.step == "2.1 Ship it"


def test_s1_node_validates_description(harness_factory):
    """Validate node rejects bad data, accepts good data on describe step."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    assert h.step == "1.1 Describe what you want"

    h.register_node(
        "1.1 Describe what you want",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("description") else "must include description",
        ),
    )

    r = h.submit({"notes": "vague idea"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"description": "build a chat app"})
    assert r
    assert r.new_step == "1.2 Write code"


def test_s1_node_archives_results(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    h.register_node(
        "1.1 Describe what you want",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"description": "string", "priority": "string"}},
            archive={"table": "vibe_descriptions"},
        ),
    )

    r = h.submit({"description": "chat app", "priority": "high"})
    assert r

    rows = h.get_archived_rows("vibe_descriptions")
    assert len(rows) == 1
    assert rows[0]["description"] == "chat app"
    assert rows[0]["priority"] == "high"


def test_s1_error_submit_on_done(harness_factory):
    """Submit on done workflow returns failure."""
    h = harness_factory("p1-vibe.yaml")
    _walk_to_evaluate(h)
    _quick_ship(h)

    r = h.submit({})
    assert not r


# ===============================================================
# Scenario 2: Quick bug fix (one tweak iteration)
# ===============================================================

def test_quick_bug_fix(harness_factory):
    """CLI weather tool: first attempt has broken API key handling, one tweak fixes it."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # 1.1 Describe: a quick CLI weather checker
    r = h.submit({
        "idea": "CLI tool that shows current weather for any city",
        "vibe": "Type 'weather tokyo' and get temp + conditions in the terminal",
    })
    assert r
    assert r.new_step == "1.2 Write code"

    # 1.2 Write: Python script using OpenWeather API
    r = h.submit({
        "file": "weather.py",
        "code": "import requests, sys; city=sys.argv[1]; r=requests.get(f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}'); print(r.json()['main']['temp'])",
        "note": "Hardcoded API_KEY variable, forgot to read from env",
    })
    assert r
    assert r.new_step == "1.3 Try it out"

    # 1.3 Try: it crashes because API_KEY is undefined
    r = h.submit({
        "command": "python weather.py tokyo",
        "result": "NameError: name 'API_KEY' is not defined",
        "works": False,
    })
    assert r
    assert r.new_step == "1.4 Evaluate result"
    assert h.step == "1.4 Evaluate result"

    # 1.4 Evaluate: mostly works, just needs the env var fix
    r = h.submit_goto("1.2 Write code")
    assert r
    assert r.new_step == "1.2 Write code"
    assert h.step == "1.2 Write code"
    assert h.status == "running"

    # 1.2 Write (tweak): read API key from environment
    r = h.submit({
        "file": "weather.py",
        "fix": "Added os.environ.get('OPENWEATHER_KEY') with fallback error message",
        "code": "import requests, sys, os; key=os.environ.get('OPENWEATHER_KEY'); city=sys.argv[1]; ...",
    })
    assert r
    assert r.new_step == "1.3 Try it out"

    # 1.3 Try: works now with env var set
    r = h.submit({
        "command": "OPENWEATHER_KEY=abc123 python weather.py tokyo",
        "result": "Tokyo: 18.5C, partly cloudy",
        "works": True,
    })
    assert r
    assert r.new_step == "1.4 Evaluate result"
    assert h.step == "1.4 Evaluate result"

    # 1.4 Evaluate: works perfectly now, ship it
    r = h.submit_goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"
    assert h.step == "2.1 Ship it"
    assert h.status == "running"

    # 2.1 Ship: publish to PyPI
    r = h.submit({
        "published_to": "PyPI as 'quick-weather'",
        "install_command": "pip install quick-weather",
    })
    assert r
    assert h.status == "done"


def test_s2_data_after_tweak(harness_factory):
    """Data from the tweak iteration overwrites the previous step data."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({"description": "v1"})
    h.submit({"code": "first_try"})
    h.submit({})
    # At 1.4, go back to 1.2
    h.submit_goto("1.2 Write code")
    h.submit({"code": "second_try"})

    data = h.state.data
    assert data["1.2 Write code"]["code"] == "second_try"


def test_s2_history_shows_loop_back(harness_factory):
    """History records the submit with goto back to 1.2."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("1.2 Write code")

    history = h.get_history(20)
    actions = [e["action"] for e in history]
    assert "transition" in actions


def test_s2_cross_executor_after_tweak(harness_factory):
    """Close executor after tweak loop-back, reopen, state correct."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("1.2 Write code")
    assert h.step == "1.2 Write code"

    h.new_executor()

    assert h.step == "1.2 Write code"
    assert h.status == "running"

    r = h.submit({"code": "fix v2"})
    assert r
    assert r.new_step == "1.3 Try it out"


def test_s2_node_validates_code(harness_factory):
    """Validate node on write code step rejects empty code."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Write code"

    h.register_node(
        "1.2 Write code",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("code") else "must include code",
        ),
    )

    r = h.submit({"notes": "no code here"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"code": "print('hello')"})
    assert r
    assert r.new_step == "1.3 Try it out"


# ===============================================================
# Scenario 3: Ten rounds getting worse
# ===============================================================

def test_ten_rounds_getting_worse(harness_factory):
    """AI-generated pixel art editor: 10 rounds of scope creep, each redescription makes it worse."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"
    assert h.status == "running"

    prompts = [
        {"idea": "Simple 16x16 pixel art canvas in the browser"},
        {"idea": "Pixel art canvas with color picker and undo"},
        {"idea": "Pixel art canvas with layers, color picker, undo, and export to PNG"},
        {"idea": "Full pixel art editor with animation frames, onion skinning, and tilemap mode"},
        {"idea": "Pixel art editor with AI-assisted color palette generation"},
        {"idea": "Pixel art editor with real-time multiplayer collaboration"},
        {"idea": "Pixel art editor with NFT minting integration"},
        {"idea": "Pixel art editor with 3D voxel preview of 2D sprites"},
        {"idea": "Pixel art editor that also does vector graphics and procedural generation"},
        {"idea": "Full game engine with integrated pixel art editor, physics, and scripting"},
    ]
    failures = [
        {"result": "Canvas renders but no draw handler attached", "works": False},
        {"result": "Color picker works but undo stack overflows", "works": False},
        {"result": "Layer system conflicts with undo, PNG export corrupted", "works": False},
        {"result": "Animation playback flickers, onion skinning off by 1 frame", "works": False},
        {"result": "AI palette API returns 429 rate limit after 3 requests", "works": False},
        {"result": "WebSocket multiplayer has 2s latency, cursors desync", "works": False},
        {"result": "NFT minting requires wallet connect which breaks on mobile", "works": False},
        {"result": "Three.js voxel renderer crashes tab on sprites > 32x32", "works": False},
        {"result": "SVG export loses pixel grid alignment, procedural gen is random noise", "works": False},
        {"result": "Script editor has no syntax highlighting, physics crashes on collision", "works": False},
    ]

    for _i in range(10):
        if h.step == "1.1 Describe what you want":
            r = h.submit(prompts[_i])
            assert r
            assert r.new_step == "1.2 Write code"
        assert h.step == "1.2 Write code"

        r = h.submit({"code": f"attempt_{_i}_500_lines_of_spaghetti.js", "lines": 500 + _i * 200})
        assert r
        assert r.new_step == "1.3 Try it out"
        assert h.step == "1.3 Try it out"

        r = h.submit(failures[_i])
        assert r
        assert r.new_step == "1.4 Evaluate result"
        assert h.step == "1.4 Evaluate result"

        # Nothing works, start over with even more ambitious scope
        r = h.submit_goto("1.1 Describe what you want")
        assert r
        assert r.new_step == "1.1 Describe what you want"
        assert h.step == "1.1 Describe what you want"
        assert h.status == "running"

    # Finally give up after 10 rounds of scope creep
    r = h.stop()
    assert r
    assert h.status == "stopped"


def test_s3_data_has_all_attempts(harness_factory):
    """After multiple rounds, last submit data wins per step key."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    for i in range(5):
        h.submit({"description": f"attempt_{i}"})
        h.submit({"code": f"code_{i}"})
        h.submit({})
        h.submit_goto("1.1 Describe what you want")

    data = h.state.data
    assert data["1.1 Describe what you want"]["description"] == "attempt_4"
    assert data["1.2 Write code"]["code"] == "code_4"


def test_s3_history_depth(harness_factory):
    """5 rounds of iteration produce many history entries."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    for _i in range(5):
        h.submit({})
        h.submit({})
        h.submit({})
        h.submit_goto("1.1 Describe what you want")

    history = h.get_history(200)
    assert len(history) >= 20


def test_s3_cross_executor_mid_retry(harness_factory):
    """Close executor after 3 rounds, reopen, continue."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    for _i in range(3):
        h.submit({})
        h.submit({})
        h.submit({})
        h.submit_goto("1.1 Describe what you want")

    assert h.step == "1.1 Describe what you want"

    h.new_executor()
    assert h.step == "1.1 Describe what you want"
    assert h.status == "running"

    r = h.submit({"description": "round 4"})
    assert r
    assert r.new_step == "1.2 Write code"


# ===============================================================
# Scenario 4: Decide proper dev, stop
# ===============================================================

def test_decide_proper_dev_stop(harness_factory):
    """Stripe integration prototype: 3 rounds of hacking reveal it needs proper error handling and tests."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # Round 1: basic charge endpoint
    r = h.submit({
        "idea": "Add Stripe one-time payment to our Flask app",
        "vibe": "Just a /charge endpoint that takes a token and amount",
    })
    assert r
    r = h.submit({
        "file": "app.py",
        "code": "stripe.Charge.create(amount=request.json['amount'], source=request.json['token'])",
    })
    assert r
    r = h.submit({
        "result": "Charge works with test card but no error handling for declined cards",
        "works": False,
    })
    assert r
    r = h.submit_goto("1.1 Describe what you want")
    assert r
    assert r.new_step == "1.1 Describe what you want"
    assert h.step == "1.1 Describe what you want"

    # Round 2: add error handling
    r = h.submit({
        "idea": "Same Stripe charge but handle CardError and InvalidRequestError",
    })
    assert r
    r = h.submit({
        "fix": "Added try/except for stripe.error.CardError, returns 402 with decline reason",
    })
    assert r
    r = h.submit({
        "result": "Error handling works but webhooks are missing, payments stuck in pending",
        "works": False,
    })
    assert r
    r = h.submit_goto("1.1 Describe what you want")
    assert r
    assert r.new_step == "1.1 Describe what you want"

    # Round 3: realize this needs webhooks, idempotency, proper architecture
    r = h.submit({
        "idea": "Need webhooks for payment_intent.succeeded, idempotency keys, retry logic",
    })
    assert r
    r = h.submit({
        "code": "Webhook endpoint with signature verification, but no idempotency yet",
    })
    assert r
    r = h.submit({
        "result": "Webhook fires but duplicate events cause double charges, need idempotency keys and a payment state machine",
        "works": False,
        "realization": "This is too complex for vibe coding, needs proper TDD approach",
    })
    assert r
    assert h.step == "1.4 Evaluate result"
    assert h.status == "running"

    # Decide this needs proper development with tests and architecture
    r = h.stop()
    assert r
    assert h.status == "stopped"


def test_s4_stop_rejects_submit(harness_factory):
    """After stopping, submits are rejected."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.stop()
    assert h.status == "stopped"

    r = h.submit({"code": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_s4_cross_executor_while_stopped(harness_factory):
    """Close executor while stopped, reopen, still stopped."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.stop()
    assert h.step == "1.3 Try it out"
    assert h.status == "stopped"

    h.new_executor()

    assert h.step == "1.3 Try it out"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "1.3 Try it out"


# ===============================================================
# Scenario 5: Stop, rest, resume
# ===============================================================

def test_stop_rest_resume(harness_factory):
    """Personal blog generator: stop at 2am for sleep, resume next morning and ship."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # 1.1 Describe: markdown-to-blog static site generator
    r = h.submit({
        "idea": "Static blog generator that converts markdown files to a styled HTML site",
        "vibe": "Minimal aesthetic, auto-generates index page with post list, RSS feed",
    })
    assert r
    assert r.new_step == "1.2 Write code"
    assert h.step == "1.2 Write code"
    assert h.status == "running"

    # 2am: too tired to keep coding, stop for the night
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "1.2 Write code"

    # Try to submit while stopped
    result = h.executor.submit({})
    assert not result
    assert "stopped" in result.message

    # 9am next morning: resume with fresh eyes
    r = h.resume()
    assert r
    assert r.new_step == "1.2 Write code"
    assert h.status == "running"
    assert h.step == "1.2 Write code"

    # 1.2 Write: Python script using markdown2 + Jinja2
    r = h.submit({
        "file": "blog.py",
        "code": "Parse all .md files in posts/, render with Jinja2 template, generate index.html with post list sorted by date",
        "dependencies": ["markdown2", "jinja2"],
    })
    assert r
    assert r.new_step == "1.3 Try it out"

    # 1.3 Try: run it on sample posts
    r = h.submit({
        "command": "python blog.py --input posts/ --output dist/",
        "result": "Generated 5 HTML pages, index page lists all posts with dates, RSS feed validates",
    })
    assert r
    assert r.new_step == "1.4 Evaluate result"

    # 1.4 Evaluate: looks great, ship to GitHub Pages
    r = h.submit_goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"
    assert h.step == "2.1 Ship it"

    # 2.1 Ship: push to gh-pages branch
    r = h.submit({
        "deploy": "GitHub Pages via gh-pages branch",
        "url": "https://myname.github.io/blog",
        "total_time": "45 minutes of actual coding",
    })
    assert r
    assert h.status == "done"


def test_s5_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p1-vibe.yaml")
    _walk_to_evaluate(h)
    _quick_ship(h)
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s5_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s5_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


def test_s5_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "1.3 Try it out"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "1.3 Try it out"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert r.new_step == "1.4 Evaluate result"


# ===============================================================
# Scenario 6: Skip straight to ship
# ===============================================================

def test_skip_straight_to_ship(harness_factory):
    """Internal Slack bot for standup reminders: YOLO skip evaluation, just deploy it."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # 1.1 Describe: Slack bot that DMs standup reminders
    r = h.submit({
        "idea": "Slack bot that sends daily standup reminders at 9am and collects responses",
        "vibe": "Simple, just post to #standup channel, no database needed",
    })
    assert r
    assert r.new_step == "1.2 Write code"

    # 1.2 Write: Node.js Slack bot with Bolt framework
    r = h.submit({
        "file": "bot.js",
        "code": "Bolt app with cron job at 9am UTC, sends blocks message to #standup, "
                "listens for thread replies, posts summary at 10am",
        "lines": 85,
    })
    assert r
    assert r.new_step == "1.3 Try it out"

    # 1.3 Try: sent a test message, looks fine
    r = h.submit({
        "result": "Test message posted to #standup-test, thread replies collected",
        "note": "Only tested happy path, but it is an internal tool so YOLO",
    })
    assert r
    assert r.new_step == "1.4 Evaluate result"
    assert h.step == "1.4 Evaluate result"

    # Skip evaluation entirely, just ship it (it is internal, who cares)
    r = h.goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"
    assert h.step == "2.1 Ship it"
    assert h.status == "running"

    # 2.1 Ship: deploy to Heroku free tier
    r = h.submit({
        "deploy": "Heroku hobby dyno",
        "slack_workspace": "acme-eng",
        "channel": "#standup",
    })
    assert r
    assert h.status == "done"


def test_s6_goto_does_not_add_data(harness_factory):
    """Goto does not produce a data entry (only submit does)."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.goto("2.1 Ship it")

    data = h.state.data
    assert "2.1 Ship it" not in data

    h.submit({"shipped": True})
    data = h.state.data
    assert "2.1 Ship it" in data


def test_s6_history_shows_goto(harness_factory):
    """History records a goto action."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.goto("2.1 Ship it")

    history = h.get_history(10)
    actions = [e["action"] for e in history]
    assert "goto" in actions


def test_s6_cross_executor_after_goto(harness_factory):
    """Goto to ship, close executor, reopen, state persists."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.goto("2.1 Ship it")
    assert h.step == "2.1 Ship it"

    h.new_executor()

    assert h.step == "2.1 Ship it"
    assert h.status == "running"

    r = h.submit({})
    assert r
    assert h.status == "done"


# ===============================================================
# Scenario 7: Back to previous round
# ===============================================================

def test_back_previous_round(harness_factory):
    """Recipe sharing app: realize at evaluation the UI is wrong, go back and redesign from scratch."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # 1.1 Describe: recipe sharing app
    r = h.submit({
        "idea": "Recipe sharing web app where users paste a recipe URL and get a clean card view",
        "vibe": "Pinterest-style grid of recipe cards with photo, title, and cook time",
    })
    assert r
    assert r.new_step == "1.2 Write code"

    # 1.2 Write: React app with URL scraping
    r = h.submit({
        "code": "React + Cheerio scraper, extracts title/image/time from recipe URLs",
        "components": ["RecipeCard", "RecipeGrid", "URLInput"],
    })
    assert r
    assert r.new_step == "1.3 Try it out"

    # 1.3 Try: grid renders but cards look terrible on mobile
    r = h.submit({
        "result": "Desktop looks OK but cards overflow on mobile, images not lazy loaded, grid is janky",
        "verdict": "Need to rethink the entire layout approach",
    })
    assert r
    assert r.new_step == "1.4 Evaluate result"
    assert h.step == "1.4 Evaluate result"

    # Go back to try step to re-test on a different device
    r = h.back()
    assert r
    assert r.new_step == "1.3 Try it out"
    assert h.step == "1.3 Try it out"
    assert h.status == "running"

    # Actually, go all the way back to the description to simplify the idea
    r = h.goto("1.1 Describe what you want")
    assert r
    assert r.new_step == "1.1 Describe what you want"
    assert h.step == "1.1 Describe what you want"
    assert h.status == "running"

    # Start over: simpler single-column layout, no grid
    r = h.submit({
        "idea": "Same recipe app but single-column feed like Instagram, mobile-first",
    })
    assert r
    r = h.submit({
        "code": "Simplified to single-column CSS, native lazy loading, viewport-based card sizing",
    })
    assert r
    r = h.submit({
        "result": "Mobile layout is clean, scrolls smoothly, images lazy load properly",
    })
    assert r
    r = h.submit_goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"
    assert h.step == "2.1 Ship it"
    assert h.status == "running"


def test_s7_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_s7_back_preserves_data(harness_factory):
    """Going back does not clear previously submitted data."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({"description": "widget"})
    h.submit({"code": "def widget(): pass"})
    assert h.step == "1.3 Try it out"

    h.back()
    assert h.step == "1.2 Write code"

    data = h.state.data
    assert data["1.1 Describe what you want"]["description"] == "widget"
    assert data["1.2 Write code"]["code"] == "def widget(): pass"


# ===============================================================
# Scenario 8: Done and start over
# ===============================================================

def test_done_start_over(harness_factory):
    """QR code generator v1 shipped, reset to start v2 with batch generation."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # V1: basic QR code generator
    r = h.submit({
        "idea": "Web app that generates QR codes from URLs",
        "vibe": "Paste a URL, get a QR code PNG, one-click download",
    })
    assert r
    r = h.submit({
        "code": "Python qrcode library + Flask, generates PNG on POST, returns base64 for preview",
    })
    assert r
    r = h.submit({
        "result": "QR codes generate correctly, download works, scans fine with phone camera",
    })
    assert r
    r = h.submit_goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"

    r = h.submit({
        "deploy": "Fly.io free tier",
        "url": "https://qrgen.fly.dev",
        "version": "1.0",
    })
    assert r
    assert h.status == "done"

    # V1 shipped, but users want batch generation
    result = h.executor.submit({})
    assert not result
    assert "already completed" in result.message

    # Reset to start V2
    h.reset()
    assert h.state is None

    # V2: batch QR code generation
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"
    assert h.status == "running"

    r = h.submit({
        "idea": "V2: upload CSV of URLs, generate QR codes in bulk, download as ZIP",
        "vibe": "Drag-and-drop CSV upload, progress bar, ZIP download",
    })
    assert r
    assert r.new_step == "1.2 Write code"
    assert h.step == "1.2 Write code"


def test_s8_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_s8_reset_clears_data(harness_factory):
    """After reset, state is None."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({"description": "stuff"})
    h.submit({"code": "plan"})

    h.reset()
    assert h.state is None


def test_s8_fresh_start_after_reset(harness_factory):
    """Reset then start gives a clean initial state."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.1 Ship it")

    h.reset()
    h.start()

    assert h.step == "1.1 Describe what you want"
    assert h.status == "running"
    data = h.state.data
    assert "2.1 Ship it" not in data


def test_s8_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p1-vibe.yaml")
    _walk_to_evaluate(h)
    _quick_ship(h)
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


# ===============================================================
# Scenario 9: Stopped submit rejected
# ===============================================================

def test_stopped_submit_rejected(harness_factory):
    """Pomodoro timer Chrome extension: API rate limit hit during testing, forced to stop."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # 1.1 Describe: pomodoro timer extension
    r = h.submit({
        "idea": "Chrome extension with a 25-min pomodoro timer, break reminders, Spotify integration",
    })
    assert r
    assert r.new_step == "1.2 Write code"

    # 1.2 Write: manifest v3 extension with Spotify API
    r = h.submit({
        "code": "Manifest V3 service worker, popup with timer UI, Spotify Web API to pause music on break",
    })
    assert r
    assert r.new_step == "1.3 Try it out"
    assert h.step == "1.3 Try it out"

    # Hit Spotify API rate limit during testing, need to wait 30 min
    r = h.stop()
    assert r
    assert h.status == "stopped"

    # Try to submit while stopped - rejected
    result = h.executor.submit({
        "result": "Timer works but Spotify returns 429 Too Many Requests",
    })
    assert not result
    assert "stopped" in result.message

    # Try goto while stopped - also rejected
    result = h.executor.submit({"_goto": "2.1 Ship it"})
    assert not result
    assert "stopped" in result.message

    # Still stopped at same step
    assert h.step == "1.3 Try it out"
    assert h.status == "stopped"


# ===============================================================
# Scenario 10: Done submit rejected
# ===============================================================

def test_done_submit_rejected(harness_factory):
    """Markdown resume builder shipped, but user realizes it needs PDF export and goes back."""
    h = harness_factory("p1-vibe.yaml")
    r = h.start()
    assert r
    assert h.step == "1.1 Describe what you want"

    # Quick path to done: simple markdown-to-HTML resume
    r = h.submit({
        "idea": "Convert markdown resume to styled HTML page with print-friendly CSS",
    })
    assert r
    r = h.submit({
        "code": "Python-markdown + custom CSS, outputs a single HTML file with @media print rules",
    })
    assert r
    r = h.submit({
        "result": "HTML renders beautifully, prints to PDF from browser",
    })
    assert r
    r = h.submit_goto("2.1 Ship it")
    assert r
    assert r.new_step == "2.1 Ship it"

    r = h.submit({
        "deploy": "Published as npm package 'md-resume'",
        "version": "1.0.0",
    })
    assert r
    assert h.status == "done"

    # Done, but realize PDF export should be built-in (not browser print)
    result = h.executor.submit({"feature": "Add wkhtmltopdf export"})
    assert not result
    assert "already completed" in result.message

    result = h.executor.submit({"_goto": "1.2 Write code"})
    assert not result
    assert "already completed" in result.message

    # Can still use goto action to reopen and add the feature
    r = h.goto("1.3 Try it out")
    assert r
    assert r.new_step == "1.3 Try it out"
    assert h.step == "1.3 Try it out"
    assert h.status == "running"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({"description": "build it"})
    h.submit({"code": "v1"})

    h.save_checkpoint("at_try_it")

    h.submit({})
    h.submit_goto("2.1 Ship it")
    assert h.step == "2.1 Ship it"

    restored = h.load_checkpoint("at_try_it")
    assert restored is not None
    assert restored.current_step == "1.3 Try it out"
    assert "1.2 Write code" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Write code"

    r = h.retry()
    assert r
    assert h.step == "1.2 Write code"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_back_returns_to_previous(harness_factory):
    """Back returns to the previously visited step."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Write code"

    h.submit({})
    assert h.step == "1.3 Try it out"

    r = h.back()
    assert r
    assert h.step == "1.2 Write code"


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p1-vibe.yaml")
    _walk_to_evaluate(h)
    _quick_ship(h)
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p1-vibe.yaml")

    for _i in range(3):
        h.start()
        h.submit({})
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Describe what you want"


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})  # 1.1 -> 1.2
    h.submit({})  # 1.2 -> 1.3

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    h.skip("just skip it")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "just skip it"


def test_node_archives_multiple_steps(harness_factory):
    """Archive nodes on different steps accumulate rows independently."""
    h = harness_factory("p1-vibe.yaml")
    h.start()

    h.register_node(
        "1.1 Describe what you want",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"description": "string"}},
            archive={"table": "descriptions"},
        ),
    )

    h.submit({"description": "idea 1"})
    h.submit({})
    h.submit({})
    h.submit_goto("1.1 Describe what you want")
    h.submit({"description": "idea 2"})

    rows = h.get_archived_rows("descriptions")
    assert len(rows) == 2
    assert rows[0]["description"] == "idea 1"
    assert rows[1]["description"] == "idea 2"


def test_edit_policy_reported_in_status(harness_factory):
    """get_status() includes edit_policy from registered node."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Write code"

    h.register_node(
        "1.2 Write code",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True,
            edit_policy=EditPolicy(
                default="warn",
                patterns=[
                    EditPolicyPattern(glob="src/**", policy="silent"),
                    EditPolicyPattern(glob="dist/**", policy="block"),
                ],
            ),
        ),
    )

    status = h.get_status()
    assert status["current_step"] == "1.2 Write code"
    assert status["node"] is not None
    assert status["node"]["edit_policy"]["default"] == "warn"


def test_reject_on_running_fails(harness_factory):
    """Reject on a running step returns failure (no wait steps in vibe flow)."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    assert h.status == "running"

    r = h.reject("should fail")
    assert not r
    assert "not waiting" in r.message.lower()


def test_approve_on_running_fails(harness_factory):
    """Approve on a running step returns failure (no wait steps in vibe flow)."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    assert h.status == "running"

    r = h.approve()
    assert not r
    assert "not waiting" in r.message.lower()


def test_node_validate_reject_then_accept(harness_factory):
    """Validate node rejects bad data on try-it step, accepts good data."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    assert h.step == "1.3 Try it out"

    h.register_node(
        "1.3 Try it out",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("tested") else "must mark as tested",
        ),
    )

    r = h.submit({"notes": "not tested"})
    assert not r
    assert "rejected" in r.message.lower()

    r = h.submit({"tested": True})
    assert r
    assert r.new_step == "1.4 Evaluate result"


def test_node_archive_on_ship_step(harness_factory):
    """Archive node on Ship step captures what was shipped."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.1 Ship it")
    assert h.step == "2.1 Ship it"

    h.register_node(
        "2.1 Ship it",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"version": "string", "notes": "string"}},
            archive={"table": "shipments"},
        ),
    )

    r = h.submit({"version": "1.0.0", "notes": "initial release"})
    assert r
    assert h.status == "done"

    rows = h.get_archived_rows("shipments")
    assert len(rows) == 1
    assert rows[0]["version"] == "1.0.0"


def test_cross_executor_preserves_data(harness_factory):
    """Close executor mid-flow, reopen, data persists."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({"description": "a cool thing"})
    h.submit({"code": "print('cool')"})

    h.new_executor()

    assert h.step == "1.3 Try it out"
    data = h.state.data
    assert data["1.1 Describe what you want"]["description"] == "a cool thing"
    assert data["1.2 Write code"]["code"] == "print('cool')"


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    h.submit({})
    assert h.step == "1.2 Write code"

    h.register_node(
        "1.2 Write code",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step by following Vibe Coding principles.\n\n## Steps\n1. Analyze requirements\n2. Write code\n3. Submit output",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p1-vibe.yaml")
    h.start()
    assert h.step == "1.1 Describe what you want"

    h.register_node(
        "1.1 Describe what you want",
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
