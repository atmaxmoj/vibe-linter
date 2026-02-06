"""Test scenarios for Progressive Enhancement workflow (p2-progressive.yaml).

Tests the Progressive Enhancement workflow including:
- Base layer (build, test)
- Enhancement loop with degradation test 2-way branching
- Full degradation test with 2-way branching
- State transitions, gotos, stops/resumes, and hot-reload
- No wait steps (fully autonomous)

Workflow structure:
  1.1 Build base HTML layer
  1.2 Test base functionality
  2.0 Enhancement loop (iterate: enhancements)
    2.1 Add enhancement layer
    2.2 Degradation test (LLM 2-way: pass->2.0, fail->2.1)
  3.1 Full degradation test (LLM: pass->Done, fail->2.0)
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

# --- Helpers ---

def _walk_to_loop(h):
    """Start -> submit 1.1 -> submit 1.2 -> arrive at 2.1 (running) in loop."""
    h.start()
    h.submit({"base": "semantic HTML"})
    h.submit({"tests": "pass"})
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"


def _do_one_enhancement(h):
    """Complete one add-test cycle ending at degradation test."""
    h.submit({"layer": "enhancement"})
    assert h.step == "2.2 Degradation test"


# ===============================================================
# Scenario 1: Four layers
# ===============================================================

def test_four_layers(harness_factory):
    """Weather dashboard: semantic HTML base, then CSS grid, JS geolocation, WebGL radar map, and service worker offline."""
    h = harness_factory(
        "p2-progressive.yaml",
        loop_data={"enhancements": ["css_grid", "js_geolocation", "webgl_radar", "service_worker"]},
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Build base HTML layer"
    assert h.status == "running"

    # Build base: semantic HTML weather dashboard that works without JS
    r = h.submit({
        "base": "Semantic HTML5 weather dashboard",
        "structure": "<main><article class='current-weather'>, <section class='forecast'> with <table> for 7-day, <aside class='alerts'>",
        "noscript": "Static weather data from server-side render, <noscript> message for enhanced features",
        "a11y": "ARIA landmarks, sr-only labels for weather icons, semantic headings h1-h3",
    })
    assert r
    assert r.new_step == "1.2 Test base functionality"
    assert h.step == "1.2 Test base functionality"
    assert h.status == "running"

    # Test: base HTML renders correctly with CSS disabled and JS off
    r = h.submit({
        "tests": [
            "Page readable with CSS disabled (Lynx browser test)",
            "All weather data accessible via screen reader (axe-core: 0 violations)",
            "7-day forecast table has proper <thead>/<tbody> structure",
            "Works in IE11 with server-rendered data (no JS needed)",
        ],
    })
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"

    # Layer 1: CSS Grid layout with responsive design
    r = h.submit({
        "layer": "CSS Grid + Custom Properties",
        "enhancements": "CSS Grid for dashboard layout, custom properties for theming, @media prefers-color-scheme for dark mode",
        "fallback": "Flexbox fallback via @supports not (display: grid), single-column stack on older browsers",
    })
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"

    # CSS degrades gracefully to flexbox
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    # Layer 2: JavaScript geolocation + live data
    r = h.submit({
        "layer": "JavaScript Geolocation + Fetch API",
        "enhancements": "navigator.geolocation for auto-detect city, fetch() for live OpenWeatherMap API, IntersectionObserver for lazy forecast cards",
        "fallback": "Manual city search form (HTML), server-rendered data as initial state",
    })
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert h.step == "2.1 Add enhancement layer"

    # Layer 3: WebGL radar map
    r = h.submit({
        "layer": "WebGL Weather Radar Map",
        "enhancements": "Mapbox GL JS for interactive radar overlay, animated precipitation layers, pinch-to-zoom",
        "fallback": "Static <img> radar snapshot from weather API, updated every 15 minutes",
    })
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert h.step == "2.1 Add enhancement layer"

    # Layer 4: Service Worker offline support
    r = h.submit({
        "layer": "Service Worker + Cache API",
        "enhancements": "Workbox precaching for app shell, runtime caching for API responses with stale-while-revalidate, Background Sync for offline city saves",
        "fallback": "Standard network requests, no offline support - app still works, just requires connectivity",
    })
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r

    # All 4 layers done, full degradation test
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"

    # Full stack: disable each layer one by one, verify graceful degradation
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()

    h.submit({"base": "HTML5"})
    data = h.state.data
    assert "1.1 Build base HTML layer" in data
    assert data["1.1 Build base HTML layer"]["base"] == "HTML5"

    h.submit({"tests": "all pass"})
    data = h.state.data
    assert "1.2 Test base functionality" in data
    assert data["1.2 Test base functionality"]["tests"] == "all pass"

    h.submit({"layer": "css enhancements"})
    data = h.state.data
    assert "2.1 Add enhancement layer" in data
    assert data["2.1 Add enhancement layer"]["layer"] == "css enhancements"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["e1"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Enhancement loop")
    assert h.step == "3.1 Full degradation test"
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_base(harness_factory):
    """Close executor at base layer, reopen, continue."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({"base": "HTML"})
    assert h.step == "1.2 Test base functionality"

    h.new_executor()

    assert h.step == "1.2 Test base functionality"
    assert h.status == "running"

    r = h.submit({"tests": "pass"})
    assert r
    assert h.step == "2.1 Add enhancement layer"


def test_s1_cross_executor_at_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"layer": "a_layer"})
    assert h.step == "2.2 Degradation test"

    h.new_executor()

    assert h.step == "2.2 Degradation test"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Enhancement loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_layer(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Add enhancement layer",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("layer") else "must include layer name",
        ),
    )

    # Bad data
    r = h.submit({"notes": "forgot"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"layer": "css"})
    assert r
    assert r.new_step == "2.2 Degradation test"


def test_s1_node_archives_layers(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["a", "b"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Add enhancement layer",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"layer_name": "string", "type": "string"}},
            archive={"table": "enhancement_layers"},
        ),
    )

    h.submit({"layer_name": "css", "type": "styling"})
    h.submit_goto("2.0 Enhancement loop")
    h.submit({"layer_name": "js", "type": "behavior"})

    rows = h.get_archived_rows("enhancement_layers")
    assert len(rows) == 2
    assert rows[0]["layer_name"] == "css"
    assert rows[1]["layer_name"] == "js"


# ===============================================================
# Scenario 2: Degradation fail
# ===============================================================

def test_degradation_fail(harness_factory):
    """IntersectionObserver lazy-loading breaks without JS: 4 rounds to get img fallback right."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["lazy_loading"]})
    r = h.start()
    assert r

    # Jump to degradation test where lazy-loading failure was caught
    r = h.goto("2.2 Degradation test")
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"
    assert h.status == "running"

    # Round 1: JS disabled -> images never load (blank placeholders)
    r = h.submit_goto("2.1 Add enhancement layer")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    r = h.submit({
        "fix": "Added loading='lazy' native attr as base, IntersectionObserver as enhancement",
        "issue": "But loading='lazy' not supported in older browsers (Safari <15.4)",
    })
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"

    # Round 2: Safari 14 still shows blank, Round 3: noscript fallback too aggressive
    for i in range(2, 4):
        r = h.submit_goto("2.1 Add enhancement layer")
        assert r
        r = h.submit({
            "fix": f"Attempt {i}: {'Added <noscript><img src=...></noscript> fallback' if i == 2 else 'Moved eager loading to first 3 images, lazy for rest'}",
        })
        assert r
        assert h.step == "2.2 Degradation test"

    # Round 4: proper progressive approach
    r = h.submit_goto("2.1 Add enhancement layer")
    assert r
    r = h.submit({
        "fix": "Final: all <img> have src (loads eagerly by default). JS adds loading='lazy' to below-fold images. IntersectionObserver adds fade-in animation as pure enhancement.",
        "pattern": "Base: standard <img src>. Enhancement 1: loading='lazy'. Enhancement 2: IntersectionObserver + CSS animation.",
    })
    assert r
    assert h.step == "2.2 Degradation test"

    # Degrades gracefully: no JS = all images load eagerly (slower but functional)
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    # Complete iteration and exit loop
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"


def test_s2_data_has_all_attempts(harness_factory):
    """All fix attempts store data (last wins per step key)."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.goto("2.1 Add enhancement layer")

    for i in range(4):
        h.submit({"layer": f"attempt_{i}"})
        if h.step != "2.1 Add enhancement layer":
            h.goto("2.1 Add enhancement layer")

    data = h.state.data
    assert "2.1 Add enhancement layer" in data


def test_s2_cross_executor_mid_retry(harness_factory):
    """Close executor after retries, reopen, continue from same step."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.2 Degradation test"

    for _ in range(2):
        h.submit_goto("2.1 Add enhancement layer")
        h.submit({})
    assert h.step == "2.2 Degradation test"

    h.new_executor()
    assert h.step == "2.2 Degradation test"
    assert h.status == "running"


# ===============================================================
# Scenario 3: Final test fail back
# ===============================================================

def test_final_test_fail_back(harness_factory):
    """Full degradation test: CSS animation layer breaks form submit on older browsers. Fix and re-test."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css_animations"]})
    r = h.start()
    assert r

    # Jump to full degradation test
    r = h.goto("3.1 Full degradation test")
    assert r
    assert r.new_step == "3.1 Full degradation test"
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"

    # Full test: CSS animation on submit button uses pointer-events:none during animation, blocking form submit in Safari 14
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"

    # Fix: wrap animation in @supports and ensure pointer-events:auto on button during submit
    r = h.submit({
        "fix": "Moved submit animation to ::after pseudo-element. Button always clickable. Animation is pure visual enhancement via @supports (animation: name).",
        "affected": "ContactForm submit button, NewsletterSignup CTA",
    })
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r

    # Back to full degradation test
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"

    # All layers degrade correctly: form works with/without CSS animations
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 4: Skip layer
# ===============================================================

def test_skip_layer(harness_factory):
    """Government form: skip WebGL map layer (WCAG AAA requirement forbids non-essential JS-dependent content)."""
    h = harness_factory(
        "p2-progressive.yaml", loop_data={"enhancements": ["css_layout", "form_validation", "map_widget"]}
    )
    r = h.start()
    assert r

    # Build and test base HTML for government benefits application form
    r = h.submit({
        "base": "Government benefits form: semantic HTML5 <form> with fieldset/legend grouping, native validation attrs",
        "a11y": "WCAG AAA: all inputs have <label>, error messages use aria-describedby, no placeholder-only labels",
    })
    assert r
    r = h.submit({
        "tests": ["Form submits via standard POST without JS", "All fields accessible via keyboard tab order", "Screen reader announces all labels and errors"],
    })
    assert r
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"

    # Layer 1: CSS layout enhancement - complete normally
    r = h.submit({
        "layer": "CSS Grid layout for multi-column form on desktop, single column on mobile",
        "fallback": "Linear single-column layout via default block flow",
    })
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    # Layer 2: JS form validation - skip (WCAG AAA: server-side validation sufficient, JS validation is optional UX improvement)
    r = h.skip("WCAG AAA compliance: JS form validation skipped. Server-side validation handles all cases. Native HTML5 constraint validation provides basic client-side feedback without JS dependency.")
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"

    r = h.submit_goto("2.0 Enhancement loop")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    # Layer 3: Interactive map widget - complete
    r = h.submit({
        "layer": "Leaflet.js office locator map with text-based alternative",
        "fallback": "Static list of office addresses with links to Google Maps",
    })
    assert r
    r = h.submit_goto("2.0 Enhancement loop")
    assert r

    # All layers processed
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"


def test_s4_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()

    h.skip("skip base layer")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "skip base layer"


# ===============================================================
# Scenario 5: Stop resume
# ===============================================================

def test_stop_resume(harness_factory):
    """News article page: stop during JS enhancement layer for sprint demo, resume after standup."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css_typography", "js_infinite_scroll"]})
    r = h.start()
    assert r

    # Build base HTML for news article page
    r = h.submit({
        "base": "Semantic article: <article> with <header>/<time>/<figure>/<blockquote>, paginated article list with <nav> prev/next links",
    })
    assert r
    assert r.new_step == "1.2 Test base functionality"
    assert h.step == "1.2 Test base functionality"

    # Test base: article readable, pagination works without JS
    r = h.submit({
        "tests": ["Article renders with default browser styles", "Pagination nav links work (page 1, 2, 3)", "Images have alt text"],
    })
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    # Stop: sprint demo starting, need to show base HTML progress to stakeholders
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.1 Add enhancement layer"

    # Demo done, resume adding CSS typography enhancement
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.1 Add enhancement layer"

    # Continue with CSS typography layer
    r = h.submit({
        "layer": "CSS Typography: Inter variable font via @font-face, responsive font sizes with clamp(), fluid line-height",
        "fallback": "System font stack: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    })
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"


def test_s5_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.goto("3.1 Full degradation test")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s5_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s5_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Scenario 6: Done reset
# ===============================================================

def test_done_reset(harness_factory):
    """v1 checkout PE done. Reset for v2: rebuild base HTML with Web Components instead of plain divs."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    r = h.start()
    assert r

    # Fast-track v1 progressive enhancement to done
    r = h.goto("3.1 Full degradation test")
    assert r
    assert r.new_step == "3.1 Full degradation test"
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # v2: migrate base layer from div soup to semantic Web Components (<checkout-form>, <cart-summary>)
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Build base HTML layer"
    assert h.status == "running"


# ===============================================================
# Scenario 7: Back
# ===============================================================

def test_back(harness_factory):
    """Recipe page: go back to fix missing <dl> for ingredients, then back to fix print stylesheet layer."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["print_css"]})
    r = h.start()
    assert r

    # Build base HTML for recipe page
    r = h.submit({
        "base": "Recipe page: <article> with <h1> title, ingredients as <ul>, steps as <ol>, nutritional info as <table>",
    })
    assert r
    assert r.new_step == "1.2 Test base functionality"
    assert h.step == "1.2 Test base functionality"

    # Realized ingredients should be <dl> (definition list) for ingredient:amount pairs, go back
    r = h.back()
    assert r
    assert r.new_step == "1.1 Build base HTML layer"
    assert h.step == "1.1 Build base HTML layer"
    assert h.status == "running"

    # Fix: use <dl> for ingredients
    r = h.submit({
        "fix": "Changed ingredients from <ul><li> to <dl><dt>flour</dt><dd>2 cups</dd></dl> for semantic ingredient:amount pairs",
    })
    assert r
    r = h.submit({
        "tests": ["<dl> renders ingredient pairs correctly", "Screen reader announces dt/dd grouping"],
    })
    assert r
    assert h.step == "2.1 Add enhancement layer"

    # Add print stylesheet as enhancement layer
    r = h.submit({
        "layer": "Print CSS: @media print hides nav/footer/ads, enlarges recipe content, adds URL after links",
        "fallback": "Browser default print: all content prints but with nav and ads",
    })
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"

    # Go back: forgot to add page-break-inside:avoid for ingredient list
    r = h.back()
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"


# ===============================================================
# Scenario 8: Empty list
# ===============================================================

def test_empty_list(harness_factory):
    """Static legal/terms page: pure HTML, no enhancement layers needed. Just base + degradation test."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": []})
    r = h.start()
    assert r

    # Build base HTML for terms of service page (pure static content, no enhancements)
    r = h.submit({
        "base": "Terms of Service: semantic HTML with <article>, <section> per clause, <details>/<summary> for FAQ",
        "reason": "Legal pages must work in ALL browsers including text-only. No CSS/JS enhancements needed.",
    })
    assert r
    r = h.submit({
        "tests": ["All sections have heading hierarchy h1>h2>h3", "Table of contents links work via #anchors", "Prints cleanly with browser default styles"],
    })
    assert r

    # No enhancement layers: loop exits immediately to full degradation test
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"


# ===============================================================
# Scenario 9: Goto
# ===============================================================

def test_goto(harness_factory):
    """Hotfix: jump to add dark mode CSS layer, then straight to full degradation test to verify."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["dark_mode"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Build base HTML layer"

    # Base HTML already built in previous sprint, jump straight to enhancement
    r = h.goto("2.1 Add enhancement layer")
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"

    # Jump to full degradation test to verify dark mode layer with all others
    r = h.goto("3.1 Full degradation test")
    assert r
    assert r.new_step == "3.1 Full degradation test"
    assert h.step == "3.1 Full degradation test"
    assert h.status == "running"

    # All layers degrade correctly including dark mode (falls back to light theme)
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 10: Consecutive back
# ===============================================================

def test_consecutive_back_3(harness_factory):
    """Contact form: three consecutive backs while debugging CSS animation layer - bounces between add/test steps.

    back() finds the most recent DIFFERENT step in history. Since history includes
    both "submit" and "transition" entries, consecutive back() calls may bounce
    between steps rather than progressing linearly backward.
    """
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css_animation"]})
    r = h.start()
    assert r

    # Build base HTML contact form
    r = h.submit({
        "base": "Contact form: <form> with name/email/message fields, honeypot anti-spam, server-side action",
    })
    assert r
    assert r.new_step == "1.2 Test base functionality"
    assert h.step == "1.2 Test base functionality"

    # Test base functionality
    r = h.submit({
        "tests": ["Form submits via POST without JS", "Required fields show native validation bubbles"],
    })
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"

    # Add CSS animation layer (transition on focus states)
    r = h.submit({
        "layer": "CSS transitions: input focus glow, label float animation via :placeholder-shown, submit button pulse",
    })
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"

    # First back: realized the focus animation is too aggressive (500ms delay feels sluggish)
    r = h.back()
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"

    # Second back: bounces to previous different step (2.2 Degradation test)
    r = h.back()
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"
    assert h.status == "running"

    # Third back: bounces back to 2.1 Add enhancement layer
    r = h.back()
    assert r
    assert r.new_step == "2.1 Add enhancement layer"
    assert h.step == "2.1 Add enhancement layer"
    assert h.status == "running"

    # Finally settled: reduce animation to 150ms and continue forward
    r = h.submit({
        "layer": "CSS transitions: 150ms focus glow, 200ms label float, reduced-motion media query disables all animations",
    })
    assert r
    assert r.new_step == "2.2 Degradation test"
    assert h.step == "2.2 Degradation test"


# ===============================================================
# Multi-dimension: Loop counter and cleanup
# ===============================================================

def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p2-progressive.yaml", loop_data={"enhancements": ["a", "b", "c"]}
    )
    _walk_to_loop(h)

    loop_info = h.state.loop_state["2.0 Enhancement loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_enhancement(h)
    h.submit_goto("2.0 Enhancement loop")

    loop_info = h.state.loop_state["2.0 Enhancement loop"]
    assert loop_info["i"] == 1

    _do_one_enhancement(h)
    h.submit_goto("2.0 Enhancement loop")

    loop_info = h.state.loop_state["2.0 Enhancement loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["only"]})
    _walk_to_loop(h)

    _do_one_enhancement(h)
    h.submit_goto("2.0 Enhancement loop")

    assert h.step == "3.1 Full degradation test"
    assert "2.0 Enhancement loop" not in h.state.loop_state


def test_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"layer": "layer_a"})
    h.submit_goto("2.0 Enhancement loop")

    h.submit({"layer": "layer_b"})
    data = h.state.data
    assert data["2.1 Add enhancement layer"]["layer"] == "layer_b"


# ===============================================================
# Multi-dimension: Node archives per iteration
# ===============================================================

def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory(
        "p2-progressive.yaml", loop_data={"enhancements": ["a", "b", "c"]}
    )
    _walk_to_loop(h)

    h.register_node(
        "2.1 Add enhancement layer",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"layer_name": "string"}},
            archive={"table": "pe_layers"},
        ),
    )

    for i in range(3):
        h.submit({"layer_name": f"layer_{i}"})
        h.submit_goto("2.0 Enhancement loop")

    rows = h.get_archived_rows("pe_layers")
    assert len(rows) == 3


# ===============================================================
# Multi-dimension: Cross-executor preserves loop
# ===============================================================

def test_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory(
        "p2-progressive.yaml", loop_data={"enhancements": ["a", "b", "c"]}
    )
    _walk_to_loop(h)

    _do_one_enhancement(h)
    h.submit_goto("2.0 Enhancement loop")

    # Mid iteration 2
    h.submit({"layer": "mid_loop"})
    assert h.step == "2.2 Degradation test"

    h.new_executor()

    assert h.step == "2.2 Degradation test"
    loop_info = h.state.loop_state["2.0 Enhancement loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({})
    assert h.step == "1.2 Test base functionality"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "1.2 Test base functionality"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({"base": "HTML"})
    h.submit({"tests": "pass"})

    h.save_checkpoint("at_loop_entry")

    h.submit({})
    h.submit_goto("2.0 Enhancement loop")
    assert h.step == "3.1 Full degradation test"

    restored = h.load_checkpoint("at_loop_entry")
    assert restored is not None
    assert restored.current_step == "2.1 Add enhancement layer"
    assert "1.2 Test base functionality" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    assert h.step == "1.1 Build base HTML layer"

    r = h.retry()
    assert r
    assert h.step == "1.1 Build base HTML layer"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.goto("3.1 Full degradation test")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Build base HTML layer"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.goto("3.1 Full degradation test")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({})
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()
    h.submit({"base": "semantic HTML"})
    h.submit({"tests": "pass"})

    h.register_node(
        "2.1 Add enhancement layer",
        NodeDefinition(
            types=["auto"],
            instructions="## Goal\nComplete this step.\n\n## Steps\n1. Analyze\n2. Implement\n3. Submit",
            check=lambda data: True,
        ),
    )

    status = h.get_status()
    assert status["node"] is not None
    assert status["node"]["instructions"] is not None
    assert "Goal" in status["node"]["instructions"]


def test_early_phase_edit_policy_in_status(harness_factory):
    """Early phase steps report edit_policy=block in status."""
    h = harness_factory("p2-progressive.yaml", loop_data={"enhancements": ["css"]})
    h.start()

    h.register_node(
        "1.1 Build base HTML layer",
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
