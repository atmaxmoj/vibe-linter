"""Test scenarios for Mobile-First workflow (p2-mobile-first.yaml).

Tests the Mobile-First Development workflow including:
- Planning phase (define breakpoints)
- Breakpoint loop with responsive check 2-way branching
- Cross-browser testing with 2-way branching
- State transitions, gotos, stops/resumes, and hot-reload

Workflow structure:
  1.1 Define breakpoints and layouts
  2.0 Breakpoint loop (iterate: breakpoints)
    2.1 Implement responsive layout
    2.2 Test responsive behavior
    2.3 Responsive check (LLM 2-way: pass->2.0, fail->2.1)
  3.1 Cross-browser testing (LLM: pass->Done, fail->2.0)
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
    """Start -> submit 1.1 -> arrive at 2.1 (running) in loop."""
    h.start()
    h.submit({"breakpoints": "mobile, tablet, desktop"})
    assert h.step == "2.1 Implement responsive layout"
    assert h.status == "running"


def _do_one_breakpoint(h):
    """Complete one implement-test-check cycle ending at responsive check."""
    h.submit({"layout": "implemented"})
    h.submit({"tests": "pass"})
    assert h.step == "2.3 Responsive check"


# ===============================================================
# Scenario 1: Three breakpoints complete
# ===============================================================

def test_three_breakpoints_complete(harness_factory):
    """E-commerce product listing page: mobile (320px), tablet (768px), desktop (1280px) responsive layouts."""
    h = harness_factory(
        "p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile", "tablet", "desktop"]}
    )
    r = h.start()
    assert r
    assert h.step == "1.1 Define breakpoints and layouts"
    assert h.status == "running"

    # Define Tailwind breakpoint system for product listing page
    r = h.submit({
        "breakpoints": {
            "mobile": {"max_width": "639px", "columns": 1, "layout": "single-column stack"},
            "tablet": {"min_width": "640px", "max_width": "1279px", "columns": 2, "layout": "2-col grid"},
            "desktop": {"min_width": "1280px", "columns": 4, "layout": "4-col grid with sidebar filters"},
        },
        "css_strategy": "Tailwind responsive prefixes: sm:, md:, lg:, xl:",
        "page": "ProductListingPage for /shop/category/:slug",
    })
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"
    assert h.status == "running"

    # Breakpoint 1: Mobile (320px) - single column, bottom sheet filters
    r = h.submit({
        "breakpoint": "mobile (320-639px)",
        "layout": "Single column ProductCard stack, sticky bottom bar with filter/sort buttons, bottom sheet for FilterPanel",
        "css": "grid grid-cols-1 gap-4, fixed bottom-0 w-full for action bar",
        "components": ["ProductCard (vertical, full-width)", "BottomSheet<FilterPanel>", "StickyActionBar"],
    })
    assert r
    assert r.new_step == "2.2 Test responsive behavior"
    assert h.step == "2.2 Test responsive behavior"

    r = h.submit({
        "tests": [
            "ProductCard renders full-width at 320px viewport",
            "FilterPanel opens as bottom sheet on tap",
            "Images lazy-load with aspect-ratio: 4/3",
            "Touch targets >= 44px per WCAG 2.5.5",
        ],
        "viewport": "320px, 375px, 414px (iPhone SE, 13, 14 Pro Max)",
    })
    assert r
    assert r.new_step == "2.3 Responsive check"
    assert h.step == "2.3 Responsive check"

    # Mobile layout verified
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"

    # Breakpoint 2: Tablet (640-1279px) - 2 column grid, collapsible sidebar
    r = h.submit({
        "breakpoint": "tablet (640-1279px)",
        "layout": "2-col product grid, collapsible sidebar filters, horizontal sort bar",
        "css": "sm:grid-cols-2 sm:gap-6, sidebar hidden by default with toggle",
    })
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert h.step == "2.1 Implement responsive layout"

    # Breakpoint 3: Desktop (1280px+) - 4 column grid with persistent sidebar
    r = h.submit({
        "breakpoint": "desktop (1280px+)",
        "layout": "4-col product grid, persistent 280px sidebar, breadcrumb nav, pagination",
        "css": "xl:grid-cols-4 xl:gap-8, xl:flex xl:flex-row for sidebar layout",
    })
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r

    # All breakpoints done, cross-browser testing
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    # Chrome, Safari, Firefox all render correctly
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


def test_s1_data_accumulates(harness_factory):
    """Each submit stores data keyed by step name."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    h.start()

    h.submit({"breakpoints": "mobile only"})
    data = h.state.data
    assert "1.1 Define breakpoints and layouts" in data
    assert data["1.1 Define breakpoints and layouts"]["breakpoints"] == "mobile only"

    h.submit({"layout": "mobile layout"})
    data = h.state.data
    assert "2.1 Implement responsive layout" in data
    assert data["2.1 Implement responsive layout"]["layout"] == "mobile layout"

    h.submit({"tests": "all pass"})
    data = h.state.data
    assert "2.2 Test responsive behavior" in data
    assert data["2.2 Test responsive behavior"]["tests"] == "all pass"


def test_s1_history_audit_trail(harness_factory):
    """After full walkthrough, history contains expected action sequence."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Breakpoint loop")
    assert h.step == "3.1 Cross-browser testing"
    h.submit_goto("Done")
    assert h.status == "done"

    history = h.get_history(100)
    actions = [e["action"] for e in reversed(history)]
    assert actions[0] == "start"
    assert "submit" in actions
    assert "transition" in actions
    assert "terminate" in actions[-1]


def test_s1_cross_executor_at_planning(harness_factory):
    """Close executor at planning phase, reopen, continue."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    assert h.step == "1.1 Define breakpoints and layouts"

    h.new_executor()

    assert h.step == "1.1 Define breakpoints and layouts"
    assert h.status == "running"

    r = h.submit({"breakpoints": "defined"})
    assert r
    assert h.step == "2.1 Implement responsive layout"


def test_s1_cross_executor_at_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state preserved."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"layout": "a_layout"})
    assert h.step == "2.2 Test responsive behavior"

    h.new_executor()

    assert h.step == "2.2 Test responsive behavior"
    assert h.status == "running"
    loop_info = h.state.loop_state.get("2.0 Breakpoint loop")
    assert loop_info is not None
    assert loop_info["i"] == 0
    assert loop_info["n"] == 2


def test_s1_node_validates_layout(harness_factory):
    """Validate node rejects bad data, accepts good data."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement responsive layout",
        NodeDefinition(
            types=["validate"],
            check=lambda data: True if data.get("layout") else "must include layout name",
        ),
    )

    # Bad data
    r = h.submit({"notes": "forgot"})
    assert not r
    assert "rejected" in r.message.lower()

    # Good data
    r = h.submit({"layout": "mobile"})
    assert r
    assert r.new_step == "2.2 Test responsive behavior"


def test_s1_node_archives_breakpoints(harness_factory):
    """Archive node writes submitted data to SQLite table."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["a", "b"]})
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement responsive layout",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"bp_name": "string", "width": "string"}},
            archive={"table": "breakpoints_done"},
        ),
    )

    h.submit({"bp_name": "mobile", "width": "320px"})
    h.submit({})
    h.submit_goto("2.0 Breakpoint loop")
    h.submit({"bp_name": "tablet", "width": "768px"})

    rows = h.get_archived_rows("breakpoints_done")
    assert len(rows) == 2
    assert rows[0]["bp_name"] == "mobile"
    assert rows[1]["bp_name"] == "tablet"


# ===============================================================
# Scenario 2: Breakpoint responsive issue
# ===============================================================

def test_breakpoint_responsive_issue(harness_factory):
    """DataTable overflows on mobile: 4 rounds of fixes for horizontal scroll, truncation, and touch."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    r = h.start()
    assert r

    # Jump to responsive check where DataTable overflow was caught
    r = h.goto("2.3 Responsive check")
    assert r
    assert r.new_step == "2.3 Responsive check"
    assert h.step == "2.3 Responsive check"
    assert h.status == "running"

    # Round 1: DataTable overflows viewport at 320px, no horizontal scroll
    r = h.submit_goto("2.1 Implement responsive layout")
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"

    r = h.submit({
        "fix": "Added overflow-x-auto wrapper around TanStack Table, but column headers still clip",
        "issue": "DataTable columns wider than 320px viewport, horizontal scrollbar appears but headers clip",
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Responsive check"

    # Round 2: headers fixed but cell text wraps badly, Round 3: truncation ellipsis but tooltip missing
    for i in range(2, 4):
        r = h.submit_goto("2.1 Implement responsive layout")
        assert r
        r = h.submit({
            "fix": f"Attempt {i}: {'Added sticky first column with shadow-right' if i == 2 else 'Added text-ellipsis + Floating UI tooltip on truncated cells'}",
        })
        assert r
        r = h.submit()
        assert r
        assert h.step == "2.3 Responsive check"

    # Round 4: switch to card layout on mobile instead of table
    r = h.submit_goto("2.1 Implement responsive layout")
    assert r
    r = h.submit({
        "fix": "Replaced table with stacked card layout at sm: breakpoint using CSS container queries",
        "solution": "CardView for mobile (<640px), TableView for tablet+, via @container (min-width: 640px)",
    })
    assert r
    r = h.submit()
    assert r
    assert h.step == "2.3 Responsive check"

    # Card layout works perfectly on mobile
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"

    # Complete iteration and exit loop
    r = h.submit()
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"


def test_s2_data_has_all_attempts(harness_factory):
    """All fix attempts store data (last wins per step key)."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.goto("2.1 Implement responsive layout")

    for i in range(4):
        h.submit({"layout": f"attempt_{i}"})
        if h.step != "2.1 Implement responsive layout":
            h.goto("2.1 Implement responsive layout")

    data = h.state.data
    assert "2.1 Implement responsive layout" in data


def test_s2_cross_executor_mid_retry(harness_factory):
    """Close executor after retries, reopen, continue from same step."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.submit({})
    h.submit({})
    h.submit({})
    assert h.step == "2.3 Responsive check"

    for _ in range(2):
        h.submit_goto("2.1 Implement responsive layout")
        h.submit({})
        h.submit({})
    assert h.step == "2.3 Responsive check"

    h.new_executor()
    assert h.step == "2.3 Responsive check"
    assert h.status == "running"


# ===============================================================
# Scenario 3: Cross-browser fail back
# ===============================================================

def test_cross_browser_fail_back(harness_factory):
    """Safari dvh unit bug: cross-browser test catches 100vh issue on iOS Safari, fix with dvh fallback."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    r = h.start()
    assert r

    # Jump to cross-browser testing
    r = h.goto("3.1 Cross-browser testing")
    assert r
    assert r.new_step == "3.1 Cross-browser testing"
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    # Safari iOS: 100vh includes address bar, hero section gets cut off
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"
    assert h.status == "running"

    # Fix: use dvh with vh fallback for hero section height
    r = h.submit({
        "fix": "Replaced h-screen with h-[100dvh] and @supports fallback: height: 100vh; height: 100dvh;",
        "affected": "HeroSection, FullScreenModal, MobileNav overlay",
        "browser": "Safari iOS 15+ (dvh supported since Safari 15.4)",
    })
    assert r
    r = h.submit({
        "tests": ["iOS Safari 16: hero fills viewport correctly", "Chrome Android: no regression", "Firefox: fallback works"],
    })
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r

    # Back to cross-browser testing
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    # All browsers pass with dvh fix
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 4: Skip breakpoint
# ===============================================================

def test_skip_breakpoint(harness_factory):
    """Admin dashboard: skip tablet breakpoint since admin is desktop-primary with mobile emergency access only."""
    h = harness_factory(
        "p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile", "tablet", "desktop"]}
    )
    r = h.start()
    assert r

    # Define breakpoints: mobile gets simplified view, tablet skipped, desktop is primary
    r = h.submit({
        "breakpoints": {
            "mobile": {"max_width": "639px", "priority": "emergency access only"},
            "tablet": {"range": "640-1023px", "priority": "SKIP - admin users are 98% desktop"},
            "desktop": {"min_width": "1024px", "priority": "primary"},
        },
        "page": "AdminDashboard with Recharts analytics, TanStack Table for user management",
    })
    assert r
    assert h.step == "2.1 Implement responsive layout"
    assert h.status == "running"

    # Breakpoint 1 (mobile): simplified single-column with critical actions only
    r = h.submit({
        "breakpoint": "mobile (320-639px)",
        "layout": "Single column: alert banner, key metrics cards, emergency action buttons only",
        "excluded": "Recharts graphs hidden, DataTable replaced with simple list view",
    })
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"

    # Breakpoint 2 (tablet): skip - analytics show <2% tablet usage for admin panel
    r = h.skip("Admin analytics show 0.8% tablet users. Tablet inherits mobile layout via CSS cascade. No dedicated tablet breakpoint needed.")
    assert r
    assert r.new_step == "2.2 Test responsive behavior"
    assert h.step == "2.2 Test responsive behavior"

    r = h.skip("Tablet tests skipped per product decision")
    assert r
    assert r.new_step == "2.3 Responsive check"
    assert h.step == "2.3 Responsive check"

    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert r.new_step == "2.1 Implement responsive layout"
    assert h.step == "2.1 Implement responsive layout"

    # Breakpoint 3 (desktop): full admin layout with sidebar, charts, tables
    r = h.submit({
        "breakpoint": "desktop (1024px+)",
        "layout": "Sidebar nav (240px) + main content: Recharts dashboard + TanStack Table with pagination",
    })
    assert r
    r = h.submit()
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r

    # All breakpoints processed
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"


def test_s4_skip_records_reason(harness_factory):
    """Skip reason appears in history data field."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()

    h.skip("skip planning")
    history = h.get_history(5)
    skip_entries = [e for e in history if e["action"] == "skip"]
    assert len(skip_entries) >= 1
    assert skip_entries[0]["data"] == "skip planning"


# ===============================================================
# Scenario 5: Stop resume
# ===============================================================

def test_stop_resume(harness_factory):
    """Blog redesign: stop during mobile responsive testing for P0 production incident, resume after hotfix."""
    h = harness_factory(
        "p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile", "tablet"]}
    )
    r = h.start()
    assert r

    # Define breakpoints for blog article page
    r = h.submit({
        "breakpoints": {"mobile": "320-639px", "tablet": "640-1023px"},
        "page": "BlogArticlePage: hero image, markdown body, author card, related posts",
    })
    assert r
    assert h.step == "2.1 Implement responsive layout"

    # Implement mobile layout for blog article
    r = h.submit({
        "breakpoint": "mobile",
        "layout": "Full-width hero image (aspect-ratio: 16/9), prose max-w-prose, stacked author card",
    })
    assert r
    assert r.new_step == "2.2 Test responsive behavior"
    assert h.step == "2.2 Test responsive behavior"

    # P0 incident: production payment gateway down, stop blog work immediately
    r = h.stop()
    assert r
    assert h.status == "stopped"
    assert h.step == "2.2 Test responsive behavior"

    # Hotfix deployed. Resume blog responsive testing
    r = h.resume()
    assert r
    assert h.status == "running"
    assert h.step == "2.2 Test responsive behavior"

    # Continue: run responsive tests for mobile blog layout
    r = h.submit({
        "tests": ["Hero image scales to full width at 320px", "Prose text readable at 16px/1.6 line-height"],
    })
    assert r
    assert r.new_step == "2.3 Responsive check"
    assert h.step == "2.3 Responsive check"


def test_s5_stop_on_done_fails(harness_factory):
    """Cannot stop an already-completed workflow."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.goto("3.1 Cross-browser testing")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.stop()
    assert not r


def test_s5_stop_on_stopped_fails(harness_factory):
    """Cannot stop an already-stopped workflow."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.stop()
    assert h.status == "stopped"

    r = h.stop()
    assert not r


def test_s5_resume_on_non_stopped_fails(harness_factory):
    """Cannot resume a running workflow."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    assert h.status == "running"

    r = h.resume()
    assert not r


# ===============================================================
# Scenario 6: Done reset
# ===============================================================

def test_done_reset(harness_factory):
    """Landing page v1 responsive done. Reset for v2 with new breakpoint for ultra-wide monitors."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    r = h.start()
    assert r

    # Fast-track v1 landing page to cross-browser complete
    r = h.goto("3.1 Cross-browser testing")
    assert r
    assert r.new_step == "3.1 Cross-browser testing"
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"

    # v2: stakeholders want ultra-wide (2560px+) support. Reset and add 4th breakpoint.
    h.reset()
    assert h.state is None

    r = h.start()
    assert r
    assert h.step == "1.1 Define breakpoints and layouts"
    assert h.status == "running"


# ===============================================================
# Scenario 7: Back
# ===============================================================

def test_back(harness_factory):
    """Checkout form: go back to add a missing 480px breakpoint after realizing iPhone SE needs special treatment."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    r = h.start()
    assert r

    # Define breakpoints for checkout form
    r = h.submit({
        "breakpoints": {"mobile": "320-639px"},
        "page": "CheckoutForm: shipping address, payment method, order summary",
        "note": "Initially planned only mobile breakpoint",
    })
    assert r
    assert h.step == "2.1 Implement responsive layout"

    # Realized we need to go back and add a 480px micro-breakpoint for iPhone SE
    r = h.back()
    assert r
    assert r.new_step == "1.1 Define breakpoints and layouts"
    assert h.step == "1.1 Define breakpoints and layouts"
    assert h.status == "running"

    # Re-submit with note about iPhone SE consideration
    # (Loop state already initialized, re-entry will exit since i=0+1=1==n=1)
    r = h.submit({
        "update": "Added consideration for iPhone SE (375px) vs larger phones (414px+). Will handle via container query.",
    })
    assert r
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    # Continue to completion
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 8: Empty breakpoint list
# ===============================================================

def test_empty_breakpoint_list(harness_factory):
    """Server-rendered email template: no responsive breakpoints needed, fixed 600px width per email client standards."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": []})
    r = h.start()
    assert r

    # Email templates use fixed-width table layout, no responsive breakpoints
    r = h.submit({
        "breakpoints": [],
        "reason": "Email template uses fixed 600px table layout. Gmail/Outlook strip media queries. No responsive breakpoints.",
        "page": "TransactionalEmailTemplate: order confirmation, password reset, welcome email",
    })
    assert r

    # Loop exits immediately since no breakpoints to iterate
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"


# ===============================================================
# Scenario 9: Goto cross-browser
# ===============================================================

def test_goto_cross_browser(harness_factory):
    """Static marketing page: responsive layouts already done in Figma, jump straight to cross-browser QA."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    r = h.start()
    assert r
    assert h.step == "1.1 Define breakpoints and layouts"

    # Layouts pixel-perfect from Figma handoff, skip straight to browser testing
    r = h.goto("3.1 Cross-browser testing")
    assert r
    assert r.new_step == "3.1 Cross-browser testing"
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    # BrowserStack: Chrome 120, Safari 17, Firefox 121, Edge 120 all pass
    r = h.submit_goto("Done")
    assert r
    assert h.step == "Done"
    assert h.status == "done"


# ===============================================================
# Scenario 10: Modify YAML
# ===============================================================

def test_modify_yaml_add_breakpoint(harness_factory):
    """Mid-sprint: add Lighthouse performance audit step after team realizes LCP is 4.2s on 3G throttle."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    r = h.start()
    assert r

    # Complete planning and breakpoint loop for mobile
    r = h.submit({
        "breakpoints": {"mobile": "320-639px"},
        "page": "ProductDetailPage with hero image carousel, specs accordion, reviews feed",
    })
    assert r
    assert h.step == "2.1 Implement responsive layout"

    r = h.submit({
        "breakpoint": "mobile",
        "layout": "Stacked: hero carousel (swipe), sticky add-to-cart bar, accordion specs, lazy reviews",
    })
    assert r
    r = h.submit({
        "tests": ["Carousel touch swipe works", "Sticky bar visible on scroll", "Accordion opens/closes"],
    })
    assert r
    r = h.submit_goto("2.0 Breakpoint loop")
    assert r
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"

    # DevOps flagged: mobile Lighthouse score is 42 (LCP 4.2s on slow 3G). Add perf audit step.
    modified_yaml = """名称: Mobile-First Development Modified
描述: Breakpoint loop with performance check

步骤:
  - 1.1 Define breakpoints and layouts

  - 2.0 Breakpoint loop:
      遍历: "breakpoints"
      子步骤:
        - 2.1 Implement responsive layout
        - 2.2 Test responsive behavior
        - 2.3 Responsive check:
            下一步:
              - 如果: "responsive layout works correctly"
                去: 2.0 Breakpoint loop
              - 去: 2.1 Implement responsive layout

  - 2.9 Run performance audit

  - 3.1 Cross-browser testing:
      下一步:
        - 如果: "works across all target browsers"
          去: Done
        - 去: 2.0 Breakpoint loop

  - Done:
      类型: terminate
      原因: Mobile-first responsive design complete
"""

    h.reload_yaml(modified_yaml)

    # Jump to the new Lighthouse performance audit step
    r = h.goto("2.9 Run performance audit")
    assert r
    assert r.new_step == "2.9 Run performance audit"
    assert h.step == "2.9 Run performance audit"
    assert h.status == "running"

    # Run Lighthouse and fix: lazy-load below-fold images, preload hero, add fetchpriority="high"
    r = h.submit({
        "audit": "Lighthouse mobile: LCP improved 4.2s -> 1.8s after image optimization",
        "fixes": ["Added loading='lazy' to below-fold images", "Preloaded hero image with fetchpriority='high'", "Replaced PNG carousel with WebP + AVIF srcset"],
        "score": {"performance": 92, "accessibility": 98, "best_practices": 100},
    })
    assert r
    assert r.new_step == "3.1 Cross-browser testing"
    assert h.step == "3.1 Cross-browser testing"
    assert h.status == "running"


# ===============================================================
# Multi-dimension: Loop counter and cleanup
# ===============================================================

def test_loop_counter_increments(harness_factory):
    """Loop index increments after each iteration."""
    h = harness_factory(
        "p2-mobile-first.yaml", loop_data={"breakpoints": ["a", "b", "c"]}
    )
    _walk_to_loop(h)

    loop_info = h.state.loop_state["2.0 Breakpoint loop"]
    assert loop_info["i"] == 0
    assert loop_info["n"] == 3

    _do_one_breakpoint(h)
    h.submit_goto("2.0 Breakpoint loop")

    loop_info = h.state.loop_state["2.0 Breakpoint loop"]
    assert loop_info["i"] == 1

    _do_one_breakpoint(h)
    h.submit_goto("2.0 Breakpoint loop")

    loop_info = h.state.loop_state["2.0 Breakpoint loop"]
    assert loop_info["i"] == 2


def test_loop_cleanup_on_exit(harness_factory):
    """Loop state is cleaned up after all iterations complete."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["only"]})
    _walk_to_loop(h)

    _do_one_breakpoint(h)
    h.submit_goto("2.0 Breakpoint loop")

    assert h.step == "3.1 Cross-browser testing"
    assert "2.0 Breakpoint loop" not in h.state.loop_state


def test_loop_data_per_iteration(harness_factory):
    """Each iteration overwrites step data keys but data persists."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["a", "b"]})
    _walk_to_loop(h)

    h.submit({"layout": "layout_a"})
    h.submit({})
    h.submit_goto("2.0 Breakpoint loop")

    h.submit({"layout": "layout_b"})
    data = h.state.data
    assert data["2.1 Implement responsive layout"]["layout"] == "layout_b"


# ===============================================================
# Multi-dimension: Node archives per iteration
# ===============================================================

def test_node_archives_per_iteration(harness_factory):
    """Archive node accumulates one row per loop iteration."""
    h = harness_factory(
        "p2-mobile-first.yaml", loop_data={"breakpoints": ["a", "b", "c"]}
    )
    _walk_to_loop(h)

    h.register_node(
        "2.1 Implement responsive layout",
        NodeDefinition(
            types=["validate", "archive"],
            check=lambda data: True,
            schema={"output": {"bp_name": "string"}},
            archive={"table": "mf_breakpoints"},
        ),
    )

    for i in range(3):
        h.submit({"bp_name": f"bp_{i}"})
        h.submit({})
        h.submit_goto("2.0 Breakpoint loop")

    rows = h.get_archived_rows("mf_breakpoints")
    assert len(rows) == 3


# ===============================================================
# Multi-dimension: Cross-executor preserves loop
# ===============================================================

def test_cross_executor_preserves_loop(harness_factory):
    """Close executor mid-loop, reopen, loop_state intact."""
    h = harness_factory(
        "p2-mobile-first.yaml", loop_data={"breakpoints": ["a", "b", "c"]}
    )
    _walk_to_loop(h)

    _do_one_breakpoint(h)
    h.submit_goto("2.0 Breakpoint loop")

    # Mid iteration 2
    h.submit({"layout": "mid_loop"})
    assert h.step == "2.2 Test responsive behavior"

    h.new_executor()

    assert h.step == "2.2 Test responsive behavior"
    loop_info = h.state.loop_state["2.0 Breakpoint loop"]
    assert loop_info["i"] == 1
    assert loop_info["n"] == 3


def test_cross_executor_stop_resume(harness_factory):
    """Stop, close executor, reopen, resume."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.submit({})
    assert h.step == "2.1 Implement responsive layout"

    h.stop()
    assert h.status == "stopped"

    h.new_executor()
    assert h.step == "2.1 Implement responsive layout"
    assert h.status == "stopped"

    r = h.resume()
    assert r
    assert h.status == "running"


# ===============================================================
# Generic / cross-cutting tests
# ===============================================================

def test_checkpoint_save_and_load(harness_factory):
    """Save checkpoint, continue, load checkpoint, state matches."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.submit({"breakpoints": "defined"})

    h.save_checkpoint("at_loop_entry")

    h.submit({})
    h.submit({})
    h.submit_goto("2.0 Breakpoint loop")
    assert h.step == "3.1 Cross-browser testing"

    restored = h.load_checkpoint("at_loop_entry")
    assert restored is not None
    assert restored.current_step == "2.1 Implement responsive layout"
    assert "1.1 Define breakpoints and layouts" in restored.data


def test_retry_stays_at_current(harness_factory):
    """Retry keeps the workflow at the current step."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    assert h.step == "1.1 Define breakpoints and layouts"

    r = h.retry()
    assert r
    assert h.step == "1.1 Define breakpoints and layouts"
    assert h.status == "running"

    history = h.get_history(5)
    actions = [e["action"] for e in history]
    assert "retry" in actions


def test_goto_nonexistent_step(harness_factory):
    """Goto to a nonexistent step returns failure."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()

    r = h.goto("99.99 Does not exist")
    assert not r
    assert "not found" in r.message.lower()


def test_back_at_start_fails(harness_factory):
    """Back at the first step with no prior history fails."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()

    r = h.back()
    assert not r
    assert "cannot go back" in r.message.lower()


def test_submit_on_stopped_fails(harness_factory):
    """Submit while stopped returns failure."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.stop()

    r = h.submit({"data": "should fail"})
    assert not r
    assert "stopped" in r.message.lower()


def test_submit_on_done_fails(harness_factory):
    """Submit while done returns failure."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.goto("3.1 Cross-browser testing")
    h.submit_goto("Done")
    assert h.status == "done"

    r = h.submit({"data": "should fail"})
    assert not r


def test_multiple_resets(harness_factory):
    """Multiple reset + start cycles work cleanly."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})

    for _ in range(3):
        h.start()
        h.submit({})
        h.reset()
        assert h.state is None

    h.start()
    assert h.step == "1.1 Define breakpoints and layouts"


def test_reset_clears_history(harness_factory):
    """After reset, history is empty."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.submit({})

    history_before = h.get_history(50)
    assert len(history_before) > 0

    h.reset()
    history_after = h.get_history(50)
    assert len(history_after) == 0


def test_cross_executor_at_done(harness_factory):
    """After completion, new executor still reports done."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.goto("3.1 Cross-browser testing")
    h.submit_goto("Done")
    assert h.status == "done"

    h.new_executor()

    assert h.step == "Done"
    assert h.status == "done"
    r = h.submit({})
    assert not r


def test_submit_with_invalid_goto_target(harness_factory):
    """Submit with _goto pointing to nonexistent step fails."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    assert h.status == "running"

    r = h.submit({"_goto": "99.99 Nonexistent"})
    assert not r
    assert "not found" in r.message.lower()


def test_history_records_transition_steps(harness_factory):
    """History records transition action for each auto-advance."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["m"]})
    h.start()
    h.submit({})
    h.submit({})

    history = h.get_history(20)
    transition_entries = [e for e in history if e["action"] == "transition"]
    assert len(transition_entries) >= 1


def test_node_instructions_in_status(harness_factory):
    """Node instructions are accessible via get_status() for Claude to read."""
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    h.start()
    h.submit({"breakpoints": "mobile, tablet, desktop"})

    h.register_node(
        "2.1 Implement responsive layout",
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
    h = harness_factory("p2-mobile-first.yaml", loop_data={"breakpoints": ["mobile"]})
    h.start()

    h.register_node(
        "1.1 Define breakpoints and layouts",
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
